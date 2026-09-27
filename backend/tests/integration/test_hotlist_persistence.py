from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from content import hotlist as hotlist_module
from content.hotlist import HotlistService
from content.hotlist_execution import HotlistExecutor
from core.errors import ApplicationError
from jobs.execution import (
    ExecutionLease,
    JobExecutionFailure,
    JobExecutionService,
    MessageReference,
    StaleExecutionLeaseError,
)
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    JobAcceptedMessage,
    JobRetryScheduledMessage,
)
from jobs.services import JobService, ResourceBudgetService
from sources.adapters.rsshub_hotlist import RsshubHotlistAdapter
from sources.contracts import HotlistEntry, HotlistPage, SourcePageState, SourceStopReason
from worker import scheduler


@dataclass(frozen=True, slots=True)
class HotlistRuntime:
    engine: Engine
    sessions: sessionmaker[Session]
    owner_id: UUID
    due_at: datetime


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[HotlistRuntime]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    owner_id = uuid4()
    current = datetime.now(UTC)
    due_at = datetime.fromtimestamp(int(current.timestamp()) // 1800 * 1800, UTC)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE identity_users CASCADE"))
        connection.execute(
            text(
                "INSERT INTO identity_users "
                "(id, username, password_hash, credential_version, created_at, updated_at) "
                "VALUES (:id, 'hotlist-persistence-test', 'test-only-hash', 1, :created, :created)"
            ),
            {"id": owner_id, "created": due_at - timedelta(seconds=1)},
        )
    with sessions.begin() as session:
        service = SourcePresetService(session, clock=lambda: due_at - timedelta(seconds=1))
        service.apply_in_transaction(owner_id=owner_id, preset=SOURCE_PRESETS["hotlist_weibo"])
    with sessions() as session:
        ResourceBudgetService(session, clock=lambda: due_at).save_budget_policy(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.network.daily",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=100,
                window_seconds=86_400,
                window_anchor_at=due_at - timedelta(days=1),
                enabled=True,
            ),
        )
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    try:
        yield HotlistRuntime(engine, sessions, owner_id, due_at)
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
        engine.dispose()


def _accept(runtime: HotlistRuntime, due_at: datetime) -> UUID:
    with runtime.sessions.begin() as session:
        accepted = scheduler.enqueue_due_hotlists_in_transaction(
            session, due_at + timedelta(seconds=2)
        )
        assert accepted == 1
    with runtime.engine.connect() as connection:
        return connection.execute(
            text("SELECT job_id FROM collection_due_windows WHERE owner_id=:owner AND due_at=:due"),
            {"owner": runtime.owner_id, "due": due_at},
        ).scalar_one()


def _message(runtime: HotlistRuntime, job_id: UUID) -> JobAcceptedMessage:
    with runtime.engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).one()
    return JobAcceptedMessage.model_validate(
        {"schema_version": 2, "message_id": row.id, "event_type": "job.accepted.v2", **row.payload}
    )


def _retry_message(runtime: HotlistRuntime, job_id: UUID) -> JobRetryScheduledMessage:
    with runtime.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT id, payload FROM outbox_messages "
                "WHERE aggregate_id=:job AND dispatch_sequence=2"
            ),
            {"job": job_id},
        ).one()
    return JobRetryScheduledMessage.model_validate(
        {
            "schema_version": 1,
            "message_id": row.id,
            "event_type": "job.retry_scheduled.v1",
            **row.payload,
        }
    )


def _page(observed_at: datetime, *, entries: int = 0) -> HotlistPage:
    items = tuple(
        HotlistEntry(rank=rank, title=f"Entry {rank}", url=f"https://example.com/{rank}")
        for rank in range(1, entries + 1)
    )
    return HotlistPage(
        source_key="hotlist_weibo",
        state=SourcePageState.COMPLETE if items else SourcePageState.EMPTY,
        items=items,
        stop_reason=SourceStopReason.END_OF_RESULTS if items else SourceStopReason.SOURCE_EMPTY,
        observed_at=observed_at,
        request_count=1,
        adapter_version="controlled-v1",
    )


