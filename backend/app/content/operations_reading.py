"""Owner-partitioned ingestion statistics; aggregates expose no stored content."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from content.models import ContentRecord


@dataclass(frozen=True, slots=True)
class SourceIngestionWindow:
    source_key: str
    current_count: int
    previous_count: int
    first_received_at: datetime
    last_received_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionHealth:
    sources: tuple[SourceIngestionWindow, ...]
    last_received_at: datetime | None


def load_ingestion_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> IngestionHealth:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("ingestion health requires aware caller transaction")
    current, previous = now - timedelta(days=7), now - timedelta(days=14)
    rows = session.execute(
        select(
            ContentRecord.source_key,
            func.sum(case((ContentRecord.created_at >= current, 1), else_=0)),
            func.sum(
                case(
                    (
                        (ContentRecord.created_at >= previous)
                        & (ContentRecord.created_at < current),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.min(ContentRecord.created_at),
            func.max(ContentRecord.created_at),
        )
        .where(
            ContentRecord.owner_id == owner_id,
            ContentRecord.object_type != "comment",
            ContentRecord.created_at <= now,
        )
        .group_by(ContentRecord.source_key)
        .order_by(ContentRecord.source_key)
    ).all()
    sources = tuple(
        SourceIngestionWindow(key, int(first), int(second), earliest, latest)
        for key, first, second, earliest, latest in rows
    )
    return IngestionHealth(sources, max((row.last_received_at for row in sources), default=None))
