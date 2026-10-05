from __future__ import annotations

import io
import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from minio.error import S3Error
from PIL import Image
from sqlalchemy import text
from tests.conftest import authenticate_test_client
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _source,
)
from tests.integration.test_publication import _freeze_publication_clock

from analysis.editorial_schemas import EditorialRunInput
from analysis.editorial_services import EditorialService
from content.editorial_rendered import (
    prepare_editorial_rendered,
    save_editorial_rendered_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from evidence.schemas import (
    AccessBasis,
    AccessPolicyStatus,
    DataClass,
    RetentionPolicyInput,
    SourceAccessPolicyInput,
)
from evidence.services import RetentionPolicyService, SourceAccessPolicyService
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
    JobAcceptedMessage,
    JobStatus,
)
from jobs.services import JobService, ResourceBudgetService
from main import create_app
from publication.media_mirror_execution import PublicationMediaExecutor
from publication.media_mirror_reading import PublicationMediaReadingService
from publication.media_mirror_schemas import MediaMirrorInput
from publication.media_mirror_services import PublicationMediaService
from publication.reading import PublicationReadingService
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService
from sources.contracts import SourceCapability
from sources.editorial_schemas import EditorialMaterial as SourceMaterial
from sources.editorial_schemas import EditorialSourceMedia

pytestmark = pytest.mark.skipif(
    not os.getenv("HOTKEY_TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)
BODY = (
    "<h2>公开发布</h2><p>OpenAI 公布新模型 API。</p>"
    '<img src="https://images.example/a.png" alt="模型图">'
)


class MemoryStorage:
    def __init__(self) -> None:
        self.objects = {}
        self.writes = []
        self.reads = []
        self.before_read = None

    def check_bucket(self) -> None:
        pass

    def put(self, name, body, mime_type):
        self.writes.append(name)
        self.objects[name] = body

    def get(self, name, *, max_bytes):
        self.reads.append(name)
        if self.before_read:
            callback, self.before_read = self.before_read, None
            callback()
        return self.objects[name]


def png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (900, 300), "red").save(output, format="PNG")
    return output.getvalue()


def message_for(sessions, job_id, at):
    with sessions() as session:
        row = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {**row.payload, "message_id": row.id, "event_type": row.event_type, "schema_version": 2}
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: at).acquire(
            job_id=job_id, worker_id="controlled-media"
        )
    return message, lease


