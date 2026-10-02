from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import TEST_DATABASE_TRUNCATE, authenticate_test_client, authenticated_owner_id

from core.config import Settings
from core.errors import ApplicationError
from jobs.coverage import CollectionCoverageQueryService
from jobs.schemas import (
    BudgetContext,
    BudgetMetric,
    BudgetPolicyInput,
    BudgetReservationInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetService
from main import create_app

_DATABASE_ENV = "HOTKEY_TEST_DATABASE_URL"
_BASE = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)


@pytest.fixture
def coverage_client() -> Iterator[tuple[TestClient, Engine, UUID]]:
    database_url = os.getenv(_DATABASE_ENV)
    if database_url is None:
        pytest.skip(f"{_DATABASE_ENV} is required for PostgreSQL integration tests")
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


def _connection(engine: Engine, owner_id: UUID, *, source_key: str = "rss_36kr") -> None:
    connection_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_connections "
                "(id, owner_id, source_key, status, current_version, created_at, updated_at) "
                "VALUES (:id, :owner, :source, 'active', 1, :now, :now)"
            ),
            {"id": connection_id, "owner": owner_id, "source": source_key, "now": _BASE},
        )
        connection.execute(
            text(
                "INSERT INTO source_connection_versions "
                "(connection_id, version, owner_id, auth_kind, config, created_by, created_at) "
                "VALUES (:id, 1, :owner, 'none', '{}'::jsonb, :owner, :now)"
            ),
            {"id": connection_id, "owner": owner_id, "now": _BASE},
        )


def _due(
    engine: Engine,
    owner_id: UUID,
    due_at: datetime,
    *,
    state: str = "missed",
    reason: str | None = "scheduler_interrupted",
    job_id: UUID | None = None,
    operation_id: UUID | None = None,
    source_key: str = "rss_36kr",
    capability: str = "search",
    topic_id: UUID | None = None,
) -> UUID:
    window_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO collection_due_windows "
                "(id, owner_id, schedule_key, topic_id, source_key, capability, due_at, "
                "window_start, window_end, connection_version, admission_state, reason, "
                "operation_id, job_id, recorded_at) VALUES "
                "(:id, :owner, :schedule, :topic, :source, :capability, :due_at, "
                ":window_start, :due_at, 1, :state, :reason, :operation, :job, :due_at)"
            ),
            {
                "id": window_id,
                "owner": owner_id,
                "schedule": uuid4(),
                "topic": topic_id,
                "source": source_key,
                "capability": capability,
                "due_at": due_at,
                "window_start": due_at - timedelta(minutes=30),
                "state": state,
                "reason": reason,
                "operation": operation_id,
                "job": job_id,
            },
        )
    return window_id


def _accepted_job(
    engine: Engine,
    owner_id: UUID,
    due_at: datetime,
    *,
    status: str,
    requests_sent: int,
    error_code: str | None = None,
    source_key: str = "rss_36kr",
    capability: str = "search",
    kind: str = "keyword.search",
    topic_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    job_id, operation_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs "
                "(id, owner_id, operation_id, kind, configuration_ref, configuration_version, "
                "source_key, source_capability, scope, request_fingerprint, status, "
                "requests_sent, progress_stage, progress_updated_at, started_at, completed_at, "
                "last_error_code, last_error_category, last_error_at, next_action, "
                "created_at, updated_at) VALUES "
                "(:id, :owner, :operation, :kind, :configuration_ref, 1, "
                ":source, :capability, CAST(:scope AS jsonb), :fingerprint, "
                ":status, :requests, :stage, :progress_at, :started_at, :completed_at, "
                ":error_code, :error_category, :error_at, :next_action, :created_at, :completed_at)"
            ),
            {
                "id": job_id,
                "owner": owner_id,
                "operation": operation_id,
                "fingerprint": job_id.bytes * 2,
                "scope": json.dumps(
                    {
                        "connection_version": 1,
                        "target_hash": job_id.bytes.hex() * 2,
                        "sort_key": "latest",
                        "rule_version": 1,
                        "scan_kind": "new_scan",
                    }
                ),
                "status": status,
                "source": source_key,
                "capability": capability,
                "kind": kind,
                "configuration_ref": f"topic:{topic_id}" if topic_id else "coverage:test",
                "requests": requests_sent,
                "stage": "request" if requests_sent else None,
                "progress_at": due_at if requests_sent else None,
                "started_at": due_at,
                "completed_at": due_at + timedelta(seconds=1),
                "error_code": error_code,
                "error_category": "transient" if error_code else None,
                "error_at": due_at if error_code else None,
                "next_action": "retry" if error_code else None,
                "created_at": due_at,
            },
        )
    return _due(
        engine,
        owner_id,
        due_at,
        state="accepted",
        reason=None,
        job_id=job_id,
        operation_id=operation_id,
        source_key=source_key,
        capability=capability,
        topic_id=topic_id,
    ), job_id


