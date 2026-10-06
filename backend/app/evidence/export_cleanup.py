"""Attach a private artifact to each actual original input's unchanged lifecycle deadline."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence.models import DeletionDirective, EvidenceResource
from evidence.schemas import CleanupTargetKind, CleanupTargetSpec
from evidence.services import ResourceUnavailableError


def attach_export_cleanup_targets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    observation_ids: tuple[UUID, ...],
    object_name: str,
    now: datetime,
) -> None:
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or not 1 <= len(observation_ids) <= 1000
        or len(set(observation_ids)) != len(observation_ids)
        or not object_name.startswith("media/exports/")
    ):
        raise ValueError(
            "export attachment requires bounded original inputs and private export path"
        )
    target = CleanupTargetSpec(kind=CleanupTargetKind.MINIO_OBJECT, reference=object_name)
    rows = tuple(
        session.scalars(
            select(EvidenceResource)
            .where(
                EvidenceResource.owner_id == owner_id,
                EvidenceResource.resource_type == "content_observation",
                EvidenceResource.resource_id.in_(observation_ids),
            )
            .order_by(EvidenceResource.id)
            .with_for_update()
        )
    )
    if {row.resource_id for row in rows} != set(observation_ids):
        raise ResourceUnavailableError("an export input is unavailable")
    deleted = set(
        session.scalars(
            select(DeletionDirective.resource_record_id).where(
                DeletionDirective.owner_id == owner_id,
                DeletionDirective.resource_record_id.in_({row.id for row in rows}),
            )
        )
    )
    if deleted or any(row.expires_at <= now for row in rows):
        raise ResourceUnavailableError("an export input is unavailable")
    value = target.model_dump(mode="json")
    for resource in rows:
        if value not in resource.cleanup_targets:
            resource.cleanup_targets = [*resource.cleanup_targets, value]
    # Autoflush is disabled; later populate_existing reads would otherwise
    # discard these cleanup targets before the caller commits.
    session.flush()
