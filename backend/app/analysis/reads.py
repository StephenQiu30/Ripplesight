from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.models import ContentAnnotation
from analysis.prompts import (
    ANALYSIS_PROMPT_VERSION,
    COMMENT_ANALYSIS_PROMPT_VERSION,
    SUPPORTED_ANALYSIS_PROMPT_VERSIONS,
)
from analysis.schemas import AnalysisJobScope, AnnotationResultState, ContentAnnotationReadView
from content.analysis_inputs import (
    analysis_observation_manifests_readable_in_transaction,
    require_analysis_observation_inputs_in_transaction,
)
from content.analysis_schemas import AnalysisObservationManifest
from core.errors import ApplicationError


def analysis_scope_inputs_readable_in_transaction(
    session: Session, *, owner_id: UUID, scope: AnalysisJobScope, now: datetime
) -> bool:
    """Require an exact frozen observation manifest, including every comment input."""
    if scope.input_manifest is None:
        return False
    try:
        require_analysis_observation_inputs_in_transaction(
            session, owner_id=owner_id, manifest=scope.input_manifest, now=now
        )
    except (ApplicationError, ValueError, ValidationError):
        return False
    return True


def annotation_inputs_readable_in_transaction(
    session: Session, *, annotation: ContentAnnotation, now: datetime
) -> bool:
    """A successful model call cannot replace an annotation's missing input proof."""
    if annotation.input_manifest is None:
        return False
    try:
        manifest = AnalysisObservationManifest.model_validate(annotation.input_manifest)
        if (
            annotation.content_version_id
            not in (
                manifest.comment_observations
                if annotation.prompt_version == COMMENT_ANALYSIS_PROMPT_VERSION
                else manifest.post_observations
            )
            or manifest.signature != annotation.input_signature
        ):
            return False
        require_analysis_observation_inputs_in_transaction(
            session, owner_id=annotation.owner_id, manifest=manifest, now=now
        )
    except (ApplicationError, ValidationError, ValueError):
        return False
    return True


def readable_annotation_ids_in_transaction(
    session: Session, *, annotations: tuple[ContentAnnotation, ...], now: datetime
) -> set[UUID]:
    """Batch modern proofs per owner while preserving each original prompt's ALL closure."""
    if not session.in_transaction() or now.utcoffset() is None or len(annotations) > 10000:
        raise RuntimeError("annotation inputs require a bounded aware caller transaction")
    readable: set[UUID] = set()
    for start in range(0, len(annotations), 500):
        batch = annotations[start : start + 500]
        grouped: dict[UUID, dict[str, AnalysisObservationManifest]] = {}
        identities: dict[UUID, tuple[UUID, str]] = {}
        for row in batch:
            if row.input_manifest is None:
                continue
            try:
                manifest = AnalysisObservationManifest.model_validate(row.input_manifest)
                signature = manifest.signature
                if signature != row.input_signature or row.content_version_id not in (
                    manifest.comment_observations
                    if row.prompt_version == COMMENT_ANALYSIS_PROMPT_VERSION
                    else manifest.post_observations
                ):
                    continue
            except (ValidationError, ValueError, TypeError):
                continue
            grouped.setdefault(row.owner_id, {})[signature] = manifest
            identities[row.id] = (row.owner_id, signature)
        permissions = {
            owner_id: analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner_id, manifests=tuple(manifests.values()), now=now
            )
            for owner_id, manifests in grouped.items()
        }
        readable.update(
            identifier
            for identifier, (owner_id, signature) in identities.items()
            if permissions[owner_id].get(signature, False)
        )
    return readable


def relevant_event_annotation_ids_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    references: dict[UUID, tuple[UUID, UUID]],
    now: datetime,
) -> frozenset[UUID]:
    """Recheck exact frozen classifications and each original prompt's ALL inputs."""
    if (
        not session.in_transaction()
        or now.utcoffset() is None
        or topic_rule_version < 1
        or len(references) > 2000
    ):
        raise RuntimeError("bounded event classifications need an aware caller transaction")
    result: set[UUID] = set()
    identifiers = tuple(references)
    for start in range(0, len(identifiers), 500):
        rows = session.scalars(
            select(ContentAnnotation)
            .where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.topic_rule_version == topic_rule_version,
                ContentAnnotation.id.in_(identifiers[start : start + 500]),
                ContentAnnotation.result_state == AnnotationResultState.VALID.value,
                ContentAnnotation.status == "annotated",
                ContentAnnotation.relevant.is_(True),
            )
            .execution_options(populate_existing=True)
        ).all()
        readable = readable_annotation_ids_in_transaction(session, annotations=tuple(rows), now=now)
        for row in rows:
            version_id, observation_id = references[row.id]
            if row.id not in readable or row.content_version_id != version_id:
                continue
            if row.input_manifest is not None:
                manifest = AnalysisObservationManifest.model_validate(row.input_manifest)
                if manifest.post_observations.get(version_id) != observation_id:
                    continue
            result.add(row.id)
    return frozenset(result)


