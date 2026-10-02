"""Read an original group Job's frozen member context without foreign ORM."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobs.editorial_schemas import EditorialGroupManifest
from jobs.models import Job
from jobs.services import ContentJobContext
from sources.contracts import SourceCapability


def load_editorial_group_manifest_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> EditorialGroupManifest | None:
    if not session.in_transaction():
        raise RuntimeError("group context reads require caller transaction")
    job = session.scalar(select(Job).where(Job.owner_id == owner_id, Job.id == job_id))
    if (
        job is None
        or job.kind != "source.editorial.x_group"
        or job.source_key != "x"
        or job.source_capability != "search"
    ):
        return None
    raw = job.scope.get("editorial_group")
    if not isinstance(raw, str) or len(raw.encode()) > 262_144:
        return None
    try:
        manifest = EditorialGroupManifest.model_validate_json(raw)
    except (ValidationError, ValueError):
        return None
    if (
        manifest.owner_id != owner_id
        or manifest.sha256 != job.scope.get("group_hash")
        or job.configuration_ref != f"editorial-group:{manifest.sha256}"
        or job.configuration_version != 1
    ):
        return None
    return manifest


def load_content_job_context_for_editorial_member_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, profile_id: UUID
) -> ContentJobContext | None:
    manifest = load_editorial_group_manifest_in_transaction(
        session, owner_id=owner_id, job_id=job_id
    )
    if manifest is None:
        return None
    member = next((m for m in manifest.members if m.profile_id == profile_id), None)
    if member is None:
        return None
    return ContentJobContext(
        job_id=job_id,
        configuration_ref=f"editorial-source:{profile_id}",
        configuration_version=member.configuration_version,
        source_key=member.source_key,
        source_capability=SourceCapability.SEARCH,
        scan_kind=None,
    )


def load_active_editorial_profile_ids_in_transaction(
    session: Session, *, owner_id: UUID
) -> frozenset[UUID]:
    if not session.in_transaction():
        raise RuntimeError("active source Job reads require caller transaction")
    rows = session.scalars(
        select(Job).where(
            Job.owner_id == owner_id,
            Job.kind.in_(("source.editorial.poll", "source.editorial.x_group")),
            Job.status.in_(("queued", "running")),
        )
    )
    profiles: set[UUID] = set()
    for job in rows:
        if job.kind == "source.editorial.x_group":
            manifest = load_editorial_group_manifest_in_transaction(
                session, owner_id=owner_id, job_id=job.id
            )
            if manifest:
                profiles.update(m.profile_id for m in manifest.members)
        else:
            try:
                profiles.add(UUID(str(job.scope.get("profile_id"))))
            except ValueError:
                continue
    return frozenset(profiles)
