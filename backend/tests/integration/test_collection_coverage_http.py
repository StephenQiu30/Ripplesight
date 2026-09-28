from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from api.dependencies import require_identity_session
from connections.schemas import SourceExecutionPolicy
from core.config import Settings
from identity.services import IdentityService
from jobs.coverage import CollectionDueWindowService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetPolicyInput,
    BudgetReservationInput,
    BudgetScopeKind,
    CollectionDueWindowInput,
    ComponentPolicyInput,
    CostClass,
    DueSkipReason,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetService
from main import create_app
from sources.contracts import SourceCapability

_BOOTSTRAP_TOKEN = "bootstrap-token-used-only-by-the-isolated-test"


@pytest.fixture
def coverage_client() -> Iterator[tuple[TestClient, UUID, datetime]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE identity_users CASCADE"))
    app = create_app(
        Settings(
            environment="test",
            log_level="WARNING",
            database_url=database_url,
            bootstrap_token=_BOOTSTRAP_TOKEN,
        )
    )
    try:
        with TestClient(app) as client:
            initialized = client.post(
                "/api/identity/initialize",
                headers={"X-HotKey-Bootstrap-Token": _BOOTSTRAP_TOKEN, "X-HotKey-CSRF": "1"},
                json={"username": "coverage-owner", "password": "correct horse battery staple"},
            )
            assert initialized.status_code == 201
            yield client, UUID(initialized.json()["user"]["id"]), datetime.now(UTC)
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE identity_users CASCADE"))
        engine.dispose()


def _record_due(
    client: TestClient,
    owner_id: UUID,
    due_at: datetime,
    *,
    capability: SourceCapability = SourceCapability.SEARCH,
    topic_id: UUID | None = None,
) -> UUID:
    policy = SourceExecutionPolicy(
        min_interval_seconds=3600,
        quiet_windows=(),
        max_queries=1,
        max_items_per_query=5,
        max_requests=26,
        max_seconds=220,
        hard_timeout_seconds=240,
        max_concurrency=1,
        enabled=True,
    )
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        return (
            CollectionDueWindowService(session)
            .record_due_in_transaction(
                CollectionDueWindowInput(
                    owner_id=owner_id,
                    schedule_key=uuid4(),
                    topic_id=topic_id,
                    source_key="bilibili",
                    capability=capability,
                    due_at=due_at,
                    window_start=due_at - timedelta(hours=6),
                    window_end=due_at,
                    connection_version=2,
                    policy_snapshot=policy,
                )
            )
            .id
        )


def _accept_hotlist_job(
    client: TestClient,
    owner_id: UUID,
    window_id: UUID,
    *,
    status: str,
    observed_count: int | None,
    completed_at: datetime,
) -> UUID:
    job_id, operation_id = uuid4(), uuid4()
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        due = session.execute(
            text("SELECT schedule_key, due_at FROM collection_due_windows WHERE id = :id"),
            {"id": window_id},
        ).one()
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, created_at, updated_at) VALUES "
                "(:id, :owner_id, :operation_id, 'source.hotlist', 'coverage:test', "
                "1, 'bilibili', 'hotlist', CAST(:scope AS jsonb), :fingerprint, :now, :now)"
            ),
            {
                "id": job_id,
                "owner_id": owner_id,
                "operation_id": operation_id,
                "fingerprint": b"h" * 32,
                "scope": '{"connection_version":2}',
                "now": completed_at,
            },
        )
        CollectionDueWindowService(session).mark_accepted_in_transaction(
            owner_id=owner_id,
            schedule_key=due.schedule_key,
            due_at=due.due_at,
            operation_id=operation_id,
            job_id=job_id,
        )
        session.execute(
            text(
                "UPDATE jobs SET status = :status, completed_at = :now, "
                "checkpoint = CAST(:checkpoint AS jsonb) WHERE id = :id"
            ),
            {
                "status": status,
                "now": completed_at,
                "id": job_id,
                "checkpoint": ('{"collection.observed_count":0}' if observed_count == 0 else "{}"),
            },
        )
        if observed_count is not None:
            session.execute(
                text(
                    "INSERT INTO hotlist_snapshots "
                    "(id, owner_id, source_key, job_id, operation_id, due_window_id, "
                    "observed_at, entry_count) VALUES "
                    "(:id, :owner_id, 'bilibili', :job_id, :operation_id, :window_id, "
                    ":now, :entry_count)"
                ),
                {
                    "id": uuid4(),
                    "owner_id": owner_id,
                    "job_id": job_id,
                    "operation_id": operation_id,
                    "window_id": window_id,
                    "now": completed_at,
                    "entry_count": observed_count,
                },
            )
    return job_id