def _coverage(
    engine: Engine,
    owner_id: UUID,
    job_id: UUID,
    due_at: datetime,
    *,
    status: str,
    stop_reason: str | None,
    pages: int,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO coverage_windows "
                "(id, owner_id, source_key, capability, target_hash, sort_key, rule_version, "
                "starts_at, ends_at, status, stop_reason, last_job_id, page_count, "
                "created_at, updated_at) VALUES "
                "(:id, :owner, 'rss_36kr', 'search', :target_hash, 'latest', 1, "
                ":starts_at, :ends_at, :status, :reason, :job, :pages, :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "target_hash": job_id.bytes * 2,
                "starts_at": starts_at or due_at - timedelta(minutes=30),
                "ends_at": ends_at or due_at,
                "status": status,
                "reason": stop_reason,
                "job": job_id,
                "pages": pages,
                "now": due_at,
            },
        )


def _settle_request(
    engine: Engine,
    owner_id: UUID,
    job_id: UUID,
    at: datetime,
    *,
    source_key: str = "rss_36kr",
    outcome: UsageOutcome = UsageOutcome.SUCCEEDED,
) -> None:
    with engine.begin() as connection:
        operation_id = connection.execute(
            text("SELECT operation_id FROM jobs WHERE id=:job"), {"job": job_id}
        ).scalar_one()
    sessions = sessionmaker[Session](engine, expire_on_commit=False)
    with sessions() as session:
        budget = ResourceBudgetService(session, clock=lambda: at)
        budget.save_component_policy(
            owner_id=owner_id,
            command=ComponentPolicyInput(
                component_key=f"collector.{source_key}",
                component_version="1",
                cost_class=CostClass.LOCAL,
                enabled_for_core=True,
                terms_reference="https://example.invalid/terms",
                reviewed_at=at,
            ),
        )
        for key, scope, reference in (
            ("global.coverage.requests", BudgetScopeKind.GLOBAL, None),
            (f"source.{source_key}.network.daily", BudgetScopeKind.SOURCE, source_key),
        ):
            budget.save_budget_policy(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key=key,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=scope,
                    scope_reference=reference,
                    limit_units=10,
                    window_seconds=86_400,
                    window_anchor_at=_BASE,
                    enabled=True,
                ),
            )
        attempt_id = uuid4()
        with session.begin():
            budget.reserve_budget_in_transaction(
                owner_id=owner_id,
                command=BudgetReservationInput(
                    reservation_id=attempt_id,
                    operation_id=operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(source_ref=source_key, job_ref=f"job:{job_id.hex}"),
                ),
            )
            budget.begin_attempt_in_transaction(
                owner_id=owner_id,
                command=UsageAttemptInput(
                    attempt_id=attempt_id,
                    operation_id=operation_id,
                    component_key=f"collector.{source_key}",
                    usage_kind=UsageKind.NETWORK_REQUEST,
                    stage="search.request",
                    started_at=at,
                ),
            )
            budget.settle_budget_reservation_in_transaction(
                owner_id=owner_id, reservation_id=attempt_id, actual_units=1
            )
            budget.finish_attempt_in_transaction(
                owner_id=owner_id,
                attempt_id=attempt_id,
                outcome=outcome,
                finished_at=at + timedelta(seconds=1),
            )


