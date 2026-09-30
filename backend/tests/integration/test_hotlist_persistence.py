from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType, SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import TEST_DATABASE_TRUNCATE

from connections import services as connection_services
from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from content import hotlist as hotlist_module
from content.hotlist import HotlistService
from content.hotlist_execution import HotlistExecutor
from content.services import ContentService, load_post_versions_for_analysis_scan
from core.errors import ApplicationError
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService
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
def runtime(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[HotlistRuntime]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    owner_id = uuid4()
    current = datetime.now(UTC)
    due_at = datetime.fromtimestamp(int(current.timestamp()) // 1800 * 1800, UTC)
    with engine.begin() as connection:
        connection.execute(text(TEST_DATABASE_TRUNCATE))
    with sessions.begin() as session:
        service = SourcePresetService(session, clock=lambda: due_at - timedelta(seconds=1))
        preset = SOURCE_PRESETS["hotlist_weibo"]
        host = getattr(request, "param", "127.0.0.1")
        if host != "127.0.0.1":
            preset = replace(
                preset,
                config=MappingProxyType(
                    {
                        "feed_url": f"http://{host}:1200/weibo/search/hot",
                        "allowed_hosts": (host,),
                    }
                ),
            )
            monkeypatch.setattr(
                connection_services,
                "SOURCE_PRESETS",
                MappingProxyType({**SOURCE_PRESETS, "hotlist_weibo": preset}),
            )
        service.apply_in_transaction(owner_id=owner_id, preset=preset)
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
            connection.execute(text(TEST_DATABASE_TRUNCATE))
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


def _ranked_page(observed_at: datetime, items: tuple[HotlistEntry, ...]) -> HotlistPage:
    return HotlistPage(
        source_key="hotlist_weibo",
        state=SourcePageState.COMPLETE,
        items=items,
        stop_reason=SourceStopReason.END_OF_RESULTS,
        observed_at=observed_at,
        request_count=1,
        adapter_version="controlled-v1",
    )


def _add_active_topics(
    runtime: HotlistRuntime, names_and_terms: tuple[tuple[str, str], ...]
) -> tuple[UUID, ...]:
    topic_ids = tuple(uuid4() for _ in names_and_terms)
    with runtime.engine.begin() as connection:
        for topic_id, (name, term) in zip(topic_ids, names_and_terms, strict=True):
            connection.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, :name, 'active', 'ready', 1, :now, :now)"
                ),
                {
                    "id": topic_id,
                    "owner_id": runtime.owner_id,
                    "name": name,
                    "now": runtime.due_at - timedelta(seconds=1),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, "
                    "created_at) VALUES "
                    "(:id, 1, :owner_id, CAST(:terms AS jsonb), '[]', '[]', :now)"
                ),
                {
                    "id": topic_id,
                    "owner_id": runtime.owner_id,
                    "terms": json.dumps([term]),
                    "now": runtime.due_at - timedelta(seconds=1),
                },
            )
    return topic_ids


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


@pytest.mark.parametrize("runtime", ["host.docker.internal"], indirect=True)
def test_container_rsshub_endpoint_reaches_hotlist_executor(runtime: HotlistRuntime) -> None:
    job_id = _accept(runtime, runtime.due_at)
    _execute(runtime, job_id, _page(runtime.due_at + timedelta(minutes=2), entries=1))
    with runtime.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT entry_count FROM hotlist_snapshots WHERE job_id=:job"),
                {"job": job_id},
            ).scalar_one()
            == 1
        )


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
    assert (latest.items[0].previous_rank, latest.items[0].rank_delta) == (None, None)


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


