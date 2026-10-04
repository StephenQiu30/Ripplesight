"""Complete an editorial post in its original identity with ALL frozen input rights."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.schemas import SourceEntryPoint
from content.editorial_rendered import (
    prepare_editorial_rendered,
    save_editorial_rendered_in_transaction,
)
from content.editorial_schemas import EditorialContentResult
from content.models import ContentObservation, ContentRecord, ContentVersion
from content.schemas import PersistContentPostInput
from content.services import ContentService
from content.topic_matches import match_editorial_content_in_transaction
from content.version_inputs import (
    observations_readable_in_transaction,
    save_version_inputs_in_transaction,
    version_inputs_readable_in_transaction,
)
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import SourceAccessPolicyService
from sources.contracts import SourceCapability, SourceDocument
from sources.editorial_schemas import EditorialBodyTarget, EditorialMaterial, fingerprint


def load_editorial_body_target_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    run_id: UUID,
    profile_id: UUID,
    configuration_version: int,
    profile_revision: int,
    job_id: UUID,
    operation_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    material: EditorialMaterial,
    now: datetime,
) -> EditorialBodyTarget | None:
    if not session.in_transaction():
        raise RuntimeError("body targets require the caller transaction")
    record = session.get(ContentRecord, content_id)
    version = session.get(ContentVersion, content_version_id)
    if (
        record is None
        or version is None
        or record.owner_id != owner_id
        or version.owner_id != owner_id
        or version.content_id != content_id
        or record.native_scope != f"editorial-profile:{profile_id}"
        or record.external_id != (material.external_id or material.identity_key)
    ):
        raise ApplicationError("editorial_material_unavailable")
    if version.text_scope == "full":
        return None
    observation = session.scalar(
        select(ContentObservation)
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id == content_id,
            ContentObservation.content_version_id == content_version_id,
        )
        .order_by(ContentObservation.received_at.desc(), ContentObservation.id.desc())
        .limit(1)
    )
    if observation is None:
        raise ApplicationError("editorial_material_unavailable")
    target = EditorialBodyTarget(
        owner_id=owner_id,
        run_id=run_id,
        profile_id=profile_id,
        configuration_version=configuration_version,
        profile_revision=profile_revision,
        job_id=job_id,
        operation_id=operation_id,
        content_id=content_id,
        expected_content_version_id=content_version_id,
        feed_observation_id=observation.id,
        material=material.model_copy(
            update={
                "body_text": None,
                "body_markdown": None,
                "body_html": None,
                "excerpt": None,
                "media": (),
                "media_details": (),
                "metadata": {},
            }
        ),
    )
    require_editorial_body_input_in_transaction(session, target=target, now=now)
    return target


def require_editorial_body_input_in_transaction(
    session: Session,
    *,
    target: EditorialBodyTarget,
    now: datetime,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("body input checks require the caller transaction")
    record = session.scalar(
        select(ContentRecord)
        .where(
            ContentRecord.owner_id == target.owner_id,
            ContentRecord.id == target.content_id,
        )
        .with_for_update()
    )
    feed = session.get(ContentObservation, target.feed_observation_id)
    latest = session.scalar(
        select(ContentObservation)
        .where(
            ContentObservation.owner_id == target.owner_id,
            ContentObservation.content_id == target.content_id,
            ContentObservation.content_version_id.is_not(None),
        )
        .order_by(ContentObservation.received_at.desc(), ContentObservation.id.desc())
        .limit(1)
    )
    if (
        record is None
        or record.native_scope != f"editorial-profile:{target.profile_id}"
        or record.external_id != (target.material.external_id or target.material.identity_key)
        or feed is None
        or feed.owner_id != target.owner_id
        or feed.content_id != target.content_id
        or feed.content_version_id != target.expected_content_version_id
        or latest is None
        or latest.content_version_id != target.expected_content_version_id
        or not observations_readable_in_transaction(
            session,
            owner_id=target.owner_id,
            observation_ids=(target.feed_observation_id,),
            now=now,
        )
        or not version_inputs_readable_in_transaction(
            session,
            owner_id=target.owner_id,
            content_version_ids=(target.expected_content_version_id,),
            now=now,
        )
    ):
        raise ApplicationError("editorial_material_unavailable")


def complete_editorial_body_in_transaction(
    session: Session,
    *,
    target: EditorialBodyTarget,
    document: SourceDocument,
    source_key: str,
    capability: SourceCapability,
    policy_version: int,
    connection_id: UUID,
    connection_version: int,
    now: datetime,
) -> EditorialContentResult:
    require_editorial_body_input_in_transaction(session, target=target, now=now)
    if document.request_url != target.target_url or document.observed_at > now:
        raise ApplicationError("editorial_material_unavailable")
    m = target.material
    payload: dict[str, object] = {
        "object_type": "post",
        "external_id": m.external_id or m.identity_key,
        "identity_basis": "guid" if m.external_id else "url_fallback",
        "canonical_url": m.url,
        "author_name": m.author,
        "published_at": m.published_at.isoformat() if m.published_at else None,
        "text_scope": document.text_scope,
        "text_origin": "machine_extracted",
        "text_origin_ref": document.extractor_version,
        "title": m.title,
        "body": document.text,
        "truncation_reason": "collector_limit" if document.text_scope == "truncated" else None,
    }
    admission = SourceAccessPolicyService(session, clock=lambda: now).admit_payload_in_transaction(
        owner_id=target.owner_id,
        source_key=source_key,
        capability=capability,
        data_class=DataClass.STRUCTURED,
        collected_at=document.observed_at,
        payload=payload,
    )
    required = {
        "external_id",
        "canonical_url",
        "title",
        "body",
        "text_scope",
        "text_origin",
        "text_origin_ref",
    }
    if document.text_scope == "truncated":
        required.add("truncation_reason")
    if (
        admission.policy_version != policy_version
        or not required.issubset(admission.fields)
        or any(admission.fields.get(field) != payload[field] for field in required)
    ):
        raise ApplicationError("editorial_material_unavailable")
    representation = prepare_editorial_rendered(
        m.model_copy(
            update={
                "body_text": document.text,
                "body_markdown": document.text,
                "body_html": None,
                "content_format": "markdown",
                "body_status": "ok",
                "media": (),
                "media_details": (),
            }
        )
    )
    result = ContentService(session, clock=lambda: now).persist_post_in_transaction(
        owner_id=target.owner_id,
        command=PersistContentPostInput(
            job_id=target.job_id,
            source_operation_id=uuid5(
                uuid5(target.operation_id, "editorial-body-v1"), m.identity_key
            ),
            connection_id=connection_id,
            connection_version=connection_version,
            entry_point=SourceEntryPoint.SCHEDULED,
            component_name="editorial-body",
            component_version="2.11.162",
            native_scope=f"editorial-profile:{target.profile_id}",
            admission=admission,
        ),
        representation_fingerprint=fingerprint(
            {
                "representation": representation.sha256,
                "feed_observation_id": str(target.feed_observation_id),
            }
        ),
    )
    version = result.latest_observation.content_version
    if result.id != target.content_id or version is None:
        raise ApplicationError("editorial_material_unavailable")
    inputs = (target.feed_observation_id, result.latest_observation.id)
    save_version_inputs_in_transaction(
        session, owner_id=target.owner_id, content_version_id=version.id, observation_ids=inputs
    )
    save_editorial_rendered_in_transaction(
        session,
        owner_id=target.owner_id,
        content_id=result.id,
        content_version_id=version.id,
        representation=representation,
        now=now,
    )
    match_editorial_content_in_transaction(
        session,
        owner_id=target.owner_id,
        profile_id=target.profile_id,
        profile_configuration_version=target.configuration_version,
        content_id=result.id,
        content_version_id=version.id,
        observation_id=result.latest_observation.id,
        job_id=target.job_id,
        connection_id=connection_id,
        connection_version=connection_version,
        policy_version=policy_version,
        now=now,
        input_observation_ids=inputs,
        grouped_job=False,
    )
    return EditorialContentResult(
        content_id=result.id,
        content_version_id=version.id,
        observation_id=result.latest_observation.id,
    )
