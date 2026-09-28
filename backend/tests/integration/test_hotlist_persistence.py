from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from confluent_kafka import Consumer, Message
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from content import hotlist as hotlist_module
from content.hotlist import HotlistService
from content.hotlist_execution import HotlistExecutor
from core.config import Settings
from jobs.coverage import CollectionDueWindowService
from jobs.execution import (
    JobExecutionFailure,
    JobExecutionService,
    JobLeaseUnavailableError,
    MessageReference,
)
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    JobAcceptedMessage,
    JobMessage,
    JobRetryScheduledMessage,
    JobStatus,
)
from jobs.services import JobService, OutboxService, ResourceBudgetService
from sources.contracts import HotlistEntry, HotlistPage, SourcePageState, SourceStopReason
from worker import scheduler
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import create_producer, publish_outbox


@dataclass(frozen=True, slots=True)
class HotlistContext:
    engine: Engine
    sessions: sessionmaker[Session]
    owner_id: UUID
    due_at: datetime


@pytest.fixture
def hotlist_context() -> Iterator[HotlistContext]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    owner_id = uuid4()
    now = datetime.now(UTC)
    due_at = datetime.fromtimestamp((int(now.timestamp()) // 1800) * 1800, UTC)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE identity_users CASCADE"))
        connection.execute(
            text(
                "INSERT INTO identity_users "
                "(id, username, password_hash, credential_version, created_at, updated_at) "
                "VALUES (:id, 'hotlist-test-owner', 'test-only-hash', 1, :now, :now)"
            ),
            {"id": owner_id, "now": due_at - timedelta(seconds=1)},
        )
    with sessions.begin() as session:
        presets = SourcePresetService(session, clock=lambda: due_at - timedelta(seconds=1))
        presets.apply_in_transaction(owner_id=owner_id, preset=SOURCE_PRESETS["hotlist_weibo"])
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
    try:
        yield HotlistContext(engine, sessions, owner_id, due_at)
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
        engine.dispose()


def test_hotlist_scheduler_persists_one_due_fact_per_bucket(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(seconds=2)
            )
            == 1
        )
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(minutes=20)
            )
            == 0
        )
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.source_key, d.capability, d.due_at, d.operation_id, d.job_id, "
                "j.operation_id FROM collection_due_windows d "
                "JOIN jobs j ON j.id = d.job_id AND j.owner_id = d.owner_id "
                "WHERE d.owner_id = :owner_id"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert len(rows) == 1
    assert rows[0].source_key == "hotlist_weibo"
    assert rows[0].capability == "hotlist"
    assert rows[0].due_at == hotlist_context.due_at
    assert rows[0].operation_id == rows[0][5]
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(minutes=30, seconds=2)
            )
            == 1
        )
    with hotlist_context.engine.connect() as connection:
        due_rows = connection.execute(
            text(
                "SELECT due_at, operation_id FROM collection_due_windows "
                "WHERE owner_id=:owner_id ORDER BY due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert [row.due_at for row in due_rows] == [
        hotlist_context.due_at,
        hotlist_context.due_at + timedelta(minutes=30),
    ]
    assert due_rows[0].operation_id != due_rows[1].operation_id


def test_hotlist_first_scan_recovers_elapsed_buckets_without_inventing_jobs(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    current_due = due_at + timedelta(minutes=90)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, current_due + timedelta(seconds=2)
            )
            == 1
        )
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.due_at, d.admission_state, d.reason, d.job_id "
                "FROM collection_due_windows d "
                "WHERE d.owner_id=:owner_id ORDER BY d.due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 1
    assert [row.due_at for row in rows] == [
        due_at + timedelta(minutes=30 * index) for index in range(4)
    ]
    assert [(row.admission_state, row.reason, row.job_id) for row in rows[:3]] == [
        ("missed", "scheduler_interrupted", None)
    ] * 3
    assert rows[3].admission_state == "accepted"
    assert rows[3].job_id is not None
    with hotlist_context.sessions() as session:
        facts = CollectionDueWindowService(session).list_execution_facts(
            owner_id=hotlist_context.owner_id,
            start=due_at,
            end=current_due + timedelta(seconds=1),
        )
    assert len(facts) == 4
    assert all(fact.has_gap and fact.requests_sent is None for fact in facts[:3])
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, current_due + timedelta(seconds=20)
            )
            == 0
        )


