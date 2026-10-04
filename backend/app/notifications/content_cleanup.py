"""Purge stored notification material when its fixed subject has been removed locally."""

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from notifications.models import NotificationDelivery


def purge_notification_subjects_in_transaction(
    session: Session, *, owner_id: UUID, subject_ids: tuple[UUID, ...]
) -> None:
    if not session.in_transaction():
        raise RuntimeError("notification cleanup requires caller transaction")
    session.execute(
        delete(NotificationDelivery).where(
            NotificationDelivery.owner_id == owner_id,
            NotificationDelivery.subject_id.in_(subject_ids),
        )
    )