class ControlledAdapter:
    def __init__(self, before_request: Callable[[int], bool], page: HotlistPage) -> None:
        self._before_request = before_request
        self._page = page

    def fetch_hotlist(self) -> HotlistPage:
        assert self._before_request(1)
        return self._page


def _execute(runtime: HotlistRuntime, job_id: UUID, page: HotlistPage) -> ExecutionLease:
    lease = _acquire(runtime, job_id, page.observed_at)
    renewed, completion = _executor(runtime, page).execute(_message(runtime, job_id), lease)
    assert completion.status.value == "succeeded"
    assert "snapshot_id" in renewed.checkpoint
    return renewed


def _acquire(runtime: HotlistRuntime, job_id: UUID, at: datetime) -> ExecutionLease:
    with runtime.sessions() as session:
        return JobExecutionService(session, lease_seconds=75, clock=lambda: at).acquire(
            job_id=job_id, worker_id="hotlist-persistence-test"
        )


def _executor(runtime: HotlistRuntime, page: HotlistPage) -> HotlistExecutor:
    executor = HotlistExecutor(
        runtime.sessions,
        lease_seconds=75,
        clock=lambda: page.observed_at,
        adapter_factory=lambda _source, _url, _hosts, before, _cancel: ControlledAdapter(
            before, page
        ),
    )
    return executor


def test_empty_feed_persists_one_observed_snapshot_linked_to_due_bucket(
    runtime: HotlistRuntime,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    observed_at = runtime.due_at + timedelta(minutes=2)
    _execute(runtime, job_id, _page(observed_at))
    with runtime.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT s.entry_count, s.observed_at, s.operation_id, d.due_at, "
                "d.operation_id AS due_operation_id FROM hotlist_snapshots s "
                "JOIN collection_due_windows d ON d.owner_id=s.owner_id AND d.job_id=s.job_id "
                "WHERE s.job_id=:job"
            ),
            {"job": job_id},
        ).one()
        assert connection.execute(text("SELECT count(*) FROM hotlist_entries")).scalar_one() == 0
        job = connection.execute(
            text("SELECT requests_sent, checkpoint FROM jobs WHERE id=:job"), {"job": job_id}
        ).one()
        usage = connection.execute(
            text("SELECT outcome FROM resource_usage_attempts WHERE operation_id=:operation"),
            {"operation": row.operation_id},
        ).scalar_one()
        reservations = connection.execute(
            text(
                "SELECT status, actual_units FROM resource_budget_reservations "
                "WHERE operation_id=:operation"
            ),
            {"operation": row.operation_id},
        ).all()
    assert (row.entry_count, row.observed_at, row.due_at) == (0, observed_at, runtime.due_at)
    assert row.operation_id == row.due_operation_id
    assert job.requests_sent == 1
    assert job.checkpoint["collection.observed_count"] == 0
    assert usage == "empty"
    assert reservations
    assert all((item.status, item.actual_units) == ("settled", 1) for item in reservations)


def test_parser_or_transport_failure_does_not_create_empty_snapshot(
    runtime: HotlistRuntime,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    failed = HotlistPage(
        source_key="hotlist_weibo",
        state=SourcePageState.STOPPED,
        items=(),
        stop_reason=SourceStopReason.PROTOCOL_ERROR,
        observed_at=runtime.due_at + timedelta(minutes=2),
        request_count=1,
        adapter_version="controlled-v1",
    )
    with pytest.raises(JobExecutionFailure, match="hotlist_protocol_error"):
        _execute(runtime, job_id, failed)
    with runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM hotlist_snapshots")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT admission_state FROM collection_due_windows WHERE job_id=:job"),
                {"job": job_id},
            ).scalar_one()
            == "accepted"
        )