def test_hotlist_recovery_starts_after_latest_connection_state_change(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    with hotlist_context.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE source_connections SET updated_at=:changed_at "
                "WHERE owner_id=:owner_id AND source_key='hotlist_weibo'"
            ),
            {
                "changed_at": due_at + timedelta(minutes=70),
                "owner_id": hotlist_context.owner_id,
            },
        )
    current_due = due_at + timedelta(minutes=90)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, current_due + timedelta(seconds=2)
            )
            == 1
        )
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT due_at, admission_state FROM collection_due_windows "
                "WHERE owner_id=:owner_id ORDER BY due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert [(row.due_at, row.admission_state) for row in rows] == [
        (due_at, "accepted"),
        (current_due, "accepted"),
    ]


def test_hotlist_interval_change_does_not_invent_old_cadence_buckets(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    interval = [1800]
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=interval[0])
    )
    due_at = hotlist_context.due_at
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    interval[0] = 3600
    later = due_at + timedelta(minutes=90, seconds=2)
    new_due = datetime.fromtimestamp((int(later.timestamp()) // 3600) * 3600, UTC)
    with hotlist_context.sessions.begin() as session:
        assert scheduler.enqueue_due_hotlists_in_transaction(session, later) == 1
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT due_at, window_end - window_start AS span FROM collection_due_windows "
                "WHERE owner_id=:owner_id ORDER BY due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert [(row.due_at, row.span) for row in rows] == [
        (due_at, timedelta(minutes=30)),
        (new_due, timedelta(hours=1)),
    ]


def test_six_hotlist_presets_each_keep_their_own_due_denominator(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    source_keys = {key for key in SOURCE_PRESETS if key.startswith("hotlist_")}
    assert len(source_keys) == 6
    with hotlist_context.sessions.begin() as session:
        service = SourcePresetService(session, clock=lambda: due_at - timedelta(seconds=1))
        for source_key in sorted(source_keys - {"hotlist_weibo"}):
            service.apply_in_transaction(
                owner_id=hotlist_context.owner_id, preset=SOURCE_PRESETS[source_key]
            )
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, due_at + timedelta(minutes=90, seconds=2)
            )
            == 6
        )
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT source_key, admission_state, count(*) AS total FROM collection_due_windows "
                "WHERE owner_id=:owner_id GROUP BY source_key, admission_state"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
        job_count = connection.execute(text("SELECT count(*) FROM jobs")).scalar_one()
        outbox_count = connection.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one()
    assert {(row.source_key, row.admission_state): row.total for row in rows} == {
        (source_key, state): count
        for source_key in source_keys
        for state, count in (("missed", 3), ("accepted", 1))
    }
    assert (job_count, outbox_count) == (6, 6)


def test_hotlist_schedule_rolls_back_due_job_and_outbox_together(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    with (
        pytest.raises(RuntimeError, match="controlled rollback"),
        hotlist_context.sessions.begin() as session,
    ):
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(seconds=2)
            )
            == 1
        )
        raise RuntimeError("controlled rollback")
    with hotlist_context.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM collection_due_windows")).scalar_one()
            == 0
        )
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 0
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(seconds=2)
            )
            == 1
        )


def _accepted_job(context: HotlistContext, due_at: datetime) -> tuple[UUID, JobMessage]:
    with context.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT j.id, o.id, o.event_type, o.payload FROM jobs j "
                "JOIN outbox_messages o ON o.aggregate_id=j.id "
                "WHERE j.owner_id=:owner_id AND j.scheduled_for_at=:due_at "
                "ORDER BY o.dispatch_sequence DESC LIMIT 1"
            ),
            {"owner_id": context.owner_id, "due_at": due_at},
        ).one()
    message_type = (
        JobAcceptedMessage if row.event_type == "job.accepted.v2" else JobRetryScheduledMessage
    )
    return row[0], message_type.model_validate(
        {
            "schema_version": 2 if message_type is JobAcceptedMessage else 1,
            "message_id": row[1],
            "event_type": row.event_type,
            **row.payload,
        }
    )


