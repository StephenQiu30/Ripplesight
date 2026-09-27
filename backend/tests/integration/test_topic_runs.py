from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from tests.integration.test_monitor_topics import (
    _TRUNCATE,
    _csrf_headers,
    _initialize,
    _topic_payload,
)

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from core.config import Settings
from main import create_app
from monitors.runs import MonitorTopicRunService
from monitors.schemas import MonitorTopicRunInput
from worker import scheduler
from worker.scheduler import enqueue_due_collections_in_transaction


@pytest.fixture
def monitor_topic_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(_TRUNCATE))
    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
        bootstrap_token="monitor-topics-isolated-bootstrap-token",
    )
    # Scheduler scans normally read process settings. The API fixture supplies
    # an explicit isolated database URL, while CI intentionally has no app URL.
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def _ready_topic(
    client: TestClient,
    *,
    source_keys: tuple[str, ...],
    interval: int = 600,
    source_min_interval: int | None = None,
) -> str:
    _initialize(client)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        owner_id = session.execute(text("SELECT id FROM identity_users")).scalar_one()
        for source_key in source_keys:
            preset = SOURCE_PRESETS[source_key]
            if source_min_interval is not None:
                preset = replace(
                    preset,
                    execution_policy=preset.execution_policy.model_copy(
                        update={"min_interval_seconds": source_min_interval}
                    ),
                )
            SourcePresetService(session).apply_in_transaction(owner_id=owner_id, preset=preset)
    created = client.post(
        "/api/topics",
        headers=_csrf_headers(client),
        json={
            **_topic_payload(),
            "source_keys": list(source_keys),
            "collection_interval_seconds": interval,
        },
    )
    assert created.status_code == 201, created.json()
    resumed = client.post(f"{created.headers['location']}/resume", headers=_csrf_headers(client))
    assert resumed.status_code == 200, resumed.json()
    return created.headers["location"]