@pytest.mark.parametrize(
    ("response", "failure_code"),
    [
        (
            httpx.Response(
                200,
                content=(
                    b'<rss version="2.0"><channel><item><title>A</title>'
                    b"<link>https://example.com/a</link></item><broken></channel></rss>"
                ),
            ),
            "hotlist_protocol_error",
        ),
        (httpx.Response(503), "hotlist_upstream_error"),
    ],
)
def test_real_adapter_failure_reaches_executor_without_empty_snapshot(
    runtime: HotlistRuntime, response: httpx.Response, failure_code: str
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    observed_at = runtime.due_at + timedelta(minutes=2)
    lease = _acquire(runtime, job_id, observed_at)
    executor = HotlistExecutor(
        runtime.sessions,
        lease_seconds=75,
        clock=lambda: observed_at,
        adapter_factory=lambda source, url, hosts, before, cancelled: RsshubHotlistAdapter(
            source_key=source,
            feed_url=url,
            allowed_hosts=hosts,
            before_request=before,
            cancelled=cancelled,
            transport=httpx.MockTransport(lambda _: response),
        ),
    )
    with pytest.raises(JobExecutionFailure, match=failure_code):
        executor.execute(_message(runtime, job_id), lease)
    with runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM hotlist_snapshots")).scalar_one() == 0
        row = connection.execute(
            text(
                "SELECT j.requests_sent, a.outcome FROM jobs j "
                "JOIN resource_usage_attempts a ON a.operation_id=j.operation_id "
                "WHERE j.id=:job"
            ),
            {"job": job_id},
        ).one()
    assert (row.requests_sent, row.outcome) == (1, "failed")


def _fail_one_hotlist_request(
    runtime: HotlistRuntime, job_id: UUID
) -> tuple[ExecutionLease, datetime]:
    failed_at = runtime.due_at + timedelta(minutes=2)
    lease = _acquire(runtime, job_id, failed_at)
    executor = HotlistExecutor(
        runtime.sessions,
        lease_seconds=75,
        clock=lambda: failed_at,
        adapter_factory=lambda source, url, hosts, before, cancelled: RsshubHotlistAdapter(
            source_key=source,
            feed_url=url,
            allowed_hosts=hosts,
            before_request=before,
            cancelled=cancelled,
            transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        ),
    )
    message = _message(runtime, job_id)
    with pytest.raises(JobExecutionFailure, match="hotlist_upstream_error") as caught:
        executor.execute(message, lease)
    assert caught.value.manual_retry_allowed
    with runtime.sessions() as session:
        JobExecutionService(session, lease_seconds=75, clock=lambda: failed_at).record_failure(
            lease,
            message=MessageReference(
                message_id=message.message_id,
                topic="hotkey.jobs.accepted.v2",
                partition=0,
                offset=3,
            ),
            failure=caught.value,
        )
    return lease, failed_at


def test_failed_hotlist_retries_original_bucket_with_new_cycle_and_cumulative_budget(
    runtime: HotlistRuntime,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    old_lease, failed_at = _fail_one_hotlist_request(runtime, job_id)
    retry_at = failed_at + timedelta(minutes=2)
    with runtime.sessions() as session:
        service = JobService(session, clock=lambda: retry_at)
        queued = service.request_retry(owner_id=runtime.owner_id, job_id=job_id)
        repeated = service.request_retry(owner_id=runtime.owner_id, job_id=job_id)
    assert queued == repeated
    assert queued.collection_cycle_no == 1
    assert queued.collection_cycle_pending
    assert queued.collection_budget_remaining_us is None

    succeeded_at = retry_at + timedelta(minutes=1)
    lease = _acquire(runtime, job_id, succeeded_at)
    with runtime.sessions() as session, pytest.raises(StaleExecutionLeaseError):
        execution = JobExecutionService(session, lease_seconds=75, clock=lambda: succeeded_at)
        execution.begin_request(old_lease)
    renewed, completion = _executor(runtime, _page(succeeded_at)).execute(
        _retry_message(runtime, job_id), lease
    )
    assert completion.status.value == "succeeded"
    assert renewed.epoch == 2
    with runtime.engine.connect() as connection:
        current = connection.execute(
            text(
                "SELECT j.operation_id, j.collection_cycle_no, j.collection_cycle_started_at, "
                "j.collection_cycle_requests_sent, j.requests_sent, j.started_at, "
                "d.due_at, s.observed_at, s.operation_id AS snapshot_operation_id "
                "FROM jobs j JOIN collection_due_windows d ON d.job_id=j.id "
                "JOIN hotlist_snapshots s ON s.job_id=j.id WHERE j.id=:job"
            ),
            {"job": job_id},
        ).one()
        attempts = (
            connection.execute(
                text(
                    "SELECT collection_cycle_no FROM job_attempts WHERE job_id=:job "
                    "ORDER BY lease_epoch"
                ),
                {"job": job_id},
            )
            .scalars()
            .all()
        )
        usage = connection.execute(
            text(
                "SELECT outcome, attempt_id FROM resource_usage_attempts "
                "WHERE operation_id=:operation ORDER BY started_at, attempt_id"
            ),
            {"operation": current.operation_id},
        ).all()
        budgets = connection.execute(
            text(
                "SELECT p.scope_kind, w.used_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.owner_id=:owner AND p.metric='network_request' "
                "ORDER BY p.scope_kind"
            ),
            {"owner": runtime.owner_id},
        ).all()
        outbox = connection.execute(
            text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).scalar_one()
    assert current.operation_id == current.snapshot_operation_id
    assert (current.due_at, current.observed_at) == (runtime.due_at, succeeded_at)
    assert (
        current.collection_cycle_no,
        current.collection_cycle_started_at,
        current.collection_cycle_requests_sent,
        current.requests_sent,
        current.started_at,
    ) == (2, succeeded_at, 1, 2, failed_at)
    assert attempts == [1, 2]
    assert len(usage) == 2
    assert {row.outcome for row in usage} == {"failed", "empty"}
    assert usage[0].attempt_id != usage[1].attempt_id
    assert budgets == [("global", 2), ("source", 2)]
    assert outbox == 2


@pytest.mark.parametrize("scope_kind", ["global", "source"])
def test_hotlist_retry_rejects_exhausted_daily_budget_without_queueing(
    runtime: HotlistRuntime,
    scope_kind: str,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    _, failed_at = _fail_one_hotlist_request(runtime, job_id)
    with runtime.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE resource_budget_policies SET limit_units=1 "
                "WHERE owner_id=:owner AND metric='network_request' "
                "AND scope_kind=:scope_kind"
            ),
            {"owner": runtime.owner_id, "scope_kind": scope_kind},
        )
    with (
        runtime.sessions() as session,
        pytest.raises(ApplicationError, match="retry_budget_exhausted"),
    ):
        JobService(session, clock=lambda: failed_at + timedelta(minutes=2)).request_retry(
            owner_id=runtime.owner_id, job_id=job_id
        )
    with runtime.engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, collection_cycle_no FROM jobs WHERE id=:job"),
            {"job": job_id},
        ).one()
        outbox = connection.execute(
            text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).scalar_one()
    assert tuple(row) == ("failed", 1)
    assert outbox == 1