def _run_page(
    context: HotlistContext,
    *,
    due_at: datetime,
    page: HotlistPage,
) -> tuple[UUID, JobStatus]:
    job_id, message = _accepted_job(context, due_at)

    def clock() -> datetime:
        return page.observed_at

    with context.sessions() as session:
        lease = JobExecutionService(session, lease_seconds=60, clock=clock).acquire(
            job_id=job_id, worker_id="hotlist-test-worker"
        )

    class PageAdapter:
        def __init__(self, before_request: Callable[[int], bool]) -> None:
            self._before_request = before_request

        def fetch_hotlist(self) -> HotlistPage:
            assert self._before_request(1) is True
            return page

    executor = HotlistExecutor(
        context.sessions,
        lease_seconds=60,
        clock=clock,
        adapter_factory=lambda _source, _url, _hosts, before, _cancel: PageAdapter(before),
    )
    reference = MessageReference(
        message_id=message.message_id,
        topic="hotkey.jobs.accepted.v2",
        partition=0,
        offset=(job_id.int % (2**60))
        + (message.dispatch_sequence if isinstance(message, JobRetryScheduledMessage) else 1),
    )
    try:
        renewed, completion = executor.execute(message, lease)
    except JobExecutionFailure as failure:
        with context.sessions() as session:
            JobExecutionService(session, lease_seconds=60, clock=clock).record_failure(
                lease, message=reference, failure=failure
            )
        return job_id, JobStatus.FAILED
    with context.sessions() as session:
        JobExecutionService(session, lease_seconds=60, clock=clock).complete(
            renewed,
            message=reference,
            completion=completion,
        )
    return job_id, completion.status


def test_successful_empty_feed_saves_original_due_and_real_zero(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    observed_at = due_at + timedelta(seconds=5)
    with hotlist_context.sessions.begin() as session:
        assert scheduler.enqueue_due_hotlists_in_transaction(session, observed_at) == 1
    job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=HotlistPage(
            source_key="hotlist_weibo",
            state=SourcePageState.EMPTY,
            items=(),
            stop_reason=SourceStopReason.SOURCE_EMPTY,
            observed_at=observed_at,
            request_count=1,
            adapter_version="controlled-hotlist-1",
        ),
    )
    assert status is JobStatus.SUCCEEDED
    with hotlist_context.engine.connect() as connection:
        snapshot = connection.execute(
            text(
                "SELECT s.id, s.entry_count, s.observed_at, s.operation_id, "
                "d.operation_id, d.due_at FROM hotlist_snapshots s "
                "JOIN collection_due_windows d ON d.id=s.due_window_id "
                "WHERE s.job_id=:job_id"
            ),
            {"job_id": job_id},
        ).one()
        usage = connection.execute(
            text(
                "SELECT outcome FROM resource_usage_attempts "
                "WHERE owner_id=:owner_id AND operation_id=:operation_id"
            ),
            {"owner_id": hotlist_context.owner_id, "operation_id": snapshot[3]},
        ).scalar_one()
    assert (snapshot.entry_count, snapshot.observed_at, snapshot.due_at) == (0, observed_at, due_at)
    assert snapshot.operation_id == snapshot[4]
    assert usage == "empty"
    with hotlist_context.sessions() as session:
        view = HotlistService(session).get_latest(
            owner_id=hotlist_context.owner_id, source_key="hotlist_weibo"
        )
        facts = CollectionDueWindowService(session).list_execution_facts(
            owner_id=hotlist_context.owner_id,
            start=due_at,
            end=due_at + timedelta(seconds=1),
        )
    assert view.entry_count == 0
    assert view.items == ()
    assert view.operation_id == snapshot.operation_id
    assert view.due_at == due_at
    assert len(facts) == 1
    assert facts[0].observed_count == 0
    assert facts[0].page_count == 1
    assert facts[0].has_gap is False