def test_manual_run_replays_one_job_and_outbox(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    runs = f"{location}/runs"
    payload = {"operation_id": str(uuid4()), "source_keys": ["hackernews"]}
    assert monitor_topic_client.post(runs, json=payload).status_code == 403
    assert (
        monitor_topic_client.post(
            f"/api/topics/{uuid4()}/runs",
            headers=_csrf_headers(monitor_topic_client),
            json=payload,
        ).status_code
        == 404
    )
    assert (
        monitor_topic_client.post(
            runs,
            headers=_csrf_headers(monitor_topic_client),
            json={"operation_id": str(uuid4()), "source_keys": ["google_news"]},
        ).status_code
        == 422
    )
    first = monitor_topic_client.post(
        runs, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    replay = monitor_topic_client.post(
        runs, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert first.status_code == 202, first.json()
    assert replay.status_code == 200, replay.json()
    assert first.json() == replay.json()
    assert len(first.json()["sources"][0]["job_ids"]) == 1
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'keyword.search'")) == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 1


def test_manual_run_rejects_anonymous_and_all_skipped(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    payload = {"operation_id": str(uuid4()), "source_keys": ["hackernews"]}
    anonymous = TestClient(monitor_topic_client.app)
    try:
        response = anonymous.post(location + "/runs", json=payload)
        assert response.status_code == 401
    finally:
        anonymous.close()
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    response = monitor_topic_client.post(
        location + "/runs", headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert response.status_code == 409
    assert response.json()["code"] == "topic_not_ready"
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 0
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 0


def test_source_minimum_interval_wins_over_topic_interval(
    monitor_topic_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = SOURCE_PRESETS["hackernews"]
    minimum_policy = preset.execution_policy.model_copy(update={"min_interval_seconds": 1800})
    monkeypatch.setattr(
        "connections.services.SOURCE_PRESETS",
        {**SOURCE_PRESETS, "hackernews": replace(preset, execution_policy=minimum_policy)},
    )
    location = _ready_topic(
        monitor_topic_client,
        source_keys=("hackernews",),
        interval=600,
        source_min_interval=1800,
    )
    with monitor_topic_client.app.state.session_factory() as session:
        interval = session.scalar(
            text("SELECT interval_seconds FROM monitor_schedules WHERE topic_id = :topic_id"),
            {"topic_id": location.rsplit("/", 1)[1]},
        )
    assert interval == 1800


def test_manual_run_freezes_connection_version_after_preset_update(
    monitor_topic_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    first = monitor_topic_client.post(
        location + "/runs",
        headers=_csrf_headers(monitor_topic_client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert first.status_code == 202, first.json()
    first_job_id = first.json()["sources"][0]["job_ids"][0]
    preset = SOURCE_PRESETS["hackernews"]
    changed = replace(
        preset,
        execution_policy=preset.execution_policy.model_copy(update={"max_queries": 1}),
    )
    monkeypatch.setattr(
        "connections.services.SOURCE_PRESETS", {**SOURCE_PRESETS, "hackernews": changed}
    )
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
        SourcePresetService(session).apply_in_transaction(owner_id=owner_id, preset=changed)
    second = monitor_topic_client.post(
        location + "/runs",
        headers=_csrf_headers(monitor_topic_client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert second.status_code == 202, second.json()
    second_job_id = second.json()["sources"][0]["job_ids"][0]
    with factory() as session:
        versions = session.execute(
            text(
                "SELECT id, scope->>'connection_version' FROM jobs "
                "WHERE id IN (:first_job_id, :second_job_id)"
            ),
            {"first_job_id": first_job_id, "second_job_id": second_job_id},
        ).all()
    assert {version for _, version in versions} == {"1", "2"}


def test_manual_run_keeps_partial_admission_on_retry(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("google_news", "hackernews"))
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.google_news.network.daily'"
            )
        )
    payload = {
        "operation_id": str(uuid4()),
        "source_keys": ["hackernews", "google_news"],
    }
    runs = f"{location}/runs"
    first = monitor_topic_client.post(
        runs, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert first.status_code == 202, first.json()
    sources = {source["source_key"]: source for source in first.json()["sources"]}
    assert sources["google_news"] == {
        "source_key": "google_news",
        "job_ids": [],
        "skip_reason": "budget",
    }
    assert len(sources["hackernews"]["job_ids"]) == 1
    replay = monitor_topic_client.post(
        runs, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert replay.status_code == 200 and replay.json() == first.json()
    changed = monitor_topic_client.post(
        runs,
        headers=_csrf_headers(monitor_topic_client),
        json={**payload, "source_keys": ["hackernews"]},
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"


def test_concurrent_manual_retries_create_one_job(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    topic_id = location.rsplit("/", 1)[1]
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
    assert owner_id is not None
    command = MonitorTopicRunInput(operation_id=uuid4(), source_keys=["hackernews"])

    def run_once() -> tuple[bool, list[str]]:
        with factory() as session:
            outcome = MonitorTopicRunService(session, monitor_topic_client.app.state.settings).run(
                owner_id=owner_id, topic_id=UUID(topic_id), command=command
            )
            return outcome.replayed, [
                str(job_id) for source in outcome.view.sources for job_id in source.job_ids
            ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_once(), range(2)))
    assert sorted(replayed for replayed, _ in results) == [False, True]
    assert results[0][1] == results[1][1]
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 1


def test_scheduler_records_missed_due_points_and_accepts_latest_atomically(
    monitor_topic_client: TestClient,
) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    topic_id = location.rsplit("/", 1)[1]
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
    assert owner_id is not None
    now = datetime.now(UTC) + timedelta(seconds=1)
    due_at = now - timedelta(minutes=20)
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE monitor_schedules SET next_run_at = :due_at "
                "WHERE owner_id = :owner_id AND topic_id = :topic_id"
            ),
            {"due_at": due_at, "owner_id": owner_id, "topic_id": topic_id},
        )
        session.execute(
            text(
                "UPDATE source_connection_versions SET created_at = :created_at "
                "WHERE owner_id = :owner_id"
            ),
            {"created_at": due_at - timedelta(minutes=1), "owner_id": owner_id},
        )
    with factory() as session, session.begin():
        assert enqueue_due_collections_in_transaction(session, now) == 1
    with factory() as session, session.begin():
        assert enqueue_due_collections_in_transaction(session, now) == 0
    with factory() as session:
        facts = session.execute(
            text(
                "SELECT due_at, admission_state, reason, job_id "
                "FROM collection_due_windows WHERE owner_id = :owner_id ORDER BY due_at"
            ),
            {"owner_id": owner_id},
        ).all()
        jobs = session.execute(
            text("SELECT id, scheduled_for_at FROM jobs WHERE owner_id = :owner_id"),
            {"owner_id": owner_id},
        ).all()
        next_run_at = session.scalar(
            text(
                "SELECT next_run_at FROM monitor_schedules "
                "WHERE owner_id = :owner_id AND topic_id = :topic_id"
            ),
            {"owner_id": owner_id, "topic_id": topic_id},
        )
        outbox_count = session.scalar(text("SELECT count(*) FROM outbox_messages"))
    assert [row[0] for row in facts] == [due_at, due_at + timedelta(minutes=10), now]
    assert [row[1] for row in facts] == ["missed", "missed", "accepted"]
    assert [row[2] for row in facts] == [
        "scheduler_interrupted",
        "scheduler_interrupted",
        None,
    ]
    assert len(jobs) == 1 and facts[-1][3] == jobs[0][0]
    assert jobs[0][1] == now
    assert next_run_at == now + timedelta(minutes=10)
    assert outbox_count == 1


def test_concurrent_scheduler_scans_claim_one_due_row(
    monitor_topic_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    factory = monitor_topic_client.app.state.session_factory
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory.begin() as session:
        session.execute(
            text("UPDATE monitor_schedules SET next_run_at = :due WHERE topic_id = :topic_id"),
            {"due": now, "topic_id": location.rsplit("/", 1)[1]},
        )

    locked = Event()
    release = Event()
    original = scheduler._process_collection_schedule

    def hold_claim(*args: object, **kwargs: object) -> tuple[int, bool]:
        locked.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(scheduler, "_process_collection_schedule", hold_claim)

    def scan() -> int:
        with factory() as session, session.begin():
            return enqueue_due_collections_in_transaction(session, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(scan)
        assert locked.wait(timeout=5)
        second = pool.submit(scan)
        try:
            assert second.result(timeout=5) == 0
        finally:
            release.set()
        assert first.result(timeout=5) == 1
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM collection_due_windows")) == 1
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 1


def test_scheduler_records_quiet_due_without_dispatch(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    topic_id = location.rsplit("/", 1)[1]
    factory = monitor_topic_client.app.state.session_factory
    now = datetime.now(UTC) + timedelta(seconds=1)
    local_hour = now.astimezone(ZoneInfo("Asia/Shanghai")).hour
    quiet = json.dumps(
        [
            {
                "timezone": "Asia/Shanghai",
                "start": f"{local_hour:02d}:00",
                "end": f"{(local_hour + 1) % 24:02d}:00",
            }
        ]
    )
    with factory.begin() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
        session.execute(
            text("UPDATE monitor_schedules SET next_run_at = :due WHERE topic_id = :topic_id"),
            {"due": now, "topic_id": topic_id},
        )
        session.execute(
            text(
                "UPDATE source_connection_versions SET execution_policy = "
                "jsonb_set(execution_policy, '{quiet_windows}', CAST(:quiet AS jsonb)) "
                "WHERE owner_id = :owner_id"
            ),
            {"owner_id": owner_id, "quiet": quiet},
        )
    with factory() as session, session.begin():
        assert enqueue_due_collections_in_transaction(session, now) == 0
    with factory() as session:
        fact = session.execute(
            text("SELECT admission_state, reason FROM collection_due_windows")
        ).one()
        assert fact == ("skipped", "quiet")
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 0
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 0


def test_scheduler_rolls_back_due_job_outbox_and_cursor_together(
    monitor_topic_client: TestClient,
) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    topic_id = location.rsplit("/", 1)[1]
    factory = monitor_topic_client.app.state.session_factory
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory.begin() as session:
        session.execute(
            text("UPDATE monitor_schedules SET next_run_at = :due WHERE topic_id = :topic_id"),
            {"due": now, "topic_id": topic_id},
        )
    with (
        factory() as session,
        pytest.raises(RuntimeError, match="injected rollback"),
        session.begin(),
    ):
        assert enqueue_due_collections_in_transaction(session, now) == 1
        raise RuntimeError("injected rollback")
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM collection_due_windows")) == 0
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 0
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 0
        assert (
            session.scalar(
                text("SELECT next_run_at FROM monitor_schedules WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            )
            == now
        )
    with factory() as session, session.begin():
        assert enqueue_due_collections_in_transaction(session, now) == 1


def test_paused_topic_does_not_accept_due_collection(monitor_topic_client: TestClient) -> None:
    location = _ready_topic(monitor_topic_client, source_keys=("hackernews",))
    paused = monitor_topic_client.post(
        location + "/pause", headers=_csrf_headers(monitor_topic_client)
    )
    assert paused.status_code == 200
    factory = monitor_topic_client.app.state.session_factory
    now = datetime.now(UTC) + timedelta(minutes=1)
    with factory() as session, session.begin():
        assert enqueue_due_collections_in_transaction(session, now) == 0
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 0
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 0