def test_coverage_http_projects_gaps_and_paginates_without_owner_leak(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    missed = _due(engine, owner_id, _BASE + timedelta(minutes=1))
    failed, _ = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=2),
        status="failed",
        requests_sent=1,
        error_code="source_rate_limited",
    )
    partial, partial_job = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=3),
        status="partially_succeeded",
        requests_sent=1,
    )
    _coverage(
        engine,
        owner_id,
        partial_job,
        _BASE + timedelta(minutes=3),
        status="partial",
        stop_reason="unverified_terminal",
        pages=1,
    )
    complete, complete_job = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=4),
        status="succeeded",
        requests_sent=1,
    )
    _coverage(
        engine,
        owner_id,
        complete_job,
        _BASE + timedelta(minutes=4),
        status="confirmed",
        stop_reason=None,
        pages=2,
    )
    _settle_request(engine, owner_id, complete_job, _BASE + timedelta(minutes=4))
    hidden = _due(engine, owner_id, _BASE + timedelta(minutes=5), source_key="google_news")

    params = {
        "start": _BASE.isoformat(),
        "end": (_BASE + timedelta(minutes=10)).isoformat(),
        "source_key": "rss_36kr",
        "capability": "search",
        "limit": 2,
    }
    first = client.get("/api/collection-coverage", params=params)
    assert first.status_code == 200, first.json()
    assert first.headers["cache-control"] == "no-store"
    assert [item["window_id"] for item in first.json()["items"]] == [str(complete), str(partial)]
    assert first.json()["items"][0]["coverage_status"] == "complete"
    assert first.json()["items"][0]["terminal_evidence"] == "verified_terminal"
    assert first.json()["items"][0]["page_count"] == 2
    assert first.json()["next_cursor"] != str(partial)
    assert len(first.json()["next_cursor"]) == 44
    assert first.json()["items"][1]["coverage_status"] == "partial"
    assert first.json()["items"][1]["gaps"][0]["reason"] == "unverified_terminal"

    # An inserted newer due point does not shift the already returned cursor boundary.
    _due(engine, owner_id, _BASE + timedelta(minutes=4, seconds=30))
    second = client.get(
        "/api/collection-coverage", params={**params, "cursor": first.json()["next_cursor"]}
    )
    assert second.status_code == 200, second.json()
    assert [item["window_id"] for item in second.json()["items"]] == [str(failed), str(missed)]
    assert second.json()["next_cursor"] is None
    assert second.json()["items"][0]["coverage_status"] == "failed"
    assert second.json()["items"][0]["stop_reason"] == "source_rate_limited"
    assert second.json()["items"][0]["page_count"] is None
    assert second.json()["items"][1]["coverage_status"] == "not_attempted"
    assert second.json()["items"][1]["request_count"] is None
    assert second.json()["items"][1]["content_ids"] is None
    assert second.json()["items"][1]["gaps"][0]["reason"] == "scheduler_interrupted"
    assert (
        client.get(
            "/api/collection-coverage",
            params={
                **params,
                "end": (_BASE + timedelta(minutes=9)).isoformat(),
                "cursor": first.json()["next_cursor"],
            },
        ).status_code
        == 422
    )
    tampered_cursor = first.json()["next_cursor"][:-1] + (
        "A" if first.json()["next_cursor"][-1] != "A" else "B"
    )
    assert (
        client.get(
            "/api/collection-coverage", params={**params, "cursor": tampered_cursor}
        ).status_code
        == 422
    )
    assert client.get(f"/api/collection-coverage/{hidden}").status_code == 404
    assert client.get(f"/api/collection-coverage/{complete}").status_code == 200
    with sessionmaker[Session](engine)() as session:
        with session.begin(), pytest.raises(ApplicationError) as forbidden:
            CollectionCoverageQueryService(session).get_coverage(
                owner_id=uuid4(), window_id=complete
            )
        assert forbidden.value.code == "resource_not_found"
    assert (
        client.get("/api/collection-coverage", params={**params, "cursor": str(hidden)}).status_code
        == 422
    )
    assert (
        client.get(
            "/api/collection-coverage", params={**params, "cursor": str(uuid4())}
        ).status_code
        == 422
    )


