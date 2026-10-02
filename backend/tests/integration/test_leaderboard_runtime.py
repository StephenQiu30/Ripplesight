from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.integration.test_leaderboard import evidence
from tests.unit.test_leaderboard_fetchers import replay_responses

from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
    JobAcceptanceInput,
    JobAcceptedMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, ResourceBudgetService
from leaderboard.execution import LeaderboardRefreshExecutor, _LeaseMeter
from leaderboard.method.constants import METHOD_VERSION, SCORING_SOURCES
from leaderboard.schedule import CONFIGURATION_REF, enqueue_due_leaderboard_in_transaction
from leaderboard.services import LeaderboardService

pytestmark = pytest.mark.skipif(
    not os.getenv("HOTKEY_TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)


def prepare(sessions, owner, at):
    with sessions.begin() as session:
        job = JobService(session, clock=lambda: at).accept_in_transaction(
            owner_id=owner,
            command=JobAcceptanceInput(
                operation_id=uuid4(),
                kind="leaderboard.refresh",
                observation=JobObservationContext(
                    configuration_ref=CONFIGURATION_REF, configuration_version=1
                ),
                scope={
                    "method_version": METHOD_VERSION,
                    "at": at.isoformat(),
                    "source_keys": "artificial-analysis",
                    "force": False,
                },
            ),
        )
        session.flush()
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job.id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        budget = ResourceBudgetService(session, clock=lambda: at)
        for collector in ("artificial-analysis", "fx"):
            budget.save_component_policy_in_transaction(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key=f"leaderboard.{collector}",
                    component_version=METHOD_VERSION,
                    cost_class=CostClass.ZERO_PRICE,
                    enabled_for_core=True,
                    terms_reference="controlled test fixture; no real supplier",
                    reviewed_at=at,
                ),
            )
        budget.save_budget_policy_in_transaction(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="leaderboard-test-network",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=20,
                window_seconds=3600,
                window_anchor_at=at,
                enabled=True,
            ),
        )
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: at).acquire(
            job_id=job.id, worker_id="controlled-leaderboard"
        )
    return message, lease


def test_six_hour_admission_is_one_job_outbox_and_closed_network_is_zero_calls() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    sessions = sessionmaker(engine)
    owner = uuid4()
    at = datetime.now(UTC).replace(minute=10, second=0, microsecond=0)
    try:
        with sessions.begin() as session:
            assert (
                enqueue_due_leaderboard_in_transaction(session, at, enabled=False, owner_id=owner)
                == 0
            )
            assert (
                enqueue_due_leaderboard_in_transaction(session, at, enabled=True, owner_id=owner)
                == 1
            )
            assert (
                enqueue_due_leaderboard_in_transaction(
                    session, at + timedelta(minutes=1), enabled=True, owner_id=owner
                )
                == 0
            )
            assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
            assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 1
        message, lease = prepare(sessions, owner, at + timedelta(seconds=1))
        calls = []
        executor = LeaderboardRefreshExecutor(
            sessions,
            clock=lambda: at + timedelta(seconds=1),
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(500)
            ),
        )
        with pytest.raises(JobExecutionFailure) as error:
            executor.execute(message, lease)
        # Closed collection still runs the method over admitted local snapshots. With none,
        # publication fails its real coverage gates instead of inventing an empty success.
        assert error.value.error_code == "leaderboard_publication_failed" and not calls
        with sessions.begin() as session:
            assert (
                session.execute(text("SELECT count(*) FROM resource_usage_attempts")).scalar_one()
                == 0
            )
            assert (
                session.execute(text("SELECT status FROM leaderboard_runs")).scalar_one()
                == "failed"
            )
            checkpoint = session.execute(
                text("SELECT checkpoint FROM jobs WHERE id=:id"), {"id": message.job_id}
            ).scalar_one()
            assert checkpoint["leaderboard_stored_only"] is True
    finally:
        engine.dispose()