def _create_topic(client: TestClient, owner_id: UUID, now: datetime) -> UUID:
    topic_id = uuid4()
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner_id, 'coverage topic', 'paused', "
                "'pending_source_selection', 1, :now, :now)"
            ),
            {"id": topic_id, "owner_id": owner_id, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:topic_id, 1, :owner_id, '[\"coverage\"]'::jsonb, "
                "'[]'::jsonb, '[]'::jsonb, :now)"
            ),
            {"topic_id": topic_id, "owner_id": owner_id, "now": now},
        )
    return topic_id


def _accept_search_job(
    client: TestClient,
    owner_id: UUID,
    topic_id: UUID,
    window_id: UUID,
    *,
    observed_count: int,
    now: datetime,
) -> tuple[UUID, UUID]:
    job_id, operation_id = uuid4(), uuid4()
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        due = session.execute(
            text(
                "SELECT schedule_key, due_at, window_start, window_end "
                "FROM collection_due_windows WHERE id = :id"
            ),
            {"id": window_id},
        ).one()
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, created_at, updated_at) VALUES "
                "(:id, :owner_id, :operation_id, 'keyword.search', :configuration_ref, "
                "1, 'bilibili', 'search', CAST(:scope AS jsonb), :fingerprint, :now, :now)"
            ),
            {
                "id": job_id,
                "owner_id": owner_id,
                "operation_id": operation_id,
                "configuration_ref": f"topic:{topic_id}",
                "scope": '{"connection_version":2}',
                "fingerprint": job_id.bytes * 2,
                "now": now,
            },
        )
        CollectionDueWindowService(session).mark_accepted_in_transaction(
            owner_id=owner_id,
            schedule_key=due.schedule_key,
            due_at=due.due_at,
            operation_id=operation_id,
            job_id=job_id,
        )
        session.execute(
            text(
                "UPDATE jobs SET status = 'succeeded', started_at = :now, "
                "completed_at = :now, requests_sent = 1, items_saved = :observed_count, "
                "progress_stage = 'save', progress_updated_at = :now, "
                "checkpoint = CAST(:checkpoint AS jsonb) WHERE id = :id"
            ),
            {
                "id": job_id,
                "now": now,
                "observed_count": observed_count,
                "checkpoint": json.dumps({"collection.observed_count": observed_count}),
            },
        )
        session.execute(
            text(
                "INSERT INTO coverage_windows "
                "(id, owner_id, source_key, capability, target_hash, sort_key, "
                "rule_version, starts_at, ends_at, status, last_job_id, "
                "page_count, created_at, updated_at) VALUES "
                "(:id, :owner_id, 'bilibili', 'search', :target_hash, 'latest', "
                "1, :starts_at, :ends_at, 'confirmed', :job_id, 1, :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner_id": owner_id,
                "target_hash": job_id.bytes * 2,
                "starts_at": due.window_start,
                "ends_at": due.window_end,
                "job_id": job_id,
                "now": now,
            },
        )
    return job_id, operation_id


