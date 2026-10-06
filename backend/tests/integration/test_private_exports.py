"""Real isolated PostgreSQL, actual local files and private MinIO prefix; no provider calls."""

import csv
import io
import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from minio.error import S3Error
from sqlalchemy import text
from tests.conftest import authenticate_test_client, authenticated_headers
from tests.integration.test_content_records import _command
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import editorial_client as _editorial_client

from content.services import ContentObservationCleanup, ContentService
from core.config import Settings
from core.errors import ApplicationError
from evidence.adapters.media_storage import create_media_storage
from evidence.adapters.minio import MinioObjectCleanup
from evidence.schemas import CleanupTargetKind, DeletionReason
from evidence.services import CleanupProcessor, LifecycleService
from jobs.execution import (
    JobExecutionFailure,
    JobExecutionService,
    MessageReference,
    StaleExecutionLeaseError,
)
from jobs.schemas import JobAcceptedMessage
from jobs.services import JobService
from reports.export_execution import PrivateExportExecutor
from reports.export_rendering import ExportArtifact
from reports.export_schemas import EXPORT_MAX_BYTES, ContentExportInput, ReportExportInput
from reports.export_services import PrivateExportService
from reports.services import ReportService

PURPOSE = "hotkey:personal-file-export:v1"


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


@pytest.fixture
def storage():
    test_minio = {
        name: os.getenv(f"HOTKEY_TEST_MINIO_{name}")
        for name in ("ENDPOINT", "ACCESS_KEY", "SECRET_KEY", "BUCKET", "SECURE")
    }
    if not any(value is not None for value in test_minio.values()):
        pytest.skip(
            "HOTKEY_TEST_MINIO_* is required for real MinIO private export tests; "
            "the repository .env is never used"
        )
    assert all(test_minio.values()), "test MinIO namespace must be complete, without .env mixing"
    assert test_minio["SECURE"] in {"true", "false"}, "test MinIO SECURE must be explicit"
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    assert database_url is not None, "an isolated PostgreSQL test database is required"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        minio_endpoint=test_minio["ENDPOINT"],
        minio_access_key=test_minio["ACCESS_KEY"],
        minio_secret_key=test_minio["SECRET_KEY"],
        minio_bucket=test_minio["BUCKET"],
        minio_secure=test_minio["SECURE"] == "true",
    )
    delegate = create_media_storage(settings)
    assert delegate is not None, "real local MinIO configuration is required"
    delegate.check_bucket()
    names: set[str] = set()

    class TrackingStorage:
        def check_bucket(self):
            delegate.check_bucket()

        def put(self, name, body, mime):
            assert name.startswith("media/exports/")
            names.add(name)
            delegate.put(name, body, mime)

        def get(self, name, *, max_bytes):
            return delegate.get(name, max_bytes=max_bytes)

    try:
        yield TrackingStorage(), delegate, names
    finally:
        for name in names:
            delegate.client.remove_object(delegate.bucket, name)
        delegate.close()


def seed(client, *, allowed=True):
    owner, topic, posts = _seed_posts(
        client, [("中文标题", "中文正文与原文引用。"), ("=SUM(1,2)", "另一项未分析材料。")]
    )
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    with sessions.begin() as session:
        if allowed:
            fields = session.scalar(
                text("SELECT field_purposes FROM source_access_policies WHERE owner_id=:owner"),
                {"owner": owner},
            )
            session.execute(
                text(
                    "UPDATE source_access_policies SET processing_purpose=:purpose, "
                    "field_purposes=CAST(:fields AS jsonb) WHERE owner_id=:owner"
                ),
                {
                    "owner": owner,
                    "purpose": PURPOSE,
                    "fields": json.dumps({key: PURPOSE for key in fields}),
                },
            )
        report = ReportService(session, clock=lambda: now).generate_daily_in_transaction(
            owner_id=owner,
            topic_id=topic,
            window_start=now - timedelta(days=1),
            window_end=now,
            cutoff_at=now,
        )
    versions = tuple(post.latest_observation.content_version.id for post in posts)
    return owner, report, versions, now