def _page(
    observed_at: datetime,
    *,
    state: SourcePageState,
    reason: SourceStopReason,
    items: tuple[HotlistEntry, ...] = (),
) -> HotlistPage:
    return HotlistPage(
        source_key="hotlist_weibo",
        state=state,
        items=items,
        stop_reason=reason,
        observed_at=observed_at,
        request_count=1,
        adapter_version="controlled-hotlist-1",
    )


@pytest.mark.parametrize(
    ("reason", "error_code"),
    [
        (SourceStopReason.UPSTREAM_ERROR, "hotlist_upstream_error"),
        (SourceStopReason.PROTOCOL_ERROR, "hotlist_protocol_error"),
        (SourceStopReason.ACCESS_DENIED, "hotlist_access_denied"),
        (SourceStopReason.RATE_LIMITED, "hotlist_rate_limited"),
    ],
)
def test_failed_bucket_has_no_empty_snapshot_and_next_bucket_keeps_its_gap(
    hotlist_context: HotlistContext,
    monkeypatch: pytest.MonkeyPatch,
    reason: SourceStopReason,
    error_code: str,
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    next_due = due_at + timedelta(minutes=30)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    failed_job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(due_at + timedelta(seconds=5), state=SourcePageState.STOPPED, reason=reason),
    )
    assert status is JobStatus.FAILED
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, next_due + timedelta(seconds=2))
            == 1
        )
    recovered_job_id, status = _run_page(
        hotlist_context,
        due_at=next_due,
        page=_page(
            next_due + timedelta(seconds=5),
            state=SourcePageState.COMPLETE,
            reason=SourceStopReason.END_OF_RESULTS,
            items=(HotlistEntry(rank=1, title="New", url="https://example.com/new"),),
        ),
    )
    assert status is JobStatus.SUCCEEDED
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.due_at, j.id, j.status, j.last_error_code, s.id AS snapshot_id, "
                "s.entry_count FROM collection_due_windows d "
                "JOIN jobs j ON j.id=d.job_id LEFT JOIN hotlist_snapshots s "
                "ON s.due_window_id=d.id WHERE d.owner_id=:owner_id ORDER BY d.due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert len(rows) == 2
    assert (rows[0].due_at, rows[0].id, rows[0].status, rows[0].last_error_code) == (
        due_at,
        failed_job_id,
        "failed",
        error_code,
    )
    assert rows[0].snapshot_id is None
    assert (rows[1].due_at, rows[1].id, rows[1].status, rows[1].entry_count) == (
        next_due,
        recovered_job_id,
        "succeeded",
        1,
    )
    with hotlist_context.sessions() as session:
        facts = CollectionDueWindowService(session).list_execution_facts(
            owner_id=hotlist_context.owner_id,
            start=due_at,
            end=next_due + timedelta(seconds=1),
        )
    assert [(fact.has_gap, fact.page_count, fact.observed_count) for fact in facts] == [
        (True, 0, None),
        (False, 1, 1),
    ]
    assert facts[0].stop_reason == error_code