def _prepare_request_budget(
    client: TestClient,
    owner_id: UUID,
    *,
    limit: int,
    source_limit: int | None = None,
    now: datetime,
) -> None:
    factory = client.app.state.session_factory
    with factory() as session:
        budget = ResourceBudgetService(session, clock=lambda: now)
        budget.save_component_policy(
            owner_id=owner_id,
            command=ComponentPolicyInput(
                component_key="collector.bilibili",
                component_version="1",
                cost_class=CostClass.LOCAL,
                enabled_for_core=True,
                terms_reference="https://example.invalid/terms",
                reviewed_at=now,
            ),
        )
        budget.save_budget_policy(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.coverage.http",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=limit,
                window_seconds=3600,
                window_anchor_at=now - timedelta(seconds=10),
                enabled=True,
            ),
        )
        if source_limit is not None:
            budget.save_budget_policy(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="source.coverage.http",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.SOURCE,
                    scope_reference="bilibili",
                    limit_units=source_limit,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )


def _settle_request(
    client: TestClient,
    owner_id: UUID,
    job_id: UUID,
    operation_id: UUID,
    *,
    now: datetime,
) -> None:
    factory = client.app.state.session_factory
    attempt_id = uuid4()
    with factory() as session, session.begin():
        budget = ResourceBudgetService(session, clock=lambda: now)
        decision = budget.reserve_budget_in_transaction(
            owner_id=owner_id,
            command=BudgetReservationInput(
                reservation_id=attempt_id,
                operation_id=operation_id,
                metric=BudgetMetric.NETWORK_REQUEST,
                requested_units=1,
                context=BudgetContext(source_ref="bilibili", job_ref=f"job:{job_id.hex}"),
            ),
        )
        assert decision.status is BudgetDecisionStatus.RESERVED
        session.flush()
        budget.begin_attempt_in_transaction(
            owner_id=owner_id,
            command=UsageAttemptInput(
                attempt_id=attempt_id,
                operation_id=operation_id,
                component_key="collector.bilibili",
                usage_kind=UsageKind.NETWORK_REQUEST,
                stage="search.request",
                started_at=now,
            ),
        )
        budget.settle_budget_reservation_in_transaction(
            owner_id=owner_id, reservation_id=attempt_id, actual_units=1
        )
        budget.finish_attempt_in_transaction(
            owner_id=owner_id,
            attempt_id=attempt_id,
            outcome=UsageOutcome.SUCCEEDED,
            finished_at=now,
        )


