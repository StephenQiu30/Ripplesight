"""Withdraw public output and purge its stored text before original version deletion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from evidence.related_cleanup import request_related_resource_deletions_in_transaction
from notifications.content_cleanup import purge_notification_subjects_in_transaction
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.projection import fingerprint
from publication.publication_models import (
    PublicationRecord,
    PublicationRevision,
    PublicationSelectedChange,
)
from publication.schemas import ProjectionView
from publication.services import PublicationService


def _uses(value: object, identifiers: set[str]) -> bool:
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, dict):
        return any(_uses(item, identifiers) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_uses(item, identifiers) for item in value)
    return False


def purge_publication_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    now: datetime,
    observation_ids: tuple[UUID, ...] = (),
    legacy_content_version_ids: tuple[UUID, ...] = (),
) -> None:
    if not session.in_transaction():
        raise RuntimeError("publication cleanup requires caller transaction")
    publisher = PublicationService(session)
    publisher._lock(owner_id)
    removed_observations = {str(value) for value in observation_ids}
    removed_versions = set(content_version_ids)
    records = tuple(
        session.scalars(select(PublicationRecord).where(PublicationRecord.owner_id == owner_id))
    )
    deleted_records = tuple(
        row
        for row in records
        if row.content_version_id in removed_versions
        or (
            row.data.get("observation_id") is None
            and row.content_version_id in legacy_content_version_ids
        )
    )
    deleted_content_ids = tuple(row.content_id for row in deleted_records)
    withdrawn_content_ids = []
    for row in records:
        if row.content_id in deleted_content_ids or not _uses(row.data, removed_observations):
            continue
        # Scrub the selected A projection. Do not republish a latest independent B observation.
        old = ProjectionView.model_validate(row.data)
        withdrawn = old.model_copy(
            update={
                "visibility": "withdrawn",
                "eligible": False,
                "selected": False,
                "indexable": False,
                "syndicate": False,
                "body_mode": "summary",
                "title": "材料已撤回",
                "original_title": None,
                "summary": None,
                "reason": None,
                "tags": [],
                "score": None,
                "media_candidate_count": 0,
                "input_fingerprint": fingerprint(
                    {
                        "removed_inputs": sorted(removed_observations),
                        "original": old.input_fingerprint,
                    }
                ),
            }
        )
        publisher._persist(owner_id, withdrawn, previous=row, now=now, reason="fixed_input_deleted")
        withdrawn_content_ids.append(row.content_id)
    # _persist also schedules selected-change rows; expose them to the fixed
    # cleanup query even when the owning Session has autoflush disabled.
    session.flush()
    affected_revisions = []
    for revision in session.scalars(
        select(PublicationRevision).where(PublicationRevision.owner_id == owner_id)
    ):
        if (
            revision.content_id in deleted_content_ids
            or _uses(revision.data, removed_observations)
            or str(revision.data.get("content_version_id")) in {str(v) for v in removed_versions}
            or (
                revision.data.get("observation_id") is None
                and str(revision.data.get("content_version_id"))
                in {str(v) for v in legacy_content_version_ids}
            )
        ):
            affected_revisions.append((revision.content_id, revision.revision))
    for change in session.scalars(
        select(PublicationSelectedChange).where(PublicationSelectedChange.owner_id == owner_id)
    ):
        if (
            change.content_id in deleted_content_ids
            or (change.content_id, change.publication_revision) in affected_revisions
        ):
            session.delete(change)
    # Delete dependent rows while the publication still exists. These models do
    # not have ORM relationships that could order pending deletes for the FK.
    session.flush()
    for start in range(0, len(affected_revisions), 500):
        session.execute(
            delete(PublicationRevision).where(
                PublicationRevision.owner_id == owner_id,
                tuple_(PublicationRevision.content_id, PublicationRevision.revision).in_(
                    affected_revisions[start : start + 500]
                ),
            )
        )
    purge_notification_subjects_in_transaction(
        session,
        owner_id=owner_id,
        subject_ids=tuple(set(deleted_content_ids) | set(withdrawn_content_ids)),
    )
    for row in deleted_records:
        session.delete(row)
    # Epoch rebuilding reads the remaining records. Flush pending deletes first
    # so it cannot create a fresh selected change for a record being removed.
    session.flush()
    if affected_revisions or deleted_records or withdrawn_content_ids:
        publisher.reset_sync_epoch_in_transaction(owner_id=owner_id, now=now)
    runs = tuple(
        run.id
        for run in session.scalars(
            select(PublicationMediaRun).where(PublicationMediaRun.owner_id == owner_id)
        )
        if run.content_version_id in removed_versions
        or _uses(run.fixed_reference, removed_observations)
        or (run.observation_id is None and run.content_version_id in legacy_content_version_ids)
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