def test_hotlist_retry_rejects_stale_connection_version_without_queueing(
    runtime: HotlistRuntime,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    _, failed_at = _fail_one_hotlist_request(runtime, job_id)
    with runtime.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_connection_versions "
                "(connection_id, version, owner_id, auth_kind, secret_ref, config, "
                "execution_policy, created_by, created_at) "
                "SELECT connection_id, 2, owner_id, auth_kind, secret_ref, config, "
                "execution_policy, created_by, :now FROM source_connection_versions "
                "WHERE owner_id=:owner AND version=1"
            ),
            {"owner": runtime.owner_id, "now": failed_at + timedelta(seconds=1)},
        )
        connection.execute(
            text(
                "UPDATE source_connections SET current_version=2, updated_at=:now "
                "WHERE owner_id=:owner AND source_key='hotlist_weibo'"
            ),
            {"owner": runtime.owner_id, "now": failed_at + timedelta(seconds=1)},
        )
    with (
        runtime.sessions() as session,
        pytest.raises(ApplicationError, match="connection_version_conflict"),
    ):
        JobService(session, clock=lambda: failed_at + timedelta(minutes=2)).request_retry(
            owner_id=runtime.owner_id, job_id=job_id
        )
    with runtime.engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, collection_cycle_no FROM jobs WHERE id=:job"),
            {"job": job_id},
        ).one()
        outbox = connection.execute(
            text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).scalar_one()
    assert tuple(row) == ("failed", 1)
    assert outbox == 1


