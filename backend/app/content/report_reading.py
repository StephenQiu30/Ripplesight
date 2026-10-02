"""Validate every frozen report input inside the caller's transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.models import ContentObservation, ContentVersion
from content.schemas import EventContentReadReference
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
    readable_resource_ids_query,
)
from jobs.services import load_content_job_context


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
    versions = sorted(set(content_version_ids), key=str)
    observation_set = set(observation_ids)
    readable = readable_resource_ids_query(
        owner_id=owner_id, resource_type="content_observation", now=now
    )
    for start in range(0, len(observation_ids), 500):
        batch = set(observation_ids[start : start + 500])
        rows = session.execute(
            select(ContentObservation.id, ContentObservation.content_version_id).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.id.in_(batch),
                ContentObservation.id.in_(readable),
            )
        ).all()
        if {row[0] for row in rows} != batch or any(row[1] not in versions for row in rows):
            return False
    if observation_set and not versions:
        return False
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    for start in range(0, len(versions), 500):
        batch_versions = versions[start : start + 500]
        version_rows = session.execute(
            select(ContentVersion.id, ContentVersion.content_id).where(
                ContentVersion.owner_id == owner_id,
                ContentVersion.id.in_(batch_versions),
            )
        ).all()
        if {row[0] for row in version_rows} != set(batch_versions):
            return False
        references = tuple(
            EventContentReadReference(content_id=row[1], content_version_id=row[0])
            for row in version_rows
        )
        items = load_event_member_content_in_transaction(
            session, owner_id=owner_id, references=references, now=now
        )
        if len(items) != len(references):
            return False
        for reference in references:
            item = items[reference]
            version = item.observation.content_version
            if (
                version is None
                or item.current_visibility is None
                or item.current_visibility.status != "visible"
            ):
                return False
            observation = session.get(ContentObservation, item.observation.id)
            context = (
                load_content_job_context(session, owner_id=owner_id, job_id=observation.job_id)
                if observation is not None
                else None
            )
            if context is None or context.source_capability is None:
                return False
            payload: dict[str, object] = {}
            if version.body:
                payload["body"] = version.body
            if version.title:
                payload["title"] = version.title
            if not payload:
                continue
            try:
                admitted = policy.admit_payload_in_transaction(
                    owner_id=owner_id,
                    source_key=item.source_key,
                    capability=context.source_capability,
                    data_class=DataClass.STRUCTURED,
                    collected_at=item.observation.observed_at,
                    payload=payload,
                )
            except (SourceAccessUnavailableError, RetentionPolicyUnavailableError, ValueError):
                return False
            if set(admitted.fields) != set(payload):
                return False
    return True
