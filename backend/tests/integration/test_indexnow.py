from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client
from tests.integration.test_publication import _freeze_publication_clock

from jobs.execution import (
    ExecutionLease,
    JobExecutionFailure,
    JobExecutionService,
    MessageReference,
)
from jobs.schemas import BudgetPolicyInput, ComponentPolicyInput, JobAcceptedMessage, JobStatus
from jobs.services import JobService, ResourceBudgetService
from operations.indexnow_services import IndexNowExecutor, enqueue_due_indexnow_in_transaction
from operations.schemas import AuditResolutionInput
from operations.services import OperationsService
from publication.indexnow_reading import load_indexable_changes_in_transaction
from publication.indexnow_schemas import IndexableChangeCursor
from publication.publication_models import PublicationRevision
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[TestClient]:
    _freeze_publication_clock(monkeypatch, request.module)
    yield from _editorial_client.__wrapped__()


def test_indexnow_verification_is_exact_and_disabled_by_default(
    editorial_client: TestClient,
) -> None:
    assert editorial_client.get("/hotkey-indexnow-key.txt").status_code == 404
    settings = editorial_client.app.state.settings
    settings.indexnow_key = SecretStr("controlled-IndexNow-public-proof-key")
    settings.indexnow_enabled = True
    assert editorial_client.get("/hotkey-indexnow-key.txt").status_code == 404
    settings.publication_indexing_enabled = True
    settings.indexnow_external_requests_enabled = True
    response = editorial_client.get("/hotkey-indexnow-key.txt")
    assert response.status_code == 200
    assert response.text == settings.indexnow_key.get_secret_value()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("text/plain")
    assert editorial_client.get("/hotkey-indexnow-key.txt/anything").status_code == 404


def test_indexnow_revision_cursor_continues_past_500_without_skipping_ties(
    editorial_client: TestClient,
) -> None:
    owner, content_id, at = _published(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        first = session.scalar(
            select(PublicationRevision).where(
                PublicationRevision.owner_id == owner,
                PublicationRevision.content_id == content_id,
            )
        )
        assert first is not None
        for revision in range(2, 505):
            session.add(
                PublicationRevision(
                    owner_id=owner,
                    content_id=content_id,
                    revision=revision,
                    operation_id=uuid4(),
                    actor_id=owner,
                    input_fingerprint=first.input_fingerprint,
                    data=first.data,
                    reason="相同时间戳的历史修订连续分页",
                    created_at=first.created_at,
                )
            )
    cursor = IndexableChangeCursor(
        changed_at=NOW - timedelta(seconds=1), content_id=UUID(int=0), revision=0
    )
    with sessions.begin() as session:
        first_page = load_indexable_changes_in_transaction(
            session, owner_id=owner, after=cursor, until=at
        )
        assert first_page.examined == 500 and first_page.next_cursor.revision == 500
        second_page = load_indexable_changes_in_transaction(
            session, owner_id=owner, after=first_page.next_cursor, until=at
        )
        assert second_page.examined == 4 and second_page.next_cursor.revision == 504
        assert second_page.paths == [f"/items/{content_id}"]
        final = load_indexable_changes_in_transaction(
            session, owner_id=owner, after=second_page.next_cursor, until=at
        )
        assert final.examined == 0 and final.next_cursor == second_page.next_cursor


def _published(client: TestClient) -> tuple[UUID, UUID, datetime]:
    owner, run, message, lease = _run(client)
    _budget(client, owner)
    _execute(client, owner, message, lease, ControlledClient())
    settings = client.app.state.settings
    settings.indexnow_enabled = settings.publication_indexing_enabled = True
    settings.indexnow_external_requests_enabled = True
    settings.indexnow_key = SecretStr("controlled-IndexNow-public-proof-key")
    settings.web_base_url = "https://controlled.example.com"
    with client.app.state.session_factory.begin() as session:
        service = PublicationService(session, indexing_enabled=True)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                indexable=True,
                license_name="受控索引许可",
                reason="本地IndexNow合同测试",
            ),
        )
        assert service.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
    return owner, run.content_id, NOW + timedelta(seconds=181)