def test_manual_retry_keeps_original_due_and_replay_cannot_duplicate_snapshot(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(
            due_at + timedelta(seconds=5),
            state=SourcePageState.STOPPED,
            reason=SourceStopReason.PROTOCOL_ERROR,
        ),
    )
    assert status is JobStatus.FAILED
    with hotlist_context.sessions() as session:
        queued = JobService(session, clock=lambda: due_at + timedelta(seconds=10)).request_retry(
            owner_id=hotlist_context.owner_id, job_id=job_id
        )
    assert queued.status.value == JobStatus.QUEUED.value
    with hotlist_context.sessions() as session:
        repeated = JobService(session, clock=lambda: due_at + timedelta(seconds=11)).request_retry(
            owner_id=hotlist_context.owner_id, job_id=job_id
        )
    assert repeated.status.value == JobStatus.QUEUED.value
    retried_job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(
            due_at + timedelta(seconds=12),
            state=SourcePageState.EMPTY,
            reason=SourceStopReason.SOURCE_EMPTY,
        ),
    )
    assert retried_job_id == job_id
    with hotlist_context.engine.connect() as connection:
        retry_error = connection.execute(
            text("SELECT last_error_code FROM jobs WHERE id=:job_id"), {"job_id": job_id}
        ).scalar_one()
    assert status is JobStatus.SUCCEEDED, retry_error
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT s.operation_id, d.operation_id, s.observed_at, d.due_at, "
                "j.collection_cycle_no FROM hotlist_snapshots s "
                "JOIN collection_due_windows d ON d.id=s.due_window_id "
                "JOIN jobs j ON j.id=s.job_id WHERE s.job_id=:job_id"
            ),
            {"job_id": job_id},
        ).all()
        outbox_count = connection.execute(
            text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job_id"),
            {"job_id": job_id},
        ).scalar_one()
    assert len(rows) == 1
    assert (rows[0][0], rows[0][1], rows[0].observed_at, rows[0].due_at) == (
        rows[0][0],
        rows[0][0],
        due_at + timedelta(seconds=12),
        due_at,
    )
    assert rows[0].collection_cycle_no == 2
    assert outbox_count == 2
    with hotlist_context.sessions() as session, pytest.raises(JobLeaseUnavailableError):
        JobExecutionService(
            session, lease_seconds=60, clock=lambda: due_at + timedelta(seconds=13)
        ).acquire(job_id=job_id, worker_id="duplicate-worker")
    with hotlist_context.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM hotlist_snapshots WHERE job_id=:job_id"),
                {"job_id": job_id},
            ).scalar_one()
            == 1
        )


def test_mid_entry_failure_rolls_back_snapshot_and_entries(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    original = hotlist_module.HotlistEntryRecord
    calls = 0

    def make_entry(**kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled mid-entry persistence fault")
        return original(**kwargs)

    monkeypatch.setattr(hotlist_module, "HotlistEntryRecord", make_entry)
    job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(
            due_at + timedelta(seconds=5),
            state=SourcePageState.COMPLETE,
            reason=SourceStopReason.END_OF_RESULTS,
            items=(
                HotlistEntry(rank=1, title="One", url="https://example.com/one"),
                HotlistEntry(rank=2, title="Two", url="https://example.com/two"),
            ),
        ),
    )
    assert status is JobStatus.FAILED
    with hotlist_context.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM hotlist_snapshots WHERE job_id=:job_id"),
                {"job_id": job_id},
            ).scalar_one()
            == 0
        )
        assert connection.execute(text("SELECT count(*) FROM hotlist_entries")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT last_error_code FROM jobs WHERE id=:job_id"), {"job_id": job_id}
            ).scalar_one()
            == "hotlist_processing_failed"
        )


def test_late_retry_keeps_old_due_while_newer_bucket_has_its_own_snapshot(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    next_due = due_at + timedelta(minutes=30)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    first_job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(
            due_at + timedelta(seconds=5),
            state=SourcePageState.STOPPED,
            reason=SourceStopReason.UPSTREAM_ERROR,
        ),
    )
    assert status is JobStatus.FAILED
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, next_due + timedelta(seconds=2))
            == 1
        )
    next_job_id, status = _run_page(
        hotlist_context,
        due_at=next_due,
        page=_page(
            next_due + timedelta(seconds=5),
            state=SourcePageState.EMPTY,
            reason=SourceStopReason.SOURCE_EMPTY,
        ),
    )
    assert status is JobStatus.SUCCEEDED
    with hotlist_context.sessions() as session:
        JobService(session, clock=lambda: next_due + timedelta(seconds=10)).request_retry(
            owner_id=hotlist_context.owner_id, job_id=first_job_id
        )
    retried_job_id, status = _run_page(
        hotlist_context,
        due_at=due_at,
        page=_page(
            next_due + timedelta(seconds=12),
            state=SourcePageState.COMPLETE,
            reason=SourceStopReason.END_OF_RESULTS,
            items=(HotlistEntry(rank=1, title="Late", url="https://example.com/late"),),
        ),
    )
    assert (retried_job_id, status) == (first_job_id, JobStatus.SUCCEEDED)
    with hotlist_context.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT s.job_id, s.observed_at, d.due_at, s.entry_count FROM hotlist_snapshots s "
                "JOIN collection_due_windows d ON d.id=s.due_window_id "
                "WHERE s.owner_id=:owner_id ORDER BY d.due_at"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).all()
    assert [(row.job_id, row.due_at, row.entry_count) for row in rows] == [
        (first_job_id, due_at, 1),
        (next_job_id, next_due, 0),
    ]
    assert rows[0].observed_at == next_due + timedelta(seconds=12)
    assert rows[1].observed_at == next_due + timedelta(seconds=5)


