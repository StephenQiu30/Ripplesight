from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from tests.conftest import TEST_DATABASE_TRUNCATE, authenticate_test_client, authenticated_owner_id
from tests.integration.test_content_collection_facts import (
    _seed_content,
    _seed_job,
    _seed_observation,
)

from core.config import Settings
from jobs.schemas import JobAcceptanceInput
from jobs.services import JobService
from main import create_app

_TRUNCATE = TEST_DATABASE_TRUNCATE


@pytest.fixture
def collection_job_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(_TRUNCATE))
    try:
        with TestClient(create_app(settings)) as client:
            authenticate_test_client(client)
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def _user_scope(client: TestClient) -> UUID:
    with client.app.state.session_factory() as session:
        return authenticated_owner_id(session)


@pytest.mark.parametrize("kind", ["keyword.search", "source.comments"])
def test_job_detail_counts_retained_identities_across_retries_without_writes(
    collection_job_client: TestClient, kind: str
) -> None:
    client = collection_job_client
    owner = _user_scope(client)
    prior, current = uuid4(), uuid4()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        for job_id in (prior, current):
            _seed_job(session, owner, job_id, now)
        session.execute(
            text(
                "UPDATE jobs SET kind=:kind, retry_count=2, checkpoint=:checkpoint, "
                "items_saved=99, progress_stage='save', progress_updated_at=created_at WHERE id=:id"
            ),
            {
                "id": current,
                "kind": kind,
                "checkpoint": json.dumps({"collection.observed_count": 8}),
            },
        )
        for index in range(4):
            content, version, changed = uuid4(), uuid4(), uuid4()
            _seed_content(session, owner, content, (version, changed), now)
            if index < 3:
                _seed_observation(session, owner, prior, content, version, now)
            _seed_observation(
                session,
                owner,
                current,
                content,
                changed if index == 0 else None if index == 2 else version,
                now + timedelta(minutes=1),
            )
            if index == 3:
                _seed_observation(
                    session, owner, current, content, changed, now + timedelta(minutes=2)
                )

    def stored_state() -> tuple[object, ...]:
        with factory() as session:
            return tuple(
                session.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
                for table in (
                    "jobs",
                    "content_observations",
                    "outbox_messages",
                    "resource_usage_attempts",
                )
            )

    before = stored_state()
    response = client.get(f"/api/jobs/{current}")
    assert response.status_code == 200
    counts = response.json()["collection_counts"]
    assert counts == {
        "observed_count": 8,
        "stored_observation_count": 5,
        "unique_content_count": 4,
        "identity_count_basis": "frozen_receipt_identity_v2",
        "inserted_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "unclassified_count": 4,
    }
    assert response.json()["progress"]["items_saved"] == 99
    assert client.get(f"/api/jobs/{current}").json()["collection_counts"] == counts
    assert stored_state() == before
    authenticate_test_client(client, owner_id=uuid4())
    denied = client.get(f"/api/jobs/{current}")
    assert denied.status_code == 404
    assert "collection_counts" not in denied.json()


@pytest.mark.parametrize("observed", [None, -1, True, "3", 0, 3])
def test_job_detail_empty_receipts_do_not_infer_upstream_zero(
    collection_job_client: TestClient, observed: object
) -> None:
    client = collection_job_client
    owner, job_id = _user_scope(client), uuid4()
    with client.app.state.session_factory.begin() as session:
        _seed_job(session, owner, job_id, datetime(2026, 10, 1, tzinfo=UTC))
        session.execute(
            text("UPDATE jobs SET checkpoint=:checkpoint WHERE id=:id"),
            {"id": job_id, "checkpoint": json.dumps({"collection.observed_count": observed})},
        )
    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    counts = response.json()["collection_counts"]
    assert counts["observed_count"] == (
        observed if type(observed) is int and observed >= 0 else None
    )
    assert all(
        counts[key] == 0
        for key in (
            "stored_observation_count",
            "unique_content_count",
            "inserted_count",
            "updated_count",
            "unchanged_count",
            "unclassified_count",
        )
    )


def _payload(
    *,
    operation_id: UUID | None = None,
    window: int = 7,
    configuration_version: int = 3,
) -> dict[str, object]:
    return {
        "operation_id": str(operation_id or uuid4()),
        "kind": "monitor.collect",
        "observation": {
            "configuration_ref": "monitor-config-1",
            "configuration_version": configuration_version,
            "source_key": "x",
            "source_capability": "search",
        },
        "scheduled_for_at": None,
        "scope": {"source_id": "account-1", "window": window},
    }


