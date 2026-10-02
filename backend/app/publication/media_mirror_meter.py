"""Each remote fetch and object write uses the existing persistent usage/budget ledger."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Event, RLock, Thread
from uuid import UUID, uuid5

from sqlalchemy.orm import Session, sessionmaker

from jobs.execution import ExecutionLease, JobExecutionService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    JobMessage,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetService
from publication.media_mirror_fetch import Outcome

COMPONENT = "publication.media_mirror"


def stage_for(file_id: UUID, kind: str, *, stage_prefix: str = "media") -> str:
    return f"{stage_prefix}.{kind}:{file_id.hex}"


class MediaRequestMeter:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        message: JobMessage,
        lease: ExecutionLease,
        *,
        clock: Callable[[], datetime],
        source_key: str,
        lease_seconds: int = 30,
        guard: Callable[[Session], object],
        component_key: str = COMPONENT,
        budget_job_ref: str = "publication.media_mirror",
        stage_prefix: str = "media",
    ) -> None:
        self.sessions, self.message, self.lease, self.clock = sessions, message, lease, clock
        self.source_key, self.lease_seconds, self.guard = source_key, lease_seconds, guard
        if not component_key or not budget_job_ref or not stage_prefix or len(stage_prefix) > 64:
            raise ValueError("a bounded explicit media meter namespace is required")
        self.component_key, self.budget_job_ref, self.stage_prefix = (
            component_key,
            budget_job_ref,
            stage_prefix,
        )
        self.stop, self.broken, self.lock = Event(), Event(), RLock()
        self.admitted: set[UUID] = set()
        self.thread: Thread | None = None

    def execution(self, session: Session) -> JobExecutionService:
        return JobExecutionService(session, lease_seconds=self.lease_seconds, clock=self.clock)

    def stage(self, file_id: UUID, kind: str) -> str:
        return stage_for(file_id, kind, stage_prefix=self.stage_prefix)

    def recover(self, file_id: UUID) -> None:
        with self.lock, self.sessions.begin() as session:
            self.execution(session).require_current_lease_in_transaction(self.lease)
            for kind in ["http", "put"]:
                ResourceBudgetService(
                    session, clock=self.clock
                ).recover_abandoned_attempts_in_transaction(
                    owner_id=self.message.owner_id,
                    operation_id=self.message.operation_id,
                    component_key=self.component_key,
                    stage=self.stage(file_id, kind),
                    finished_at=self.clock(),
                )

    def before(self, file_id: UUID, kind: str, index: int) -> bool:
        stage = self.stage(file_id, kind)
        identity = uuid5(self.message.operation_id, f"{stage}:{index}")
        with self.lock:
            if self.broken.is_set() or identity in self.admitted:
                return False
            with self.sessions.begin() as session:
                execution = self.execution(session)
                execution.require_current_lease_in_transaction(self.lease)
                self.guard(session)
                budgets = ResourceBudgetService(session, clock=self.clock)
                decision = budgets.reserve_budget_in_transaction(
                    owner_id=self.message.owner_id,
                    command=BudgetReservationInput(
                        reservation_id=identity,
                        operation_id=self.message.operation_id,
                        metric=BudgetMetric.NETWORK_REQUEST,
                        requested_units=1,
                        context=BudgetContext(
                            source_ref=self.source_key, job_ref=self.budget_job_ref
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
                        component_key=self.component_key,
                        usage_kind=UsageKind.NETWORK_REQUEST,
                        stage=stage,
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

    def after(self, file_id: UUID, kind: str, index: int, outcome: Outcome) -> None:
        identity = uuid5(self.message.operation_id, f"{self.stage(file_id, kind)}:{index}")
        with self.lock, self.sessions.begin() as session:
            self.execution(session).require_current_lease_allowing_cancel_in_transaction(self.lease)
            budget = ResourceBudgetService(session, clock=self.clock)
            budget.settle_budget_reservation_in_transaction(
                owner_id=self.message.owner_id,
                reservation_id=identity,
                actual_units=0 if outcome == "not_sent" else 1,
            )
            budget.finish_attempt_in_transaction(
                owner_id=self.message.owner_id,
                attempt_id=identity,
                outcome=UsageOutcome.SUCCEEDED
                if outcome == "succeeded"
                else UsageOutcome.EMPTY
                if outcome == "not_sent"
                else UsageOutcome.FAILED,
                finished_at=self.clock(),
            )

    def start(self) -> None:
        def heartbeat() -> None:
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

        self.thread = Thread(target=heartbeat, name="publication-media-lease", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