def test_real_kafka_hotlist_redelivery_keeps_one_empty_snapshot(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if bootstrap is None or database_url is None:
        pytest.skip("PostgreSQL and Kafka integration endpoints are required")
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    due_at = hotlist_context.due_at
    observed_at = due_at + timedelta(seconds=5)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, due_at + timedelta(seconds=2))
            == 1
        )
    job_id, _ = _accepted_job(hotlist_context, due_at)
    topic = f"hotkey.tests.hotlist.{uuid4().hex}"
    group_id = f"hotkey-tests-hotlist-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])[topic].result(10)
    with hotlist_context.engine.begin() as connection:
        connection.execute(
            text("UPDATE outbox_messages SET topic=:topic WHERE aggregate_id=:job_id"),
            {"topic": topic, "job_id": job_id},
        )

    def consumer() -> Consumer:
        return Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": group_id,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
                "session.timeout.ms": 6_000,
            }
        )

    def receive(target: Consumer) -> Message:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = target.poll(0.2)
            if message is None:
                continue
            if message.error() is not None:
                raise RuntimeError(str(message.error()))
            return message
        raise AssertionError("hotlist Kafka message was not received")

    class EmptyAdapter:
        def __init__(self, before_request: Callable[[int], bool]) -> None:
            self._before_request = before_request

        def fetch_hotlist(self) -> HotlistPage:
            assert self._before_request(1) is True
            return _page(
                observed_at,
                state=SourcePageState.EMPTY,
                reason=SourceStopReason.SOURCE_EMPTY,
            )

    executor = HotlistExecutor(
        hotlist_context.sessions,
        lease_seconds=60,
        clock=lambda: observed_at,
        adapter_factory=lambda _source, _url, _hosts, before, _cancel: EmptyAdapter(before),
    )

    def collect(context: JobExecutionContext):
        context.lease, completion = executor.execute(context.message, context.lease)
        return completion

    handler = create_job_message_handler(
        hotlist_context.sessions,
        {"source.hotlist": collect},
        worker_id="hotlist-kafka-test-worker",
        lease_seconds=60,
        clock=lambda: observed_at,
    )
    first = consumer()
    second: Consumer | None = None
    try:
        producer = create_producer(
            Settings(
                database_url=database_url,
                kafka_bootstrap_servers=bootstrap,
                kafka_delivery_timeout_seconds=10,
            )
        )
        with hotlist_context.sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(producer, envelope, timeout_seconds=10),
                    published_at=due_at + timedelta(seconds=2),
                )
                == 1
            )
        first.subscribe([topic])
        delivered = receive(first)
        handler(delivered)
        first.close()  # The offset remains uncommitted, so the next consumer receives it again.
        second = consumer()
        second.subscribe([topic])
        replay = receive(second)
        assert replay.offset() == delivered.offset()
        handler(replay)
        second.commit(message=replay, asynchronous=False)
    finally:
        first.close()
        if second is not None:
            second.close()
        with suppress(Exception):
            admin.delete_topics([topic], operation_timeout=10)[topic].result(10)
    with hotlist_context.engine.connect() as connection:
        snapshot_count = connection.execute(
            text("SELECT count(*) FROM hotlist_snapshots WHERE job_id=:job_id"),
            {"job_id": job_id},
        ).scalar_one()
        usage_count = connection.execute(
            text(
                "SELECT count(*) FROM resource_usage_attempts "
                "WHERE owner_id=:owner_id AND usage_kind='network_request'"
            ),
            {"owner_id": hotlist_context.owner_id},
        ).scalar_one()
        processed_count = connection.execute(
            text("SELECT count(*) FROM processed_messages WHERE job_id=:job_id"),
            {"job_id": job_id},
        ).scalar_one()
    assert (snapshot_count, usage_count, processed_count) == (1, 1, 1)