def event_annotation_observation_is_relevant_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    content_version_id: UUID,
    observation_id: UUID,
    now: datetime,
    annotation_id: UUID | None = None,
    topic_rule_version: int | None = None,
) -> bool:
    """Recheck the frozen classification without choosing another source observation."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("event classification needs an aware caller transaction")
    statement = select(ContentAnnotation).where(
        ContentAnnotation.owner_id == owner_id,
        ContentAnnotation.topic_id == topic_id,
        ContentAnnotation.content_version_id == content_version_id,
        ContentAnnotation.result_state == AnnotationResultState.VALID.value,
        ContentAnnotation.status == "annotated",
        ContentAnnotation.relevant.is_(True),
    )
    if annotation_id is not None:
        statement = statement.where(ContentAnnotation.id == annotation_id)
    if topic_rule_version is not None:
        statement = statement.where(ContentAnnotation.topic_rule_version == topic_rule_version)
    rows = session.scalars(
        statement.order_by(ContentAnnotation.created_at.desc(), ContentAnnotation.id.desc()).limit(
            32
        )
    ).all()
    readable = readable_annotation_ids_in_transaction(session, annotations=tuple(rows), now=now)
    for row in rows:
        if row.id not in readable:
            continue
        if row.input_manifest is not None:
            manifest = AnalysisObservationManifest.model_validate(row.input_manifest)
            if manifest.post_observations.get(content_version_id) != observation_id:
                continue
        return True
    return False


def report_annotations_readable_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    annotation_ids: tuple[UUID, ...],
    content_version_ids: tuple[UUID, ...],
    now: datetime | None = None,
) -> bool:
    """Check frozen analysis identities without leaking annotation ORM to reports."""
    if not session.in_transaction():
        raise RuntimeError("report annotation reads require the caller's transaction")
    versions = set(content_version_ids)
    for start in range(0, len(annotation_ids), 500):
        batch = set(annotation_ids[start : start + 500])
        rows = (
            session.execute(
                select(ContentAnnotation).where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.topic_id == topic_id,
                    ContentAnnotation.id.in_(batch),
                )
            )
            .scalars()
            .all()
        )
        readable = readable_annotation_ids_in_transaction(
            session, annotations=tuple(rows), now=now or datetime.now(UTC)
        )
        if {row.id for row in rows} != batch or any(
            row.content_version_id not in versions or row.id not in readable for row in rows
        ):
            return False
    return True


def load_content_annotations_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    readable_version_ids: set[UUID],
    now: datetime | None = None,
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
    readable = readable_annotation_ids_in_transaction(
        session, annotations=tuple(rows), now=now or datetime.now(UTC)
    )
    return [ContentAnnotationReadView.model_validate(row) for row in rows if row.id in readable]


def load_report_annotation_observation_ids_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    annotation_ids: tuple[UUID, ...],
    now: datetime,
) -> tuple[UUID, ...]:
    if not session.in_transaction() or now.utcoffset() is None or len(annotation_ids) > 10000:
        raise RuntimeError("report annotation inputs require bounded aware caller transaction")
    inputs: set[UUID] = set()
    for start in range(0, len(annotation_ids), 500):
        batch = set(annotation_ids[start : start + 500])
        rows = session.scalars(
            select(ContentAnnotation).where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.id.in_(batch),
            )
        ).all()
        if {row.id for row in rows} != batch:
            raise ApplicationError("editorial_material_unavailable")
        readable = readable_annotation_ids_in_transaction(session, annotations=tuple(rows), now=now)
        for row in rows:
            if row.id not in readable:
                raise ApplicationError("editorial_material_unavailable")
            if row.input_manifest is not None:
                manifest = AnalysisObservationManifest.model_validate(row.input_manifest)
                inputs.update(manifest.input_observation_ids)
                if len(inputs) > 2000:
                    raise ApplicationError("editorial_material_unavailable")
    return tuple(sorted(inputs, key=str))


def load_preferred_annotation_states_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    prompt_version: str,
    content_version_ids: set[UUID],
    now: datetime | None = None,
) -> dict[UUID, tuple[AnnotationResultState, bool | None, str]]:
    """Read preferred results without recomputation inside the caller's transaction.

    Returns:
        State, relevance and the selected prompt version for each readable body version.
        Valid supported legacy results remain eligible when the current result is absent.

    Raises:
        RuntimeError: The caller has not started a transaction.
    """
    if not session.in_transaction():
        raise RuntimeError("annotation reads require the caller's transaction")
    if not content_version_ids:
        return {}
    rows = session.scalars(
        select(ContentAnnotation)
        .where(
            ContentAnnotation.owner_id == owner_id,
            ContentAnnotation.topic_id == topic_id,
            ContentAnnotation.topic_rule_version == topic_rule_version,
            ContentAnnotation.prompt_version.in_(
                SUPPORTED_ANALYSIS_PROMPT_VERSIONS
                if prompt_version == ANALYSIS_PROMPT_VERSION
                else (prompt_version,)
            ),
            ContentAnnotation.content_version_id.in_(content_version_ids),
        )
        .order_by(
            (ContentAnnotation.result_state == AnnotationResultState.VALID.value).desc(),
            (ContentAnnotation.prompt_version == prompt_version).desc(),
            ContentAnnotation.created_at.desc(),
            ContentAnnotation.id.desc(),
        )
    ).all()
    result: dict[UUID, tuple[AnnotationResultState, bool | None, str]] = {}
    readable = readable_annotation_ids_in_transaction(
        session, annotations=tuple(rows), now=now or datetime.now(UTC)
    )
    for row in rows:
        if row.id in readable:
            result.setdefault(
                row.content_version_id,
                (AnnotationResultState(row.result_state), row.relevant, row.prompt_version),
            )
    return result


def load_current_annotation_states_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    prompt_version: str,
    content_version_ids: set[UUID],
    now: datetime | None = None,
) -> dict[UUID, tuple[AnnotationResultState, bool | None]]:
    """Project readable preferred results into the existing state/relevance contract."""
    return {
        identifier: (state, relevant)
        for identifier, (state, relevant, _) in load_preferred_annotation_states_in_transaction(
            session,
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=topic_rule_version,
            prompt_version=prompt_version,
            content_version_ids=content_version_ids,
            now=now,
        ).items()
    }