def execution(sessions, view, now):
    with sessions() as session:
        row = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:id"),
            {"id": view.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {**row.payload, "schema_version": 2, "message_id": row.id, "event_type": row.event_type}
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=view.job_id, worker_id="private-export-integration"
        )
    return message, lease


@pytest.mark.parametrize(
    "kind,format",
    [("report", "markdown"), ("report", "pdf"), ("content", "csv"), ("content", "json")],
)
def test_actual_artifacts_or_pdf_unavailable_original_jobs_hashes_permissions_and_minio(
    editorial_client, storage, kind, format, tmp_path, record_property
):
    store, _delegate, names = storage
    editorial_client.app.state.media_storage = store
    owner, report, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    operation = uuid4()
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        if kind == "report":
            command = ReportExportInput(
                operation_id=operation, report_version=report.version, format=format
            )
            view = service.accept_report(owner_id=owner, report_id=report.id, command=command)
            assert (
                service.accept_report(owner_id=owner, report_id=report.id, command=command) == view
            )
        else:
            command = ContentExportInput(
                operation_id=operation, content_version_ids=versions, format=format
            )
            view = service.accept_content(owner_id=owner, command=command)
            assert service.accept_content(owner_id=owner, command=command) == view
    message, lease = execution(sessions, view, now)
    executor = PrivateExportExecutor(sessions, store, clock=lambda: now)
    try:
        completion = executor.execute(message, lease)
    except JobExecutionFailure as error:
        if format != "pdf" or error.error_code != "export_renderer_unavailable":
            raise
        record_property("pdf_result", "renderer_unavailable_no_artifact")
        assert not names and not list(tmp_path.iterdir())
        with sessions() as session:
            service = PrivateExportService(session, store, clock=lambda: now)
            failed = service.get(owner_id=owner, export_id=view.id, kind=kind)
            assert (
                failed.status == "failed" and failed.failure_code == "export_renderer_unavailable"
            )
            assert failed.artifact_sha256 is None and failed.artifact_size is None
            with pytest.raises(ApplicationError, match="export_not_ready"):
                service.download(owner_id=owner, export_id=view.id, kind=kind)
        return
    if format == "pdf":
        record_property("pdf_result", "actual_local_locked_renderer_file")
    assert completion is not None
    assert executor.execute(message, lease) == completion
    assert len(names) == 1
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: now).complete(
            lease,
            message=MessageReference(message.message_id, "hotkey.jobs", 0, 0),
            completion=completion,
        )
        service = PrivateExportService(session, store, clock=lambda: now)
        done = service.get(owner_id=owner, export_id=view.id, kind=kind)
        assert done.status == "succeeded" and done.content_count == 2
        download = service.download(owner_id=owner, export_id=view.id, kind=kind)
        assert done.artifact_sha256 == download.sha256 and done.artifact_size == len(download.body)
        assert 1 <= len(download.body) <= EXPORT_MAX_BYTES
        path = tmp_path / download.filename
        path.write_bytes(download.body)
        if format == "markdown":
            assert "中文标题" in path.read_text() and str(report.id) in path.read_text()
        elif format == "json":
            decoded = json.loads(path.read_text())
            assert decoded["rows"][0]["published_at"] is None
            assert set(decoded["manifest"]["content_version_ids"]) == {
                str(item) for item in versions
            }
        elif format == "csv":
            rows = list(csv.DictReader(io.StringIO(download.body.decode("utf-8-sig"))))
            assert len(rows) == 2 and any(row["title"].startswith("'=SUM") for row in rows)
        else:
            assert download.body.startswith(b"%PDF-") and b"/ToUnicode" in download.body
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.download(owner_id=uuid4(), export_id=view.id, kind=kind)
    response = editorial_client.get(
        f"/api/{'report' if kind == 'report' else 'content'}-exports/{view.id}/download"
    )
    assert response.status_code == 200 and response.content == download.body
    assert response.headers["cache-control"] == "private, no-store"
    with sessions.begin() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM jobs WHERE kind=:kind"), {"kind": f"{kind}.export"}
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM provenance_manifests WHERE job_id=:job"),
                {"job": view.job_id},
            )
            == 1
        )
        targets = session.execute(
            text(
                "SELECT cleanup_targets FROM evidence_resources "
                "WHERE owner_id=:owner AND resource_type='content_observation'"
            ),
            {"owner": owner},
        )
        assert all(
            any(item.get("reference") in names for item in row.cleanup_targets) for row in targets
        )
        session.execute(
            text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
            {"owner": owner},
        )
    assert editorial_client.get(f"/api/{kind}-exports/{view.id}/download").status_code in {403, 404}
    assert len(names) == 1


