"""Validate every frozen report input inside the caller's transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.models import ContentObservation
from content.version_inputs import legacy_content_versions_readable_in_transaction


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
    if originals:
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
    if originals and {r.content_version_id for r in rows} != versions:
        return False
    if not originals:
        # Legacy manifests without observations must remain on the strict legacy graph.
        return legacy_content_versions_readable_in_transaction(
            session, owner_id=owner_id, content_version_ids=tuple(versions), now=now
        ) and not session.scalar(
            select(ContentObservation.id)
            .where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_version_id.in_(versions),
                ContentObservation.input_basis.is_not(None),
            )
            .limit(1)
        )
    return True