@pytest.fixture
def prepared(request, monkeypatch):
    _freeze_publication_clock(monkeypatch, request.module)
    metadata_only = getattr(request, "param", None) == "metadata"
    video = getattr(request, "param", None) == "video"
    browser = getattr(request, "param", None) == "browser"
    rendered_body = (
        BODY
        if not video
        else (
            "<h2>公开视频</h2><p>OpenAI 公布新模型 API。</p>"
            '<video src="https://images.example/owned.mp4"></video>'
        )
    )
    if browser:
        rendered_body += '<video src="https://images.example/owned.mp4"></video>'
    private = Settings(
        _env_file=Path(__file__).resolve().parents[3] / ".env",
        environment="test",
        database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
        ai_enabled=False,
        media_mirror_allow_external_requests=False,
    )
    # This fixture runs on the host; the shared Compose endpoint uses its
    # container-only host alias. Keep the configured local port and credentials.
    if private.minio_endpoint and private.minio_endpoint.startswith("host.docker.internal:"):
        private.minio_endpoint = private.minio_endpoint.replace(
            "host.docker.internal:", "127.0.0.1:", 1
        )
    with TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
                log_level="WARNING",
                media_mirror_enabled=True,
                ai_enabled=False,
                minio_endpoint=private.minio_endpoint,
                minio_access_key=private.minio_access_key,
                minio_secret_key=private.minio_secret_key,
                minio_bucket=private.minio_bucket,
                minio_secure=private.minio_secure,
            )
        )
    ) as client:
        client.app.state.settings.public_publication_owner_id = authenticate_test_client(client)
        owner, _, posts = _seed_posts(
            client,
            [("OpenAI new model", "只含文字和官方附件" if metadata_only else rendered_body)],
            now=NOW,
            dated=True,
        )
        _source(client, owner)
        version = posts[0].latest_observation.content_version
        assert version
        sessions = client.app.state.session_factory
        with sessions() as session:
            editorial = EditorialService(session, clock=lambda: NOW).request_run(
                owner_id=owner,
                content_id=posts[0].id,
                source_key="x",
                command=EditorialRunInput(operation_id=uuid4(), content_version_id=version.id),
            )
        message, lease = message_for(sessions, editorial.job_id, NOW)
        _budget(client, owner)
        _execute(client, owner, message, lease, ControlledClient())
        with sessions.begin() as session:
            if metadata_only:
                session.execute(
                    text(
                        "UPDATE source_access_policies SET field_purposes=field_purposes || "
                        '\'{"media":"受控官方附件"}\'::jsonb '
                        "WHERE source_key='x' AND owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            save_editorial_rendered_in_transaction(
                session,
                owner_id=owner,
                content_id=posts[0].id,
                content_version_id=version.id,
                representation=prepare_editorial_rendered(
                    SourceMaterial(
                        external_id="search-0",
                        identity_key="controlled-media-material",
                        url="https://example.com/article",
                        title="OpenAI new model",
                        body_text="只含文字和官方附件"
                        if metadata_only
                        else "OpenAI 公布新模型 API。",
                        body_html=None if metadata_only else rendered_body,
                        content_format="text" if metadata_only else "html",
                        body_status="ok",
                        media=("https://images.example/a.png", "https://images.example/unknown")
                        if metadata_only
                        else (),
                        media_details=(
                            EditorialSourceMedia(
                                url="https://images.example/a.png", kind="image", alt="官方附件"
                            ),
                        )
                        if metadata_only
                        else (),
                    )
                ),
                now=NOW,
            )
            policy = SourceAccessPolicyService(session, clock=lambda: NOW).save_in_transaction(
                owner_id=owner,
                command=SourceAccessPolicyInput(
                    source_key="x",
                    capability=SourceCapability.PAGE_CONTENT,
                    status=AccessPolicyStatus.APPROVED,
                    enabled=True,
                    access_basis=AccessBasis.WRITTEN_PERMISSION,
                    terms_reference="controlled media fixture only",
                    processing_purpose="licensed fixed media reading",
                    component_name="publication.media_mirror",
                    component_version="1",
                    component_license="MIT",
                    field_purposes={"url": "licensed media reference"},
                    reviewed_at=NOW,
                ),
            )
            RetentionPolicyService(session, clock=lambda: NOW).save_in_transaction(
                owner_id=owner,
                command=RetentionPolicyInput(
                    source_policy_id=policy.id, data_class=DataClass.MEDIA, requested_days=1
                ),
            )
            PublicationService(session).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key="x",
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=0,
                    participation_mode="editorial",
                    body_format="html",
                    site_fulltext=True,
                    syndicate_fulltext=getattr(request, "param", None) == "syndicated",
                    release_delay_seconds=0,
                    license_name="受控媒体许可",
                    reason="固定测试",
                ),
                now=NOW,
            )
            PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=posts[0].id, now=NOW
            )
            budgets = ResourceBudgetService(session, clock=lambda: NOW)
            budgets.save_component_policy_in_transaction(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key="publication.media_mirror",
                    component_version="1",
                    cost_class=CostClass.ZERO_PRICE,
                    enabled_for_core=True,
                    terms_reference="controlled fixture, no real media source",
                    reviewed_at=NOW,
                ),
            )
            budgets.save_budget_policy_in_transaction(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key="media-network",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    limit_units=100,
                    window_seconds=3600,
                    window_anchor_at=NOW,
                    enabled=True,
                ),
            )
        at = NOW + timedelta(seconds=1)
        command = MediaMirrorInput(
            operation_id=uuid4(), content_version_id=version.id, policy_revision=1
        )
        if getattr(request, "param", True) is False:
            yield (
                client,
                owner,
                SimpleNamespace(
                    content_id=posts[0].id, content_version_id=version.id, policy_revision=1
                ),
                None,
                None,
                at,
            )
            return
        with sessions() as session:
            run = PublicationMediaService(session, enabled=True).request(
                owner_id=owner, content_id=posts[0].id, command=command, now=at
            )
            assert (
                PublicationMediaService(session, enabled=True)
                .request(owner_id=owner, content_id=posts[0].id, command=command, now=at)
                .replayed
            )
        message, lease = message_for(sessions, run.job_id, at)
        yield client, owner, run, message, lease, at


