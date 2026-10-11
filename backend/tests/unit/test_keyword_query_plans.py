import pytest
from pydantic import ValidationError

from jobs.query_plans import (
    build_keyword_query_plan,
    read_keyword_query_plan,
    require_planned_keyword_query,
)


def test_query_limit_keeps_every_candidate_in_original_order() -> None:
    plan = build_keyword_query_plan(("AI", "模型", "产品"), max_queries=1)
    assert [(item.query, item.admitted, item.skip_reason) for item in plan.queries] == [
        ("AI", True, None),
        ("模型", False, "query_limit"),
        ("产品", False, "query_limit"),
    ]
    assert read_keyword_query_plan({"query_plan": plan.model_dump_json()}) == plan
    require_planned_keyword_query({"query_plan": plan.model_dump_json(), "query": "AI"})
    with pytest.raises(ValueError, match="not admitted"):
        require_planned_keyword_query({"query_plan": plan.model_dump_json(), "query": "模型"})


@pytest.mark.parametrize("reason", ["source_unavailable", "quiet", "budget", "rate_limited"])
def test_skipped_source_explains_every_query_without_claiming_a_source_limit(reason) -> None:
    plan = build_keyword_query_plan(("AI", "模型"), max_queries=None, skip_reason=reason)
    assert plan.max_queries is None
    assert all(not item.admitted and item.skip_reason == reason for item in plan.queries)


def test_old_job_has_unknown_query_plan_instead_of_invented_coverage() -> None:
    assert read_keyword_query_plan({"query": "AI"}) is None
    require_planned_keyword_query({"query": "AI"})


@pytest.mark.parametrize("value", [True, "{}", "not-json", '{"version":2}'])
def test_invalid_snapshot_is_rejected(value) -> None:
    with pytest.raises(ValueError):
        read_keyword_query_plan({"query_plan": value})


@pytest.mark.parametrize("limit", [0, 129])
def test_invalid_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValidationError):
        build_keyword_query_plan(("AI",), max_queries=limit)
