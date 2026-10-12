"""Regression samples for independent relevance and each first valid result."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from analysis.dimensions import merge_post_dimensions
from analysis.schemas import AnnotationDimensions, AnnotationWrite
from analysis.services import resolve_annotation_results

VERSION = UUID(int=1)
CALL = UUID(int=2)


def resolve(*, call=CALL, retry=0, **changes):
    raw = dict(
        content_version_id=str(VERSION),
        relevant=True,
        relevance_reason="固定原帖讨论主题",
        summary="主题摘要",
        sentiment="neutral",
        viewpoints=["固定观点"],
    )
    raw.update(changes)
    (result,) = resolve_annotation_results(
        expected_content_version_ids=(VERSION,), raw_items=[raw], ai_call_id=call, retry_index=retry
    )
    assert result.dimension_results is not None
    return result


@pytest.mark.parametrize(
    "changes",
    [
        {"sentiment": "confused"},
        {"viewpoints": [""]},
        {"sentiment": "confused", "viewpoints": [""]},
        {"sentiment": "confused", "retry": 1},
    ],
)
def test_optional_errors_do_not_discard_valid_relevance(changes):
    result = resolve(**changes)
    assert result.relevant is True and result.result_state.value == "valid"
    dimensions = result.dimension_results
    assert dimensions.relevance.reason == "固定原帖讨论主题"
    assert dimensions.relevance.ai_call_id == CALL
    assert any(
        x.state in {"invalid", "failed"} for x in (dimensions.sentiment, dimensions.viewpoints)
    )
    assert result.error_code is None


def test_valid_optional_results_survive_invalid_relevance():
    result = resolve(relevant="true")
    assert result.relevant is None and result.result_state.value == "invalid"
    assert result.sentiment is None and result.viewpoints == ()
    assert result.dimension_results.sentiment.value == "neutral"
    assert result.dimension_results.viewpoints.value == ("固定观点",)


@pytest.mark.parametrize(
    "changes",
    [
        {"sentiment": 0},
        {"sentiment": {}},
        {"viewpoints": "观点"},
        {"viewpoints": [1]},
        {"viewpoints": [" "]},
        {"viewpoints": ["x" * 201]},
        {"viewpoints": ["x"] * 6},
    ],
)
def test_malformed_optional_dimensions_remain_invalid(changes):
    result = resolve(**changes)
    dimension = "sentiment" if "sentiment" in changes else "viewpoints"
    outcome = getattr(result.dimension_results, dimension)
    assert outcome.state == "invalid" and outcome.value is None
    assert outcome.error_code == f"analysis_{dimension}_invalid"
    assert result.relevant is True


def test_not_analysed_is_not_neutral_and_false_is_preserved():
    result = resolve(sentiment=None, viewpoints=[])
    assert result.dimension_results.sentiment.state == "not_analyzed"
    assert result.dimension_results.viewpoints.state == "not_analyzed"
    false = resolve(relevant=False, sentiment="positive")
    assert false.relevant is False and false.result_state.value == "valid"
    assert false.dimension_results.sentiment.state == "invalid"


def test_missing_optional_fields_do_not_create_empty_success():
    raw = dict(
        content_version_id=str(VERSION), relevant=True, relevance_reason="理由", summary="摘要"
    )
    (result,) = resolve_annotation_results(
        expected_content_version_ids=(VERSION,), raw_items=[raw], ai_call_id=CALL
    )
    assert result.relevant is True
    assert result.dimension_results.sentiment.state == "invalid"
    assert result.dimension_results.viewpoints.state == "invalid"


def test_first_valid_values_and_call_provenance_are_independent():
    first = resolve(relevant="true").dimension_results
    second = resolve(call=UUID(int=3), sentiment="invalid", viewpoints=[""]).dimension_results
    merged = merge_post_dimensions(first, second, incoming_is_late=True)
    assert merged.relevance == second.relevance
    assert merged.sentiment == first.sentiment
    assert merged.viewpoints == first.viewpoints
    third = resolve(
        call=UUID(int=4), relevant=False, sentiment=None, viewpoints=[]
    ).dimension_results
    assert merge_post_dimensions(merged, third, incoming_is_late=False) == merged


def test_late_invalid_result_cannot_replace_a_newer_failure():
    current = resolve(relevant="true", sentiment="invalid", viewpoints=[""]).dimension_results
    older = resolve(
        call=UUID(int=3), relevant="true", sentiment="invalid", viewpoints=[""], retry=1
    ).dimension_results
    assert merge_post_dimensions(current, older, incoming_is_late=True) == current


def test_persisted_dimension_types_and_new_call_projection_are_validated():
    result = resolve()
    data = result.dimension_results.model_dump(mode="json")
    assert AnnotationDimensions.model_validate(data) == result.dimension_results
    data["relevance"]["value"] = "true"
    with pytest.raises(ValidationError):
        AnnotationDimensions.model_validate(data)
    data = result.model_dump(mode="json")
    data["dimension_results"]["sentiment"]["ai_call_id"] = str(UUID(int=99))
    with pytest.raises(ValidationError, match="actual common call"):
        AnnotationWrite.model_validate(data)
    data = result.model_dump(mode="json")
    data["sentiment"] = "positive"
    with pytest.raises(ValidationError, match="project independent"):
        AnnotationWrite.model_validate(data)