def test_purpose_not_read_and_pre_generation_withdrawal_no_artifact(editorial_client, storage):
    store, _, names = storage
    owner, report, versions, now = seed(editorial_client, allowed=False)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        with pytest.raises(ApplicationError, match="editorial_export_not_authorized"):
            service.accept_report(
                owner_id=owner,
                report_id=report.id,
                command=ReportExportInput(
                    operation_id=uuid4(), report_version=1, format="markdown"
                ),
            )
        with pytest.raises(ApplicationError, match="editorial_export_not_authorized"):
            service.accept_content(
                owner_id=owner,
                command=ContentExportInput(
                    operation_id=uuid4(), content_version_ids=versions, format="json"
                ),
            )
    assert not names
    with sessions.begin() as session:
        fields = session.scalar(
            text("SELECT field_purposes FROM source_access_policies WHERE owner_id=:owner"),
            {"owner": owner},
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET processing_purpose=:purpose, "
                "field_purposes=CAST(:fields AS jsonb) WHERE owner_id=:owner"
            ),
            {
                "owner": owner,
                "purpose": PURPOSE,
                "fields": json.dumps({key: PURPOSE for key in fields}),
            },
        )
    with sessions() as session:
        view = PrivateExportService(session, store, clock=lambda: now).accept_content(
            owner_id=owner,
            command=ContentExportInput(
                operation_id=uuid4(), content_version_ids=versions, format="json"
            ),
        )
    message, lease = execution(sessions, view, now)
    with sessions.begin() as session:
        session.execute(
            text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
            {"owner": owner},
        )
    with pytest.raises(JobExecutionFailure):
        PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    assert not names
    with sessions() as session:
        result = PrivateExportService(session, store).get(
            owner_id=owner, export_id=view.id, kind="content"
        )
        assert result.status == "blocked" and result.artifact_size is None


def test_missing_locked_pdf_renderer_fails_original_job_without_minio_artifact(
    editorial_client, storage, monkeypatch
):
    import reports.export_rendering as rendering

    store, _, names = storage
    owner, report, _, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    monkeypatch.setattr(rendering, "_FONT_PATHS", ())
    with sessions() as session:
        view = PrivateExportService(session, store, clock=lambda: now).accept_report(
            owner_id=owner,
            report_id=report.id,
            command=ReportExportInput(
                operation_id=uuid4(), report_version=report.version, format="pdf"
            ),
        )
    message, lease = execution(sessions, view, now)
    with pytest.raises(JobExecutionFailure) as unavailable:
        PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    assert unavailable.value.error_code == "export_renderer_unavailable" and not names
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        failed = service.get(owner_id=owner, export_id=view.id, kind="report")
        assert failed.status == "failed" and failed.failure_code == "export_renderer_unavailable"
        assert failed.artifact_sha256 is None and failed.artifact_size is None
        with pytest.raises(ApplicationError, match="export_not_ready"):
            service.download(owner_id=owner, export_id=view.id, kind="report")