def test_coverage_query_has_owner_scoped_list_and_detail_contract(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    listing = paths["/api/collection-coverage"]["get"]
    detail = paths["/api/collection-coverage/{window_id}"]["get"]

    assert listing["operationId"] == "listCollectionCoverage"
    assert detail["operationId"] == "getCollectionCoverage"
    assert listing["security"] == detail["security"] == [{"SessionCookie": []}]
    assert {"start", "end"}.issubset(
        {parameter["name"] for parameter in listing["parameters"] if parameter["required"]}
    )
    assert {"401", "404", "422", "500"}.issubset(listing["responses"])


def test_missing_job_is_a_visible_gap_and_cursor_is_bound_to_query(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, owner_id, now = coverage_client
    due_times = [now - timedelta(hours=hour) for hour in (3, 2, 1)]
    ids = [_record_due(client, owner_id, instant) for instant in due_times]
    params = {
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat(),
        "source_key": "bilibili",
        "capability": "search",
        "limit": 1,
    }
    first = client.get("/api/collection-coverage", params=params)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    row = first.json()["items"][0]
    assert row["window_id"] == str(ids[-1])
    assert row["coverage_status"] == "unattempted"
    assert row["job_id"] is None and row["request_count"] is None
    assert row["current_connection_version"] is None
    assert row["current_connection_status"] is None
    assert row["page_count"] is None and row["observed_count"] is None
    assert row["budget_consumed"] is None and row["analysis_valid_count"] is None
    assert row["gaps"] == [
        {
            "start": (due_times[-1] - timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
            "end": due_times[-1].isoformat().replace("+00:00", "Z"),
            "reason": "unattempted",
        }
    ]

    cursor = first.json()["next_cursor"]
    assert cursor
    _record_due(client, owner_id, now - timedelta(minutes=30))
    second = client.get("/api/collection-coverage", params={**params, "cursor": cursor})
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["window_id"] == str(ids[-2])
    assert (
        client.get(
            "/api/collection-coverage", params={**params, "limit": 2, "cursor": cursor}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/collection-coverage",
            params={
                **params,
                "cursor": cursor[:8] + ("A" if cursor[8] != "A" else "B") + cursor[9:],
            },
        ).status_code
        == 422
    )
    assert client.get(f"/api/collection-coverage/{ids[0]}").status_code == 200
    assert client.get(f"/api/collection-coverage/{uuid4()}").status_code == 404
    factory = client.app.state.session_factory
    with factory() as session:
        identity = IdentityService(session, client.app.state.settings).authenticate(
            client.cookies["hotkey_session"]
        )
    foreign = replace(
        identity,
        view=identity.view.model_copy(
            update={"user": identity.view.user.model_copy(update={"id": uuid4()})}
        ),
    )
    client.app.dependency_overrides[require_identity_session] = lambda: foreign
    try:
        assert client.get(f"/api/collection-coverage/{ids[0]}").status_code == 404
        assert client.get("/api/collection-coverage", params=params).json()["items"] == []
    finally:
        client.app.dependency_overrides.clear()


def test_coverage_rejects_invalid_ranges_and_anonymous_reads(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, _, now = coverage_client
    path = "/api/collection-coverage"
    base = {"start": now.isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
    assert client.get(path, params={**base, "end": base["start"]}).status_code == 422
    assert (
        client.get(path, params={**base, "end": (now + timedelta(days=32)).isoformat()}).status_code
        == 422
    )
    assert (
        client.get(path, params={**base, "start": now.replace(tzinfo=None).isoformat()}).status_code
        == 422
    )
    cookies = dict(client.cookies)
    client.cookies.clear()
    assert client.get(path, params=base).status_code == 401
    for name, value in cookies.items():
        client.cookies.set(name, value)


def test_rate_and_budget_skips_preserve_admission_reason_without_job_metrics(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, owner_id, now = coverage_client
    factory = client.app.state.session_factory
    for offset, reason in ((2, DueSkipReason.RATE_LIMITED), (1, DueSkipReason.BUDGET)):
        window_id = _record_due(client, owner_id, now - timedelta(hours=offset))
        with factory() as session, session.begin():
            due = session.execute(
                text("SELECT schedule_key, due_at FROM collection_due_windows WHERE id = :id"),
                {"id": window_id},
            ).one()
            CollectionDueWindowService(session).mark_skipped_in_transaction(
                owner_id=owner_id,
                schedule_key=due.schedule_key,
                due_at=due.due_at,
                reason=reason,
            )
        response = client.get(f"/api/collection-coverage/{window_id}")
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["admission_state"] == "skipped"
        assert row["admission_reason"] == reason.value
        assert row["coverage_status"] == "unattempted"
        assert len(row["gaps"]) == 1 and row["gaps"][0]["reason"] == reason.value
        assert all(
            row[key] is None
            for key in (
                "job_id",
                "attempts",
                "request_count",
                "request_attempt_count",
                "page_count",
                "observed_count",
                "budget_consumed",
                "analysis_valid_count",
            )
        )


def test_empty_hotlist_and_later_failure_keep_distinct_coverage_facts(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, owner_id, now = coverage_client
    empty_id = _record_due(
        client, owner_id, now - timedelta(hours=4), capability=SourceCapability.HOTLIST
    )
    failed_id = _record_due(
        client, owner_id, now - timedelta(hours=3), capability=SourceCapability.HOTLIST
    )
    stopped_id = _record_due(
        client, owner_id, now - timedelta(hours=2), capability=SourceCapability.HOTLIST
    )
    _accept_hotlist_job(
        client,
        owner_id,
        empty_id,
        status="succeeded",
        observed_count=0,
        completed_at=now - timedelta(hours=3, minutes=55),
    )
    _accept_hotlist_job(
        client,
        owner_id,
        failed_id,
        status="failed",
        observed_count=None,
        completed_at=now - timedelta(hours=2, minutes=55),
    )
    _accept_hotlist_job(
        client,
        owner_id,
        stopped_id,
        status="cancelled",
        observed_count=None,
        completed_at=now - timedelta(hours=1, minutes=55),
    )
    empty = client.get(f"/api/collection-coverage/{empty_id}")
    failed = client.get(f"/api/collection-coverage/{failed_id}")
    stopped = client.get(f"/api/collection-coverage/{stopped_id}")
    assert empty.status_code == failed.status_code == stopped.status_code == 200
    assert empty.json()["coverage_status"] == "empty"
    assert empty.json()["terminal_evidence"] is True
    assert empty.json()["page_count"] == 1 and empty.json()["observed_count"] == 0
    assert len(empty.json()["snapshot_ids"]) == 1 and empty.json()["gaps"] == []
    assert failed.json()["coverage_status"] == "failed"
    assert failed.json()["snapshot_ids"] == [] and failed.json()["page_count"] == 0
    assert failed.json()["observed_count"] == 0 and len(failed.json()["gaps"]) == 1
    assert failed.json()["last_success_at"] == empty.json()["finished_at"]
    assert stopped.json()["coverage_status"] == "stopped"
    assert stopped.json()["last_success_at"] == empty.json()["finished_at"]


def test_partial_keyword_window_keeps_page_and_budget_gap(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, owner_id, now = coverage_client
    window_id = _record_due(client, owner_id, now - timedelta(hours=5))
    job_id, operation_id = uuid4(), uuid4()
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        due = session.execute(
            text(
                "SELECT schedule_key, due_at, window_start, window_end "
                "FROM collection_due_windows WHERE id = :id"
            ),
            {"id": window_id},
        ).one()
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, requests_sent, progress_stage, progress_updated_at, "
                "checkpoint, created_at, updated_at) VALUES "
                "(:id, :owner_id, :operation_id, 'keyword.search', 'coverage:test', "
                "1, 'bilibili', 'search', CAST(:scope AS jsonb), :fingerprint, 1, "
                "'save', :now, CAST(:checkpoint AS jsonb), :now, :now)"
            ),
            {
                "id": job_id,
                "owner_id": owner_id,
                "operation_id": operation_id,
                "scope": '{"connection_version":2}',
                "fingerprint": b"p" * 32,
                "checkpoint": '{"collection.observed_count":3}',
                "now": now,
            },
        )
        CollectionDueWindowService(session).mark_accepted_in_transaction(
            owner_id=owner_id,
            schedule_key=due.schedule_key,
            due_at=due.due_at,
            operation_id=operation_id,
            job_id=job_id,
        )
        session.execute(
            text(
                "UPDATE jobs SET status = 'partially_succeeded', completed_at = :now WHERE id = :id"
            ),
            {"now": now, "id": job_id},
        )
        session.execute(
            text(
                "INSERT INTO coverage_windows "
                "(id, owner_id, source_key, capability, target_hash, sort_key, "
                "rule_version, starts_at, ends_at, status, stop_reason, last_job_id, "
                "page_count, created_at, updated_at) VALUES "
                "(:id, :owner_id, 'bilibili', 'search', :target_hash, 'latest', "
                "1, :starts_at, :ends_at, 'partial', 'budget_exhausted', :job_id, "
                "1, :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner_id": owner_id,
                "target_hash": b"p" * 32,
                "starts_at": due.window_start,
                "ends_at": due.window_end,
                "job_id": job_id,
                "now": now,
            },
        )
    response = client.get(f"/api/collection-coverage/{window_id}")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["coverage_status"] == "partial"
    assert item["request_count"] == 1 and item["request_attempt_count"] == 0
    assert item["page_count"] == 1 and item["observed_count"] == 3
    assert item["budget_consumed"] is None and item["gaps"][0]["reason"] == "budget_exhausted"

    attempt_id = uuid4()
    with factory() as session:
        budget = ResourceBudgetService(session, clock=lambda: now)
        budget.save_component_policy(
            owner_id=owner_id,
            command=ComponentPolicyInput(
                component_key="collector.bilibili",
                component_version="1",
                cost_class=CostClass.LOCAL,
                enabled_for_core=True,
                terms_reference="https://example.invalid/terms",
                reviewed_at=now,
            ),
        )
        budget.save_budget_policy(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.coverage.http",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=2,
                window_seconds=3600,
                window_anchor_at=now - timedelta(seconds=10),
                enabled=True,
            ),
        )
        with session.begin():
            decision = budget.reserve_budget_in_transaction(
                owner_id=owner_id,
                command=BudgetReservationInput(
                    reservation_id=attempt_id,
                    operation_id=operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(source_ref="bilibili", job_ref=f"job:{job_id.hex}"),
                ),
            )
            assert decision.status is BudgetDecisionStatus.RESERVED
            session.flush()
            budget.begin_attempt_in_transaction(
                owner_id=owner_id,
                command=UsageAttemptInput(
                    attempt_id=attempt_id,
                    operation_id=operation_id,
                    component_key="collector.bilibili",
                    usage_kind=UsageKind.NETWORK_REQUEST,
                    stage="search.request",
                    started_at=now,
                ),
            )
            budget.settle_budget_reservation_in_transaction(
                owner_id=owner_id, reservation_id=attempt_id, actual_units=1
            )
            budget.finish_attempt_in_transaction(
                owner_id=owner_id,
                attempt_id=attempt_id,
                outcome=UsageOutcome.SUCCEEDED,
                finished_at=now,
            )
    charged = client.get(f"/api/collection-coverage/{window_id}")
    assert charged.status_code == 200, charged.text
    assert charged.json()["request_attempt_count"] == 1
    assert charged.json()["budget_limit"] == 2
    assert charged.json()["budget_reserved"] == 0
    assert charged.json()["budget_consumed"] == 1


def test_confirmed_keyword_windows_reconcile_content_and_annotation_states(
    coverage_client: tuple[TestClient, UUID, datetime],
) -> None:
    client, owner_id, now = coverage_client
    topic_id = _create_topic(client, owner_id, now)
    older = _record_due(client, owner_id, now - timedelta(hours=4), topic_id=topic_id)
    newer = _record_due(client, owner_id, now - timedelta(hours=3), topic_id=topic_id)
    first_job, first_operation = _accept_search_job(
        client, owner_id, topic_id, older, observed_count=3, now=now
    )
    second_job, second_operation = _accept_search_job(
        client, owner_id, topic_id, newer, observed_count=2, now=now
    )
    _prepare_request_budget(client, owner_id, limit=10, source_limit=3, now=now)
    _settle_request(client, owner_id, first_job, first_operation, now=now)
    _settle_request(client, owner_id, second_job, second_operation, now=now)

    contents = tuple(uuid4() for _ in range(4))
    versions = tuple(uuid4() for _ in range(4))
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        for job_id, epoch, outcome in (
            (first_job, 1, "expired"),
            (first_job, 2, "succeeded"),
            (second_job, 1, "succeeded"),
        ):
            session.execute(
                text(
                    "INSERT INTO job_attempts "
                    "(id, job_id, lease_epoch, collection_cycle_no, worker_id, "
                    "started_at, lease_expires_at, finished_at, outcome) VALUES "
                    "(:id, :job_id, :epoch, 1, 'coverage-worker', "
                    ":now, :expires_at, :now, :outcome)"
                ),
                {
                    "id": uuid4(),
                    "job_id": job_id,
                    "epoch": epoch,
                    "now": now,
                    "expires_at": now + timedelta(minutes=5),
                    "outcome": outcome,
                },
            )
        for index, (content_id, version_id) in enumerate(zip(contents, versions, strict=True)):
            session.execute(
                text(
                    "INSERT INTO content_records "
                    "(id, owner_id, source_key, object_type, external_id, created_at) "
                    "VALUES (:id, :owner_id, 'bilibili', 'post', :external_id, :now)"
                ),
                {
                    "id": content_id,
                    "owner_id": owner_id,
                    "external_id": f"coverage-{index}",
                    "now": now,
                },
            )
            session.execute(
                text(
                    "INSERT INTO content_versions "
                    "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                    "title, created_at) VALUES "
                    "(:id, :owner_id, :content_id, :fingerprint, 'full', 'source', "
                    "'coverage title', :now)"
                ),
                {
                    "id": version_id,
                    "owner_id": owner_id,
                    "content_id": content_id,
                    "fingerprint": version_id.bytes * 2,
                    "now": now,
                },
            )
        for job_id, content_index, received_at in (
            (first_job, 0, now),
            (first_job, 1, now),
            (first_job, 2, now),
            (second_job, 0, now + timedelta(seconds=1)),
            (second_job, 3, now + timedelta(seconds=1)),
        ):
            session.execute(
                text(
                    "INSERT INTO content_observations "
                    "(id, owner_id, content_id, job_id, source_operation_id, "
                    "content_version_id, observed_at, received_at) VALUES "
                    "(:id, :owner_id, :content_id, :job_id, :operation_id, "
                    ":version_id, :now, :received_at)"
                ),
                {
                    "id": uuid4(),
                    "owner_id": owner_id,
                    "content_id": contents[content_index],
                    "job_id": job_id,
                    "operation_id": uuid4(),
                    "version_id": versions[content_index],
                    "now": now,
                    "received_at": received_at,
                },
            )
            session.execute(
                text(
                    "INSERT INTO content_discoveries "
                    "(id, owner_id, content_id, job_id, first_observed_at, created_at) "
                    "VALUES (:id, :owner_id, :content_id, :job_id, :now, :received_at)"
                ),
                {
                    "id": uuid4(),
                    "owner_id": owner_id,
                    "content_id": contents[content_index],
                    "job_id": job_id,
                    "now": now,
                    "received_at": received_at,
                },
            )
        call_id = uuid4()
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, "
                "output_tokens, reasoning_output_tokens, duration_ms, created_at) VALUES "
                "(:id, :owner_id, 'analysis.annotate', 'test', 'test-model', "
                ":prompt_version, :fingerprint, 'succeeded', 0, 0, 0, 0, 0, :now)"
            ),
            {
                "id": call_id,
                "owner_id": owner_id,
                "prompt_version": ANALYSIS_PROMPT_VERSION,
                "fingerprint": b"a" * 32,
                "now": now,
            },
        )
        for index, result_state in ((0, "valid"), (1, "invalid")):
            session.execute(
                text(
                    "INSERT INTO content_annotations "
                    "(id, owner_id, content_id, content_version_id, topic_id, "
                    "topic_rule_version, prompt_version, relevant, relevance_reason, "
                    "summary, viewpoints, ai_call_id, status, result_state, error_code, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, :content_id, :version_id, :topic_id, 1, "
                    ":prompt_version, :relevant, :reason, :summary, '[]'::jsonb, "
                    ":call_id, :status, :result_state, :error_code, :now, :now)"
                ),
                {
                    "id": uuid4(),
                    "owner_id": owner_id,
                    "content_id": contents[index],
                    "version_id": versions[index],
                    "topic_id": topic_id,
                    "prompt_version": ANALYSIS_PROMPT_VERSION,
                    "relevant": False if result_state == "valid" else None,
                    "reason": "not relevant" if result_state == "valid" else None,
                    "summary": "no match" if result_state == "valid" else None,
                    "call_id": call_id,
                    "status": "annotated" if result_state == "valid" else "unanalyzed",
                    "result_state": result_state,
                    "error_code": None if result_state == "valid" else "analysis_output_missing",
                    "now": now,
                },
            )
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, scope, request_fingerprint, status, "
                "last_error_code, last_error_category, last_error_at, next_action, "
                "created_at, updated_at) VALUES "
                "(:id, :owner_id, :operation_id, 'analysis.annotate', :reference, 1, "
                "CAST(:scope AS jsonb), :fingerprint, 'failed', 'model_unavailable', "
                "'transient', :now, 'retry later', :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner_id": owner_id,
                "operation_id": uuid4(),
                "reference": f"topic:{topic_id}",
                "scope": json.dumps(
                    {
                        "topic_id": str(topic_id),
                        "topic_rule_version": 1,
                        "prompt_version": ANALYSIS_PROMPT_VERSION,
                        "content_version_ids": json.dumps([str(versions[3])]),
                    }
                ),
                "fingerprint": b"a" * 32,
                "now": now,
            },
        )

    params = {
        "source_key": "bilibili",
        "capability": "search",
        "topic_id": str(topic_id),
        "start": (now - timedelta(hours=6)).isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
    }
    response = client.get("/api/collection-coverage", params=params)
    assert response.status_code == 200, response.text
    rows = {UUID(item["window_id"]): item for item in response.json()["items"]}
    assert set(rows) == {older, newer}
    first, second = rows[older], rows[newer]
    assert first["coverage_status"] == "analysis_pending"
    assert first["analysis_valid_count"] == 1
    assert first["analysis_invalid_count"] == 1
    assert first["analysis_pending_count"] == 1
    assert first["analysis_failed_count"] == 0
    assert second["coverage_status"] == "confirmed"
    assert second["analysis_valid_count"] == 1
    assert second["analysis_failed_count"] == 1
    assert second["analysis_invalid_count"] == 0
    assert second["analysis_pending_count"] == 0
    assert first["inserted_count"] == 3 and first["deduplicated_count"] == 0
    assert second["inserted_count"] == 1 and second["deduplicated_count"] == 1
    assert set(first["content_ids"]) == {str(item) for item in contents[:3]}
    assert set(second["content_ids"]) == {str(contents[0]), str(contents[3])}
    assert all(item["request_count"] == 1 for item in (first, second))
    assert all(item["request_attempt_count"] == 1 for item in (first, second))
    assert all(item["budget_limit"] == 3 for item in (first, second))
    assert all(item["budget_consumed"] == 1 for item in (first, second))
    assert all(item["page_count"] == 1 and item["gaps"] == [] for item in (first, second))
    assert first["attempts"] == 2
    assert second["attempts"] == 1
    with factory() as session:
        counts = dict(
            session.execute(
                text(
                    "SELECT job_id, count(*) FROM content_observations "
                    "WHERE owner_id = :owner_id AND job_id IN (:first, :second) GROUP BY job_id"
                ),
                {"owner_id": owner_id, "first": first_job, "second": second_job},
            ).all()
        )
        budget_rows = session.scalar(
            text(
                "SELECT count(*) FROM resource_budget_reservations "
                "WHERE owner_id = :owner_id AND operation_id IN (:first, :second)"
            ),
            {"owner_id": owner_id, "first": first_operation, "second": second_operation},
        )
    assert counts == {first_job: first["observed_count"], second_job: second["observed_count"]}
    assert budget_rows == 4
