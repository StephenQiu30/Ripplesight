"""Read independently validated sentiment for explicitly public fixed report inputs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.models import ContentAnnotation
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.reads import readable_annotation_ids_in_transaction
from analysis.schemas import AnnotationDimensions, Sentiment
from content.analysis_schemas import AnalysisObservationManifest
from monitors.services import current_topic_rule_identities_query

ReportSentimentState = Literal[
    "valid", "not_analyzed", "pending", "failed", "invalid", "not_relevant", "unavailable"
]


@dataclass(frozen=True, slots=True)
class PublicReportAnalysisRef:
    """A report whose exact observation has already passed public permission checks."""

    content_id: UUID
    content_version_id: UUID
    observation_id: UUID


@dataclass(frozen=True, slots=True)
class PublicReportSentiment:
    """Non-sensitive analysis projection; no private diagnostic or model call escapes."""

    state: ReportSentimentState
    label: Sentiment | None = None


def _dimension_outcome(row: ContentAnnotation) -> PublicReportSentiment:
    if row.dimension_results is None:
        return PublicReportSentiment("pending" if row.result_state == "pending" else "unavailable")
    try:
        dimensions = AnnotationDimensions.model_validate(row.dimension_results)
    except (ValidationError, ValueError, TypeError):
        return PublicReportSentiment("invalid")
    relevance = dimensions.relevance
    valid = relevance.state == "valid"
    if (
        relevance.state != row.result_state
        or row.status != ("annotated" if valid else "unanalyzed")
        or row.relevant != (relevance.value if valid else None)
        or row.relevance_reason != relevance.reason
        or row.summary != relevance.summary
        or row.error_code != relevance.error_code
        or row.sentiment != (dimensions.sentiment.value if valid else None)
        or row.viewpoints
        != (
            list(dimensions.viewpoints.value)
            if valid and isinstance(dimensions.viewpoints.value, tuple)
            else []
        )
    ):
        return PublicReportSentiment("invalid")
    if relevance.state in {"failed", "invalid"}:
        return PublicReportSentiment(relevance.state)
    if relevance.value is False:
        return PublicReportSentiment("not_relevant")
    sentiment = dimensions.sentiment
    if sentiment.state == "valid" and isinstance(sentiment.value, str):
        return PublicReportSentiment("valid", Sentiment(sentiment.value))
    return PublicReportSentiment(sentiment.state)


def read_public_report_sentiments_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    references: tuple[PublicReportAnalysisRef, ...],
    now: datetime,
) -> dict[UUID, PublicReportSentiment]:
    """Read the current rule's latest exact observation, never fall back after failure.

    The caller grants public permission only for the supplied report observations.
    Every original analysis input must be in that whitelist and still privately
    readable. Overflow produces unavailable outcomes for the whole input group;
    this function never writes, queues or calls a provider.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("public sentiment requires an aware caller transaction")
    unavailable = {ref.content_id: PublicReportSentiment("unavailable") for ref in references}
    if len(references) > 2000:
        return unavailable
    if not references:
        return {}
    rules = current_topic_rule_identities_query().subquery()
    rows = tuple(
        session.scalars(
            select(ContentAnnotation)
            .join(
                rules,
                (rules.c.owner_id == ContentAnnotation.owner_id)
                & (rules.c.id == ContentAnnotation.topic_id)
                & (rules.c.current_version == ContentAnnotation.topic_rule_version),
            )
            .where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.content_version_id.in_(
                    {r.content_version_id for r in references}
                ),
                ContentAnnotation.prompt_version == ANALYSIS_PROMPT_VERSION,
            )
            .order_by(ContentAnnotation.created_at.desc(), ContentAnnotation.id.desc())
            .limit(2001)
            .execution_options(populate_existing=True)
        )
    )
    if len(rows) > 2000:
        return unavailable
    refs = {ref.content_version_id: ref for ref in references}
    public_observations = {ref.observation_id for ref in references}
    chosen: dict[UUID, ContentAnnotation] = {}
    manifests: dict[UUID, AnalysisObservationManifest] = {}
    for row in rows:
        ref = refs[row.content_version_id]
        # Match the raw fixed identity before validating. A corrupt latest proof
        # must not expose an older valid conclusion for that same observation.
        raw_posts = row.input_manifest.get("post_observations") if row.input_manifest else None
        if not isinstance(raw_posts, dict) or raw_posts.get(str(ref.content_version_id)) != str(
            ref.observation_id
        ):
            continue
        if ref.content_id in chosen:
            continue
        chosen[ref.content_id] = row
        try:
            manifest = AnalysisObservationManifest.model_validate(row.input_manifest)
        except (ValidationError, ValueError, TypeError):
            continue
        if (
            row.content_id == ref.content_id
            and manifest.signature == row.input_signature
            and set(manifest.input_observation_ids) <= public_observations
            and row.created_at.utcoffset() is not None
            and row.updated_at.utcoffset() is not None
            and row.created_at <= row.updated_at <= now
        ):
            manifests[row.id] = manifest
    permitted = readable_annotation_ids_in_transaction(
        session, annotations=tuple(row for row in chosen.values() if row.id in manifests), now=now
    )
    result = {ref.content_id: PublicReportSentiment("not_analyzed") for ref in references}
    for content_id, row in chosen.items():
        result[content_id] = (
            _dimension_outcome(row) if row.id in permitted else PublicReportSentiment("unavailable")
        )
    return result