def test_failure_bounds_original_unchanged_stale_lease_and_csrf(editorial_client, storage):
    store, _, names = storage
    editorial_client.app.state.media_storage = store
    owner, report, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    command = ContentExportInput(operation_id=uuid4(), content_version_ids=versions, format="json")
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        view = service.accept_content(owner_id=owner, command=command)
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.accept_content(
                owner_id=owner, command=command.model_copy(update={"format": "csv"})
            )
    message, lease = execution(sessions, view, now)

    def renderer(*args, **kwargs):
        return ExportArtifact(b"x" * (EXPORT_MAX_BYTES + 1), "application/json", "json")

    with pytest.raises(JobExecutionFailure, match="export_size_exceeded"):
        PrivateExportExecutor(sessions, store, clock=lambda: now, renderer=renderer).execute(
            message, lease
        )
    assert not names
    with sessions() as session:
        assert (
            PrivateExportService(session, store)
            .get(owner_id=owner, export_id=view.id, kind="content")
            .status
            == "failed"
        )
        assert (
            session.scalar(
                text("SELECT body_markdown FROM reports WHERE id=:id"), {"id": report.id}
            )
            == report.body_markdown
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM content_versions WHERE id IN (:a,:b)"),
                {"a": versions[0], "b": versions[1]},
            )
            == 2
        )
    with pytest.raises(StaleExecutionLeaseError):
        PrivateExportExecutor(sessions, store, clock=lambda: now).execute(
            message, replace(lease, epoch=lease.epoch + 1)
        )
    assert not names
    payload = command.model_copy(update={"operation_id": uuid4(), "format": "csv"}).model_dump(
        mode="json"
    )
    assert editorial_client.post("/api/content-exports", json=payload).status_code == 403
    assert (
        editorial_client.post(
            "/api/content-exports", json=payload, headers=authenticated_headers(editorial_client)
        ).status_code
        == 202
    )
    authenticate_test_client(editorial_client, owner_id=uuid4())
    assert editorial_client.get(f"/api/content-exports/{view.id}").status_code == 404
    editorial_client.cookies.clear()
    assert editorial_client.get(f"/api/content-exports/{view.id}").status_code == 401


def test_retention_deletion_removes_real_minio_artifact_and_reference(editorial_client, storage):
    store, delegate, names = storage
    owner, _, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        view = PrivateExportService(session, store, clock=lambda: now).accept_content(
            owner_id=owner,
            command=ContentExportInput(
                operation_id=uuid4(), content_version_ids=versions, format="json"
            ),
        )
    message, lease = execution(sessions, view, now)
    assert PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    name = next(iter(names))
    assert delegate.get(name, max_bytes=EXPORT_MAX_BYTES)
    with sessions() as session:
        observation = session.scalar(
            text(
                "SELECT resource_id FROM evidence_resources WHERE owner_id=:owner "
                "AND resource_type='content_observation' ORDER BY id LIMIT 1"
            ),
            {"owner": owner},
        )
        LifecycleService(session, clock=lambda: now).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=observation,
            reason=DeletionReason.SOURCE_DELETED,
        )
    processor = CleanupProcessor(
        sessions,
        clock=lambda: now,
        handlers={
            CleanupTargetKind.MINIO_OBJECT: MinioObjectCleanup(delegate.client, delegate.bucket),
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(sessions),
        },
    )
    result = processor.process_due(limit=100)
    assert result.failed == 0 and result.succeeded >= 2
    with pytest.raises(S3Error) as missing:
        delegate.get(name, max_bytes=EXPORT_MAX_BYTES)
    assert missing.value.code in {"NoSuchKey", "NoSuchObject"}
    with sessions() as session:
        result = PrivateExportService(session, store).get(
            owner_id=owner, export_id=view.id, kind="content"
        )
        assert result.status == "blocked" and result.artifact_sha256 is None