def test_coverage_http_deduplicates_content_and_keeps_source_budget_separate(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    first_window, first_job = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=1),
        status="partially_succeeded",
        requests_sent=1,
    )
    second_at = _BASE + timedelta(minutes=2)
    second_window, second_job = _accepted_job(
        engine, owner_id, second_at, status="partially_succeeded", requests_sent=1
    )
    content_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO content_records "
                "(id, owner_id, source_key, object_type, external_id, created_at) "
                "VALUES (:id, :owner, 'rss_36kr', 'post', :external_id, :now)"
            ),
            {"id": content_id, "owner": owner_id, "external_id": content_id.hex, "now": _BASE},
        )
        for job_id, observed_at in (
            (first_job, _BASE + timedelta(minutes=1)),
            (second_job, second_at),
        ):
            connection.execute(
                text(
                    "INSERT INTO content_observations "
                    "(id, owner_id, content_id, job_id, source_operation_id, "
                    "observed_at, received_at) VALUES "
                    "(:id, :owner, :content, :job, :operation, :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "owner": owner_id,
                    "content": content_id,
                    "job": job_id,
                    "operation": uuid4(),
                    "at": observed_at,
                },
            )
        operation_id = connection.execute(
            text("SELECT operation_id FROM jobs WHERE id=:job"), {"job": second_job}
        ).scalar_one()
    sessions = sessionmaker[Session](engine, expire_on_commit=False)
    with sessions() as session:
        budget = ResourceBudgetService(session, clock=lambda: second_at)
        budget.save_component_policy(
            owner_id=owner_id,
            command=ComponentPolicyInput(
                component_key="collector.rss_36kr",
                component_version="1",
                cost_class=CostClass.LOCAL,
                enabled_for_core=True,
                terms_reference="https://example.invalid/terms",
                reviewed_at=second_at,
            ),
        )
        for key, scope, reference in (
            ("global.coverage.requests", BudgetScopeKind.GLOBAL, None),
            ("source.rss_36kr.network.daily", BudgetScopeKind.SOURCE, "rss_36kr"),
        ):
            budget.save_budget_policy(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key=key,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=scope,
                    scope_reference=reference,
                    limit_units=10,
                    window_seconds=86_400,
                    window_anchor_at=_BASE,
                    enabled=True,
                ),
            )
        attempt_id = uuid4()
        with session.begin():
            budget.reserve_budget_in_transaction(
                owner_id=owner_id,
                command=BudgetReservationInput(
                    reservation_id=attempt_id,
                    operation_id=operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(source_ref="rss_36kr", job_ref=f"job:{second_job.hex}"),
                ),
            )
            budget.begin_attempt_in_transaction(
                owner_id=owner_id,
                command=UsageAttemptInput(
                    attempt_id=attempt_id,
                    operation_id=operation_id,
                    component_key="collector.rss_36kr",
                    usage_kind=UsageKind.NETWORK_REQUEST,
                    stage="search.request",
                    started_at=second_at,
                ),
            )
            budget.settle_budget_reservation_in_transaction(
                owner_id=owner_id, reservation_id=attempt_id, actual_units=1
            )
            budget.finish_attempt_in_transaction(
                owner_id=owner_id,
                attempt_id=attempt_id,
                outcome=UsageOutcome.SUCCEEDED,
                finished_at=second_at + timedelta(seconds=1),
            )
    _settle_request(engine, owner_id, second_job, second_at + timedelta(seconds=2))
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET requests_sent=2 WHERE id=:job"), {"job": second_job}
        )
    result = client.get(f"/api/collection-coverage/{second_window}")
    assert result.status_code == 200, result.json()
    view = result.json()
    assert view["request_count"] == view["request_attempt_count"] == 2
    assert view["content_ids"] == [str(content_id)]
    assert view["inserted_count"] == 0
    assert view["deduplicated_count"] == 1
    assert view["analysis"] is None
    assert view["last_success_at"] is None
    assert {item["budget_key"]: item["consumed_units"] for item in view["budgets"]} == {
        "global.coverage.requests": 2,
        "source.rss_36kr.network.daily": 2,
    }
    first = client.get(f"/api/collection-coverage/{first_window}")
    assert first.status_code == 200
    assert first.json()["inserted_count"] == 1


