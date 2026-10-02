from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from tests.conftest import TEST_DATABASE_TRUNCATE, authenticate_test_client, authenticated_owner_id
from tests.integration.test_collection_coverage_http import (
    _accepted_job,
    _connection,
    _due,
)

from core.config import Settings
from main import create_app


@pytest.fixture
def metrics_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Engine, UUID]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required")
    # CI supplies an app-local Settings instance but no HOTKEY_DATABASE_URL.
    monkeypatch.delenv("HOTKEY_DATABASE_URL", raising=False)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(TEST_DATABASE_TRUNCATE))
    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
    )
    try:
        with TestClient(create_app(settings)) as client:
            authenticate_test_client(client)
            with client.app.state.session_factory() as session:
                owner_id = authenticated_owner_id(session)
            yield client, engine, owner_id
    finally:
        with engine.begin() as connection:
            connection.execute(text(TEST_DATABASE_TRUNCATE))
        engine.dispose()


def test_metrics_use_owner_visible_due_ids_and_keep_unfinished_denominator(
    metrics_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = metrics_client
    _connection(engine, owner_id)
    now = datetime.now(UTC).replace(microsecond=0)
    due_times = tuple(now - timedelta(seconds=600 - index * 10) for index in range(5))
    first, first_job = _accepted_job(
        engine, owner_id, due_times[0], status="succeeded", requests_sent=0
    )
    second, second_job = _accepted_job(
        engine, owner_id, due_times[1], status="succeeded", requests_sent=0
    )
    missed = _due(engine, owner_id, due_times[2])
    quiet = _due(engine, owner_id, due_times[3], state="skipped", reason="quiet")
    limited = _due(engine, owner_id, due_times[4], state="skipped", reason="rate_limited")
    _due(engine, owner_id, due_times[0], source_key="private_source")
    with engine.begin() as connection:
        for job_id, finished_at in (
            (first_job, due_times[0] + timedelta(seconds=300)),
            (second_job, due_times[1] + timedelta(seconds=301)),
        ):
            connection.execute(
                text("UPDATE jobs SET completed_at = :finished WHERE id = :job_id"),
                {"job_id": job_id, "finished": finished_at},
            )
        for epoch, outcome in ((1, "failed"), (2, "succeeded")):
            connection.execute(
                text(
                    "INSERT INTO job_attempts "
                    "(id, job_id, lease_epoch, collection_cycle_no, worker_id, "
                    "queued_at, started_at, lease_expires_at, finished_at, outcome) "
                    "VALUES (:id, :job_id, :epoch, 1, 'metrics-test', :started, "
                    ":started, :expires, :finished, :outcome)"
                ),
                {
                    "id": UUID(int=epoch),
                    "job_id": first_job,
                    "epoch": epoch,
                    "started": due_times[0] + timedelta(seconds=epoch),
                    "expires": due_times[0] + timedelta(seconds=epoch + 90),
                    "finished": due_times[0] + timedelta(seconds=epoch + 2),
                    "outcome": outcome,
                },
            )

    response = client.get(
        "/api/collection-coverage/metrics",
        params={
            "start": (now - timedelta(seconds=610)).isoformat(),
            "end": (now + timedelta(seconds=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.json()
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["metric_version"] == "collection-v2"
    assert payload["analysis_status"] == "not_computable"
    assert [(item["source_key"], item["capability"]) for item in payload["sources"]] == [
        ("rss_36kr", "search")
    ]
    metric = payload["sources"][0]
    assert metric["timing"]["due_count"] == 5
    assert metric["timing"]["excluded_count"] == 2
    assert metric["timing"]["sample_count"] == 3
    assert metric["timing"]["finished_count"] == 2
    assert metric["timing"]["timeout_count"] == 1
    assert metric["timing"]["median_seconds"] == 301
    assert metric["timing"]["result"] == "failed"
    assert {item["evidence_id"] for item in metric["exclusions"]} == {
        str(quiet),
        str(limited),
    }
    assert {item["starts_at"] for item in metric["exclusions"]} == {
        due_times[3].isoformat().replace("+00:00", "Z"),
        due_times[4].isoformat().replace("+00:00", "Z"),
    }
    assert all(
        datetime.fromisoformat(item["ends_at"]) - datetime.fromisoformat(item["starts_at"])
        == timedelta(microseconds=1)
        for item in metric["exclusions"]
    )
    assert {first, second, missed}.isdisjoint(
        {UUID(item["evidence_id"]) for item in metric["exclusions"]}
    )


def test_metrics_reject_non_utc_and_overlong_ranges(
    metrics_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = metrics_client
    _connection(engine, owner_id)
    for start, end in (
        ("2026-09-27T00:00:00+08:00", "2026-09-28T00:00:00Z"),
        ("2026-09-27T00:00:00Z", "2026-10-29T00:00:00Z"),
    ):
        response = client.get(
            "/api/collection-coverage/metrics", params={"start": start, "end": end}
        )
        assert response.status_code == 422


def test_hotlist_denominator_enumerates_missing_bucket_in_72_hour_window(
    metrics_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = metrics_client
    _connection(engine, owner_id)
    now = datetime.now(UTC)
    start_epoch = int((now - timedelta(days=4)).timestamp()) // 1800 * 1800
    start = datetime.fromtimestamp(start_epoch, UTC)
    end = start + timedelta(hours=72)
    for index in range(144):
        if index == 43:
            continue
        _due(
            engine,
            owner_id,
            start + timedelta(minutes=30 * index),
            source_key="rss_36kr",
            capability="hotlist",
        )
    response = client.get(
        "/api/collection-coverage/metrics",
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "source_key": "rss_36kr",
            "capability": "hotlist",
        },
    )
    assert response.status_code == 200, response.json()
    hotlist = response.json()["sources"][0]["hotlist"]
    assert (hotlist["expected_count"], hotlist["recorded_count"], hotlist["missing_count"]) == (
        144,
        143,
        1,
    )
    assert hotlist["success_ratio"] == 0
    assert hotlist["phase_verified"] is False
    timing = response.json()["sources"][0]["timing"]
    assert timing["due_count"] == 144
    assert timing["sample_count"] == 144
    assert timing["timeout_count"] == 144
    assert timing["result"] == "indeterminate"
