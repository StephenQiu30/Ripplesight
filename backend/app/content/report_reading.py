"""Validate every frozen report input inside the caller's transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.models import ContentObservation


def report_inputs_readable_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    observation_ids: tuple[UUID, ...],
    now: datetime,
) -> bool:
    """Require exact original Evidence and current field permission; never substitute versions."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("report inputs require an aware caller transaction")
    from content.observation_inputs import observation_input_closure_in_transaction
    from content.version_inputs import observations_readable_in_transaction
    from core.errors import ApplicationError

    versions = set(content_version_ids)
    originals = set(observation_ids)
    if not versions:
        return not originals
    if not originals:
        return False
    try:
        closure = observation_input_closure_in_transaction(
            session, owner_id=owner_id, observation_ids=tuple(originals)
        )
    except ApplicationError:
        return False
    if not observations_readable_in_transaction(
        session, owner_id=owner_id, observation_ids=closure, now=now
    ):
        return False
    rows = tuple(
        session.scalars(
            select(ContentObservation).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_version_id.in_(versions),
                ContentObservation.id.in_(originals),
            )
        )
    )
    return {r.content_version_id for r in rows} == versions