def test_actual_fixed_media_job_budget_evidence_bytes_and_revocation(prepared):
    client, owner, run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    storage, calls = MemoryStorage(), []
    executor = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=png())
        ),
    )
    result = executor.execute(message, lease)
    assert result and result.status == JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    assert len(calls) == 1 and len(storage.writes) == 12
    with sessions.begin() as session:
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM evidence_resources "
                    "WHERE resource_type='publication_media'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM provenance_manifests "
                    "WHERE method_key='publication.media-mirror'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM resource_usage_attempts "
                    "WHERE operation_id=:op AND outcome='succeeded'"
                ),
                {"op": message.operation_id},
            ).scalar_one()
            == 14
        )
        assert (
            session.execute(
                text(
                    "SELECT sum(w.used_units) FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.budget_key='media-network'"
                )
            ).scalar_one()
            == 14
        )
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=at
        )
        assert detail and detail.body and detail.body.media[0].state == "available"
        assert detail.category is not None
        assert "<img" in detail.body.original_html and "srcset=" in detail.body.original_html
        assert "https://images.example" not in detail.body.original_html
        file_id = session.execute(text("SELECT id FROM publication_media_files")).scalar_one()
    with sessions() as session:
        excluded = "opinion" if detail.category != "opinion" else "tip"
        reads = len(storage.reads)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            PublicationMediaReadingService(session, storage, public_categories=(excluded,)).read(
                owner_id=owner, file_id=file_id, mode="image-720", redistribute=False, now=at
            )
        assert len(storage.reads) == reads  # Exclusion is checked before reading cached objects.
        reading = PublicationMediaReadingService(session, storage)
        image = reading.read(
            owner_id=owner, file_id=file_id, mode="image-720", redistribute=False, now=at
        )
        assert Image.open(io.BytesIO(image.body)).size == (720, 240)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            reading.read(owner_id=owner, file_id=file_id, mode="image-720", now=at)

    def revoke():
        with sessions.begin() as session:
            PublicationService(session).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key="x",
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=1,
                    participation_mode="editorial",
                    site_fulltext=False,
                    license_name="媒体许可撤回",
                    reason="撤回",
                ),
                now=at,
            )

    storage.before_read = revoke
    with sessions() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        PublicationMediaReadingService(session, storage).read(
            owner_id=owner, file_id=file_id, mode="full", redistribute=False, now=at
        )
    assert len(calls) == 1


