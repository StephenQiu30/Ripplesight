import os
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_editorial_source_profiles import NOW, budgets, setup
from tests.integration.test_editorial_source_profiles import engine as engine

from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import JobExecutionService
from jobs.models import Job
from jobs.schemas import JobAcceptedMessage, JobStatus
from sources.editorial_preview_job import EditorialSourcePreviewExecutor
from sources.editorial_preview_schemas import (
    EditorialRemotePreviewInput,
    EditorialSamplePreviewInput,
)
from sources.editorial_preview_services import EditorialSourcePreviewService
from sources.editorial_schemas import EditorialCursor


def settings():
    return Settings(
        _env_file=None,
        database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
        editorial_sources_enabled=True,
        editorial_public_requests_enabled=True,
    )


def admission(session, owner, profile, configuration, *, now=NOW):
    command = EditorialRemotePreviewInput(
        operation_id=uuid4(), expected_revision=profile.revision, reason="Controlled preview only"
    )
    job = EditorialSourcePreviewService(session, configuration, clock=lambda: now).enqueue(
        owner_id=owner, profile_id=profile.id, command=command
    )
    with session.begin():
        row = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:id"),
            {"id": job.id},
        ).one()
    message = JobAcceptedMessage.model_validate(
        dict(**row.payload, message_id=row.id, event_type=row.event_type, schema_version=2)
    )
    lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
        job_id=job.id, worker_id="preview"
    )
    return command, message, lease


def test_remote_preview_original_job_returns_bounded_metadata_without_ingesting_or_mutating_source(
    engine,
):
    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        source, owner, profile, _ = setup(session)
        budgets(session, owner)
        _command, message, lease = admission(session, owner, profile, configuration)
    calls = []

    def handle(request):
        calls.append(request.url)
        return httpx.Response(
            200,
            text='<rss version="2.0"><channel><title>Controlled</title>'
            + "".join(
                f"<item><title>News {i}</title><link>https://example.com/{i}</link>"
                "<description>Given source summary</description></item>"
                for i in range(25)
            )
            + "</channel></rss>",
        )

    executor = EditorialSourcePreviewExecutor(
        sessions, configuration, clock=lambda: NOW, transport=httpx.MockTransport(handle)
    )
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    with sessions() as session:
        result = EditorialSourcePreviewService(session, configuration, clock=lambda: NOW).read(
            owner_id=owner, job_id=message.job_id
        )
        assert result.preview.status == "complete" and result.preview.count == 25
        assert len(result.preview.items) == 20 and result.preview.requests == 1 and len(calls) == 1
        after = source.__class__(session, clock=lambda: NOW).get_profile(
            owner_id=owner, profile_id=profile.id
        )
        assert after.last_ok_at is None and after.has_backlog == profile.has_backlog
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 0
            assert session.scalar(text("SELECT count(*) FROM editorial_source_runs")) == 0
            assert session.scalar(text("SELECT count(*) FROM event_attention_sources")) == 0
            assert session.scalar(
                text("SELECT cursor FROM editorial_source_profiles WHERE id=:id"),
                {"id": profile.id},
            ) == EditorialCursor().model_dump(mode="json")
            assert session.scalar(select(Job).where(Job.id == message.job_id)).requests_sent == 1
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
            )


def test_unknown_preview_recovery_never_reissues_or_allows_new_operation(engine):
    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        budgets(session, owner)
        _, message, lease = admission(session, owner, profile, configuration)
    calls = []

    def handle(request):
        calls.append(request.url)
        raise httpx.ReadTimeout("Controlled unknown response")

    executor = EditorialSourcePreviewExecutor(
        sessions, configuration, clock=lambda: NOW, transport=httpx.MockTransport(handle)
    )
    assert executor.execute(message, lease).status == JobStatus.PARTIALLY_SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.PARTIALLY_SUCCEEDED
    with sessions() as session:
        service = EditorialSourcePreviewService(session, configuration, clock=lambda: NOW)
        result = service.read(owner_id=owner, job_id=message.job_id)
        assert result.preview.status == "unknown" and len(calls) == 1
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service.enqueue(
                owner_id=owner,
                profile_id=profile.id,
                command=EditorialRemotePreviewInput(
                    operation_id=uuid4(),
                    expected_revision=profile.revision,
                    reason="Cannot bypass unknown receipt",
                ),
            )
        with session.begin():
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
            )