def test_hotlist_match_persists_one_content_for_two_topics_and_skips_unmatched(
    runtime: HotlistRuntime,
) -> None:
    ai_topic, chip_topic = _add_active_topics(runtime, (("AI topic", "AI"), ("Chip topic", "chip")))
    job_id = _accept(runtime, runtime.due_at)
    page = _ranked_page(
        runtime.due_at + timedelta(minutes=2),
        (
            HotlistEntry(
                rank=1,
                title="New AI chip",
                url="https://example.com/chip",
                summary=None,
            ),
            HotlistEntry(
                rank=2,
                title="daily bulletin",
                url="https://example.com/daily",
                summary=None,
            ),
        ),
    )
    renewed = _execute(runtime, job_id, page)
    replayed, completion = _executor(runtime, page).execute(_message(runtime, job_id), renewed)
    assert replayed == renewed
    assert completion.status.value == "succeeded"

    with runtime.engine.connect() as connection:
        entries = connection.execute(
            text(
                "SELECT rank, content_id, matched_topic_names, matched_topic_ids "
                "FROM hotlist_entries ORDER BY rank"
            )
        ).all()
        records = connection.execute(
            text("SELECT id, source_key, external_id FROM content_records")
        ).all()
        discoveries = connection.execute(
            text("SELECT content_id, job_id FROM content_discoveries")
        ).all()
        observations = connection.execute(
            text("SELECT content_id, job_id FROM content_observations")
        ).all()
        snapshots = connection.execute(
            text("SELECT job_id, entry_count FROM hotlist_snapshots")
        ).all()
    assert len(entries) == 2
    assert entries[0].rank == 1
    assert set(entries[0].matched_topic_names) == {"AI topic", "Chip topic"}
    assert set(entries[0].matched_topic_ids) == {str(ai_topic), str(chip_topic)}
    assert (entries[1].rank, entries[1].content_id, entries[1].matched_topic_ids) == (2, None, [])
    assert len(records) == len(discoveries) == len(observations) == 1
    assert records[0].id == entries[0].content_id == discoveries[0].content_id
    assert observations[0].content_id == records[0].id
    assert discoveries[0].job_id == observations[0].job_id == job_id
    assert (records[0].source_key, records[0].external_id) == (
        "hotlist_weibo",
        "https://example.com/chip",
    )
    assert snapshots == [(job_id, 2)]
    with runtime.sessions() as session:
        service = ContentService(session, clock=lambda: page.observed_at)
        for topic_id in (ai_topic, chip_topic):
            visible, cursor = service.list_contents(
                owner_id=runtime.owner_id, topic_id=topic_id, cursor=None, limit=1
            )
            assert [item.id for item in visible] == [records[0].id]
            assert cursor is None
        detail = service.get_content(owner_id=runtime.owner_id, content_id=records[0].id)
        assert {item.topic_id for item in detail.analysis_topics} == {ai_topic, chip_topic}


def test_analysis_scan_excludes_expired_hotlist_evidence(runtime: HotlistRuntime) -> None:
    (topic_id,) = _add_active_topics(runtime, (("AI topic", "AI"),))
    job_id = _accept(runtime, runtime.due_at)
    _execute(
        runtime,
        job_id,
        _ranked_page(
            runtime.due_at + timedelta(minutes=2),
            (HotlistEntry(rank=1, title="AI news", url="https://example.com/expired"),),
        ),
    )
    with runtime.sessions.begin() as session:
        expiry = session.scalar(text("SELECT max(expires_at) FROM evidence_resources"))
        historical = load_post_versions_for_analysis_scan(
            session,
            owner_id=runtime.owner_id,
            topic_id=topic_id,
            source_keys=(),
        )
        assert len(historical) == 1
        assert (
            load_post_versions_for_analysis_scan(
                session,
                owner_id=runtime.owner_id,
                topic_id=topic_id,
                source_keys=(),
                readable_at=expiry,
            )
            == ()
        )