def _network_budget(client: TestClient, owner: UUID, at: datetime) -> None:
    with client.app.state.session_factory.begin() as session:
        service = ResourceBudgetService(session, clock=lambda: at)
        service.save_component_policy_in_transaction(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="operations.indexnow",
                component_version="1",
                cost_class="zero_price",
                enabled_for_core=True,
                reviewed_at=at,
                terms_reference="https://www.indexnow.org/documentation",
            ),
        )
        for scope in ("global", "source"):
            service.save_budget_policy_in_transaction(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key=f"indexnow.{scope}",
                    metric="network_request",
                    scope_kind=scope,
                    scope_reference="indexnow" if scope == "source" else None,
                    limit_units=20,
                    window_seconds=86400,
                    window_anchor_at=NOW,
                    enabled=True,
                ),
            )


def _accept(
    client: TestClient, owner: UUID, at: datetime
) -> tuple[UUID, JobAcceptedMessage, ExecutionLease]:
    sessions, settings = client.app.state.session_factory, client.app.state.settings
    with sessions.begin() as session:
        assert (
            enqueue_due_indexnow_in_transaction(session, owner_id=owner, now=at, settings=settings)
            == 1
        )
        session.flush()
        row = session.execute(
            text(
                "SELECT id,job_id FROM operations_audit_operations "
                "WHERE action='indexnow.submit' "
                "ORDER BY created_at DESC,id DESC LIMIT 1"
            )
        ).one()
    with sessions() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": row.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        lease = JobExecutionService(
            session, lease_seconds=settings.job_lease_seconds, clock=lambda: at
        ).acquire(job_id=row.job_id, worker_id="controlled-indexnow")
    return row.id, message, lease


class UnreadResponse(httpx.SyncByteStream):
    def __iter__(self):
        raise AssertionError("IndexNow must not read a provider body")
        yield b""


def test_indexnow_rechecks_accepted_urls_after_policy_withdrawal_without_new_article_revision(
    editorial_client: TestClient,
) -> None:
    owner, content_id, at = _published(editorial_client)
    _network_budget(editorial_client, owner, at)
    _, message, lease = _accept(editorial_client, owner, at)
    sessions, settings = (
        editorial_client.app.state.session_factory,
        editorial_client.app.state.settings,
    )
    requests: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, stream=UnreadResponse())

    with httpx.Client(transport=httpx.MockTransport(receive)) as client:
        IndexNowExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
        later = at + timedelta(days=1)
        with sessions.begin() as session:
            PublicationService(session, indexing_enabled=True).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key="x",
                now=later,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=1,
                    participation_mode="isolated",
                    indexable=False,
                    license_name="受控索引许可已撤回",
                    reason="直接来源许可收紧,不生成文章新修订",
                ),
            )
            assert session.scalar(text("SELECT count(*) FROM publication_revisions")) == 1
        _, removal_message, removal_lease = _accept(editorial_client, owner, later)
        IndexNowExecutor(sessions, settings, clock=lambda: later, client=client).execute(
            removal_message, removal_lease
        )
        assert len(requests) == 2
        with sessions() as session:
            assert session.scalar(text("SELECT count(*) FROM publication_revisions")) == 1
            proof = session.execute(
                text("SELECT after_state FROM operations_audit_operations WHERE operation_id=:op"),
                {"op": removal_message.operation_id},
            ).scalar_one()
            assert proof["eligibilities"] == {f"/items/{content_id}": False}
        # Walk subsequent receipt pages, including the removal receipt itself.
        # Current false equals the latest accepted false: no second removal POST.
        for offset in range(1, 5):
            tick = later + timedelta(seconds=offset)
            with sessions.begin() as session:
                accepted = enqueue_due_indexnow_in_transaction(
                    session, owner_id=owner, now=tick, settings=settings
                )
            if not accepted:
                break
            with sessions() as session:
                row = session.execute(
                    text(
                        "SELECT job_id FROM operations_audit_operations "
                        "WHERE action='indexnow.submit' "
                        "ORDER BY created_at DESC,id DESC LIMIT 1"
                    )
                ).one()
                outbox = session.execute(
                    text(
                        "SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:id"
                    ),
                    {"id": row.job_id},
                ).one()
                current_message = JobAcceptedMessage.model_validate(
                    {
                        **outbox.payload,
                        "message_id": outbox.id,
                        "event_type": outbox.event_type,
                        "schema_version": 2,
                    }
                )
                current_lease = JobExecutionService(
                    session, lease_seconds=settings.job_lease_seconds, clock=lambda tick=tick: tick
                ).acquire(job_id=row.job_id, worker_id="controlled-indexnow-removal-tail")
            IndexNowExecutor(
                sessions, settings, clock=lambda tick=tick: tick, client=client
            ).execute(current_message, current_lease)
        else:
            pytest.fail("receipt recheck did not stop at the current cycle tail")
        assert len(requests) == 2