def test_unknown_put_same_object_replay_hash_and_download_expiry(editorial_client, storage):
    store, delegate, names = storage
    owner, _, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        command = ContentExportInput(
            operation_id=uuid4(), content_version_ids=versions, format="json"
        )
        view = service.accept_content(owner_id=owner, command=command)
        alias = command.model_copy(update={"operation_id": uuid4()})
        assert service.accept_content(owner_id=owner, command=alias).id == view.id
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.accept_content(
                owner_id=owner, command=alias.model_copy(update={"format": "csv"})
            )
    message, lease = execution(sessions, view, now)

    class UnknownPut:
        check_bucket = store.check_bucket
        get = store.get

        def put(self, name, body, mime):
            store.put(name, body, mime)
            raise OSError("controlled missing PUT receipt after private object write")

    with pytest.raises(JobExecutionFailure, match="export_artifact_failed"):
        PrivateExportExecutor(sessions, UnknownPut(), clock=lambda: now).execute(message, lease)
    assert len(names) == 1

    name = next(iter(names))
    assert delegate.get(name, max_bytes=EXPORT_MAX_BYTES)
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        assert service.get(owner_id=owner, export_id=view.id, kind="content").status == "failed"
        with pytest.raises(ApplicationError, match="export_not_ready"):
            service.download(owner_id=owner, export_id=view.id, kind="content")
    # Controlled recovery of the same still-live original lease uses one deterministic object key.
    assert PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    assert len(names) == 1
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        receipt = service.download(owner_id=owner, export_id=view.id, kind="content")
    delegate.put(name, b"tampered private artifact", "application/json")
    with sessions() as session, pytest.raises(ApplicationError, match="export_storage_unavailable"):
        PrivateExportService(session, store, clock=lambda: now).download(
            owner_id=owner, export_id=view.id, kind="content"
        )
    delegate.put(name, receipt.body, receipt.mime_type)
    current = [now]

    class ExpireDuringDownload:
        check_bucket = store.check_bucket
        put = store.put

        def get(self, name, *, max_bytes):
            body = store.get(name, max_bytes=max_bytes)
            current[0] = now + timedelta(days=31)
            return body

    with sessions() as session, pytest.raises(ApplicationError):
        PrivateExportService(session, ExpireDuringDownload(), clock=lambda: current[0]).download(
            owner_id=owner, export_id=view.id, kind="content"
        )
    assert len(names) == 1


@pytest.mark.parametrize("kind", ["content", "report"])
def test_frozen_observation_survives_later_equivalent_input_but_not_original_withdrawal(
    editorial_client, storage, kind
):
    store, _, _ = storage
    owner, report, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = PrivateExportService(session, store, clock=lambda: now)
        if kind == "content":
            view = service.accept_content(
                owner_id=owner,
                command=ContentExportInput(
                    operation_id=uuid4(), content_version_ids=versions, format="json"
                ),
            )
        else:
            view = service.accept_report(
                owner_id=owner,
                report_id=report.id,
                command=ReportExportInput(
                    operation_id=uuid4(), report_version=report.version, format="json"
                ),
            )
    message, lease = execution(sessions, view, now)
    completion = PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    assert completion is not None
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: now).complete(
            lease,
            message=MessageReference(message.message_id, "hotkey.jobs", 0, 0),
            completion=completion,
        )
        original = PrivateExportService(session, store, clock=lambda: now).download(
            owner_id=owner, export_id=view.id, kind=kind
        )
        frozen = json.loads(original.body)["manifest"]["content_inputs"]
        selection = next(item for item in frozen if item["version_id"] == str(versions[0]))
        context = session.execute(
            text(
                "SELECT ob.job_id, er.source_policy_id, er.retention_policy_id, "
                "(SELECT id FROM source_connections WHERE owner_id=:owner) AS connection_id "
                "FROM content_observations ob JOIN evidence_resources er "
                "ON er.owner_id=ob.owner_id AND er.resource_id=ob.id WHERE ob.id=:observation"
            ),
            {"owner": owner, "observation": selection["observation_id"]},
        ).one()
    with sessions() as session:
        updated = ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=context.connection_id,
                policy_id=context.source_policy_id,
                retention_id=context.retention_policy_id,
                job_id=context.job_id,
                operation_id=uuid4(),
                observed_at=datetime.now(UTC),
                external_id="search-0",
                extra_fields={
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "中文标题",
                    "body": "中文正文与原文引用。",
                    "canonical_url": "https://example.invalid/posts/search-0?new-observation=1",
                    "published_at": None,
                },
            ),
        )
        assert updated.latest_observation.content_version.id == versions[0]
        assert str(updated.latest_observation.id) != selection["observation_id"]
        unchanged = PrivateExportService(session, store, clock=lambda: datetime.now(UTC)).download(
            owner_id=owner, export_id=view.id, kind=kind
        )
        assert unchanged.body == original.body and unchanged.sha256 == original.sha256
        assert (
            str(updated.latest_observation.id)
            not in json.loads(unchanged.body)["manifest"]["observation_ids"]
        )
        LifecycleService(session, clock=lambda: datetime.now(UTC)).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=UUID(selection["observation_id"]),
            reason=DeletionReason.SOURCE_DELETED,
        )
    with sessions() as session, pytest.raises(ApplicationError):
        PrivateExportService(session, store, clock=lambda: datetime.now(UTC)).download(
            owner_id=owner, export_id=view.id, kind=kind
        )