def test_cancel_inside_final_media_http_records_cancellation_without_object_writes(prepared):
    client, owner, run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    storage, calls, cancelled = MemoryStorage(), [], [False]

    def cancel(request):
        calls.append(request)
        with sessions() as session:
            JobService(session, clock=lambda: at).request_cancel(owner_id=owner, job_id=run.job_id)
        cancelled[0] = True
        return httpx.Response(200, content=png())

    completion = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(cancel),
    ).execute(message, lease, cancelled=lambda: cancelled[0])
    assert completion is None and len(calls) == 1 and not storage.writes
    with sessions.begin() as session:
        assert (
            session.execute(text("SELECT status FROM publication_media_runs")).scalar_one()
            == "cancelled"
        )
        assert (
            session.execute(text("SELECT status FROM publication_media_files")).scalar_one()
            == "cancelled"
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM resource_usage_attempts WHERE outcome='started'")
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("prepared", ["metadata"], indirect=True)
def test_official_metadata_only_media_uses_fixed_source_format_and_rechecks_media_field_grant(
    prepared,
):
    client, owner, run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    storage, calls = MemoryStorage(), []
    with sessions.begin() as session:
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=at
        )
        assert detail.body.original_format == "text"  # policy says html; source fact says text.
        assert [item.kind for item in detail.body.media] == ["image", "unknown"]
        assert (
            session.execute(text("SELECT count(*) FROM publication_media_files")).scalar_one() == 1
        )
    result = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=png())
        ),
    ).execute(message, lease)
    assert result.status == JobStatus.SUCCEEDED and len(calls) == 1
    with sessions.begin() as session:
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=at
        )
        assert detail.body.media[0].state == "available" and "<img" in detail.body.original_html
        assert detail.body.media[1].state == "original_link"
        file_id = session.execute(text("SELECT id FROM publication_media_files")).scalar_one()
        session.execute(
            text(
                "UPDATE source_access_policies SET field_purposes=field_purposes-'media' "
                "WHERE source_key='x' AND owner_id=:owner"
            ),
            {"owner": owner},
        )
    with sessions() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        PublicationMediaReadingService(session, storage).read(
            owner_id=owner, file_id=file_id, mode="full", redistribute=False, now=at
        )
    assert len(calls) == 1


@pytest.mark.parametrize("prepared", ["video"], indirect=True)
def test_real_owned_video_container_is_preserved_and_guarded_as_single_object(prepared):
    client, owner, run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    storage, calls = MemoryStorage(), []
    body = (
        Path(__file__).resolve().parents[1] / "fixtures/publication/owned-video.mp4"
    ).read_bytes()
    result = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=body)
        ),
    ).execute(message, lease)
    assert result.status == JobStatus.SUCCEEDED and len(calls) == 1 and len(storage.writes) == 1
    with sessions.begin() as session:
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=at
        )
        assert detail.body.media[0].kind == "video" and detail.body.media[0].state == "available"
        assert "<video" in detail.body.original_html and "controls" in detail.body.original_html
        file_id = session.execute(text("SELECT id FROM publication_media_files")).scalar_one()
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM resource_usage_attempts "
                    "WHERE operation_id=:operation AND outcome='succeeded'"
                ),
                {"operation": message.operation_id},
            ).scalar_one()
            == 3
        )
    with sessions() as session:
        actual = PublicationMediaReadingService(session, storage).read(
            owner_id=owner, file_id=file_id, mode="original", redistribute=False, now=at
        )
        assert actual.body == body and actual.mime_type == "video/mp4"


@pytest.mark.parametrize("prepared", ["syndicated"], indirect=True)
def test_third_party_media_url_requires_explicit_current_syndication_grant(prepared):
    client, owner, run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    storage = MemoryStorage()
    PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=png())),
    ).execute(message, lease)
    with sessions.begin() as session:
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=at, redistribute=True
        )
        assert detail.syndicate_fulltext and not detail.body.media[0].reading_url.endswith("/site")
        file_id = session.execute(text("SELECT id FROM publication_media_files")).scalar_one()
    with sessions() as session:
        result = PublicationMediaReadingService(session, storage).read(
            owner_id=owner, file_id=file_id, mode="image-720", now=at
        )
        assert Image.open(io.BytesIO(result.body)).size == (720, 240)


def test_unknown_media_response_never_downloads_again_on_replay(prepared):
    client, _owner, _run, message, lease, at = prepared
    sessions = client.app.state.session_factory
    calls = []

    def response(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled unknown")

    executor = PublicationMediaExecutor(
        sessions,
        MemoryStorage(),
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(response),
    )
    for _ in range(2):
        with pytest.raises(JobExecutionFailure):
            executor.execute(message, lease)
    assert len(calls) == 1
    with sessions.begin() as session:
        assert (
            session.execute(text("SELECT status FROM publication_media_runs")).scalar_one()
            == "unknown"
        )
        assert (
            session.execute(text("SELECT status FROM publication_media_files")).scalar_one()
            == "unknown"
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM resource_usage_attempts WHERE operation_id=:op"),
                {"op": message.operation_id},
            ).scalar_one()
            == 1
        )
        assert session.execute(
            text(
                "SELECT sum(w.used_units),sum(w.reserved_units) FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.budget_key='media-network'"
            )
        ).one() == (1, 0)


