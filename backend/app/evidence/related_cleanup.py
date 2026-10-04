"""Enqueue derived-resource cleanup through the original lifecycle targets and barriers."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence.models import DeletionDirective, EvidenceResource
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService


def request_related_resource_deletions_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    resource_ids: tuple[UUID, ...],
    resource_type: str | None,
    now: datetime,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("related cleanup requires aware caller transaction")
    query = select(EvidenceResource).where(EvidenceResource.owner_id == owner_id)
    if resource_type is None:
        query = query.where(EvidenceResource.id.in_(resource_ids))
    else:
        query = query.where(
            EvidenceResource.resource_type == resource_type,
            EvidenceResource.resource_id.in_(resource_ids),
        )
    lifecycle = LifecycleService(session, clock=lambda: now)
    for resource in session.scalars(query.with_for_update()):
        exists = session.scalar(
            select(DeletionDirective.id).where(
                DeletionDirective.owner_id == owner_id,
                DeletionDirective.resource_record_id == resource.id,
            )
        )
        if exists is None:
            lifecycle._create_deletion(
                resource=resource,
                operation_id=uuid4(),
                reason=DeletionReason.SOURCE_DELETED,
                now=now,
            )
