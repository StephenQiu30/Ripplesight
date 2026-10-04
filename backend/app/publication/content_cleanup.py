"""Withdraw public output and purge its stored text before original version deletion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from evidence.related_cleanup import request_related_resource_deletions_in_transaction
from notifications.content_cleanup import purge_notification_subjects_in_transaction
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.publication_models import (
    PublicationRecord,
    PublicationRevision,
    PublicationSelectedChange,
)
from publication.services import PublicationService


def purge_publication_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    now: datetime,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("publication cleanup requires caller transaction")
    publisher = PublicationService(session)
    publisher._lock(owner_id)
    publications = tuple(
        session.scalars(
            select(PublicationRecord).where(
                PublicationRecord.owner_id == owner_id,
                PublicationRecord.content_version_id.in_(content_version_ids),
            )
        )
    )
    for row in publications:
        # Live input guards already block this output; publish records its withdrawal first.
        publisher.publish_in_transaction(owner_id=owner_id, content_id=row.content_id, now=now)
    content_ids = tuple(row.content_id for row in publications)
    purge_notification_subjects_in_transaction(session, owner_id=owner_id, subject_ids=content_ids)
    session.execute(
        delete(PublicationSelectedChange).where(
            PublicationSelectedChange.owner_id == owner_id,
            PublicationSelectedChange.content_id.in_(content_ids),
        )
    )
    session.execute(
        delete(PublicationRevision).where(
            PublicationRevision.owner_id == owner_id,
            PublicationRevision.content_id.in_(content_ids),
        )
    )
    session.execute(
        delete(PublicationRecord).where(
            PublicationRecord.owner_id == owner_id, PublicationRecord.content_id.in_(content_ids)
        )
    )
    if publications:
        # A reset prevents clients from interpreting physically removed ledger entries as complete.
        publisher.reset_sync_epoch_in_transaction(owner_id=owner_id, now=now)
    runs = tuple(
        session.scalars(
            select(PublicationMediaRun.id).where(
                PublicationMediaRun.owner_id == owner_id,
                PublicationMediaRun.content_version_id.in_(content_version_ids),
            )
        )
    )
    resource_ids = tuple(
        value
        for value in session.scalars(
            select(PublicationMediaFile.evidence_resource_id).where(
                PublicationMediaFile.owner_id == owner_id,
                PublicationMediaFile.run_id.in_(runs),
                PublicationMediaFile.evidence_resource_id.is_not(None),
            )
        )
        if value is not None
    )
    request_related_resource_deletions_in_transaction(
        session, owner_id=owner_id, resource_ids=resource_ids, resource_type=None, now=now
    )
    session.execute(
        delete(PublicationMediaFile).where(
            PublicationMediaFile.owner_id == owner_id, PublicationMediaFile.run_id.in_(runs)
        )
    )
    session.execute(
        delete(PublicationMediaRun).where(
            PublicationMediaRun.owner_id == owner_id, PublicationMediaRun.id.in_(runs)
        )
    )
