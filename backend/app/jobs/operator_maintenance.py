from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from jobs.models import Job, OutboxMessage
from jobs.schemas import JobAcceptanceInput, JobAcceptedMessage
from jobs.services import JOB_ACCEPTED_EVENT_TYPE, JOB_ACCEPTED_TOPIC, JobService


def accept_notification_scan_in_transaction(
    session: Session, *, owner_id: UUID, command: JobAcceptanceInput, now: datetime
) -> bool:
    if not session.in_transaction() or command.kind != "notification.scan":
        raise ValueError("only notification scans can use this scheduled admission")
    lock = int.from_bytes(
        hashlib.sha256(f"{owner_id}:{command.operation_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    session.execute(select(func.pg_advisory_xact_lock(lock)))
    if (
        session.scalar(
            select(Job.id).where(
                Job.owner_id == owner_id,
                Job.kind == command.kind,
                Job.operation_id == command.operation_id,
            )
        )
        is not None
    ):
        return False
    JobService(session, clock=lambda: now).accept_in_transaction(owner_id=owner_id, command=command)
    return True


@dataclass(frozen=True, slots=True)
class OperatorJobHealth:
    queued_count: int
    queued_over_two_hours: int
    expired_running_count: int
    unknown_result_count: int
    oldest_queued_at: datetime | None


def load_operator_job_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> OperatorJobHealth:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("job health requires aware caller transaction")
    rows = session.execute(
        select(
            Job.status, Job.created_at, Job.next_run_at, Job.lease_expires_at, Job.last_error_code
        ).where(Job.owner_id == owner_id, Job.status.in_(["queued", "running", "failed"]))
    ).all()
    due = [
        row
        for row in rows
        if row.status == "queued" and (row.next_run_at is None or row.next_run_at <= now)
    ]
    return OperatorJobHealth(
        queued_count=len(due),
        queued_over_two_hours=sum(row.created_at <= now - timedelta(hours=2) for row in due),
        expired_running_count=sum(
            row.status == "running"
            and row.lease_expires_at is not None
            and row.lease_expires_at <= now
            for row in rows
        ),
        unknown_result_count=sum(
            bool(row.last_error_code and "unknown" in row.last_error_code) for row in rows
        ),
        oldest_queued_at=min((row.created_at for row in due), default=None),
    )


def republish_due_jobs_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime, limit: int = 100
) -> tuple[UUID, ...]:
    """Redispatch original due jobs; never reopen terminal or unknown paid jobs."""
    if not session.in_transaction() or now.utcoffset() is None or not 1 <= limit <= 1000:
        raise RuntimeError("job redispatch requires a bounded aware caller transaction")
    session.flush()
    rows = list(
        session.scalars(
            select(Job)
            .where(
                Job.owner_id == owner_id,
                or_(
                    (Job.status == "queued")
                    & or_(Job.next_run_at.is_(None), Job.next_run_at <= now),
                    (Job.status == "running") & (Job.lease_expires_at <= now),
                ),
            )
            .order_by(Job.created_at, Job.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    dispatched: list[UUID] = []
    for row in rows:
        if (
            session.scalar(
                select(OutboxMessage.id).where(
                    OutboxMessage.aggregate_id == row.id, OutboxMessage.published_at.is_(None)
                )
            )
            is not None
        ):
            continue
        last = (
            session.scalar(
                select(func.max(OutboxMessage.dispatch_sequence)).where(
                    OutboxMessage.aggregate_id == row.id
                )
            )
            or 0
        )
        session.add(
            OutboxMessage(
                id=uuid4(),
                aggregate_id=row.id,
                topic=JOB_ACCEPTED_TOPIC,
                message_key=row.id,
                event_type=JOB_ACCEPTED_EVENT_TYPE,
                dispatch_sequence=last + 1,
                payload={
                    "job_id": str(row.id),
                    "owner_id": str(owner_id),
                    "operation_id": str(row.operation_id),
                    "kind": row.kind,
                    "configuration_ref": row.configuration_ref,
                    "configuration_version": row.configuration_version,
                    "source_key": row.source_key,
                    "source_capability": row.source_capability,
                },
                available_at=now,
                created_at=now,
                published_at=None,
            )
        )
        dispatched.append(row.id)
    session.flush()
    return tuple(dispatched)


def record_operator_delivery_resolution_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, delivered: bool, now: datetime
) -> None:
    if not session.in_transaction():
        raise RuntimeError("job resolution requires caller transaction")
    row = session.scalar(
        select(Job).where(Job.owner_id == owner_id, Job.id == job_id).with_for_update()
    )
    if (
        row is None
        or row.kind not in {"operations.maintenance", "publication.indexnow"}
        or (
            row.kind == "publication.indexnow"
            and row.last_error_code != "indexnow_submission_unknown"
        )
        or row.status != "failed"
        or not row.last_error_code
        or "unknown" not in row.last_error_code
    ):
        raise ValueError("unknown delivery must be a terminal owned maintenance job")
    row.last_error_code = (
        "operations_delivery_confirmed" if delivered else "operations_delivery_not_delivered"
    )
    row.next_action = (
        "运营已在目的地确认送达" if delivered else "运营已确认未送达,可按原任务显式重试"
    )
    row.manual_retry_allowed, row.updated_at = not delivered, now


def load_watchdog_message_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> JobAcceptedMessage:
    if not session.in_transaction():
        raise RuntimeError("local watchdog dispatch requires caller transaction")
    job = session.scalar(select(Job).where(Job.owner_id == owner_id, Job.id == job_id))
    if job is None or job.kind != "operations.maintenance" or job.scope.get("action") != "watchdog":
        raise ValueError("only an owned watchdog job can execute outside the Kafka worker")
    outbox = session.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.aggregate_id == job_id,
            OutboxMessage.event_type == JOB_ACCEPTED_EVENT_TYPE,
        )
        .order_by(OutboxMessage.dispatch_sequence)
        .limit(1)
    )
    if outbox is None:
        raise RuntimeError("accepted watchdog has no original outbox")
    return JobAcceptedMessage.model_validate(
        {
            **outbox.payload,
            "message_id": outbox.id,
            "schema_version": 2,
            "event_type": JOB_ACCEPTED_EVENT_TYPE,
        }
    )


def record_operator_notification_resolution_in_transaction(
    session: Session, *, owner_id: UUID, delivery_id: UUID, delivered: bool, now: datetime
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("notification job resolution requires aware caller transaction")
    rows = list(
        session.scalars(
            select(Job)
            .where(
                Job.owner_id == owner_id,
                Job.kind == "notification.send",
                Job.scope["delivery_id"].astext == str(delivery_id),
            )
            .with_for_update()
        )
    )
    if (
        len(rows) != 1
        or rows[0].status != "failed"
        or rows[0].last_error_code != "notification_delivery_unknown"
    ):
        raise ValueError("notification resolution requires its original terminal unknown job")
    job = rows[0]
    job.last_error_code = (
        "notification_delivery_confirmed" if delivered else "notification_delivery_not_delivered"
    )
    job.manual_retry_allowed, job.updated_at = not delivered, now
    job.next_action = (
        "运营已核对目的地确认送达" if delivered else "运营确认未送达,可在原任务显式重试"
    )


def first_job_admitted_at_in_transaction(
    session: Session, *, owner_id: UUID, kind: str
) -> datetime | None:
    if not session.in_transaction() or not 0 < len(kind) <= 80:
        raise ValueError("job admission health requires caller transaction and bounded kind")
    return session.scalar(
        select(func.min(Job.created_at)).where(Job.owner_id == owner_id, Job.kind == kind)
    )
