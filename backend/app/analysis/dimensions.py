"""Validate independent post dimensions and preserve each first valid outcome."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from analysis.schemas import (
    AnnotationDimensionResult,
    AnnotationDimensions,
    AnnotationOutputItem,
    AnnotationResultState,
    AnnotationStatus,
    AnnotationWrite,
    Sentiment,
)


def resolve_post_dimensions(
    raw: Mapping[str, object], *, content_version_id: UUID, ai_call_id: UUID, retry_index: int
) -> AnnotationWrite:
    """Validate v2 dimensions independently without coercing or filling missing fields.

    Optional dimensions do not trigger a relevance compensation. Null sentiment
    and empty viewpoints explicitly mean not analysed under the frozen v2 prompt.

    Args:
        raw: One item from an already checked response envelope and frozen version set.
        content_version_id: The version selected by the envelope validator.
        ai_call_id: The actual completed call that produced this item.
        retry_index: Whether this is the existing relevance compensation attempt.

    Returns:
        Independently validated outcomes and their legacy relevance projection.
        Invalid optional fields are retained as failures rather than raised.
    """
    failure_state = "failed" if retry_index else "invalid"

    def failure(dimension: str) -> AnnotationDimensionResult:
        return AnnotationDimensionResult(
            state=failure_state,
            error_code=f"analysis_{dimension}_invalid",
            ai_call_id=ai_call_id,
        )

    core = {key: value for key, value in raw.items() if key not in {"sentiment", "viewpoints"}}
    try:
        output = AnnotationOutputItem.model_validate({**core, "sentiment": None, "viewpoints": []})
    except ValidationError:
        relevance = AnnotationDimensionResult(
            state=failure_state,
            error_code="analysis_invalid_exhausted" if retry_index else "analysis_output_invalid",
            ai_call_id=ai_call_id,
        )
    else:
        relevance = AnnotationDimensionResult(
            state="valid",
            value=output.relevant,
            reason=output.relevance_reason,
            summary=output.summary,
            ai_call_id=ai_call_id,
        )

    sentiment = failure("sentiment")
    if "sentiment" in raw:
        try:
            value: Sentiment | None = TypeAdapter(Sentiment | None).validate_python(
                raw["sentiment"]
            )
        except ValidationError:
            pass
        else:
            if value is None:
                sentiment = AnnotationDimensionResult(state="not_analyzed", ai_call_id=ai_call_id)
            elif not (relevance.state == "valid" and relevance.value is False):
                sentiment = AnnotationDimensionResult(
                    state="valid", value=value.value, ai_call_id=ai_call_id
                )

    viewpoints = failure("viewpoints")
    if "viewpoints" in raw:
        try:
            validated = AnnotationOutputItem.model_validate(
                {
                    "content_version_id": content_version_id,
                    "relevant": True,
                    "relevance_reason": "validation",
                    "summary": "validation",
                    "sentiment": None,
                    "viewpoints": raw["viewpoints"],
                }
            ).viewpoints
        except ValidationError:
            pass
        else:
            viewpoints = AnnotationDimensionResult(
                state="valid" if validated else "not_analyzed",
                value=validated or None,
                ai_call_id=ai_call_id,
            )

    dimensions = AnnotationDimensions(
        relevance=relevance, sentiment=sentiment, viewpoints=viewpoints
    )
    valid = relevance.state == "valid"
    return AnnotationWrite(
        content_version_id=content_version_id,
        relevant=relevance.value if isinstance(relevance.value, bool) else None,
        relevance_reason=relevance.reason,
        summary=relevance.summary,
        sentiment=Sentiment(sentiment.value)
        if valid and isinstance(sentiment.value, str)
        else None,
        viewpoints=viewpoints.value if valid and isinstance(viewpoints.value, tuple) else (),
        ai_call_id=ai_call_id,
        status=AnnotationStatus.ANNOTATED if valid else AnnotationStatus.UNANALYZED,
        result_state=AnnotationResultState(relevance.state),
        error_code=relevance.error_code,
        dimension_results=dimensions,
    )


def merge_post_dimensions(
    current: AnnotationDimensions, incoming: AnnotationDimensions, *, incoming_is_late: bool
) -> AnnotationDimensions:
    """Keep each first valid value without transferring its call provenance.

    Args:
        current: Persisted, validated outcomes for the same frozen input.
        incoming: Validated outcomes from another call for that input.
        incoming_is_late: Whether the incoming timestamp predates the stored update.

    Returns:
        First valid values, or the newest failure when neither value is valid.
        A late valid result may repair a failure; a late failure cannot replace it.
    """

    def choose(
        old: AnnotationDimensionResult, new: AnnotationDimensionResult
    ) -> AnnotationDimensionResult:
        if old.state == "valid" or (incoming_is_late and new.state != "valid"):
            return old
        return new

    return AnnotationDimensions(
        relevance=choose(current.relevance, incoming.relevance),
        sentiment=choose(current.sentiment, incoming.sentiment),
        viewpoints=choose(current.viewpoints, incoming.viewpoints),
    )