@pytest.mark.parametrize("mode", ["expired", "deleted"])
def test_old_hotlist_match_cannot_borrow_new_readable_observation(
    runtime: HotlistRuntime, mode: str
) -> None:
    ai_topic, chip_topic = _add_active_topics(runtime, (("AI", "AI"), ("Chip", "chip")))
    first = _accept(runtime, runtime.due_at)
    _execute(
        runtime,
        first,
        _ranked_page(
            runtime.due_at + timedelta(minutes=2),
            (HotlistEntry(rank=1, title="AI news", url="https://example.com/changed"),),
        ),
    )
    next_due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, next_due)
    now = next_due + timedelta(minutes=2)
    _execute(
        runtime,
        second,
        _ranked_page(
            now,
            (
                HotlistEntry(rank=1, title="chip news", url="https://example.com/changed"),
                HotlistEntry(rank=2, title="chip extra", url="https://example.com/extra"),
            ),
        ),
    )
    with runtime.sessions() as session:
        old_id, content_id = session.execute(
            text("SELECT id, content_id FROM content_observations WHERE job_id=:job"),
            {"job": first},
        ).one()
        session.rollback()
        if mode == "deleted":
            LifecycleService(session, clock=lambda: now).request_deletion(
                owner_id=runtime.owner_id,
                operation_id=uuid4(),
                resource_type="content_observation",
                resource_id=old_id,
                reason=DeletionReason.USER_REQUEST,
            )
        else:
            with session.begin():
                session.execute(
                    text("UPDATE evidence_resources SET expires_at=:now WHERE resource_id=:id"),
                    {"now": now, "id": old_id},
                )
        service = ContentService(session, clock=lambda: now)
        assert service.list_contents(
            owner_id=runtime.owner_id, topic_id=ai_topic, cursor=None, limit=1
        ) == ([], None)
        seen = []
        cursor = None
        for _ in range(2):
            page, cursor = service.list_contents(
                owner_id=runtime.owner_id, topic_id=chip_topic, cursor=cursor, limit=1
            )
            assert len(page) == 1
            seen.append(page[0].id)
        assert len(set(seen)) == 2 and content_id in seen and cursor is None
        detail = service.get_content(owner_id=runtime.owner_id, content_id=content_id)
        assert {topic.topic_id for topic in detail.analysis_topics} == {chip_topic}
        with session.begin():
            assert (
                load_post_versions_for_analysis_scan(
                    session,
                    owner_id=runtime.owner_id,
                    topic_id=ai_topic,
                    source_keys=(),
                    readable_at=now,
                )
                == ()
            )
        with pytest.raises(ApplicationError):
            service.get_content(owner_id=uuid4(), content_id=content_id)


def test_repeated_url_keeps_feed_ranks_and_one_content_observation(
    runtime: HotlistRuntime,
) -> None:
    _add_active_topics(runtime, (("AI topic", "AI"),))
    job_id = _accept(runtime, runtime.due_at)
    page = _ranked_page(
        runtime.due_at + timedelta(minutes=2),
        (
            HotlistEntry(rank=1, title="AI first", url="https://example.com/story?item=3"),
            HotlistEntry(
                rank=2,
                title="AI duplicate",
                url="https://EXAMPLE.com/story?item=3&utm_source=feed#top",
            ),
        ),
    )
    _execute(runtime, job_id, page)
    with runtime.engine.connect() as connection:
        entries = connection.execute(
            text("SELECT rank, content_id FROM hotlist_entries ORDER BY rank")
        ).all()
        records = connection.execute(text("SELECT count(*) FROM content_records")).scalar_one()
        discoveries = connection.execute(
            text("SELECT count(*) FROM content_discoveries")
        ).scalar_one()
        observations = connection.execute(
            text("SELECT count(*) FROM content_observations")
        ).scalar_one()
    assert [row.rank for row in entries] == [1, 2]
    assert entries[0].content_id == entries[1].content_id
    assert records == discoveries == observations == 1

    next_due = runtime.due_at + timedelta(minutes=30)
    second_job = _accept(runtime, next_due)
    second_page = _ranked_page(
        next_due + timedelta(minutes=2),
        (
            HotlistEntry(rank=1, title="Other", url="https://example.com/other"),
            HotlistEntry(rank=2, title="AI story", url="https://example.com/story?item=3"),
        ),
    )
    _execute(runtime, second_job, second_page)
    with runtime.sessions() as session:
        latest = HotlistService(session).get_latest(
            owner_id=runtime.owner_id, source_key="hotlist_weibo"
        )
    assert (latest.items[1].previous_rank, latest.items[1].rank_delta) == (1, -1)
    assert latest.items[1].rank_change == "down"