def test_closed_collection_publishes_real_stored_kemeny_round_without_client_or_usage(monkeypatch):
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    sessions = sessionmaker(engine)
    owner, at = uuid4(), datetime.now(UTC)
    try:
        with sessions.begin() as session:
            for source in SCORING_SOURCES:
                LeaderboardService(session).store_snapshot(evidence(source.key, at), at=at)
        message, lease = prepare(sessions, owner, at + timedelta(seconds=1))

        def forbidden_client(*_args, **_kwargs):
            raise AssertionError("closed collection must not construct a client or request meter")

        monkeypatch.setattr("leaderboard.execution.LeaderboardFetchClient", forbidden_client)
        monkeypatch.setattr("leaderboard.execution._LeaseMeter", forbidden_client)
        executor = LeaderboardRefreshExecutor(sessions, clock=lambda: at + timedelta(seconds=1))
        completion = executor.execute(message, lease)
        assert completion.status == JobStatus.SUCCEEDED
        assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
        with sessions.begin() as session:
            assert (
                session.execute(text("SELECT status FROM leaderboard_runs")).scalar_one()
                == "published"
            )
            assert (
                session.execute(text("SELECT count(*) FROM leaderboard_rankings")).scalar_one() > 0
            )
            assert (
                session.execute(text("SELECT count(*) FROM resource_usage_attempts")).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_request_outcomes_settle_once_and_expired_unknown_is_never_requested_again() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    sessions = sessionmaker(engine)
    owner = uuid4()
    at = datetime.now(UTC)
    try:
        message, lease = prepare(sessions, owner, at)
        meter = _LeaseMeter(sessions, message, lease, lambda: at, 30)
        assert not meter.recover()
        for index, outcome in enumerate(("succeeded", "failed", "unknown", "not_sent"), 1):
            assert meter.before("artificial-analysis", index)
            assert not meter.before("artificial-analysis", index)
            meter.after("artificial-analysis", index, outcome)
            meter.after("artificial-analysis", index, outcome)
        assert meter.before("artificial-analysis", 5)
        with sessions.begin() as session:
            row = session.execute(
                text("SELECT used_units,reserved_units FROM resource_budget_windows")
            ).one()
            assert row.used_units == 3 and row.reserved_units == 1
            assert (
                session.execute(
                    text("SELECT requests_sent FROM jobs WHERE id=:job"), {"job": message.job_id}
                ).scalar_one()
                == 5
            )
        resumed_at = at + timedelta(seconds=31)
        with sessions() as session:
            resumed = JobExecutionService(
                session, lease_seconds=30, clock=lambda: resumed_at
            ).acquire(job_id=message.job_id, worker_id="restarted-leaderboard")
        calls = []
        executor = LeaderboardRefreshExecutor(
            sessions,
            allow_external_requests=True,
            clock=lambda: resumed_at,
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(500)
            ),
        )
        with pytest.raises(JobExecutionFailure) as error:
            executor.execute(message, resumed)
        assert error.value.error_code == "leaderboard_interrupted_requests" and not calls
        with sessions.begin() as session:
            row = session.execute(
                text("SELECT used_units,reserved_units FROM resource_budget_windows")
            ).one()
            assert row.used_units == 4 and row.reserved_units == 0
            assert (
                session.execute(
                    text("SELECT count(*) FROM resource_usage_attempts WHERE outcome='started'")
                ).scalar_one()
                == 0
            )
            assert session.execute(text("SELECT count(*) FROM leaderboard_runs")).scalar_one() == 0
    finally:
        engine.dispose()


def test_refresh_budgeted_http_preserves_bad_source_and_commits_replay_receipt() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    sessions = sessionmaker(engine)
    owner = uuid4()
    at = datetime.now(UTC)
    try:
        message, lease = prepare(sessions, owner, at)
        with sessions.begin() as session:
            service = LeaderboardService(session)
            for key in (
                "artificial-analysis",
                "arena-text",
                "deepswe-v1-1",
                "livebench-reasoning",
                "epoch-simpleqa",
                "vals-finance-agent",
            ):
                service.store_snapshot(evidence(key, at), at=at)
        responses = replay_responses()
        calls = []

        def transport(request):
            calls.append(str(request.url))
            if request.url.host == "api.frankfurter.app":
                return httpx.Response(
                    200, json={"date": at.date().isoformat(), "rates": {"CNY": 7.1}}
                )
            return httpx.Response(200, json=responses[str(request.url)])

        executor = LeaderboardRefreshExecutor(
            sessions,
            allow_external_requests=True,
            artificial_analysis_api_key="controlled-not-real",
            clock=lambda: at,
            transport=httpx.MockTransport(transport),
            solver_seconds=5,
        )
        result = executor.execute(message, lease)
        assert result.status == JobStatus.PARTIALLY_SUCCEEDED and len(calls) == 2
        assert executor.execute(message, lease).status == result.status and len(calls) == 2
        with sessions.begin() as session:
            assert (
                session.execute(
                    text("SELECT count(*) FROM leaderboard_runs WHERE status='published'")
                ).scalar_one()
                == 1
            )
            assert (
                session.execute(text("SELECT count(*) FROM leaderboard_snapshots")).scalar_one()
                == 6
            )
            assert (
                session.execute(text("SELECT used_units FROM resource_budget_windows")).scalar_one()
                == 2
            )
            assert (
                session.execute(
                    text("SELECT count(*) FROM resource_usage_attempts WHERE outcome='succeeded'")
                ).scalar_one()
                == 2
            )
            assert (
                session.execute(
                    text(
                        "SELECT error_code FROM leaderboard_source_states "
                        "WHERE source_key='artificial-analysis'"
                    )
                ).scalar_one()
                == "suspicious_row_count_shrink"
            )
            assert (
                session.execute(
                    text("SELECT checkpoint->>'leaderboard_completed' FROM jobs WHERE id=:job"),
                    {"job": message.job_id},
                ).scalar_one()
                == "true"
            )
    finally:
        engine.dispose()
