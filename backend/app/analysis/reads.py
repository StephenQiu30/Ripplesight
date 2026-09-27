from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.models import ContentAnnotation
from analysis.schemas import ContentAnnotationReadView


def load_content_annotations_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    readable_version_ids: set[UUID],
) -> list[ContentAnnotationReadView]:
    """Read analysis rows only for content versions backed by readable observations."""
    if not session.in_transaction():
        raise RuntimeError("annotation reads require the caller's transaction")
    if not readable_version_ids:
        return []
    rows = session.scalars(
        select(ContentAnnotation)
        .where(
            ContentAnnotation.owner_id == owner_id,
            ContentAnnotation.content_id == content_id,
            ContentAnnotation.content_version_id.in_(readable_version_ids),
        )
        .order_by(
            ContentAnnotation.topic_id,
            ContentAnnotation.content_version_id,
            ContentAnnotation.topic_rule_version,
            ContentAnnotation.prompt_version,
        )
    ).all()
    return [ContentAnnotationReadView.model_validate(row) for row in rows]
