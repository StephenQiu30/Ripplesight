"""Freeze exact original input permission for stored-material alert metrics."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from content.models import ContentObservation
from content.report_reading import report_inputs_readable_in_transaction
from content.version_inputs import observations_readable_in_transaction


@dataclass(frozen=True)
class AlertContentInput:
    version_id: UUID
    observation_ids: tuple[UUID, ...]
    first_received_at: datetime


def freeze_alert_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    version_ids: tuple[UUID, ...],
    as_of: datetime,
    now: datetime,
) -> dict[UUID, AlertContentInput]:
    if (
        not session.in_transaction()
        or len(version_ids) > 1000
        or now.utcoffset() is None
        or as_of.utcoffset() is None
    ):
        raise ValueError("alert inputs require bounded aware caller transaction")
    result = {}
    for version_id in set(version_ids):
        rows = tuple(
            session.scalars(
                select(ContentObservation)
                .where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_version_id == version_id,
                    ContentObservation.received_at < as_of,
                )
                .order_by(ContentObservation.received_at, ContentObservation.id)
            )
        )
        if not rows:
            continue
        # The oldest original receipt defines the acquired-material window, while
        # the exact selected observation is frozen and cannot be substituted later.
        original = rows[0]
        if not observations_readable_in_transaction(
            session, owner_id=owner_id, observation_ids=(original.id,), now=now
        ) or not report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(version_id,),
            observation_ids=(original.id,),
            now=now,
        ):
            continue
        first_received = session.scalar(
            select(func.min(ContentObservation.received_at)).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_id == original.content_id,
                ContentObservation.received_at < as_of,
            )
        )
        assert first_received is not None
        result[version_id] = AlertContentInput(version_id, (original.id,), first_received)
    return result