@pytest.mark.parametrize("status", [200, 202])
def test_indexnow_original_job_receipt_budget_and_free_replay(
    editorial_client: TestClient, status: int
) -> None:
    owner, content_id, at = _published(editorial_client)
    _network_budget(editorial_client, owner, at)
    audit, message, lease = _accept(editorial_client, owner, at)
    requests: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, stream=UnreadResponse())

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        executor = IndexNowExecutor(
            editorial_client.app.state.session_factory,
            editorial_client.app.state.settings,
            clock=lambda: at,
            client=client,
        )
        assert executor.execute(message, lease).status is JobStatus.SUCCEEDED
        assert executor.execute(message, lease).status is JobStatus.SUCCEEDED
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.indexnow.org/indexnow"
    import json

    body = json.loads(requests[0].content)
    assert body["urlList"] == [f"https://controlled.example.com/items/{content_id}"]
    assert body["keyLocation"].endswith("/hotkey-indexnow-key.txt")
    with editorial_client.app.state.session_factory() as session:
        state = session.execute(
            text("SELECT status,after_state FROM operations_audit_operations WHERE id=:id"),
            {"id": audit},
        ).one()
        assert state.status == "succeeded"
        assert state.after_state["stage"] == (
            "accepted" if status == 200 else "key_validation_pending"
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM resource_usage_attempts WHERE operation_id=:op"),
                {"op": message.operation_id},
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": message.job_id}
            )
            == 1
        )


def test_indexnow_unknown_never_resends_until_original_job_operator_resolution(
    editorial_client: TestClient,
) -> None:
    owner, _, at = _published(editorial_client)
    _network_budget(editorial_client, owner, at)
    audit, message, lease = _accept(editorial_client, owner, at)
    requests: list[httpx.Request] = []

    def lose(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("controlled response lost", request=request)

    sessions, settings = (
        editorial_client.app.state.session_factory,
        editorial_client.app.state.settings,
    )
    with httpx.Client(transport=httpx.MockTransport(lose)) as client:
        executor = IndexNowExecutor(sessions, settings, clock=lambda: at, client=client)
        with pytest.raises(JobExecutionFailure, match="indexnow_submission_unknown") as caught:
            executor.execute(message, lease)
        assert not caught.value.manual_retry_allowed and caught.value.retry_at is None
        with pytest.raises(JobExecutionFailure, match="indexnow_submission_unknown"):
            executor.execute(message, lease)
    assert len(requests) == 1
    with sessions() as session:
        JobExecutionService(
            session, lease_seconds=settings.job_lease_seconds, clock=lambda: at
        ).record_failure(
            lease,
            message=MessageReference(message.message_id, "controlled.indexnow", 0, 1),
            failure=caught.value,
        )
    with sessions.begin() as session:
        assert (
            enqueue_due_indexnow_in_transaction(
                session, owner_id=owner, now=at + timedelta(days=1), settings=settings
            )
            == 0
        )
    with sessions() as session:
        view = OperationsService(session, clock=lambda: at).resolve_delivery(
            owner_id=owner,
            audit_id=audit,
            command=AuditResolutionInput(
                operation_id=uuid4(), reason="在受控目标确认未接收", outcome="not_delivered"
            ),
        )
        assert view.status == "failed"
        retried = JobService(session, clock=lambda: at).request_retry(
            owner_id=owner, job_id=message.job_id
        )
        assert retried.id == message.job_id
    with sessions() as session:
        next_lease = JobExecutionService(
            session, lease_seconds=settings.job_lease_seconds, clock=lambda: at
        ).acquire(job_id=message.job_id, worker_id="controlled-indexnow-after-review")
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=UnreadResponse()))
    ) as client:
        assert (
            IndexNowExecutor(sessions, settings, clock=lambda: at, client=client)
            .execute(message, next_lease)
            .status
            is JobStatus.SUCCEEDED
        )
    with sessions() as session:
        assert (
            session.scalar(text("SELECT count(*) FROM jobs WHERE kind='publication.indexnow'")) == 1
        )
        assert (
            session.scalar(
                text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": message.job_id}
            )
            == 2
        )


