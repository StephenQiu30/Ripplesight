"""Fenced benchmark refresh with durable request reservations and conservative replay."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, RLock, Thread
from uuid import UUID, uuid5

import httpx
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    JobFailureCategory,
    JobMessage,
    JobStatus,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetService, load_job_execution_configuration
from leaderboard.fetch import SOURCE_KEYS, LeaderboardFetchClient, RequestOutcome
from leaderboard.method.constants import METHOD_VERSION
from leaderboard.refresh import LeaderboardRefreshService
from leaderboard.schedule import CONFIGURATION_REF
from leaderboard.services import LeaderboardService

_STAGE = "leaderboard_request"


def request_attempt_id(operation_id: UUID, collector: str, index: int) -> UUID:
    if collector not in {*SOURCE_KEYS, "fx"} or index < 1:
        raise ValueError("invalid leaderboard request identity")
    return uuid5(operation_id, f"leaderboard:{collector}:{index}")


class _LeaseMeter:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        message: JobMessage,
        lease: ExecutionLease,
        clock: Callable[[], datetime],
        lease_seconds: int,
    ) -> None:
        self.sessions, self.message, self.lease, self.clock = sessions, message, lease, clock
        self.lease_seconds = lease_seconds
        self.lock = RLock()
        self.stop, self.broken = Event(), Event()
        self.admitted: set[UUID] = set()

    def execution(self, session: Session) -> JobExecutionService:
        return JobExecutionService(session, lease_seconds=self.lease_seconds, clock=self.clock)

    def recover(self) -> bool:
        with self.lock, self.sessions.begin() as session:
            self.execution(session).require_current_lease_in_transaction(self.lease)
            budgets = ResourceBudgetService(session, clock=self.clock)
            for collector in (*SOURCE_KEYS, "fx"):
                budgets.recover_abandoned_attempts_in_transaction(
                    owner_id=self.message.owner_id,
                    operation_id=self.message.operation_id,
                    component_key=f"leaderboard.{collector}",
                    stage=_STAGE,
                    finished_at=self.clock(),
                )
        with self.sessions() as session:
            summary = ResourceBudgetService(session).usage_summary(
                owner_id=self.message.owner_id, operation_id=self.message.operation_id
            )
            return summary.total_attempts > 0

    def before(self, collector: str, index: int) -> bool:
        identity = request_attempt_id(self.message.operation_id, collector, index)
        with self.lock:
            if self.broken.is_set() or identity in self.admitted:
                return False
            with self.sessions.begin() as session:
                execution = self.execution(session)
                execution.require_current_lease_in_transaction(self.lease)
                budgets = ResourceBudgetService(session, clock=self.clock)
                decision = budgets.reserve_budget_in_transaction(
                    owner_id=self.message.owner_id,
                    command=BudgetReservationInput(
                        reservation_id=identity,
                        operation_id=self.message.operation_id,
                        metric=BudgetMetric.NETWORK_REQUEST,
                        requested_units=1,
                        context=BudgetContext(
                            source_ref=f"leaderboard:{collector}", job_ref="leaderboard.refresh"
                        ),
                    ),
                )
                if decision.status != BudgetDecisionStatus.RESERVED:
                    return False
                attempt = budgets.begin_attempt_in_transaction(
                    owner_id=self.message.owner_id,
                    command=UsageAttemptInput(
                        attempt_id=identity,
                        operation_id=self.message.operation_id,
                        component_key=f"leaderboard.{collector}",
                        usage_kind=UsageKind.NETWORK_REQUEST,
                        stage=_STAGE,
                        started_at=self.clock(),
                    ),
                )
                if attempt.outcome != UsageOutcome.STARTED:
                    return False
                self.lease, allowed = execution.begin_request_in_transaction(self.lease)
                if not allowed:
                    budgets.settle_budget_reservation_in_transaction(
                        owner_id=self.message.owner_id, reservation_id=identity, actual_units=0
                    )
                    budgets.finish_attempt_in_transaction(
                        owner_id=self.message.owner_id,
                        attempt_id=identity,
                        outcome=UsageOutcome.EMPTY,
                        finished_at=self.clock(),
                    )
                    return False
            self.admitted.add(identity)
            return True

    def after(self, collector: str, index: int, outcome: RequestOutcome) -> None:
        identity = request_attempt_id(self.message.operation_id, collector, index)
        with self.lock, self.sessions.begin() as session:
            self.execution(session).require_current_lease_allowing_cancel_in_transaction(self.lease)
            budgets = ResourceBudgetService(session, clock=self.clock)
            budgets.settle_budget_reservation_in_transaction(
                owner_id=self.message.owner_id,
                reservation_id=identity,
                actual_units=0 if outcome == "not_sent" else 1,
            )
            budgets.finish_attempt_in_transaction(
                owner_id=self.message.owner_id,
                attempt_id=identity,
                outcome=UsageOutcome.SUCCEEDED
                if outcome == "succeeded"
                else UsageOutcome.EMPTY
                if outcome == "not_sent"
                else UsageOutcome.FAILED,
                finished_at=self.clock(),
            )

    def heartbeat(self) -> None:
        while not self.stop.wait(max(1, self.lease_seconds / 3)):
            try:
                with self.lock, self.sessions.begin() as session:
                    execution = self.execution(session)
                    current = execution.require_current_lease_in_transaction(self.lease)
                    self.lease = execution.save_checkpoint_in_transaction(
                        current,
                        sequence=current.checkpoint_sequence,
                        checkpoint=current.checkpoint,
                    )
            except Exception:
                self.broken.set()
                return


class LeaderboardRefreshExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        allow_external_requests: bool = False,
        artificial_analysis_api_key: str | None = None,
        github_token: str | None = None,
        max_requests_per_source: int = 1000,
        max_seconds_per_source: float = 600,
        solver_seconds: float = 300,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if (
            not 1 <= max_requests_per_source <= 1000
            or not 0 < max_seconds_per_source <= 600
            or not 0 < solver_seconds <= 300
        ):
            raise ValueError("leaderboard execution bounds exceeded")
        self.sessions, self.allow_external_requests = sessions, allow_external_requests
        self.api_key, self.github_token = artificial_analysis_api_key, github_token
        self.max_requests, self.max_seconds, self.solver_seconds = (
            max_requests_per_source,
            max_seconds_per_source,
            solver_seconds,
        )
        self.lease_seconds, self.transport = lease_seconds, transport
        self.clock = clock or (lambda: datetime.now(UTC))

    def failure(
        self, code: str, category: JobFailureCategory = JobFailureCategory.CONFIGURATION_UNAVAILABLE
    ) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self.clock(),
            next_action="核对来源许可、费用、请求回执与预算,必要时以新操作受理",
            manual_retry_allowed=False,
        )

    def completion(self, partial: bool) -> JobCompletion:
        return JobCompletion(
            status=JobStatus.PARTIALLY_SUCCEEDED if partial else JobStatus.SUCCEEDED,
            failure=self.failure("leaderboard_sources_partial", JobFailureCategory.INVALID_RESPONSE)
            if partial
            else None,
        )

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion:
        with self.sessions.begin() as session:
            current = JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            ).require_current_lease_in_transaction(lease)
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                message.kind != "leaderboard.refresh"
                or configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != CONFIGURATION_REF
                or message.configuration_ref != CONFIGURATION_REF
                or configuration.observation.configuration_version != 1
                or message.configuration_version != 1
                or configuration.scope.get("method_version") != METHOD_VERSION
            ):
                raise self.failure("leaderboard_job_mismatch", JobFailureCategory.INVALID_INPUT)
            if current.checkpoint.get("leaderboard_completed") is True:
                if current.checkpoint.get("leaderboard_round_status") == "failed":
                    raise self.failure(
                        "leaderboard_publication_failed", JobFailureCategory.INVALID_RESPONSE
                    )
                return self.completion(bool(current.checkpoint.get("leaderboard_partial")))
            try:
                at = datetime.fromisoformat(str(configuration.scope["at"]))
                if at.utcoffset() is None or at > self.clock():
                    raise ValueError("invalid frozen round time")
            except (KeyError, ValueError) as error:
                raise self.failure(
                    "leaderboard_job_mismatch", JobFailureCategory.INVALID_INPUT
                ) from error
            force = configuration.scope.get("force") is True
            source_keys = configuration.scope.get("source_keys")
            keys = tuple(str(source_keys).split(",")) if source_keys else None
            if keys is not None and set(keys) - {
                key for values in SOURCE_KEYS.values() for key in values
            }:
                raise self.failure("leaderboard_job_mismatch", JobFailureCategory.INVALID_INPUT)
        if not self.allow_external_requests:
            return self._stored_round(message, lease, at=at, force=force, cancelled=cancelled)
        meter = _LeaseMeter(self.sessions, message, lease, self.clock, self.lease_seconds)
        if meter.recover():
            raise self.failure(
                "leaderboard_interrupted_requests", JobFailureCategory.INVALID_RESPONSE
            )
        thread = Thread(target=meter.heartbeat, daemon=True, name="leaderboard-lease")
        thread.start()

        def is_cancelled() -> bool:
            return meter.broken.is_set() or bool(cancelled and cancelled())

        def client(name: str) -> LeaderboardFetchClient:
            return LeaderboardFetchClient(
                allow_external_requests=self.allow_external_requests,
                before_request=lambda index: meter.before(name, index),
                after_request=lambda index, outcome: meter.after(name, index, outcome),
                cancelled=is_cancelled,
                max_requests=self.max_requests,
                max_seconds=self.max_seconds,
                api_key=self.api_key,
                github_token=self.github_token,
                transport=self.transport,
            )

        try:
            with self.sessions() as session:
                bind = session.get_bind()
                if not isinstance(bind, Engine):
                    raise RuntimeError("leaderboard requires an engine-bound session")
                with bind.connect() as lock_connection:
                    acquired = lock_connection.scalar(
                        text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                        {"key": "leaderboard-refresh"},
                    )
                    lock_connection.commit()
                    if not acquired:
                        raise self.failure("leaderboard_refresh_in_progress")
                    try:
                        with session.begin():
                            round_, details = LeaderboardRefreshService(
                                session, lambda: client("fx"), named_client_factory=client
                            ).refresh(
                                at=at,
                                force=force,
                                keys=keys,
                                time_limit_seconds=self.solver_seconds,
                            )
                            if is_cancelled():
                                raise self.failure("leaderboard_execution_cancelled")
                            partial = (
                                any(not source["ok"] for source in details["sources"])
                                or "error_code" in details["fx"]
                            )
                            with meter.lock:
                                execution = meter.execution(session)
                                current = execution.require_current_lease_in_transaction(
                                    meter.lease
                                )
                                meter.lease = execution.save_checkpoint_in_transaction(
                                    current,
                                    sequence=current.checkpoint_sequence + 1,
                                    checkpoint={
                                        "leaderboard_completed": True,
                                        "leaderboard_round_id": str(round_.run_id),
                                        "leaderboard_round_status": round_.status,
                                        "leaderboard_partial": partial,
                                        "method_version": METHOD_VERSION,
                                    },
                                )
                    finally:
                        lock_connection.execute(
                            text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                            {"key": "leaderboard-refresh"},
                        )
                        lock_connection.commit()
            if round_.status == "failed":
                raise self.failure(
                    "leaderboard_publication_failed", JobFailureCategory.INVALID_RESPONSE
                )
            return self.completion(partial)
        finally:
            meter.stop.set()
            thread.join(timeout=2)

    def _stored_round(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        at: datetime,
        force: bool,
        cancelled: Callable[[], bool] | None,
    ) -> JobCompletion:
        """Compute admitted local evidence when collection is disabled; never create a client."""
        if cancelled and cancelled():
            raise self.failure("leaderboard_execution_cancelled")
        with self.sessions.begin() as session:
            execution = JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            )
            current = execution.require_current_lease_in_transaction(lease)
            service = LeaderboardService(session)
            service.import_official_prices(at=at)
            round_ = service.run_round(at=at, force=force, time_limit_seconds=self.solver_seconds)
            if cancelled and cancelled():
                raise self.failure("leaderboard_execution_cancelled")
            current = execution.require_current_lease_in_transaction(lease)
            execution.save_checkpoint_in_transaction(
                current,
                sequence=current.checkpoint_sequence + 1,
                checkpoint={
                    "leaderboard_completed": True,
                    "leaderboard_round_id": str(round_.run_id),
                    "leaderboard_round_status": round_.status,
                    "leaderboard_partial": False,
                    "leaderboard_stored_only": True,
                    "method_version": METHOD_VERSION,
                },
            )
        if round_.status == "failed":
            raise self.failure(
                "leaderboard_publication_failed", JobFailureCategory.INVALID_RESPONSE
            )
        return self.completion(False)