def test_coverage_http_requires_full_confirmed_range_and_reconciled_request(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    due_at = _BASE + timedelta(minutes=40)
    window_id, job_id = _accepted_job(engine, owner_id, due_at, status="succeeded", requests_sent=1)
    _coverage(
        engine,
        owner_id,
        job_id,
        due_at,
        status="confirmed",
        stop_reason=None,
        pages=1,
        ends_at=due_at - timedelta(minutes=20),
    )
    _settle_request(engine, owner_id, job_id, due_at)
    response = client.get(f"/api/collection-coverage/{window_id}")
    assert response.status_code == 200, response.json()
    view = response.json()
    assert view["coverage_status"] == "partial"
    assert view["terminal_evidence"] == "unverified_terminal"
    assert view["gaps"] == [
        {
            "starts_at": (due_at - timedelta(minutes=20)).isoformat().replace("+00:00", "Z"),
            "ends_at": due_at.isoformat().replace("+00:00", "Z"),
            "reason": "unverified_terminal",
        }
    ]

    # The same fully covered due still needs a matching usage and budget ledger.
    unreconciled_at = due_at + timedelta(minutes=1)
    another_window, another_job = _accepted_job(
        engine, owner_id, unreconciled_at, status="succeeded", requests_sent=1
    )
    _coverage(
        engine,
        owner_id,
        another_job,
        unreconciled_at,
        status="confirmed",
        stop_reason=None,
        pages=1,
    )
    unreconciled = client.get(f"/api/collection-coverage/{another_window}")
    assert unreconciled.status_code == 200, unreconciled.json()
    assert unreconciled.json()["coverage_status"] == "partial"
    assert unreconciled.json()["terminal_evidence"] == "unverified_terminal"
    assert unreconciled.json()["gaps"][0]["reason"] == "request_budget_unreconciled"


def test_coverage_http_does_not_count_network_success_as_collection_success(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    due_at = _BASE + timedelta(minutes=1)
    window_id, job_id = _accepted_job(
        engine,
        owner_id,
        due_at,
        status="failed",
        requests_sent=1,
        error_code="source_parse_error",
    )
    _settle_request(engine, owner_id, job_id, due_at)
    response = client.get(f"/api/collection-coverage/{window_id}")
    assert response.status_code == 200, response.json()
    assert response.json()["coverage_status"] == "failed"
    assert response.json()["last_success_at"] is None


def test_coverage_http_reuses_confirmed_scope_without_recounting_prior_job_pages(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    due_at = _BASE + timedelta(minutes=30)
    _, first_job = _accepted_job(engine, owner_id, due_at, status="succeeded", requests_sent=1)
    _coverage(
        engine,
        owner_id,
        first_job,
        due_at,
        status="confirmed",
        stop_reason=None,
        pages=2,
    )
    _settle_request(engine, owner_id, first_job, due_at)
    reused_window, reused_job = _accepted_job(
        engine, owner_id, due_at, status="succeeded", requests_sent=0
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET scope=CAST(:scope AS jsonb) WHERE id=:job"),
            {
                "job": reused_job,
                "scope": json.dumps(
                    {
                        "connection_version": 1,
                        "target_hash": first_job.bytes.hex() * 2,
                        "sort_key": "latest",
                        "rule_version": 1,
                        "scan_kind": "new_scan",
                    }
                ),
            },
        )
    response = client.get(f"/api/collection-coverage/{reused_window}")
    assert response.status_code == 200, response.json()
    assert response.json()["coverage_status"] == "complete"
    assert response.json()["terminal_evidence"] == "verified_terminal"
    assert response.json()["gaps"] == []
    assert response.json()["page_count"] == 0
    assert response.json()["request_count"] == 0


def test_coverage_http_distinguishes_empty_hotlist_snapshot_from_failure(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id, source_key="hotlist_36kr")
    empty_window, empty_job = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=1),
        status="succeeded",
        requests_sent=1,
        source_key="hotlist_36kr",
        capability="hotlist",
        kind="source.hotlist",
    )
    failed_window, _ = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=2),
        status="failed",
        requests_sent=1,
        error_code="hotlist_upstream_error",
        source_key="hotlist_36kr",
        capability="hotlist",
        kind="source.hotlist",
    )
    snapshot_id = uuid4()
    observed_at = _BASE + timedelta(minutes=1, seconds=1)
    with engine.begin() as connection:
        operation_id = connection.execute(
            text("SELECT operation_id FROM jobs WHERE id=:job"), {"job": empty_job}
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO hotlist_snapshots "
                "(id, owner_id, source_key, job_id, operation_id, observed_at, entry_count) "
                "VALUES (:id, :owner, 'hotlist_36kr', :job, :operation, :at, 0)"
            ),
            {
                "id": snapshot_id,
                "owner": owner_id,
                "job": empty_job,
                "operation": operation_id,
                "at": observed_at,
            },
        )
    _settle_request(
        engine,
        owner_id,
        empty_job,
        _BASE + timedelta(minutes=1),
        source_key="hotlist_36kr",
        outcome=UsageOutcome.EMPTY,
    )
    empty = client.get(f"/api/collection-coverage/{empty_window}")
    failed = client.get(f"/api/collection-coverage/{failed_window}")
    assert empty.status_code == failed.status_code == 200
    assert empty.json()["coverage_status"] == "empty"
    assert empty.json()["terminal_evidence"] == "snapshot_observed"
    assert empty.json()["observed_count"] == 0
    assert empty.json()["page_count"] == 1
    assert empty.json()["snapshot_ids"] == [str(snapshot_id)]
    assert failed.json()["coverage_status"] == "failed"
    assert failed.json()["snapshot_ids"] == []
    assert failed.json()["observed_count"] is None


