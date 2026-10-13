"""Whole-board cleanup, preserving rejection audits and exact independent observations."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from content.hotlist_material import entry_resource_id
from content.identity_history import lock_owner_history_in_transaction
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentObservation, HotlistSnapshot
from evidence.related_cleanup import request_related_resource_deletions_in_transaction
from evidence.schemas import CleanupTargetKind
from evidence.services import registered_cleanup_authorized_in_transaction


class HotlistSnapshotCleanup:
    """Deleting one original position conservatively purges the entire fixed board."""

    def __init__(
        self, sessions: sessionmaker[Session], *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, reference: str) -> None:
        identifier = UUID(reference)
        with self._sessions() as session, session.begin():
            snapshot = session.get(HotlistSnapshot, identifier)
            if snapshot is None:
                return
            owner = snapshot.owner_id
            lock_owner_history_in_transaction(session, owner_id=owner)
            identities = {
                "hotlist_snapshot": {identifier},
                "hotlist_entry": {entry_resource_id(identifier, i) for i in range(1, 101)},
            }
            if not registered_cleanup_authorized_in_transaction(
                session,
                owner_id=owner,
                identities=identities,
                kind=CleanupTargetKind.POSTGRES_HOTLIST_SNAPSHOT,
                reference=reference,
            ):
                raise ValueError("hotlist cleanup has no matching registered deletion decision")
            now = self._clock()
            for resource_type, ids in identities.items():
                request_related_resource_deletions_in_transaction(
                    session,
                    owner_id=owner,
                    resource_ids=tuple(ids),
                    resource_type=resource_type,
                    now=now,
                )
            observations = tuple(
                session.scalars(
                    select(ContentObservation.id).where(
                        ContentObservation.owner_id == owner,
                        ContentObservation.job_id == snapshot.job_id,
                    )
                )
            )
            for observation_id in observations:
                purge_observation_dependants_in_transaction(
                    session, owner_id=owner, observation_id=observation_id, now=now
                )
            session.execute(
                delete(HotlistSnapshot).where(
                    HotlistSnapshot.owner_id == owner, HotlistSnapshot.id == identifier
                )
            )