def test_indexnow_crash_after_sending_recovers_budget_without_second_http(
    editorial_client: TestClient,
) -> None:
    owner, _, at = _published(editorial_client)
    _network_budget(editorial_client, owner, at)
    _, message, lease = _accept(editorial_client, owner, at)
    sessions, settings = (
        editorial_client.app.state.session_factory,
        editorial_client.app.state.settings,
    )

    def crash(request: httpx.Request) -> httpx.Response:
        raise SystemExit("controlled process interruption after durable sending")

    with (
        httpx.Client(transport=httpx.MockTransport(crash)) as client,
        pytest.raises(SystemExit),
    ):
        IndexNowExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
    later = at + timedelta(seconds=settings.job_lease_seconds + 1)
    with sessions() as session:
        renewed = JobExecutionService(
            session, lease_seconds=settings.job_lease_seconds, clock=lambda: later
        ).acquire(job_id=message.job_id, worker_id="controlled-indexnow-restarted")
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda request: pytest.fail("unknown must not send"))
        ) as client,
        pytest.raises(JobExecutionFailure, match="indexnow_submission_unknown"),
    ):
        IndexNowExecutor(sessions, settings, clock=lambda: later, client=client).execute(
            message, renewed
        )
    with sessions() as session:
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM resource_usage_attempts "
                    "WHERE operation_id=:op AND outcome='failed'"
                ),
                {"op": message.operation_id},
            )
            == 1
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM resource_budget_reservations "
                    "WHERE operation_id=:op AND status='reserved'"
                ),
                {"op": message.operation_id},
            )
            == 0
        )


def test_indexnow_disabled_compute_and_empty_paths_use_no_network(
    editorial_client: TestClient,
) -> None:
    owner, _, at = _published(editorial_client)
    settings = editorial_client.app.state.settings
    settings.indexnow_external_requests_enabled = False
    _, message, lease = _accept(editorial_client, owner, at)
    sessions = editorial_client.app.state.session_factory
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: pytest.fail("disabled must not send"))
    ) as client:
        assert (
            IndexNowExecutor(sessions, settings, clock=lambda: at, client=client)
            .execute(message, lease)
            .status
            is JobStatus.SUCCEEDED
        )
    with sessions() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM resource_usage_attempts WHERE operation_id=:op"),
                {"op": message.operation_id},
            )
            == 0
        )
        assert (
            session.scalar(
                text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": message.job_id}
            )
            == 0
        )
    with sessions.begin() as session:
        page = load_indexable_changes_in_transaction(
            session,
            owner_id=uuid4(),
            after=IndexableChangeCursor(
                changed_at=NOW - timedelta(days=1), content_id=UUID(int=0), revision=0
            ),
            until=at,
        )
        assert page.examined == 0 and page.paths == []