def test_coverage_http_keeps_analysis_anomaly_separate_from_unknown(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    topic_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner, 'coverage topic', 'paused', 'pending_source_selection', 1, :at, :at)"
            ),
            {"id": topic_id, "owner": owner_id, "at": _BASE},
        )
        connection.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:topic, 1, :owner, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :at)"
            ),
            {"topic": topic_id, "owner": owner_id, "at": _BASE},
        )
    window_id, collection_job_id = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=1),
        status="partially_succeeded",
        requests_sent=1,
        topic_id=topic_id,
    )
    contents = (uuid4(), uuid4(), uuid4())
    versions = (uuid4(), uuid4(), uuid4())
    call_id = uuid4()
    with engine.begin() as connection:
        for content_id, version_id in zip(contents, versions, strict=True):
            connection.execute(
                text(
                    "INSERT INTO content_records "
                    "(id, owner_id, source_key, object_type, external_id, created_at) "
                    "VALUES (:id, :owner, 'rss_36kr', 'post', :external_id, :at)"
                ),
                {"id": content_id, "owner": owner_id, "external_id": content_id.hex, "at": _BASE},
            )
            connection.execute(
                text(
                    "INSERT INTO content_versions "
                    "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                    "title, created_at) VALUES "
                    "(:id, :owner, :content, :fingerprint, 'full', 'source', 'title', :at)"
                ),
                {
                    "id": version_id,
                    "owner": owner_id,
                    "content": content_id,
                    "fingerprint": version_id.bytes * 2,
                    "at": _BASE,
                },
            )
        for content_id, version_id in zip(contents[:2], versions[:2], strict=True):
            connection.execute(
                text(
                    "INSERT INTO content_observations "
                    "(id, owner_id, content_id, job_id, source_operation_id, "
                    "content_version_id, observed_at, received_at) VALUES "
                    "(:id, :owner, :content, :job, :operation, :version, :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "owner": owner_id,
                    "content": content_id,
                    "job": collection_job_id,
                    "operation": uuid4(),
                    "version": version_id,
                    "at": _BASE + timedelta(minutes=1),
                },
            )
        connection.execute(
            text(
                "INSERT INTO jobs "
                "(id, owner_id, operation_id, kind, configuration_ref, configuration_version, "
                "scope, request_fingerprint, status, created_at, updated_at) VALUES "
                "(:id, :owner, :operation, 'analysis.annotate', :ref, 1, "
                "CAST(:scope AS jsonb), :fingerprint, 'queued', :at, :at)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "operation": uuid4(),
                "ref": f"topic:{topic_id}",
                "scope": json.dumps(
                    {
                        "topic_id": str(topic_id),
                        "topic_rule_version": 1,
                        "prompt_version": "v1",
                        "content_version_ids": json.dumps([str(item) for item in versions[:2]]),
                    }
                ),
                "fingerprint": b"a" * 32,
                "at": _BASE,
            },
        )
        connection.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, "
                "output_tokens, reasoning_output_tokens, duration_ms, created_at) "
                "VALUES (:id, :owner, 'analysis.annotate', 'test', 'test-model', 'v1', "
                ":fingerprint, 'succeeded', 0, 0, 0, 0, 0, :at)"
            ),
            {"id": call_id, "owner": owner_id, "fingerprint": b"b" * 32, "at": _BASE},
        )
        connection.execute(
            text(
                "INSERT INTO content_annotations "
                "(id, owner_id, content_id, content_version_id, topic_id, "
                "topic_rule_version, prompt_version, viewpoints, ai_call_id, status, "
                "result_state, error_code, diagnostic_history, created_at, updated_at) "
                "VALUES (:id, :owner, :content, :version, :topic, 1, 'v1', "
                "'[]'::jsonb, :call, 'unanalyzed', 'invalid', 'invalid_output', "
                "'[]'::jsonb, :at, :at)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "content": contents[0],
                "version": versions[0],
                "topic": topic_id,
                "call": call_id,
                "at": _BASE,
            },
        )
    known = client.get(f"/api/collection-coverage/{window_id}")
    assert known.status_code == 200, known.json()
    assert known.json()["analysis"] == {
        "pending_count": 1,
        "failed_count": 0,
        "invalid_count": 1,
        "valid_count": 0,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO content_observations "
                "(id, owner_id, content_id, job_id, source_operation_id, "
                "content_version_id, observed_at, received_at) VALUES "
                "(:id, :owner, :content, :job, :operation, :version, :at, :at)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "content": contents[2],
                "job": collection_job_id,
                "operation": uuid4(),
                "version": versions[2],
                "at": _BASE + timedelta(minutes=1),
            },
        )
    unknown = client.get(f"/api/collection-coverage/{window_id}")
    assert unknown.status_code == 200
    assert unknown.json()["analysis"] is None