def test_local_sample_audit_is_idempotent_and_does_not_store_raw_sample(engine):
    with Session(engine) as session:
        _, owner, _, _ = setup(session)
        service = EditorialSourcePreviewService(session, settings(), clock=lambda: NOW)
        command = EditorialSamplePreviewInput(
            operation_id=uuid4(),
            reason="Given RSS parser sample",
            configuration={
                "kind": "rss",
                "feed_url": "https://example.com/feed",
                "allowed_hosts": ["example.com"],
            },
            sample="<rss><channel><title>Sample</title><item><title>Controlled local title</title>"
            "<link>https://example.com/local</link>"
            "<description>PRIVATE RAW SAMPLE MARKER</description>"
            "</item></channel></rss>",
        )
        result = service.preview_sample(owner_id=owner, command=command)
        assert result == service.preview_sample(owner_id=owner, command=command)
        with session.begin():
            payload = session.execute(
                text("SELECT before_state FROM operations_audit_operations WHERE operation_id=:op"),
                {"op": command.operation_id},
            ).scalar_one()
            assert "sample" not in payload and payload["sample_sha256"]
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 0


def test_review_unknown_requires_exact_original_operation_current_cas_and_never_rewrites_receipt(
    engine,
):
    from jobs.execution import MessageReference
    from sources.editorial_preview_schemas import EditorialPreviewReviewInput

    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        budgets(session, owner)
        command, message, lease = admission(session, owner, profile, configuration)
    calls = []

    def handle(request):
        calls.append(request.url)
        raise httpx.ReadTimeout("Controlled unknown response")

    completion = EditorialSourcePreviewExecutor(
        sessions, configuration, clock=lambda: NOW, transport=httpx.MockTransport(handle)
    ).execute(message, lease)
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).complete(
            lease,
            message=MessageReference(message.message_id, "controlled-preview", 0, 0),
            completion=completion,
        )
        service = EditorialSourcePreviewService(session, configuration, clock=lambda: NOW)
        original = service.read(owner_id=owner, job_id=message.job_id).preview
        review = EditorialPreviewReviewInput(
            operation_id=uuid4(),
            preview_operation_id=command.operation_id,
            expected_revision=profile.revision,
            reason="Supplier response remains uncertain; cap was verified",
        )
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service.review(
                owner_id=owner,
                job_id=message.job_id,
                command=review.model_copy(update={"expected_revision": profile.revision + 1}),
            )
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service.review(
                owner_id=owner,
                job_id=message.job_id,
                command=review.model_copy(update={"preview_operation_id": uuid4()}),
            )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.review(owner_id=uuid4(), job_id=message.job_id, command=review)
        accepted = service.review(owner_id=owner, job_id=message.job_id, command=review)
        assert accepted.reviewed and accepted.status == "unknown"
        assert service.review(owner_id=owner, job_id=message.job_id, command=review) == accepted
        assert service.read(owner_id=owner, job_id=message.job_id).preview == original
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.review(
                owner_id=owner,
                job_id=message.job_id,
                command=review.model_copy(update={"reason": "Different evidence"}),
            )
        new_job = service.enqueue(
            owner_id=owner,
            profile_id=profile.id,
            command=EditorialRemotePreviewInput(
                operation_id=uuid4(),
                expected_revision=profile.revision,
                reason="Explicit new request after manual review",
            ),
        )
        assert new_job.id != message.job_id and len(calls) == 1
        with session.begin():
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM operations_audit_operations WHERE action="
                        "'editorial.source.preview.review'"
                    )
                )
                == 1
            )
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
            )


