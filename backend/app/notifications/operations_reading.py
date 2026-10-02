"""Delivery ledger health; no target addresses or credentials leave this reader."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notifications.models import NotificationDelivery


@dataclass(frozen=True, slots=True)
class NotificationDeliveryHealth:
    failed_last_day: int
    unknown_count: int


def load_delivery_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> NotificationDeliveryHealth:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("delivery health requires aware caller transaction")
    failed = session.scalar(
        select(func.count())
        .select_from(NotificationDelivery)
        .where(
            NotificationDelivery.owner_id == owner_id,
            NotificationDelivery.status == "failed",
            NotificationDelivery.updated_at >= now - timedelta(days=1),
            NotificationDelivery.updated_at <= now,
        )
    )
    unknown = session.scalar(
        select(func.count())
        .select_from(NotificationDelivery)
        .where(NotificationDelivery.owner_id == owner_id, NotificationDelivery.status == "unknown")
    )
    return NotificationDeliveryHealth(int(failed or 0), int(unknown or 0))