def test_coverage_http_keeps_pending_skipped_stopped_and_budget_gap_distinct(
    coverage_client: tuple[TestClient, Engine, UUID],
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    pending = _due(engine, owner_id, _BASE + timedelta(minutes=1), state="pending", reason=None)
    skipped = _due(engine, owner_id, _BASE + timedelta(minutes=2), state="skipped", reason="budget")
    stopped, _ = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=3),
        status="cancelled",
        requests_sent=0,
    )
    limited, limited_job = _accepted_job(
        engine,
        owner_id,
        _BASE + timedelta(minutes=4),
        status="partially_succeeded",
        requests_sent=1,
    )
    _coverage(
        engine,
        owner_id,
        limited_job,
        _BASE + timedelta(minutes=4),
        status="partial",
        stop_reason="budget_exhausted",
        pages=1,
    )
    expected = {
        pending: ("pending", "pending", None),
        skipped: ("not_attempted", "budget", None),
        stopped: ("stopped", "stopped", 0),
        limited: ("partial", "budget_exhausted", 1),
    }
    for window_id, (status, reason, requests) in expected.items():
        response = client.get(f"/api/collection-coverage/{window_id}")
        assert response.status_code == 200, response.json()
        view = response.json()
        assert view["coverage_status"] == status
        assert view["gaps"][0]["reason"] == reason
        assert view["request_count"] == requests


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-09-27T00:00:00Z", "2026-09-27T00:00:00Z"),
        ("2026-09-27T00:00:00Z", "2026-10-29T00:00:00Z"),
        ("2026-09-27T00:00:00", "2026-09-28T00:00:00Z"),
    ],
)
def test_coverage_http_rejects_invalid_ranges(
    coverage_client: tuple[TestClient, Engine, UUID], start: str, end: str
) -> None:
    client, engine, owner_id = coverage_client
    _connection(engine, owner_id)
    response = client.get("/api/collection-coverage", params={"start": start, "end": end})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