def test_abandoned_preview_new_epoch_conservatively_settles_original_reservations_without_http(
    engine,
):
    from datetime import timedelta
    from uuid import uuid5

    from jobs.schemas import (
        BudgetContext,
        BudgetMetric,
        BudgetReservationInput,
        UsageAttemptInput,
        UsageKind,
    )
    from jobs.services import ResourceBudgetService

    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    later = NOW + timedelta(seconds=31)
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        budgets(session, owner)
        _, message, lease = admission(session, owner, profile, configuration)
        with session.begin():
            ledger = ResourceBudgetService(session, clock=lambda: NOW)
            ledger.reserve_budget_in_transaction(
                owner_id=owner,
                command=BudgetReservationInput(
                    reservation_id=uuid5(message.job_id, "network:1"),
                    operation_id=message.operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(
                        source_ref=profile.source_key, job_ref=str(message.job_id)
                    ),
                ),
            )
            ledger.begin_attempt_in_transaction(
                owner_id=owner,
                command=UsageAttemptInput(
                    attempt_id=uuid5(message.job_id, "usage:1"),
                    operation_id=message.operation_id,
                    component_key="collector.editorial",
                    usage_kind=UsageKind.NETWORK_REQUEST,
                    stage="source_request",
                    started_at=NOW,
                ),
            )
            execution = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW)
            live, allowed = execution.begin_request_in_transaction(lease)
            assert allowed
            execution.save_checkpoint_in_transaction(
                live, sequence=1, checkpoint={"source_preview_started": True}
            )
        resumed = JobExecutionService(session, lease_seconds=30, clock=lambda: later).acquire(
            job_id=message.job_id, worker_id="new-epoch"
        )
        assert resumed.epoch > lease.epoch
    calls = []
    executor = EditorialSourcePreviewExecutor(
        sessions,
        configuration,
        clock=lambda: later,
        transport=httpx.MockTransport(lambda request: calls.append(request.url)),
    )
    assert executor.execute(message, resumed).status == JobStatus.PARTIALLY_SUCCEEDED
    with sessions() as session:
        result = EditorialSourcePreviewService(session, configuration, clock=lambda: later).read(
            owner_id=owner, job_id=message.job_id
        )
        assert result.preview.status == "unknown" and result.preview.requests == 1 and not calls
        with session.begin():
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
            )
            assert session.scalar(text("SELECT sum(used_units) FROM resource_budget_windows")) == 1
            assert session.scalar(text("SELECT outcome FROM resource_usage_attempts")) == "failed"


@pytest.mark.parametrize("blocked_by", ["switch", "budget", "permission"])
def test_remote_preview_default_switch_missing_budget_and_revoked_permission_are_zero_requests(
    engine, blocked_by
):
    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        if blocked_by != "budget":
            budgets(session, owner)
        _, message, lease = admission(session, owner, profile, configuration)
        if blocked_by == "permission":
            with session.begin():
                session.execute(
                    text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                    {"key": profile.source_key},
                )
    if blocked_by == "switch":
        configuration = configuration.model_copy(update={"editorial_sources_enabled": False})
    calls = []
    completion = EditorialSourcePreviewExecutor(
        sessions,
        configuration,
        clock=lambda: NOW,
        transport=httpx.MockTransport(lambda request: calls.append(request.url)),
    ).execute(message, lease)
    assert completion.status == JobStatus.PARTIALLY_SUCCEEDED and not calls
    with sessions() as session:
        result = EditorialSourcePreviewService(session, configuration, clock=lambda: NOW).read(
            owner_id=owner, job_id=message.job_id
        )
        assert result.preview.status == "blocked" and result.preview.requests == 0
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
            assert session.scalar(text("SELECT count(*) FROM resource_budget_reservations")) == 0


def test_current_permission_is_rechecked_on_result_get_without_http(engine):
    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        budgets(session, owner)
        _, message, lease = admission(session, owner, profile, configuration)
    calls = []

    def handle(request):
        calls.append(request.url)
        return httpx.Response(200, text="<rss><channel><title>Controlled</title></channel></rss>")

    assert (
        EditorialSourcePreviewExecutor(
            sessions, configuration, clock=lambda: NOW, transport=httpx.MockTransport(handle)
        )
        .execute(message, lease)
        .status
        == JobStatus.SUCCEEDED
    )
    with sessions() as session:
        with session.begin():
            session.execute(
                text(
                    "UPDATE evidence_retention_policies SET requested_days=0,effective_days=0 "
                    "WHERE source_policy_id IN (SELECT id FROM source_access_policies "
                    "WHERE source_key=:key)"
                ),
                {"key": profile.source_key},
            )
        with pytest.raises(ApplicationError, match="editorial_source_unavailable"):
            EditorialSourcePreviewService(session, configuration, clock=lambda: NOW).read(
                owner_id=owner, job_id=message.job_id
            )
    assert len(calls) == 1


