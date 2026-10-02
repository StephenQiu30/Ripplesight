from datetime import UTC, datetime

from analysis.editorial_pipeline import EditorialStep, next_editorial_step
from tests.unit.test_editorial_rules import material

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def test_two_independent_score_stages_do_not_share_the_same_cached_result() -> None:
    outputs = {"prefilter": {"label": "PASS", "reason": "AI新模型"}}
    first = next_editorial_step(material(), outputs, now=NOW)
    assert isinstance(first, EditorialStep) and first.key == "score-1"
    outputs["score-1"] = {"attentionScore": 59}
    second = next_editorial_step(material(), outputs, now=NOW)
    assert isinstance(second, EditorialStep) and second.key == "score-2"
    assert second.prompt == first.prompt and second.prompt_version == first.prompt_version
    outputs["score-2"] = {"attentionScore": 61}
    selection = next_editorial_step(material(), outputs, now=NOW, selection_only=True)
    assert isinstance(selection, dict) and selection["selected"] and selection["score"] == 60


def test_confirmed_block_stops_all_paid_stages_but_title_only_block_continues() -> None:
    output = {"prefilter": {"label": "BLOCK", "reason": "普通经营"}}
    blocked = next_editorial_step(material(), output, now=NOW)
    assert isinstance(blocked, dict) and blocked["relevance"] == "block"
    continuation = next_editorial_step(material(body=""), output, now=NOW)
    assert isinstance(continuation, EditorialStep) and continuation.key == "score-1"


def test_ungraded_material_is_structured_without_selection_scores() -> None:
    step = next_editorial_step(
        material(tier="UNGRADED"), {"prefilter": {"label": "UNKNOWN", "reason": "待证据"}}, now=NOW
    )
    assert isinstance(step, EditorialStep) and step.key == "structure"


def test_understanding_guard_can_remove_publication_without_losing_score_evidence() -> None:
    outputs = {
        "prefilter": {"label": "PASS", "reason": "AI模型"},
        "score-1": {"attentionScore": 90},
        "score-2": {"attentionScore": 90},
        "structure": {
            "category": "ai-models",
            "tags": ["模型"],
            "subjects": ["openai"],
            "fact": None,
        },
        "understand": {
            "itemType": "model_release",
            "authorRole": "principal",
            "tags": ["模型"],
            "editorialJudgment": "公开API",
            "titleZh": "Anthropic 发布模型",
            "summaryZh": "Claude 模型已发布。",
        },
    }
    result = next_editorial_step(material(title="New OpenAI model"), outputs, now=NOW)
    assert isinstance(result, dict)
    assert result["score"] == 90 and not result["selected"]
    assert result["relevance"] == "unknown"
    assert result["writing"]["identity_guard"]["outcome"] == "fallback"


def test_chinese_short_post_is_verbatim_and_no_summary_stage_is_scheduled() -> None:
    outputs = {
        "prefilter": {"label": "PASS", "reason": "公开用法"},
        "score-1": {"attentionScore": 30},
        "score-2": {"attentionScore": 30},
        "structure": {"category": "tip", "tags": ["教程"], "subjects": [], "fact": None},
    }
    item = material(source_kind="x_search", body="这个新模型现在可以直接在本地使用。")
    result = next_editorial_step(item, outputs, now=NOW)
    assert isinstance(result, dict) and result["writing"]["kind"] == "verbatim"
    assert result["writing"]["summary_zh"] == item.body and not result["selected"]