def test_empty_bucket_then_nonempty_bucket_keep_distinct_observations(
    runtime: HotlistRuntime,
) -> None:
    first = _accept(runtime, runtime.due_at)
    _execute(runtime, first, _page(runtime.due_at + timedelta(minutes=2)))
    next_due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, next_due)
    _execute(runtime, second, _page(next_due + timedelta(minutes=2), entries=1))
    with runtime.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.due_at, s.observed_at, s.entry_count, s.operation_id "
                "FROM hotlist_snapshots s JOIN collection_due_windows d "
                "ON d.owner_id=s.owner_id AND d.job_id=s.job_id ORDER BY d.due_at"
            )
        ).all()
    assert [(row.due_at, row.entry_count) for row in rows] == [
        (runtime.due_at, 0),
        (next_due, 1),
    ]
    assert rows[0].operation_id != rows[1].operation_id
    with runtime.sessions() as session:
        latest = HotlistService(session).get_latest(
            owner_id=runtime.owner_id, source_key="hotlist_weibo"
        )
    assert latest.due_at == next_due
    assert latest.entry_count == 1
    assert latest.items[0].rank_change == "new"


def test_failed_bucket_preserves_error_and_next_bucket_can_succeed(
    runtime: HotlistRuntime,
) -> None:
    first = _accept(runtime, runtime.due_at)
    failed = HotlistPage(
        source_key="hotlist_weibo",
        state=SourcePageState.STOPPED,
        items=(),
        stop_reason=SourceStopReason.UPSTREAM_ERROR,
        observed_at=runtime.due_at + timedelta(minutes=2),
        request_count=1,
        adapter_version="controlled-v1",
    )
    lease = _acquire(runtime, first, failed.observed_at)
    message = _message(runtime, first)
    with pytest.raises(JobExecutionFailure, match="hotlist_upstream_error") as captured:
        _executor(runtime, failed).execute(message, lease)
    with runtime.sessions() as session:
        JobExecutionService(
            session, lease_seconds=75, clock=lambda: failed.observed_at
        ).record_failure(
            lease,
            message=MessageReference(
                message_id=message.message_id,
                topic="hotkey.jobs.accepted.v2",
                partition=0,
                offset=1,
            ),
            failure=captured.value,
        )
    next_due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, next_due)
    _execute(runtime, second, _page(next_due + timedelta(minutes=2)))
    with runtime.engine.connect() as connection:
        old = connection.execute(
            text(
                "SELECT d.due_at, d.admission_state, j.last_error_code "
                "FROM collection_due_windows d JOIN jobs j ON j.id=d.job_id "
                "WHERE d.job_id=:job"
            ),
            {"job": first},
        ).one()
        snapshots = connection.execute(
            text("SELECT job_id, entry_count FROM hotlist_snapshots")
        ).all()
    assert (old.due_at, old.admission_state, old.last_error_code) == (
        runtime.due_at,
        "accepted",
        "hotlist_upstream_error",
    )
    assert [(row.job_id, row.entry_count) for row in snapshots] == [(second, 0)]


def test_replayed_message_and_scan_do_not_duplicate_original_snapshot(
    runtime: HotlistRuntime,
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    page = _page(runtime.due_at + timedelta(minutes=2))
    renewed = _execute(runtime, job_id, page)
    with runtime.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, runtime.due_at + timedelta(minutes=3)
            )
            == 0
        )
    replayed, completion = _executor(runtime, page).execute(_message(runtime, job_id), renewed)
    assert replayed == renewed
    assert completion.status.value == "succeeded"
    with runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM hotlist_snapshots")).scalar_one() == 1
        assert (
            connection.execute(text("SELECT count(*) FROM collection_due_windows")).scalar_one()
            == 1
        )


