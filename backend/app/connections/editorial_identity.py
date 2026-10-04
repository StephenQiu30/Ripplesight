"""Recheck internal source Job authority for a parser identity candidate without side effects."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceRun
from connections.editorial_rsshub import (
    load_current_editorial_profile_in_transaction,
    require_editorial_rsshub_execution_in_transaction,
)
from core.errors import ApplicationError
from jobs.schemas import JobStatus
from jobs.services import (
    load_content_job_context,
    load_job_cancellation_state_in_transaction,
    load_job_execution_configuration,
)
from sources.contracts import SourceCapability
from sources.editorial_identity import (
    EditorialNativeIdentityProof,
    verify_editorial_native_identity,
)
from sources.editorial_schemas import EditorialMaterial, fingerprint


def load_editorial_native_identity_source_material_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    configuration_version: int,
    job_id: UUID,
    material: EditorialMaterial,
    proof: EditorialNativeIdentityProof,
    now: datetime,
) -> EditorialMaterial:
    """Recover the original staged parser material, never identity from a body response."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("native identity reads require caller transaction and aware time")
    run = session.scalar(
        select(EditorialSourceRun)
        .where(
            EditorialSourceRun.owner_id == owner_id,
            EditorialSourceRun.profile_id == profile_id,
            EditorialSourceRun.job_id == job_id,
        )
        .with_for_update()
    )
    raw = run.prepared_page.get("materials") if run is not None and run.prepared_page else None
    if not isinstance(raw, list):
        raise ApplicationError("editorial_version_conflict")
    candidates = [
        value
        for value in raw
        if isinstance(value, dict)
        and value.get("url") == material.url
        and value.get("identity_key") == material.identity_key
        and value.get("external_id") == material.external_id
        and value.get("native_identity") == proof.model_dump(mode="json")
    ]
    if len(candidates) != 1:
        raise ApplicationError("editorial_version_conflict")
    original = EditorialMaterial.model_validate(candidates[0])
    require_editorial_native_identity_authority_in_transaction(
        session,
        owner_id=owner_id,
        profile_id=profile_id,
        configuration_version=configuration_version,
        job_id=job_id,
        material=original,
        proof=proof,
        now=now,
    )
    return original


def require_editorial_native_identity_authority_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    profile_id: UUID,
    configuration_version: int,
    job_id: UUID,
    material: EditorialMaterial,
    proof: EditorialNativeIdentityProof,
    now: datetime,
) -> None:
    """A typed proof is insufficient without the original staged, current approved Job.

    Uses only connections ORM and Job/source-owned helpers in the caller's
    transaction. Field-purpose admission remains the Content writer's decision.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("native identity authority requires caller transaction and aware time")
    profile, version, configuration = load_current_editorial_profile_in_transaction(
        session, owner_id=owner_id, profile_id=profile_id
    )
    context = load_content_job_context(session, owner_id=owner_id, job_id=job_id)
    execution = load_job_execution_configuration(session, job_id=job_id)
    cancellation = load_job_cancellation_state_in_transaction(
        session, owner_id=owner_id, job_id=job_id
    )
    run = session.scalar(
        select(EditorialSourceRun)
        .where(
            EditorialSourceRun.owner_id == owner_id,
            EditorialSourceRun.profile_id == profile_id,
            EditorialSourceRun.job_id == job_id,
        )
        .with_for_update()
    )
    if (
        version.kind != "rss"
        or version.version != configuration_version
        or context is None
        or execution is None
        or execution.owner_id != owner_id
        or execution.kind != "source.editorial.poll"
        or context.source_key != profile.source_key
        or context.source_capability != SourceCapability.SEARCH
        or context.configuration_ref != f"editorial-source:{profile_id}"
        or context.configuration_version != configuration_version
        or execution.scope.get("profile_id") != str(profile_id)
        or execution.scope.get("revision") != profile.revision
        or cancellation is None
        or cancellation.status is not JobStatus.RUNNING
        or cancellation.requested_at is not None
        or run is None
        or run.status != "staged"
        or run.configuration_version != configuration_version
        or run.profile_revision != profile.revision
        or run.operation_id != execution.operation_id
        or run.prepared_page is None
        or run.input_hash
        != fingerprint(
            {
                "profile_id": str(profile_id),
                "configuration_version": configuration_version,
                "revision": profile.revision,
                "job_id": str(job_id),
            }
        )
        or verify_editorial_native_identity(material, configuration=configuration) != proof
    ):
        raise ApplicationError("editorial_version_conflict")
    staged_materials = run.prepared_page.get("materials")
    if not isinstance(staged_materials, list) or not any(
        value == material.model_dump(mode="json") for value in staged_materials
    ):
        raise ApplicationError("editorial_version_conflict")
    admission = require_editorial_rsshub_execution_in_transaction(
        session,
        owner_id=owner_id,
        profile_id=profile_id,
        configuration_version=configuration_version,
        revision=profile.revision,
        now=now,
    )
    if (
        admission.configuration_sha256 != proof.configuration_sha256
        or admission.revision != proof.collector_revision
    ):
        raise ApplicationError("editorial_version_conflict")