def test_interrupted_partial_object_write_is_tracked_and_never_refetched(prepared):
    client, _owner, _run, message, lease, at = prepared
    sessions = client.app.state.session_factory

    class InterruptedStorage(MemoryStorage):
        def put(self, name, body, mime_type):
            super().put(name, body, mime_type)
            raise SystemExit("controlled process exit after object write")

    calls, storage = [], InterruptedStorage()
    executor = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=png())
        ),
    )
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    with pytest.raises(JobExecutionFailure):
        executor.execute(message, lease)
    assert len(calls) == 1 and len(storage.writes) == 1
    with sessions.begin() as session:
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM evidence_resources "
                    "WHERE resource_type='publication_media'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(text("SELECT status FROM publication_media_files")).scalar_one()
            == "unknown"
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM resource_usage_attempts WHERE outcome='started'")
            ).scalar_one()
            == 0
        )


def test_completed_object_write_before_receipt_is_recovered_without_new_http(prepared):
    client, _owner, _run, message, lease, at = prepared
    sessions = client.app.state.session_factory

    class InterruptedStorage(MemoryStorage):
        def put(self, name, body, mime_type):
            super().put(name, body, mime_type)
            if len(self.writes) == 12:
                raise SystemExit("controlled crash after final owned object")

    storage, calls = InterruptedStorage(), []
    executor = PublicationMediaExecutor(
        sessions,
        storage,
        allow_external_requests=True,
        clock=lambda: at,
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, content=png())
        ),
    )
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    result = executor.execute(message, lease)
    assert result.status == JobStatus.SUCCEEDED
    assert len(calls) == 1 and len(storage.writes) == 12 and len(storage.reads) == 12
    with sessions.begin() as session:
        assert (
            session.execute(text("SELECT status FROM publication_media_runs")).scalar_one()
            == "complete"
        )
        assert (
            session.execute(text("SELECT status FROM publication_media_files")).scalar_one()
            == "complete"
        )
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM provenance_manifests "
                    "WHERE method_key='publication.media-mirror'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM resource_usage_attempts WHERE outcome='started'")
            ).scalar_one()
            == 0
        )