def test_late_previous_bucket_result_keeps_original_due_and_actual_observed_time(
    runtime: HotlistRuntime,
) -> None:
    first = _accept(runtime, runtime.due_at)
    next_due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, next_due)
    _execute(runtime, second, _page(next_due + timedelta(minutes=2)))
    observed_late = next_due + timedelta(minutes=4)
    _execute(runtime, first, _page(observed_late, entries=1))
    with runtime.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.due_at, s.observed_at, s.entry_count "
                "FROM hotlist_snapshots s JOIN collection_due_windows d "
                "ON d.owner_id=s.owner_id AND d.job_id=s.job_id ORDER BY d.due_at"
            )
        ).all()
    assert [(row.due_at, row.observed_at, row.entry_count) for row in rows] == [
        (runtime.due_at, observed_late, 1),
        (next_due, next_due + timedelta(minutes=2), 0),
    ]


def test_mid_entry_write_failure_rolls_back_snapshot_and_entries(
    runtime: HotlistRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _accept(runtime, runtime.due_at)
    original = hotlist_module.HotlistEntryRecord

    def fail_second(*args: object, **kwargs: object) -> object:
        if kwargs.get("rank") == 2:
            raise RuntimeError("injected second entry failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(hotlist_module, "HotlistEntryRecord", fail_second)
    with pytest.raises(JobExecutionFailure, match="hotlist_processing_failed"):
        _execute(runtime, job_id, _page(runtime.due_at + timedelta(minutes=2), entries=2))
    with runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM hotlist_snapshots")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM hotlist_entries")).scalar_one() == 0
        assert (
            connection.execute(text("SELECT count(*) FROM resource_usage_attempts")).scalar_one()
            == 1
        )


def test_database_rejects_snapshot_without_matching_due_or_duplicate_operation(
    runtime: HotlistRuntime,
) -> None:
    first = _accept(runtime, runtime.due_at)
    _execute(runtime, first, _page(runtime.due_at + timedelta(minutes=2)))
    next_due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, next_due)
    with runtime.engine.connect() as connection:
        operation_id = connection.execute(
            text("SELECT operation_id FROM hotlist_snapshots WHERE job_id=:job"), {"job": first}
        ).scalar_one()
        second_operation = connection.execute(
            text("SELECT operation_id FROM collection_due_windows WHERE job_id=:job"),
            {"job": second},
        ).scalar_one()

    def insert_snapshot(
        job_id: UUID, candidate_operation: UUID, source_key: str = "hotlist_weibo"
    ) -> None:
        with runtime.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO hotlist_snapshots "
                    "(id, owner_id, source_key, job_id, operation_id, observed_at, entry_count) "
                    "VALUES (:id, :owner, :source, :job, :operation, :observed, 0)"
                ),
                {
                    "id": uuid4(),
                    "owner": runtime.owner_id,
                    "source": source_key,
                    "job": job_id,
                    "operation": candidate_operation,
                    "observed": next_due + timedelta(minutes=3),
                },
            )

    with pytest.raises(IntegrityError) as duplicate:
        insert_snapshot(second, operation_id)
    assert duplicate.value.orig.diag.constraint_name == (
        "hotlist_snapshots_owner_source_operation_key"
    )
    with pytest.raises(IntegrityError) as wrong_operation:
        insert_snapshot(second, uuid4())
    assert wrong_operation.value.orig.diag.constraint_name == (
        "hotlist_snapshots_owner_due_identity_fkey"
    )
    with pytest.raises(IntegrityError) as wrong_source:
        insert_snapshot(second, second_operation, "hotlist_baidu")
    assert wrong_source.value.orig.diag.constraint_name == (
        "hotlist_snapshots_owner_due_identity_fkey"
    )
    with runtime.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM collection_due_windows WHERE job_id=:job"), {"job": second}
        )
    with pytest.raises(IntegrityError) as missing_due:
        insert_snapshot(second, second_operation)
    assert missing_due.value.orig.diag.constraint_name == (
        "hotlist_snapshots_owner_due_identity_fkey"
    )
