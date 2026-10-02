"""Original Job and budget state for bounded source previews; no additional ledger."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from jobs.models import Job, ResourceBudgetReservation, ResourceUsageAttempt
from jobs.schemas import UsageOutcome
from jobs.services import ResourceBudgetService
from operations.services import has_succeeded_action_target_in_transaction


@dataclass(frozen=True)
class EditorialPreviewJobState:
    status: str
    started: bool
    requests: int

    @property
    def terminal(self) -> bool:
        return self.status in {"succeeded", "partially_succeeded", "failed", "cancelled"}


def load_editorial_preview_job_state_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, operation_id: UUID
) -> EditorialPreviewJobState:
    if not session.in_transaction():
        raise RuntimeError("preview state reads require caller transaction")
    job = session.scalar(
        select(Job)
        .where(
            Job.owner_id == owner_id,
            Job.id == job_id,
            Job.operation_id == operation_id,
            Job.kind == "source.editorial.preview",
        )
        .with_for_update()
    )
    if job is None:
        raise ApplicationError("resource_not_found")
    return EditorialPreviewJobState(
        status=job.status,
        started=bool(job.checkpoint.get("source_preview_started")),
        requests=job.requests_sent,
    )


def require_no_unresolved_editorial_preview_in_transaction(
    session: Session, *, owner_id: UUID, profile_id: UUID, operation_id: UUID
) -> None:
    """A new operation cannot replace an in-flight or unknown original request."""
    if not session.in_transaction():
        raise RuntimeError("preview admission requires caller transaction")
    rows = session.scalars(
        select(Job).where(
            Job.owner_id == owner_id,
            Job.kind == "source.editorial.preview",
            Job.configuration_ref == f"editorial-source:{profile_id}",
            Job.operation_id != operation_id,
        )
    )
    for job in rows:
        unresolved = job.checkpoint.get("preview_status") == "unknown" or (
            job.checkpoint.get("source_preview_started") and "preview_status" not in job.checkpoint
        )
        reviewed = (
            has_succeeded_action_target_in_transaction(
                session,
                owner_id=owner_id,
                action="editorial.source.preview.review",
                target_ref=str(job.id),
            )
            if unresolved
            else False
        )
        if job.status in {"queued", "running"} or (unresolved and not reviewed):
            raise ApplicationError("editorial_version_conflict")


def recover_editorial_preview_budgets_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, operation_id: UUID, now: datetime
) -> int:
    """Settle only this original preview operation's abandoned reservations at their caps."""
    if not session.in_transaction():
        raise RuntimeError("preview recovery requires caller transaction")
    job = session.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.owner_id == owner_id,
            Job.operation_id == operation_id,
            Job.kind == "source.editorial.preview",
        )
    )
    if job is None:
        raise ValueError("preview recovery requires its original Job")
    reservations = list(
        session.scalars(
            select(ResourceBudgetReservation)
            .where(
                ResourceBudgetReservation.owner_id == owner_id,
                ResourceBudgetReservation.operation_id == operation_id,
                ResourceBudgetReservation.status == "reserved",
            )
            .order_by(ResourceBudgetReservation.reservation_id)
            .with_for_update()
        )
    )
    ledger = ResourceBudgetService(session, clock=lambda: now)
    caps: dict[UUID, int] = {}
    for row in reservations:
        if row.reservation_id in caps and caps[row.reservation_id] != row.requested_units:
            raise RuntimeError("original preview budget caps disagree")
        caps[row.reservation_id] = row.requested_units
    for reservation_id, cap in caps.items():
        ledger.settle_budget_reservation_in_transaction(
            owner_id=owner_id, reservation_id=reservation_id, actual_units=cap
        )
    attempts = list(
        session.scalars(
            select(ResourceUsageAttempt.attempt_id).where(
                ResourceUsageAttempt.owner_id == owner_id,
                ResourceUsageAttempt.operation_id == operation_id,
                ResourceUsageAttempt.outcome == "started",
            )
        )
    )
    for attempt_id in attempts:
        ledger.finish_attempt_in_transaction(
            owner_id=owner_id,
            attempt_id=attempt_id,
            outcome=UsageOutcome.FAILED,
            finished_at=now,
        )
    return len(caps)
