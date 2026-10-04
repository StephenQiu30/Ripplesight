"""Delete exact input dependants atomically through the existing observation cleanup target."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from content.editorial_rendered_models import ContentRenderedMaterial
from content.models import (
    ContentObservation,
    ContentObservationInput,
    ContentRecord,
    ContentVersion,
    ContentVersionInput,
)


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
    legacy_versions: set[UUID] = set()
    while pending:
        legacy = (
            set(
                session.scalars(
                    select(ContentVersionInput.content_version_id).where(
                        ContentVersionInput.owner_id == owner_id,
                        ContentVersionInput.observation_id.in_(pending),
                    )
                )
            )
            - legacy_versions
        )
        legacy_versions.update(legacy)
        derived = set(
            session.scalars(
                select(ContentObservationInput.output_observation_id).where(
                    ContentObservationInput.owner_id == owner_id,
                    ContentObservationInput.input_observation_id.in_(pending),
                )
            )
        )
        derived.update(
            session.scalars(
                select(ContentObservation.id).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.input_basis.is_(None),
                    ContentObservation.content_version_id.in_(legacy),
                )
            )
        )
        pending = derived - observations
        observations.update(pending)
        if len(observations) > 10000:
            raise ValueError("content deletion graph exceeds bounded transaction")
    candidate_versions = {
        v
        for v in session.scalars(
            select(ContentObservation.content_version_id).where(
                ContentObservation.owner_id == owner_id, ContentObservation.id.in_(observations)
            )
        )
        if v is not None
    }
    retained_versions = set(
        session.scalars(
            select(ContentObservation.content_version_id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_version_id.in_(candidate_versions),
                ContentObservation.id.not_in(observations),
            )
        )
    )
    versions = candidate_versions - retained_versions
    legacy_versions.update(candidate_versions)
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
    from jobs.content_cleanup import purge_analysis_job_materials_in_transaction
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
        legacy_content_version_ids=tuple(legacy_versions),
    )
    purge_alert_content_inputs_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=tuple(versions),
        observation_ids=tuple(observations),
    )
    ordered_versions = tuple(sorted(versions, key=str))
    ordered_observations = tuple(sorted(observations, key=str))
    ordered_legacy_versions = tuple(sorted(legacy_versions, key=str))
    for start in range(
        0, max(len(ordered_versions), len(ordered_observations), len(ordered_legacy_versions)), 1000
    ):
        batch = ordered_versions[start : start + 1000]
        obs_batch = ordered_observations[start : start + 1000]
        purge_publication_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=batch,
            observation_ids=obs_batch,
            legacy_content_version_ids=ordered_legacy_versions[start : start + 1000],
            now=now,
        )
        purge_event_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=batch,
            content_ids=tuple(empty_content_ids),
            observation_ids=obs_batch,
            legacy_content_version_ids=ordered_legacy_versions[start : start + 1000],
            now=now,
        )
        purge_analysis_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=batch,
            observation_ids=obs_batch,
            legacy_content_version_ids=ordered_legacy_versions[start : start + 1000],
            now=now,
        )
        purge_editorial_material_receipts_in_transaction(
            session, owner_id=owner_id, content_version_ids=batch, observation_ids=obs_batch
        )
    # Analysis-owned cleanup must first inspect the original call/Job prompt,
    # including legacy comment versions. Scrub its retained text only afterwards.
    purge_analysis_job_materials_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=ordered_observations,
        content_version_ids=ordered_versions,
        legacy_content_version_ids=ordered_legacy_versions,
    )
    session.execute(
        delete(ContentObservationInput).where(
            ContentObservationInput.owner_id == owner_id,
            (ContentObservationInput.output_observation_id.in_(observations))
            | (ContentObservationInput.input_observation_id.in_(observations)),
        )
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
            (ContentVersionInput.content_version_id.in_(versions))
            | (ContentVersionInput.observation_id.in_(observations)),
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
