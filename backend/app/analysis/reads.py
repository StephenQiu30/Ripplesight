from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.models import ContentAnnotation
from analysis.schemas import AnnotationResultState, ContentAnnotationReadView


def report_annotations_readable_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    annotation_ids: tuple[UUID, ...],
    content_version_ids: tuple[UUID, ...],
) -> bool:
    """Check frozen analysis identities without leaking annotation ORM to reports."""
    if not session.in_transaction():
        raise RuntimeError("report annotation reads require the caller's transaction")
    versions = set(content_version_ids)
    for start in range(0, len(annotation_ids), 500):
        batch = set(annotation_ids[start : start + 500])
        rows = session.execute(
            select(ContentAnnotation.id, ContentAnnotation.content_version_id).where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.id.in_(batch),
            )
        ).all()
        if {row[0] for row in rows} != batch or any(row[1] not in versions for row in rows):
            return False
    return True


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


def load_current_annotation_states_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    prompt_version: str,
    content_version_ids: set[UUID],
) -> dict[UUID, tuple[AnnotationResultState, bool | None]]:
    """Project only the selected topic's current rule and prompt for visible versions."""
    if not session.in_transaction():
        raise RuntimeError("annotation reads require the caller's transaction")
    if not content_version_ids:
        return {}
    rows = session.scalars(
        select(ContentAnnotation).where(
            ContentAnnotation.owner_id == owner_id,
            ContentAnnotation.topic_id == topic_id,
            ContentAnnotation.topic_rule_version == topic_rule_version,
            ContentAnnotation.prompt_version == prompt_version,
            ContentAnnotation.content_version_id.in_(content_version_ids),
        )
    ).all()
    return {
        row.content_version_id: (AnnotationResultState(row.result_state), row.relevant)
        for row in rows
    }