@pytest.mark.parametrize("kind", ["content", "report"])
def test_explicit_new_operation_after_cancel_keeps_old_receipt_and_uses_new_original_job(
    editorial_client, storage, kind
):
    store, _, names = storage
    owner, report, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    command = (
        ContentExportInput(operation_id=uuid4(), content_version_ids=versions, format="json")
        if kind == "content"
        else ReportExportInput(operation_id=uuid4(), report_version=report.version, format="json")
    )

    def accept(session, value):
        service = PrivateExportService(session, store, clock=lambda: now)
        return (
            service.accept_content(owner_id=owner, command=value)
            if kind == "content"
            else service.accept_report(owner_id=owner, report_id=report.id, command=value)
        )

    with sessions() as session:
        original = accept(session, command)
        JobService(session, clock=lambda: now).request_cancel(
            owner_id=owner, job_id=original.job_id
        )
        same_operation = accept(session, command)
        assert same_operation.id == original.id and same_operation.job_id == original.job_id
        assert (
            same_operation.status == "cancelled"
            and same_operation.input_sha256 == original.input_sha256
        )
        assert not names
        next_command = command.model_copy(update={"operation_id": uuid4()})
        renewed = accept(session, next_command)
        assert renewed.id != original.id and renewed.job_id != original.job_id
        assert renewed.input_sha256 == original.input_sha256 and renewed.status == "pending"
        assert accept(session, next_command).id == renewed.id
        assert accept(session, command).id == original.id
        assert (
            accept(session, next_command.model_copy(update={"operation_id": uuid4()})).id
            == renewed.id
        )
    message, lease = execution(sessions, renewed, now)
    completion = PrivateExportExecutor(sessions, store, clock=lambda: now).execute(message, lease)
    assert completion is not None
    assert len(names) == 1
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: now).complete(
            lease,
            message=MessageReference(message.message_id, "hotkey.jobs", 0, 0),
            completion=completion,
        )
        service = PrivateExportService(session, store, clock=lambda: now)
        assert service.download(owner_id=owner, export_id=renewed.id, kind=kind).body
        assert service.get(owner_id=owner, export_id=original.id, kind=kind).status == "cancelled"
        assert (
            session.scalar(text("SELECT status FROM jobs WHERE id=:id"), {"id": original.job_id})
            == "cancelled"
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM jobs WHERE owner_id=:owner AND kind=:kind"),
                {"owner": owner, "kind": f"{kind}.export"},
            )
            == 2
        )
        table = "content_export_requests" if kind == "content" else "report_exports"
        old_manifest = session.scalar(
            text(f"SELECT input_manifest FROM {table} WHERE id=:id"),
            {"id": original.id},
        )
        assert (
            json.loads(service.download(owner_id=owner, export_id=renewed.id, kind=kind).body)[
                "manifest"
            ]
            == old_manifest
        )