def _csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-HotKey-CSRF": client.cookies["hotkey_csrf"]}


def _accept_internal_job(client: TestClient, payload: dict[str, object]) -> UUID:
    factory = client.app.state.session_factory
    with factory() as session:
        owner_id = authenticated_owner_id(session)
        job = JobService(session).accept(
            owner_id=owner_id,
            command=JobAcceptanceInput.model_validate(payload, strict=False),
        )
    return job.id


def _set_job_facts(
    session: Session,
    *,
    job_id: UUID,
    status: str,
    started_at: datetime,
    completed_at: datetime | None,
    outcome: str,
    delayed_at: datetime | None = None,
) -> None:
    updated_at = delayed_at or completed_at
    assert updated_at is not None
    session.execute(
        text(
            "INSERT INTO job_attempts "
            "(id, job_id, lease_epoch, collection_cycle_no, worker_id, queued_at, "
            "started_at, lease_expires_at, finished_at, outcome) VALUES "
            "(:id, :job_id, 1, 1, 'freshness-test', :started_at, :started_at, "
            ":lease_expires_at, :finished_at, :outcome)"
        ),
        {
            "id": uuid4(),
            "job_id": job_id,
            "started_at": started_at,
            "lease_expires_at": started_at + timedelta(minutes=10),
            "finished_at": updated_at,
            "outcome": outcome,
        },
    )
    session.execute(
        text(
            "UPDATE jobs SET created_at = :created_at, status = :status, "
            "started_at = :started_at, collection_cycle_no = 1, "
            "collection_cycle_started_at = :started_at, completed_at = :completed_at, "
            "updated_at = :updated_at, "
            "defer_reason = :defer_reason, next_run_at = :next_run_at, retry_count = :retry_count, "
            "last_error_code = :error_code, last_error_category = :error_category, "
            "last_error_at = :error_at, next_action = :next_action "
            "WHERE id = :job_id"
        ),
        {
            "job_id": job_id,
            "created_at": started_at - timedelta(minutes=5),
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": updated_at,
            "defer_reason": "rate_limited" if delayed_at is not None else None,
            "next_run_at": delayed_at + timedelta(minutes=10) if delayed_at else None,
            "retry_count": 1 if delayed_at is not None else 0,
            "error_code": "collector_budget_exhausted" if delayed_at is not None else None,
            "error_category": "rate_limited" if delayed_at is not None else None,
            "error_at": delayed_at,
            "next_action": "等待预算窗口恢复" if delayed_at is not None else None,
        },
    )


