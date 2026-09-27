from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from connections.presets import SOURCE_PRESETS
from connections.schemas import SourceQuietWindow
from connections.services import SourcePresetService
from jobs.coverage import CollectionDueWindowService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
)
from jobs.services import ResourceBudgetService
from worker import scheduler


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


def test_hotlist_due_records_budget_skip_without_job(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    with hotlist_context.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hotlist_weibo.network.daily'"
            )
        )
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(seconds=2)
            )
            == 0
        )
    with hotlist_context.engine.connect() as connection:
        assert connection.execute(
            text("SELECT admission_state, reason FROM collection_due_windows")
        ).one() == ("skipped", "budget")
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0


def test_hotlist_due_records_quiet_skip_without_job(
    hotlist_context: HotlistContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler, "get_settings", lambda: SimpleNamespace(hotlist_interval_seconds=1800)
    )
    hour = hotlist_context.due_at.astimezone(ZoneInfo("Asia/Shanghai")).hour
    preset = SOURCE_PRESETS["hotlist_weibo"]
    quiet_preset = replace(
        preset,
        execution_policy=preset.execution_policy.model_copy(
            update={
                "quiet_windows": (
                    SourceQuietWindow(
                        timezone="Asia/Shanghai",
                        start=f"{hour:02d}:00",
                        end=f"{(hour + 1) % 24:02d}:00",
                    ),
                )
            }
        ),
    )
    monkeypatch.setattr(
        "connections.services.SOURCE_PRESETS",
        {**SOURCE_PRESETS, "hotlist_weibo": quiet_preset},
    )
    with hotlist_context.sessions.begin() as session:
        SourcePresetService(
            session, clock=lambda: hotlist_context.due_at - timedelta(seconds=1)
        ).apply_in_transaction(owner_id=hotlist_context.owner_id, preset=quiet_preset)
    with hotlist_context.sessions.begin() as session:
        assert (
            scheduler.enqueue_due_hotlists_in_transaction(
                session, hotlist_context.due_at + timedelta(seconds=2)
            )
            == 0
        )
    with hotlist_context.engine.connect() as connection:
        assert connection.execute(
            text("SELECT admission_state, reason FROM collection_due_windows")
        ).one() == ("skipped", "quiet")
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
