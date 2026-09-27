from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.integration.test_hotlist_persistence import (
    HotlistRuntime,
    _accept,
    _acquire,
    _execute,
    _executor,
    _message,
    _page,
    _ranked_page,
)

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from content.hotlist import HotlistService
from core.errors import ApplicationError
from jobs.execution import JobExecutionFailure, JobExecutionService, MessageReference
from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
from jobs.services import ResourceBudgetService
from sources.contracts import HotlistEntry, HotlistPage, SourcePageState, SourceStopReason
from worker import scheduler


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
                "VALUES (:id, 'hotlist-query-test', 'test-only-hash', 1, :created, :created)"
            ),
            {"id": owner_id, "created": due_at - timedelta(seconds=1)},
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
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    try:
        yield HotlistRuntime(engine, sessions, owner_id, due_at)
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
        engine.dispose()


def test_history_cursor_and_fixed_snapshot_entries_survive_newer_insert(
    runtime: HotlistRuntime,
) -> None:
    first_job = _accept(runtime, runtime.due_at)
    _execute(
        runtime,
        first_job,
        _ranked_page(
            runtime.due_at + timedelta(minutes=2),
            (HotlistEntry(rank=1, title="AI story", url="https://example.com/one"),),
        ),
    )
    second_due = runtime.due_at + timedelta(minutes=30)
    second_job = _accept(runtime, second_due)
    _execute(
        runtime,
        second_job,
        _ranked_page(
            second_due + timedelta(minutes=2),
            (
                HotlistEntry(rank=1, title="Second", url="https://example.com/two"),
                HotlistEntry(rank=2, title="AI story", url="https://example.com/one"),
            ),
        ),
    )
    with runtime.sessions() as session:
        service = HotlistService(session)
        first_page, cursor = service.list_history(
            owner_id=runtime.owner_id, source_key="hotlist_weibo", limit=1
        )
    assert len(first_page) == 1
    assert cursor == str(first_page[0].snapshot_id)
    assert first_page[0].previous_snapshot_id is not None

    third_due = second_due + timedelta(minutes=30)
    third_job = _accept(runtime, third_due)
    _execute(runtime, third_job, _page(third_due + timedelta(minutes=2)))
    with runtime.sessions() as session:
        service = HotlistService(session)
        older_page, next_cursor = service.list_history(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            cursor=first_page[0].snapshot_id,
            limit=1,
        )
        fixed = service.get_historical(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            snapshot_id=first_page[0].snapshot_id,
            limit=1,
        )
        fixed_next = service.get_historical(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            snapshot_id=first_page[0].snapshot_id,
            cursor=fixed.next_cursor,
            limit=1,
        )
    assert len(older_page) == 1
    assert older_page[0].snapshot_id == first_page[0].previous_snapshot_id
    assert next_cursor is None
    assert fixed.entry_count == 2
    assert fixed.previous_snapshot_id == older_page[0].snapshot_id
    assert [(item.rank, item.rank_change) for item in fixed.items] == [(1, "new")]
    assert [(item.rank, item.previous_rank, item.rank_delta) for item in fixed_next.items] == [
        (2, 1, -1)
    ]


def test_empty_snapshot_is_in_history_and_cursor_is_source_owner_scoped(
    runtime: HotlistRuntime,
) -> None:
    job = _accept(runtime, runtime.due_at)
    _execute(runtime, job, _page(runtime.due_at + timedelta(minutes=2)))
    with runtime.sessions() as session:
        service = HotlistService(session)
        rows, cursor = service.list_history(owner_id=runtime.owner_id, source_key="hotlist_weibo")
        assert len(rows) == 1 and cursor is None
        assert rows[0].entry_count == 0
        view = service.get_historical(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            snapshot_id=rows[0].snapshot_id,
        )
        assert view.items == ()
        with pytest.raises(ValueError, match="cursor"):
            service.list_history(
                owner_id=runtime.owner_id, source_key="hotlist_weibo", cursor=uuid4()
            )
        with pytest.raises(ApplicationError) as inaccessible:
            service.get_historical(
                owner_id=uuid4(),
                source_key="hotlist_weibo",
                snapshot_id=rows[0].snapshot_id,
            )
        assert inaccessible.value.code == "resource_not_found"

    with runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=runtime.owner_id, preset=SOURCE_PRESETS["hotlist_baidu"]
        )
    with runtime.sessions() as session, pytest.raises(ValueError, match="cursor"):
        HotlistService(session).list_history(
            owner_id=runtime.owner_id,
            source_key="hotlist_baidu",
            cursor=rows[0].snapshot_id,
        )


def test_unsuccessful_due_bucket_is_reported_as_gap_between_snapshots(
    runtime: HotlistRuntime,
) -> None:
    first = _accept(runtime, runtime.due_at)
    _execute(runtime, first, _page(runtime.due_at + timedelta(minutes=2), entries=1))
    failed_due = runtime.due_at + timedelta(minutes=30)
    failed_job = _accept(runtime, failed_due)
    failed_page = HotlistPage(
        source_key="hotlist_weibo",
        state=SourcePageState.STOPPED,
        items=(),
        stop_reason=SourceStopReason.UPSTREAM_ERROR,
        observed_at=failed_due + timedelta(minutes=2),
        request_count=1,
        adapter_version="controlled-v1",
    )
    lease = _acquire(runtime, failed_job, failed_page.observed_at)
    message = _message(runtime, failed_job)
    with pytest.raises(JobExecutionFailure) as captured:
        _executor(runtime, failed_page).execute(message, lease)
    with runtime.sessions() as session:
        executions = JobExecutionService(
            session, lease_seconds=75, clock=lambda: failed_page.observed_at
        )
        executions.record_failure(
            lease,
            message=MessageReference(
                message_id=message.message_id,
                topic="hotkey.jobs.accepted.v2",
                partition=0,
                offset=1,
            ),
            failure=captured.value,
        )
    third_due = runtime.due_at + timedelta(minutes=60)
    third = _accept(runtime, third_due)
    _execute(runtime, third, _page(third_due + timedelta(minutes=2)))

    with runtime.sessions() as session:
        service = HotlistService(session)
        rows, _ = service.list_history(owner_id=runtime.owner_id, source_key="hotlist_weibo")
        current = service.get_historical(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            snapshot_id=rows[0].snapshot_id,
        )
    assert [(row.entry_count, row.gap_count) for row in rows] == [(0, 1), (1, 0)]
    assert rows[0].previous_snapshot_id == rows[1].snapshot_id
    assert current.gap_count == 1
