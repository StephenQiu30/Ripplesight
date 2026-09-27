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
from jobs.execution import (
    ExecutionLease,
    JobExecutionFailure,
    JobExecutionService,
    MessageReference,
)
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    JobAcceptedMessage,
)
from jobs.services import ResourceBudgetService
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