def test_same_url_on_two_hotlists_keeps_distinct_source_identities(
    runtime: HotlistRuntime,
) -> None:
    _add_active_topics(runtime, (("AI topic", "AI"),))
    first_job = _accept(runtime, runtime.due_at)
    entry = HotlistEntry(rank=1, title="AI story", url="https://example.com/story?item=3")
    _execute(runtime, first_job, _ranked_page(runtime.due_at + timedelta(minutes=2), (entry,)))

    with runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=runtime.owner_id, preset=SOURCE_PRESETS["hotlist_baidu"]
        )
    next_due = runtime.due_at + timedelta(minutes=30)
    with runtime.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(session, next_due + timedelta(seconds=2))
            == 2
        )
    with runtime.engine.connect() as connection:
        second_job = connection.execute(
            text(
                "SELECT job_id FROM collection_due_windows "
                "WHERE source_key='hotlist_baidu' AND due_at=:due"
            ),
            {"due": next_due},
        ).scalar_one()
    baidu_page = HotlistPage(
        source_key="hotlist_baidu",
        state=SourcePageState.COMPLETE,
        items=(entry,),
        stop_reason=SourceStopReason.END_OF_RESULTS,
        observed_at=next_due + timedelta(minutes=2),
        request_count=1,
        adapter_version="controlled-v1",
    )
    _execute(runtime, second_job, baidu_page)

    with runtime.engine.connect() as connection:
        records = connection.execute(
            text("SELECT id, source_key, external_id FROM content_records ORDER BY source_key")
        ).all()
    assert [(record.source_key, record.external_id) for record in records] == [
        ("hotlist_baidu", "https://example.com/story?item=3"),
        ("hotlist_weibo", "https://example.com/story?item=3"),
    ]
    assert records[0].id != records[1].id


def test_equivalent_hotlist_urls_keep_content_identity_and_previous_rank(
    runtime: HotlistRuntime,
) -> None:
    _add_active_topics(runtime, (("AI topic", "AI"),))
    first_job = _accept(runtime, runtime.due_at)
    first_page = _ranked_page(
        runtime.due_at + timedelta(minutes=2),
        (
            HotlistEntry(rank=1, title="Unrelated", url="https://example.com/other"),
            HotlistEntry(
                rank=2,
                title="AI story",
                url="https://example.com/article?article=7&utm_source=rss#top",
            ),
        ),
    )
    _execute(runtime, first_job, first_page)
    next_due = runtime.due_at + timedelta(minutes=30)
    second_job = _accept(runtime, next_due)
    second_page = _ranked_page(
        next_due + timedelta(minutes=2),
        (
            HotlistEntry(
                rank=1,
                title="AI story",
                url="https://EXAMPLE.com/article?article=7",
            ),
            HotlistEntry(rank=2, title="Unrelated", url="https://example.com/other"),
        ),
    )
    renewed = _execute(runtime, second_job, second_page)
    replayed, completion = _executor(runtime, second_page).execute(
        _message(runtime, second_job), renewed
    )
    assert replayed == renewed
    assert completion.status.value == "succeeded"

    with runtime.sessions() as session:
        latest = HotlistService(session).get_latest(
            owner_id=runtime.owner_id, source_key="hotlist_weibo"
        )
    assert (latest.due_at, latest.entry_count) == (next_due, 2)
    assert (latest.items[0].rank, latest.items[0].rank_change) == (1, "up")
    assert (latest.items[0].previous_rank, latest.items[0].rank_delta) == (2, 1)
    assert latest.items[1].rank_change == "down"
    assert (latest.items[1].previous_rank, latest.items[1].rank_delta) == (1, -1)

    with runtime.engine.connect() as connection:
        entries = connection.execute(
            text(
                "SELECT s.job_id, e.rank, e.content_id FROM hotlist_entries e "
                "JOIN hotlist_snapshots s ON s.id=e.snapshot_id "
                "WHERE e.content_id IS NOT NULL ORDER BY s.observed_at"
            )
        ).all()
        records = connection.execute(text("SELECT id, external_id FROM content_records")).all()
        discoveries = connection.execute(
            text("SELECT content_id, job_id FROM content_discoveries ORDER BY job_id")
        ).all()
        observations = connection.execute(
            text("SELECT content_id, job_id FROM content_observations ORDER BY job_id")
        ).all()
    assert [(item.job_id, item.rank) for item in entries] == [(first_job, 2), (second_job, 1)]
    assert len(records) == 1
    assert records[0].external_id == "https://example.com/article?article=7"
    assert entries[0].content_id == entries[1].content_id == records[0].id
    assert {item.job_id for item in discoveries} == {first_job, second_job}
    assert {item.job_id for item in observations} == {first_job, second_job}
    assert len(discoveries) == len(observations) == 2
    assert {item.content_id for item in discoveries + observations} == {records[0].id}


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
    _add_active_topics(runtime, (("Entry topic", "Entry"),))
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
        assert connection.execute(text("SELECT count(*) FROM content_records")).scalar_one() == 0
        assert (
            connection.execute(text("SELECT count(*) FROM content_discoveries")).scalar_one() == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM content_observations")).scalar_one() == 0
        )
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
