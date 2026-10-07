"""Bounded delivery from the canonical outbox for an explicitly scoped host runner."""

from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from jobs.execution import MessageReference
from jobs.models import Job, OutboxMessage, ProcessedMessage
from jobs.schemas import JobMessage
from jobs.services import JOB_EVENT_SCHEMA_VERSIONS, OutboxEnvelope


def pending_source_deliveries(
    session: Session,
    *,
    owner_id: UUID,
    source_key: str,
    now: datetime,
) -> tuple[tuple[JobMessage, MessageReference], ...]:
    """No new queue; Kafka may later redeliver the same id and observe it processed."""
    rows = session.scalars(
        select(OutboxMessage)
        .join(Job, Job.id == OutboxMessage.aggregate_id)
        .where(
            Job.owner_id == owner_id,
            Job.source_key == source_key,
            Job.scope["source_adapter_version"].as_string() == "bilibili-chrome-poc-1",
            Job.kind.in_(("keyword.search", "source.comments")),
            Job.status.in_(("queued", "running")),
            or_(Job.lease_expires_at.is_(None), Job.lease_expires_at <= now),
            or_(Job.next_run_at.is_(None), Job.next_run_at <= now),
            OutboxMessage.available_at <= now,
            ~select(ProcessedMessage.id).where(ProcessedMessage.id == OutboxMessage.id).exists(),
        )
        .order_by(OutboxMessage.created_at, OutboxMessage.dispatch_sequence)
        .limit(4)
    ).all()
    return tuple(
        (
            TypeAdapter(JobMessage).validate_python(
                OutboxEnvelope(
                    message_id=row.id,
                    topic=row.topic,
                    message_key=row.message_key,
                    event_type=row.event_type,
                    schema_version=JOB_EVENT_SCHEMA_VERSIONS[row.event_type],
                    payload=dict(row.payload),
                ).message_body()
            ),
            MessageReference(
                message_id=row.id,
                topic=f"local.outbox.{row.id}",
                partition=0,
                offset=row.dispatch_sequence,
            ),
        )
        for row in rows
    )