def test_preview_http_contract_requires_operator_csrf_and_has_typed_results(engine):
    from fastapi.testclient import TestClient

    from main import create_app

    with Session(engine, expire_on_commit=False) as session:
        _, _owner, profile, _ = setup(session)
    configuration = settings().model_copy(
        update={
            "environment": "test",
            "operator_token": SecretStr("controlled-preview-token"),
        }
    )
    app = create_app(configuration)
    local = {
        "operation_id": str(uuid4()),
        "reason": "Local sample parser contract",
        "configuration": {
            "kind": "rss",
            "feed_url": "https://example.com/feed",
            "allowed_hosts": ["example.com"],
        },
        "sample": "<rss><channel><title>Given sample</title></channel></rss>",
    }
    path = "/api/editorial-sources/preview/sample"
    token = {"X-HotKey-Operator-Token": "controlled-preview-token"}
    with TestClient(app) as client:
        from tests.conftest import authenticate_test_client

        assert client.post(path, json=local).status_code == 401
        authenticate_test_client(client, owner_id=_owner)
        headers = {**token, "X-HotKey-CSRF": client.cookies["hotkey_csrf"]}
        assert client.post(path, json=local).status_code == 401
        assert client.post(path, json=local, headers=token).status_code == 403
        complete = client.post(path, json=local, headers=headers)
        assert complete.status_code == 200 and complete.headers["cache-control"] == "no-store"
        assert complete.json()["requests"] == 0 and complete.json()["mode"] == "sample"
        invalid = client.post(
            path, json={**local, "operation_id": str(uuid4()), "sample": "Bad XML"}, headers=headers
        )
        assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_editorial_input"
        remote = {
            "operation_id": str(uuid4()),
            "reason": "Stored version preview",
            "expected_revision": profile.revision,
        }
        stale = client.post(
            f"/api/editorial-sources/{profile.id}/previews",
            headers=headers,
            json={**remote, "expected_revision": profile.revision + 1},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "editorial_version_conflict"
        queued = client.post(
            f"/api/editorial-sources/{profile.id}/previews", headers=headers, json=remote
        )
        assert queued.status_code == 202 and queued.json()["status"] == "queued"
        job_id = queued.json()["id"]
        assert client.get(f"/api/editorial-sources/previews/{job_id}").status_code == 401
        result = client.get(f"/api/editorial-sources/previews/{job_id}", headers=token)
        assert result.status_code == 200 and result.json()["preview"] is None
        assert result.json()["job"]["id"] == job_id
        reviewed = client.post(
            f"/api/editorial-sources/previews/{job_id}/review",
            headers=headers,
            json={
                "operation_id": str(uuid4()),
                "preview_operation_id": remote["operation_id"],
                "expected_revision": profile.revision,
                "reason": "Queued request is not unknown",
            },
        )
        assert reviewed.status_code == 409
        schema = client.get("/openapi.json").json()
        assert (
            "sample" in schema["components"]["schemas"]["EditorialSamplePreviewInput"]["required"]
        )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM content_records")) == 0
        assert connection.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


def test_terminal_interrupted_preview_is_read_as_unknown_and_manual_review_settles_original_cap(
    engine,
):
    from uuid import uuid5

    from jobs.execution import JobCompletion, JobExecutionFailure, MessageReference
    from jobs.schemas import BudgetContext, BudgetMetric, BudgetReservationInput, JobFailureCategory
    from jobs.services import ResourceBudgetService
    from sources.editorial_preview_schemas import EditorialPreviewReviewInput

    sessions = sessionmaker(engine, expire_on_commit=False)
    configuration = settings()
    with sessions() as session:
        _, owner, profile, _ = setup(session)
        budgets(session, owner)
        command, message, lease = admission(session, owner, profile, configuration)
        with session.begin():
            ResourceBudgetService(session, clock=lambda: NOW).reserve_budget_in_transaction(
                owner_id=owner,
                command=BudgetReservationInput(
                    reservation_id=uuid5(message.job_id, "network:1"),
                    operation_id=command.operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(
                        source_ref=profile.source_key, job_ref=str(message.job_id)
                    ),
                ),
            )
            execution = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW)
            live, allowed = execution.begin_request_in_transaction(lease)
            assert allowed
            execution.save_checkpoint_in_transaction(
                live, sequence=1, checkpoint={"source_preview_started": True}
            )
        JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).complete(
            lease,
            message=MessageReference(message.message_id, "interrupted-preview", 0, 0),
            completion=JobCompletion(
                status=JobStatus.PARTIALLY_SUCCEEDED,
                failure=JobExecutionFailure(
                    error_code="source_preview_deadline",
                    category=JobFailureCategory.TRANSIENT,
                    occurred_at=NOW,
                    next_action="Explicit review of uncertain request",
                    manual_retry_allowed=False,
                ),
            ),
        )
        service = EditorialSourcePreviewService(session, configuration, clock=lambda: NOW)
        view = service.read(owner_id=owner, job_id=message.job_id)
        assert view.preview.status == "unknown" and view.preview.requests == 1
        with session.begin():
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 1
            )
        review = EditorialPreviewReviewInput(
            operation_id=uuid4(),
            preview_operation_id=command.operation_id,
            expected_revision=profile.revision,
            reason="Original request outcome was independently checked",
        )
        assert service.review(owner_id=owner, job_id=message.job_id, command=review).reviewed
        with session.begin():
            assert (
                session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
            )
            assert session.scalar(text("SELECT sum(used_units) FROM resource_budget_windows")) == 1
        assert service.read(owner_id=owner, job_id=message.job_id).preview == view.preview
        assert (
            service.enqueue(
                owner_id=owner,
                profile_id=profile.id,
                command=EditorialRemotePreviewInput(
                    operation_id=uuid4(),
                    expected_revision=profile.revision,
                    reason="Separate explicit admission after review",
                ),
            ).id
            != message.job_id
        )


