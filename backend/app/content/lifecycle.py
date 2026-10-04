"""Delete exact input dependants atomically through the existing observation cleanup target."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from content.editorial_rendered_models import ContentRenderedMaterial
from content.models import ContentObservation, ContentRecord, ContentVersion, ContentVersionInput


def purge_observation_dependants_in_transaction(
    session: Session, *, owner_id: UUID, observation_id: UUID, now: datetime
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("content lifecycle requires aware caller transaction")
    original = session.scalar(
        select(ContentObservation).where(
            ContentObservation.owner_id == owner_id, ContentObservation.id == observation_id
        )
    )
    if original is None:
        return
    observations = {observation_id}
    pending = {observation_id}
    versions: set[UUID] = set()
    while pending:
        derived = (
            set(
                session.scalars(
                    select(ContentVersionInput.content_version_id).where(
                        ContentVersionInput.owner_id == owner_id,
                        ContentVersionInput.observation_id.in_(pending),
                    )
                )
            )
            - versions
        )
        versions.update(derived)
        pending = (
            set(
                session.scalars(
                    select(ContentObservation.id).where(
                        ContentObservation.owner_id == owner_id,
                        ContentObservation.content_version_id.in_(derived),
                    )
                )
            )
            - observations
        )
        observations.update(pending)
    if original.content_version_id is not None:
        retained = session.scalar(
            select(ContentObservation.id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_version_id == original.content_version_id,
                ContentObservation.id.not_in(observations),
            )
        )
        if retained is None:
            versions.add(original.content_version_id)
    content_ids = set(
        session.scalars(
            select(ContentObservation.content_id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.id.in_(observations),
            )
        )
    )
    empty_content_ids = content_ids - set(
        session.scalars(
            select(ContentObservation.content_id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_id.in_(content_ids),
                ContentObservation.id.not_in(observations),
            )
        )
    )
    from analysis.content_cleanup import purge_analysis_content_inputs_in_transaction
    from connections.editorial_cleanup import purge_editorial_material_receipts_in_transaction
    from events.content_cleanup import purge_event_content_inputs_in_transaction
    from evidence.related_cleanup import request_related_resource_deletions_in_transaction
    from notifications.alert_services import purge_alert_content_inputs_in_transaction
    from publication.content_cleanup import purge_publication_content_inputs_in_transaction
    from reports.content_cleanup import purge_report_content_inputs_in_transaction

    # The barrier is committed in the same transaction as cleanup. No surviving alias can lift it.
    request_related_resource_deletions_in_transaction(
        session,
        owner_id=owner_id,
        resource_type="content_observation",
        resource_ids=tuple(observations),
        now=now,
    )
    # A report/export freezes observation permission even when another observation
    # keeps the raw version. Always purge exact observation dependants.
    purge_report_content_inputs_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=tuple(versions),
        observation_ids=tuple(observations),
    )
    purge_alert_content_inputs_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=tuple(versions),
        observation_ids=tuple(observations),
    )
    for start in range(0, len(versions), 1000):
        batch = tuple(sorted(versions, key=str)[start : start + 1000])
        purge_publication_content_inputs_in_transaction(
            session, owner_id=owner_id, content_version_ids=batch, now=now
        )
        purge_event_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=batch,
            content_ids=tuple(empty_content_ids),
            now=now,
        )
        purge_analysis_content_inputs_in_transaction(
            session, owner_id=owner_id, content_version_ids=batch, now=now
        )
        purge_editorial_material_receipts_in_transaction(
            session, owner_id=owner_id, content_version_ids=batch
        )
    session.execute(
        delete(ContentRenderedMaterial).where(
            ContentRenderedMaterial.owner_id == owner_id,
            ContentRenderedMaterial.content_version_id.in_(versions),
        )
    )
    session.execute(
        delete(ContentVersionInput).where(
            ContentVersionInput.owner_id == owner_id,
            ContentVersionInput.content_version_id.in_(versions),
        )
    )
    session.execute(
        delete(ContentObservation).where(
            ContentObservation.owner_id == owner_id, ContentObservation.id.in_(observations)
        )
    )
    session.execute(
        delete(ContentVersion).where(
            ContentVersion.owner_id == owner_id, ContentVersion.id.in_(versions)
        )
    )
    session.execute(
        delete(ContentRecord).where(
            ContentRecord.owner_id == owner_id, ContentRecord.id.in_(empty_content_ids)
        )
    )
