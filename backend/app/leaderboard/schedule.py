"""Six-hour refresh admission uses the existing jobs/outbox and a frozen method."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService, load_job_id_for_operation_in_transaction
from leaderboard.method.constants import METHOD_VERSION

INTERVAL_SECONDS = 6 * 60 * 60
_ANCHOR = datetime(1970, 1, 1, 0, 5, tzinfo=UTC)
_NAMESPACE = UUID("7d9c06ae-daa8-4d78-93da-2dcb5464adf3")
CONFIGURATION_REF = "leaderboard:public-consensus"


def leaderboard_window(now: datetime) -> datetime:
    if now.utcoffset() is None:
        raise ValueError("leaderboard scheduler requires aware time")
    # Shanghai 02:05/08:05/14:05/20:05 == UTC 18:05/00:05/06:05/12:05.
    slot = int((now - _ANCHOR).total_seconds()) // INTERVAL_SECONDS
    return _ANCHOR + timedelta(seconds=slot * INTERVAL_SECONDS)


def leaderboard_operation_id(owner_id: UUID, now: datetime) -> UUID:
    return uuid5(_NAMESPACE, f"{owner_id}:{METHOD_VERSION}:{leaderboard_window(now).isoformat()}")


def enqueue_due_leaderboard_in_transaction(
    session: Session, now: datetime, *, enabled: bool, owner_id: UUID
) -> int:
    if not session.in_transaction():
        raise RuntimeError("leaderboard admission requires caller transaction")
    window = leaderboard_window(now)
    if not enabled:
        return 0
    operation_id = leaderboard_operation_id(owner_id, now)
    # Serialize this admission/count pair; the Job uniqueness constraint is still authoritative.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"leaderboard-admit:{owner_id}:{operation_id}"},
    )
    if (
        load_job_id_for_operation_in_transaction(
            session, owner_id=owner_id, operation_id=operation_id
        )
        is not None
    ):
        return 0
    service = JobService(session, clock=lambda: now)
    service.accept_in_transaction(
        owner_id=owner_id,
        command=JobAcceptanceInput(
            operation_id=operation_id,
            kind="leaderboard.refresh",
            observation=JobObservationContext(
                configuration_ref=CONFIGURATION_REF, configuration_version=1
            ),
            scheduled_for_at=window,
            scope={"method_version": METHOD_VERSION, "at": window.isoformat(), "force": False},
        ),
    )
    return 1