def test_real_existing_minio_owned_objects_read_and_lifecycle_cleanup(prepared, monkeypatch):
    from evidence.adapters.minio import MinioObjectCleanup
    from evidence.schemas import CleanupTargetKind, DeletionReason
    from evidence.services import CleanupProcessor, LifecycleService

    client, owner, _run, message, lease, at = prepared
    import publication.media_mirror_reading as media_reading

    class FixtureReadDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz is not None else at.replace(tzinfo=None)

    # The fixture deliberately advances past its 180s release gate. HTTP reads
    # must observe that same clock, including evidence's future-material guard.
    monkeypatch.setattr(media_reading, "datetime", FixtureReadDateTime)
    sessions = client.app.state.session_factory
    storage = client.app.state.media_storage
    if storage is None:
        pytest.skip("existing configured MinIO is required")
    names = []
    calls = []
    try:
        result = PublicationMediaExecutor(
            sessions,
            storage,
            allow_external_requests=True,
            clock=lambda: at,
            resolver=lambda host: ("8.8.8.8",),
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200, content=png())
            ),
        ).execute(message, lease)
        assert result.status == JobStatus.SUCCEEDED and len(calls) == 1
        with sessions.begin() as session:
            file = session.execute(text("SELECT id,renditions FROM publication_media_files")).one()
            names = [item["object_name"] for item in file.renditions.values()]
        assert len(names) == 12 and all(
            name.startswith(f"media/{owner}/{file.id}/") for name in names
        )
        reading = client.get(f"/api/publication/media/{file.id}/image-720/site")
        assert reading.status_code == 200 and reading.headers["cache-control"] == "no-store"
        assert Image.open(io.BytesIO(reading.content)).size == (720, 240)
        assert client.get(f"/api/publication/media/{file.id}/image-720").status_code == 404
        with sessions() as session:
            LifecycleService(session, clock=lambda: at).request_deletion(
                owner_id=owner,
                operation_id=uuid4(),
                resource_type="publication_media",
                resource_id=file.id,
                reason=DeletionReason.USER_REQUEST,
            )
        assert client.get(f"/api/publication/media/{file.id}/image-720/site").status_code == 404
        result = CleanupProcessor(
            sessions,
            handlers={
                CleanupTargetKind.MINIO_OBJECT: MinioObjectCleanup(storage.client, storage.bucket)
            },
            clock=lambda: at,
        ).process_due(limit=20)
        assert result.succeeded == 12 and result.failed == 0
        for name in names:
            with pytest.raises(S3Error):
                storage.get(name, max_bytes=100000)
    finally:
        with sessions.begin() as session:
            persisted = session.execute(
                text("SELECT renditions FROM publication_media_files WHERE owner_id=:owner"),
                {"owner": owner},
            ).scalars()
            names = list(
                {
                    *names,
                    *(
                        item["object_name"]
                        for descriptors in persisted
                        for item in descriptors.values()
                    ),
                }
            )
        # Only exact names emitted by this controlled Job; never a bucket or prefix purge.
        for name in names:
            if name.startswith(f"media/{owner}/"):
                storage.client.remove_object(storage.bucket, name)


@pytest.mark.parametrize("prepared", [False], indirect=True)
def test_automatic_media_admission_is_atomic_disabled_or_unknown_never_requeues(prepared):
    from publication.schedule import enqueue_due_media_in_transaction

    client, owner, target, _, _, at = prepared
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        baseline = session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one()
        assert (
            enqueue_due_media_in_transaction(
                session, owner_id=owner, now=at, enabled=False, allow_external_requests=True
            )
            == 0
        )
        assert (
            enqueue_due_media_in_transaction(
                session, owner_id=owner, now=at, enabled=True, allow_external_requests=False
            )
            == 0
        )
        assert (
            enqueue_due_media_in_transaction(
                session, owner_id=owner, now=at, enabled=True, allow_external_requests=True
            )
            == 1
        )
        assert (
            enqueue_due_media_in_transaction(
                session, owner_id=owner, now=at, enabled=True, allow_external_requests=True
            )
            == 0
        )
        session.flush()
        assert (
            session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one()
            == baseline + 1
        )
        assert (
            session.execute(text("SELECT count(*) FROM publication_media_runs")).scalar_one() == 1
        )
        job_id = session.execute(text("SELECT job_id FROM publication_media_runs")).scalar_one()
        assert (
            session.execute(text("SELECT content_id FROM publication_media_runs")).scalar_one()
            == target.content_id
        )
    message, lease = message_for(sessions, job_id, at)
    calls = []

    def unknown(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled unknown")

    with pytest.raises(JobExecutionFailure):
        PublicationMediaExecutor(
            sessions,
            MemoryStorage(),
            allow_external_requests=True,
            clock=lambda: at,
            resolver=lambda host: ("8.8.8.8",),
            transport=httpx.MockTransport(unknown),
        ).execute(message, lease)
    with sessions.begin() as session:
        assert (
            enqueue_due_media_in_transaction(
                session,
                owner_id=owner,
                now=at + timedelta(minutes=10),
                enabled=True,
                allow_external_requests=True,
            )
            == 0
        )
        assert (
            session.execute(text("SELECT count(*) FROM publication_media_runs")).scalar_one() == 1
        )
    assert len(calls) == 1