def test_internal_job_status_is_readable_after_refresh(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    payload = _payload()
    job_id = _accept_internal_job(collection_job_client, payload)

    refreshed = collection_job_client.get(f"/api/jobs/{job_id}")
    body = refreshed.json()
    freshness = body["source_freshness"]

    assert refreshed.status_code == 200
    assert refreshed.headers["cache-control"] == "no-store"
    assert body == {
        "id": str(job_id),
        "operation_id": payload["operation_id"],
        "kind": "monitor.collect",
        "observation": payload["observation"],
        "status": "queued",
        "progress": {
            "stage": None,
            "requests_sent": 0,
            "items_saved": 0,
            "updated_at": None,
        },
        "cancellation": None,
        "failure": None,
        "result_content_id": None,
        "retry_count": 0,
        "collection_cycle_no": 0,
        "collection_cycle_started_at": None,
        "collection_cycle_requests_sent": 0,
        "collection_cycle_pending": False,
        "latest_attempt_started_at": None,
        "latest_attempt_finished_at": None,
        "queue_wait_us": body["queue_wait_us"],
        "attempt_elapsed_us": None,
        "total_elapsed_us": None,
        "collection_budget_remaining_us": None,
        "next_run_at": None,
        "scheduled_for_at": None,
        "started_at": None,
        "completed_at": None,
        "created_at": body["created_at"],
        "source_freshness": freshness,
        "coverage_windows": [],
        "query_plan": None,
        "collection_counts": None,
        "collection_executions": None,
        "collection_executions_has_more": False,
    }
    assert body["queue_wait_us"] is not None and body["queue_wait_us"] >= 0
    assert freshness == {
        "last_attempt_at": None,
        "last_success_at": None,
        "delay_reason": "internal_queue",
        "delay_since_at": body["created_at"],
        "delay_duration_us": freshness["delay_duration_us"],
    }
    assert isinstance(freshness["delay_duration_us"], int)
    assert freshness["delay_duration_us"] >= 0
    assert "owner_id" not in body
    assert "scope" not in body


def test_job_status_reports_last_attempt_full_success_and_budget_delay(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    success_job_id = _accept_internal_job(collection_job_client, _payload())
    partial_job_id = _accept_internal_job(collection_job_client, _payload())
    delayed_job_id = _accept_internal_job(collection_job_client, _payload())
    other_version_job_id = _accept_internal_job(
        collection_job_client,
        _payload(configuration_version=4),
    )

    factory = collection_job_client.app.state.session_factory
    now = datetime.now(UTC)
    last_success_at = now - timedelta(hours=1)
    partial_completed_at = now - timedelta(minutes=10)
    last_attempt_at = now - timedelta(minutes=5)
    delayed_at = now - timedelta(minutes=2)
    other_version_success_at = now - timedelta(minutes=1)
    jobs = (
        (
            success_job_id,
            "succeeded",
            last_success_at - timedelta(minutes=2),
            last_success_at,
            None,
        ),
        (
            partial_job_id,
            "partially_succeeded",
            partial_completed_at - timedelta(minutes=2),
            partial_completed_at,
            None,
        ),
        (delayed_job_id, "queued", last_attempt_at, None, delayed_at),
        (
            other_version_job_id,
            "succeeded",
            other_version_success_at - timedelta(minutes=1),
            other_version_success_at,
            None,
        ),
    )
    with factory() as session, session.begin():
        for job_id, status, started_at, job_completed_at, delay_at in jobs:
            _set_job_facts(
                session,
                job_id=job_id,
                status=status,
                started_at=started_at,
                completed_at=job_completed_at,
                outcome="delayed" if delay_at is not None else "succeeded",
                delayed_at=delay_at,
            )

    response = collection_job_client.get(f"/api/jobs/{delayed_job_id}")

    assert response.status_code == 200, response.json()
    freshness = response.json()["source_freshness"]
    assert datetime.fromisoformat(freshness["last_attempt_at"].replace("Z", "+00:00")) == (
        last_attempt_at
    )
    assert datetime.fromisoformat(freshness["last_success_at"].replace("Z", "+00:00")) == (
        last_success_at
    )
    assert freshness["delay_reason"] == "budget_exhausted"
    assert datetime.fromisoformat(freshness["delay_since_at"].replace("Z", "+00:00")) == (
        delayed_at
    )
    assert freshness["delay_duration_us"] >= 0


def test_job_history_uses_owner_scoped_stable_cursor_and_safe_summary(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    job_ids: list[str] = []
    for window in (1, 2, 3):
        job_ids.append(str(_accept_internal_job(collection_job_client, _payload(window=window))))

    created_at = datetime(2026, 9, 23, 8, tzinfo=UTC)
    factory = collection_job_client.app.state.session_factory
    with factory() as session, session.begin():
        for job_id in job_ids:
            session.execute(
                text(
                    "UPDATE jobs SET created_at = :created_at, updated_at = :created_at "
                    "WHERE id = :job_id"
                ),
                {"created_at": created_at, "job_id": job_id},
            )

    history = collection_job_client.get("/api/jobs", params={"limit": 2})

    assert history.status_code == 200, history.json()
    assert history.headers["cache-control"] == "no-store"
    expected = sorted(
        (collection_job_client.get(f"/api/jobs/{job_id}").json() for job_id in job_ids),
        key=lambda job: (job["created_at"], job["id"]),
        reverse=True,
    )
    first_page = history.json()
    assert [item["id"] for item in first_page["items"]] == [item["id"] for item in expected[:2]]
    assert first_page["next_cursor"] == expected[1]["id"]
    assert set(first_page["items"][0]) == {
        "id",
        "kind",
        "source_key",
        "source_capability",
        "status",
        "requests_sent",
        "items_saved",
        "created_at",
        "started_at",
        "completed_at",
        "next_run_at",
    }
    assert "owner_id" not in first_page["items"][0]
    assert "scope" not in first_page["items"][0]
    assert "request_fingerprint" not in first_page["items"][0]

    next_page = collection_job_client.get(
        "/api/jobs",
        params={"cursor": first_page["next_cursor"], "limit": 2},
    )
    assert next_page.status_code == 200, next_page.json()
    assert [item["id"] for item in next_page.json()["items"]] == [
        item["id"] for item in expected[2:]
    ]
    assert next_page.json()["next_cursor"] is None
    assert collection_job_client.get("/api/jobs", params={"limit": 0}).status_code == 422
    assert (
        collection_job_client.get(
            "/api/jobs",
            params={"cursor": str(uuid4())},
        ).status_code
        == 404
    )


def test_job_history_is_readable_without_an_account(
    collection_job_client: TestClient,
) -> None:
    response = collection_job_client.get("/api/jobs")

    assert response.status_code == 200


def test_continuous_failure_issue_endpoint_is_authenticated_and_redacted(
    collection_job_client: TestClient,
) -> None:
    assert collection_job_client.get("/api/jobs/issues").status_code == 200
    _user_scope(collection_job_client)

    job_ids: list[str] = []
    for window in (1, 2, 3):
        payload = _payload(window=window)
        payload["observation"] = {
            **payload["observation"],
            "configuration_version": window,
        }
        job_ids.append(str(_accept_internal_job(collection_job_client, payload)))

    now = datetime.now(UTC)
    factory = collection_job_client.app.state.session_factory
    with factory() as session, session.begin():
        for index, job_id in enumerate(job_ids, start=1):
            completed_at = now + timedelta(minutes=index)
            session.execute(
                text(
                    "UPDATE jobs SET status = 'failed', started_at = :started_at, "
                    "completed_at = :completed_at, updated_at = :completed_at, "
                    "last_error_code = 'source.timeout', "
                    "last_error_category = 'transient', last_error_at = :completed_at, "
                    "next_action = '检查来源连接' WHERE id = :job_id"
                ),
                {
                    "started_at": completed_at - timedelta(seconds=1),
                    "completed_at": completed_at,
                    "job_id": job_id,
                },
            )

    response = collection_job_client.get("/api/jobs/issues")

    assert response.status_code == 200, response.json()
    assert response.headers["cache-control"] == "no-store"
    issues = response.json()
    assert len(issues) == 1
    assert set(issues[0]) == {
        "source_key",
        "source_capability",
        "configuration_ref",
        "configuration_version",
        "latest_failed_job_id",
        "failure",
        "consecutive_failure_threshold",
    }
    assert issues[0]["source_key"] == "x"
    assert issues[0]["source_capability"] == "search"
    assert issues[0]["configuration_ref"] == "monitor-config-1"
    assert issues[0]["latest_failed_job_id"] == job_ids[-1]
    assert issues[0]["configuration_version"] == 3
    assert issues[0]["consecutive_failure_threshold"] == 3
    assert issues[0]["failure"]["error_code"] == "source.timeout"
    assert issues[0]["failure"]["next_action"] == "检查来源连接"
    assert "scope" not in str(issues)
    assert "source_id" not in str(issues)
    assert "owner_id" not in str(issues)


def test_webpage_submission_derives_connection_context_without_leaking_url_to_outbox(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    configured = collection_job_client.put(
        "/api/source-connections/web",
        headers=_csrf_headers(collection_job_client),
        json={
            "expected_version": 0,
            "status": "active",
            "allowed_hosts": ["example.com"],
        },
    )
    assert configured.status_code == 200, configured.json()
    operation_id = uuid4()

    accepted = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json={
            "operation_id": str(operation_id),
            "kind": "webpage.collect",
            "url": "https://EXAMPLE.com/Articles/One?q=1#ignored",
        },
    )

    assert accepted.status_code == 202, accepted.json()
    job_id = accepted.json()["job_id"]
    refreshed = collection_job_client.get(f"/api/jobs/{job_id}")
    assert refreshed.status_code == 200
    assert refreshed.json()["kind"] == "webpage.collect"
    assert refreshed.json()["observation"] == {
        "configuration_ref": f"connection:{configured.json()['id'].replace('-', '')}",
        "configuration_version": 1,
        "source_key": "web",
        "source_capability": "page_content",
    }
    assert refreshed.json()["result_content_id"] is None

    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        job = session.execute(
            text(
                "SELECT scope, configuration_ref, configuration_version, source_key, "
                "source_capability FROM jobs WHERE id = :job_id"
            ),
            {"job_id": job_id},
        ).one()
        outbox_payload = session.execute(
            text("SELECT payload FROM outbox_messages WHERE aggregate_id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()
    assert job.scope == {
        "connection_id": configured.json()["id"],
        "entry_point": "manual",
        "target_url": "https://example.com/Articles/One?q=1",
    }
    assert job.configuration_ref == f"connection:{configured.json()['id'].replace('-', '')}"
    assert job.configuration_version == 1
    assert job.source_key == "web"
    assert job.source_capability == "page_content"
    assert "target_url" not in outbox_payload


def test_webpage_submission_rejects_client_owned_execution_context(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)

    response = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json={
            "operation_id": str(uuid4()),
            "kind": "webpage.collect",
            "url": "https://example.com/article",
            "scope": {"connection_id": str(uuid4())},
            "observation": {
                "configuration_ref": "attacker-controlled",
                "configuration_version": 99,
                "source_key": "web",
                "source_capability": "page_content",
            },
        },
    )

    assert response.status_code == 422
    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0


def test_webpage_lost_response_replay_survives_connection_replacement(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    configured = collection_job_client.put(
        "/api/source-connections/web",
        headers=_csrf_headers(collection_job_client),
        json={
            "expected_version": 0,
            "status": "active",
            "allowed_hosts": ["example.com"],
        },
    )
    assert configured.status_code == 200
    operation_id = uuid4()
    payload = {
        "operation_id": str(operation_id),
        "kind": "webpage.collect",
        "url": "https://example.com/article#first",
    }
    original = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json=payload,
    )
    replaced = collection_job_client.put(
        "/api/source-connections/web",
        headers=_csrf_headers(collection_job_client),
        json={
            "expected_version": 1,
            "status": "active",
            "allowed_hosts": ["other.example"],
        },
    )
    replayed = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json={**payload, "url": "https://EXAMPLE.com/article"},
    )
    conflicting = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json={**payload, "url": "https://other.example/article"},
    )

    assert original.status_code == 202
    assert replaced.status_code == 200
    assert replaced.json()["version"] == 2
    assert replayed.status_code == 202
    assert replayed.json()["job_id"] == original.json()["job_id"]
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "idempotency_conflict"
    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
        assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 1


def test_running_job_cancel_request_is_persisted_for_inflight_boundary(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    job_id = str(_accept_internal_job(collection_job_client, _payload()))
    factory = collection_job_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET status = 'running', lease_owner = 'worker-red', "
                "lease_epoch = 1, lease_expires_at = now() + interval '1 minute', "
                "started_at = now(), updated_at = now() WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )

    cancelled = collection_job_client.post(
        f"/api/jobs/{job_id}/cancel",
        headers=_csrf_headers(collection_job_client),
    )

    assert cancelled.status_code == 200, cancelled.json()
    assert cancelled.headers["cache-control"] == "no-store"
    assert cancelled.json()["status"] == "cancelling"
    assert cancelled.json()["cancellation"] == {
        "requested_at": cancelled.json()["cancellation"]["requested_at"],
        "deadline_at": cancelled.json()["cancellation"]["deadline_at"],
        "timed_out": False,
    }


def test_queued_job_cancel_is_immediate_idempotent_and_terminal_conflicts(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    job_id = _accept_internal_job(collection_job_client, _payload())
    location = f"/api/jobs/{job_id}"
    cancel_location = f"{location}/cancel"

    first = collection_job_client.post(
        cancel_location,
        headers=_csrf_headers(collection_job_client),
    )
    repeated = collection_job_client.post(
        cancel_location,
        headers=_csrf_headers(collection_job_client),
    )

    assert first.status_code == repeated.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert first.json()["completed_at"] is not None
    assert first.json()["cancellation"]["deadline_at"] is None
    assert repeated.json()["cancellation"] == first.json()["cancellation"]

    factory = collection_job_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET status = 'succeeded', completed_at = now(), "
                "cancel_requested_at = NULL, cancel_deadline_at = NULL, "
                "updated_at = now() WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )
    conflict = collection_job_client.post(
        cancel_location,
        headers=_csrf_headers(collection_job_client),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "job_not_cancellable"


def test_job_routes_enforce_csrf_and_missing_resource_boundaries(
    collection_job_client: TestClient,
) -> None:
    payload = {
        "operation_id": str(uuid4()),
        "kind": "webpage.collect",
        "url": "https://example.com/article",
    }
    _user_scope(collection_job_client)
    missing_csrf = collection_job_client.post("/api/jobs", json=payload)
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "csrf_invalid"

    missing_job = collection_job_client.get(f"/api/jobs/{uuid4()}")
    assert missing_job.status_code == 404
    assert missing_job.json()["code"] == "resource_not_found"


def test_cancel_route_enforces_csrf_and_owner_boundary(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    missing_csrf = collection_job_client.post(f"/api/jobs/{uuid4()}/cancel")
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "csrf_invalid"

    missing_job = collection_job_client.post(
        f"/api/jobs/{uuid4()}/cancel",
        headers=_csrf_headers(collection_job_client),
    )
    assert missing_job.status_code == 404
    assert missing_job.json()["code"] == "resource_not_found"


def test_retry_rejects_non_failed_job_without_duplicate_dispatch(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    job_id = _accept_internal_job(collection_job_client, _payload())

    retried = collection_job_client.post(
        f"/api/jobs/{job_id}/retry",
        headers=_csrf_headers(collection_job_client),
    )

    assert retried.status_code == 409
    assert retried.json()["code"] == "job_not_retryable"
    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
        assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 1


def test_manual_retry_reuses_failed_job_and_is_idempotent(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    job_id = str(_accept_internal_job(collection_job_client, _payload()))
    factory = collection_job_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET status = 'failed', completed_at = now(), retry_count = 0, "
                "last_error_code = 'connection_expired', "
                "last_error_category = 'authentication_required', last_error_at = now(), "
                "next_action = '修复连接后重试', manual_retry_allowed = true, "
                "updated_at = now() WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )

    first = collection_job_client.post(
        f"/api/jobs/{job_id}/retry",
        headers=_csrf_headers(collection_job_client),
    )
    repeated = collection_job_client.post(
        f"/api/jobs/{job_id}/retry",
        headers=_csrf_headers(collection_job_client),
    )

    assert first.status_code == repeated.status_code == 202
    assert first.headers["location"] == f"/api/jobs/{job_id}"
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["id"] == repeated.json()["id"] == job_id
    assert first.json()["status"] == repeated.json()["status"] == "queued"
    assert first.json()["retry_count"] == repeated.json()["retry_count"] == 1
    assert first.json()["failure"] == {
        "error_code": "connection_expired",
        "category": "authentication_required",
        "occurred_at": first.json()["failure"]["occurred_at"],
        "next_action": "修复连接后重试",
        "manual_retry_allowed": True,
    }
    with factory() as session:
        rows = session.execute(
            text(
                "SELECT dispatch_sequence, event_type FROM outbox_messages "
                "ORDER BY dispatch_sequence"
            )
        ).all()
    assert rows == [(1, "job.accepted.v2"), (2, "job.retry_scheduled.v1")]


def test_retry_route_enforces_csrf_and_missing_resource_boundary(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    missing_csrf = collection_job_client.post(f"/api/jobs/{uuid4()}/retry")
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "csrf_invalid"

    missing_job = collection_job_client.post(
        f"/api/jobs/{uuid4()}/retry",
        headers=_csrf_headers(collection_job_client),
    )
    assert missing_job.status_code == 404
    assert missing_job.json()["code"] == "resource_not_found"


def test_public_submission_rejects_unregistered_job_kinds(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)
    payload = _payload()
    payload["kind"] = "arbitrary.command"

    response = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 0


def test_public_submission_rejects_job_kind_without_worker_handler(
    collection_job_client: TestClient,
) -> None:
    _user_scope(collection_job_client)

    response = collection_job_client.post(
        "/api/jobs",
        headers=_csrf_headers(collection_job_client),
        json=_payload(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    factory = collection_job_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 0


def test_job_openapi_contract_is_generated_from_runtime_routes(
    collection_job_client: TestClient,
) -> None:
    schema = collection_job_client.get("/openapi.json").json()
    create_operation = schema["paths"]["/api/jobs"]["post"]
    get_operation = schema["paths"]["/api/jobs/{job_id}"]["get"]
    cancel_operation = schema["paths"]["/api/jobs/{job_id}/cancel"]["post"]
    retry_operation = schema["paths"]["/api/jobs/{job_id}/retry"]["post"]

    assert create_operation["operationId"] == "createCollectionJob"
    assert "200" not in create_operation["responses"]
    assert create_operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JobAcceptedView"
    }
    assert create_operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WebPageCollectionJobInput"
    }
    assert "CollectionJobInput" not in schema["components"]["schemas"]
    assert get_operation["operationId"] == "getCollectionJob"
    assert get_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JobStatusView"
    }
    assert create_operation.get("security")
    assert get_operation.get("security")
    assert cancel_operation["operationId"] == "cancelCollectionJob"
    assert cancel_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JobStatusView"
    }
    assert cancel_operation.get("security")
    assert retry_operation["operationId"] == "retryCollectionJob"
    assert "200" not in retry_operation["responses"]
    assert retry_operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JobStatusView"
    }
    assert retry_operation.get("security")
    for status_code in ("403", "409", "422", "500", "503"):
        assert create_operation["responses"][status_code]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/ErrorView"}


@pytest.mark.parametrize("kind", ["keyword.search", "source.comments"])
@pytest.mark.parametrize("outcome", [None, "failed", "cancelled", "expired", "succeeded"])
def test_execution_counts_partition_each_round_and_keep_cumulative_distinct(
    collection_job_client: TestClient, kind: str, outcome: str | None
) -> None:
    client = collection_job_client
    owner = _user_scope(client)
    job = uuid4()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        _seed_job(session, owner, job, now)
        session.execute(text("UPDATE jobs SET kind=:kind WHERE id=:id"), {"kind": kind, "id": job})
        for epoch in (1, 2):
            session.execute(
                text(
                    "INSERT INTO job_attempts (id,job_id,lease_epoch,collection_cycle_no,worker_id,"
                    "queued_at,started_at,lease_expires_at,finished_at,outcome,"
                    "collection_counts_tracked,collection_observed_count) VALUES "
                    "(:id,:job,:epoch,1,'test',:now,:now,:expires,:finished,:outcome,true,:observed)"
                ),
                {
                    "id": uuid4(),
                    "job": job,
                    "epoch": epoch,
                    "now": now,
                    "expires": now + timedelta(seconds=60),
                    "finished": now if epoch == 1 or outcome else None,
                    "outcome": "failed" if epoch == 1 else outcome,
                    "observed": 6 if epoch == 1 else 8,
                },
            )
        # Round two: one new, one updated, one unchanged, one insufficient identity.
        for index in range(4):
            content, v1, v2 = uuid4(), uuid4(), uuid4()
            _seed_content(session, owner, content, (v1, v2), now)
            if index != 0:
                _seed_observation(session, owner, job, content, None if index == 3 else v1, now)
                session.execute(
                    text("UPDATE content_observations SET execution_epoch=1 WHERE content_id=:id"),
                    {"id": content},
                )
            for offset in (1, 2):
                _seed_observation(
                    session,
                    owner,
                    job,
                    content,
                    None if index == 3 else v2 if index == 1 else v1,
                    now + timedelta(seconds=offset),
                )
            session.execute(
                text(
                    "UPDATE content_observations SET execution_epoch=2 "
                    "WHERE content_id=:id AND received_at>:now"
                ),
                {"id": content, "now": now},
            )
        before = (
            session.execute(
                text("SELECT row_to_json(a)::text FROM job_attempts a ORDER BY lease_epoch")
            )
            .scalars()
            .all()
        )
    response = client.get(f"/api/jobs/{job}")
    assert response.status_code == 200, response.json()
    body = response.json()
    second, first = body["collection_executions"]
    assert second["execution_epoch"] == 2 and second["collection_cycle_no"] == 1
    assert second["outcome"] == outcome
    counts = second["counts"]
    assert counts["observed_count"] == 8 and counts["stored_observation_count"] == 8
    assert counts["unique_content_count"] == 4
    assert [
        counts[name]
        for name in ("inserted_count", "updated_count", "unchanged_count", "unclassified_count")
    ] == [0, 0, 0, 4]
    assert first["counts"]["inserted_count"] == 0
    assert first["counts"]["unclassified_count"] == 3
    assert body["collection_counts"]["inserted_count"] == 0
    assert body["collection_counts"]["unclassified_count"] == 4
    assert body["collection_counts"]["updated_count"] == 0
    assert body["collection_executions_has_more"] is False
    assert (
        client.get(f"/api/jobs/{job}").json()["collection_executions"]
        == body["collection_executions"]
    )
    with factory() as session:
        assert (
            session.execute(
                text("SELECT row_to_json(a)::text FROM job_attempts a ORDER BY lease_epoch")
            )
            .scalars()
            .all()
            == before
        )
    authenticate_test_client(client)
    assert client.get(f"/api/jobs/{job}").status_code == 404


def test_execution_history_is_bounded_and_legacy_counts_remain_unknown(
    collection_job_client: TestClient,
) -> None:
    client = collection_job_client
    owner, job = _user_scope(client), uuid4()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        _seed_job(session, owner, job, now)
    assert client.get(f"/api/jobs/{job}").json()["collection_executions"] == []
    with factory.begin() as session:
        for epoch in range(1, 23):
            session.execute(
                text(
                    "INSERT INTO job_attempts (id,job_id,lease_epoch,collection_cycle_no,worker_id,"
                    "queued_at,started_at,lease_expires_at,collection_counts_tracked) "
                    "VALUES (:id,:job,:epoch,1,'test',:now,:now,:expires,:tracked)"
                ),
                {
                    "id": uuid4(),
                    "job": job,
                    "epoch": epoch,
                    "now": now,
                    "expires": now + timedelta(seconds=60),
                    "tracked": epoch != 21,
                },
            )
    body = client.get(f"/api/jobs/{job}").json()
    assert len(body["collection_executions"]) == 20
    assert body["collection_executions_has_more"] is True
    assert body["collection_executions"][0]["execution_epoch"] == 22
    assert body["collection_executions"][-1]["execution_epoch"] == 3
    assert body["collection_executions"][1]["counts"] is None
    counts = body["collection_executions"][0]["counts"]
    assert counts["observed_count"] is None
    assert counts["unique_content_count"] == counts["stored_observation_count"] == 0


def test_fenced_execution_checkpoint_delta_replay_expiry_and_zero(
    collection_job_client: TestClient,
) -> None:
    from jobs.execution import (
        CheckpointConflictError,
        JobExecutionService,
        StaleExecutionLeaseError,
    )

    client = collection_job_client
    owner, job = _user_scope(client), uuid4()
    now = [datetime.now(UTC)]
    factory = client.app.state.session_factory
    with factory.begin() as session:
        _seed_job(session, owner, job, now[0])
    with factory() as session:
        execution = JobExecutionService(session, lease_seconds=5, clock=lambda: now[0])
        first = execution.acquire(job_id=job, worker_id="first")
        first = execution.save_checkpoint(
            first, sequence=1, checkpoint={"collection.observed_count": 3}, observed_items=3
        )
        replay = execution.save_checkpoint(first, sequence=1, checkpoint=first.checkpoint)
        assert replay.checkpoint_sequence == 1
        now[0] += timedelta(seconds=6)
        second = execution.acquire(job_id=job, worker_id="second")
        with pytest.raises(StaleExecutionLeaseError):
            execution.save_checkpoint(
                first, sequence=2, checkpoint={"collection.observed_count": 99}
            )
        with pytest.raises(CheckpointConflictError):
            execution.save_checkpoint(
                second, sequence=2, checkpoint={"collection.observed_count": 2}, observed_items=0
            )
        second = execution.save_checkpoint(
            second, sequence=2, checkpoint={"collection.observed_count": 3}, observed_items=0
        )
        second = execution.save_checkpoint(
            second, sequence=3, checkpoint={"collection.observed_count": 5}, observed_items=2
        )
    body = client.get(f"/api/jobs/{job}").json()
    second_view, first_view = body["collection_executions"]
    assert second_view["collection_cycle_no"] == first_view["collection_cycle_no"] == 1
    assert second_view["counts"]["observed_count"] == 2
    assert first_view["counts"]["observed_count"] == 3
    assert first_view["outcome"] == "expired"


def test_observation_replay_preserves_original_execution_and_rejects_unknown_epoch(
    collection_job_client: TestClient,
) -> None:
    from sqlalchemy.exc import IntegrityError

    from content.services import ContentService

    client = collection_job_client
    owner, job, content, version, operation = (uuid4() for _ in range(5))
    owner = _user_scope(client)
    now = datetime(2026, 10, 1, tzinfo=UTC)
    factory = client.app.state.session_factory
    with factory.begin() as session:
        _seed_job(session, owner, job, now)
        _seed_content(session, owner, content, (version,), now)
        for epoch in (1, 2):
            session.execute(
                text(
                    "INSERT INTO job_attempts (id,job_id,lease_epoch,collection_cycle_no,worker_id,"
                    "queued_at,started_at,lease_expires_at,collection_counts_tracked) "
                    "VALUES (:id,:job,:epoch,1,'test',:now,:now,:expires,true)"
                ),
                {
                    "id": uuid4(),
                    "job": job,
                    "epoch": epoch,
                    "now": now,
                    "expires": now + timedelta(seconds=60),
                },
            )
        service = ContentService(session)
        first = service._find_or_create_observation(
            history_complete=False,
            owner_id=owner,
            content_id=content,
            job_id=job,
            source_operation_id=operation,
            observed_at=now,
            received_at=now,
            execution_epoch=1,
            values={"content_version_id": version},
        )
        replay = service._find_or_create_observation(
            history_complete=False,
            owner_id=owner,
            content_id=content,
            job_id=job,
            source_operation_id=operation,
            observed_at=now,
            received_at=now + timedelta(seconds=1),
            execution_epoch=2,
            values={"content_version_id": version},
        )
        assert first.id == replay.id and replay.execution_epoch == 1
        with pytest.raises(IntegrityError), session.begin_nested():
            service._find_or_create_observation(
                history_complete=False,
                owner_id=owner,
                content_id=content,
                job_id=job,
                source_operation_id=uuid4(),
                observed_at=now,
                received_at=now,
                execution_epoch=99,
                values={"content_version_id": version},
            )
    body = client.get(f"/api/jobs/{job}").json()
    second, first = body["collection_executions"]
    assert second["counts"]["unique_content_count"] == 0
    assert first["counts"]["unique_content_count"] == 1