def test_official_x_preview_reads_one_page_meters_original_cost_and_preserves_all_source_watermarks(
    engine,
):
    from datetime import timedelta

    from tests.integration.test_editorial_group_runtime import group_setup

    from jobs.schemas import BudgetMetric, BudgetPolicyInput
    from jobs.services import ResourceBudgetService

    sessions, owner, profiles, now = group_setup(engine)
    profile = profiles[0]
    configuration = settings().model_copy(
        update={
            "editorial_x_authorized": True,
            "editorial_x_token": SecretStr("controlled-official-x-bearer"),
            "editorial_x_post_unit_usd_micros": 10,
        }
    )
    with sessions() as session:
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="preview.x.source",
                metric=BudgetMetric.X_API_USD_MICROS,
                scope_kind="source",
                scope_reference="x",
                limit_units=1000000,
                window_seconds=3600,
                window_anchor_at=now - timedelta(minutes=1),
                enabled=True,
            ),
        )
        _, message, lease = admission(session, owner, profile, configuration, now=now)
        with session.begin():
            previous = session.scalar(
                text("SELECT cursor FROM editorial_source_profiles WHERE id=:id"),
                {"id": profile.id},
            )
    calls = []

    def handle(request):
        calls.append(request.url)
        assert request.url.host == "api.x.com"
        assert request.url.path == "/2/tweets/search/recent"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": str(1000 + index),
                        "author_id": "1",
                        "text": f"Controlled release {index}",
                        "created_at": now.isoformat(),
                    }
                    for index in range(4)
                ],
                "includes": {"users": [{"id": "1", "username": "one", "name": "One"}]},
                "meta": {"next_token": "not-fetched"},
            },
        )

    executor = EditorialSourcePreviewExecutor(
        sessions, configuration, clock=lambda: now, transport=httpx.MockTransport(handle)
    )
    assert executor.execute(message, lease).status == JobStatus.PARTIALLY_SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.PARTIALLY_SUCCEEDED
    with sessions() as session:
        result = (
            EditorialSourcePreviewService(session, configuration, clock=lambda: now)
            .read(owner_id=owner, job_id=message.job_id)
            .preview
        )
        assert result.count == 4 and result.requests == 1 and len(calls) == 1
        assert result.status == "partial" and result.reason == "x_gap_pending"
        with session.begin():
            assert (
                session.scalar(
                    text("SELECT cursor FROM editorial_source_profiles WHERE id=:id"),
                    {"id": profile.id},
                )
                == previous
            )
            assert (
                session.scalar(
                    text(
                        "SELECT sum(actual_units) FROM resource_budget_reservations "
                        "WHERE operation_id=:op AND metric='x_api_usd_micros'"
                    ),
                    {"op": message.operation_id},
                )
                == 80
            )
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 0
            assert session.scalar(text("SELECT count(*) FROM editorial_source_runs")) == 0
            assert (
                session.scalar(
                    text(
                        "SELECT count(DISTINCT reservation_id) FROM resource_budget_reservations "
                        "WHERE operation_id=:op AND metric='x_api_usd_micros'"
                    ),
                    {"op": message.operation_id},
                )
                == 1
            )
