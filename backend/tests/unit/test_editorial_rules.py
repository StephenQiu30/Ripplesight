from datetime import UTC, datetime
from uuid import UUID

import pytest

from analysis.editorial_rules import (
    decide_selection,
    finalize_copy,
    needs_short_post_translation,
    normalize_prefilter,
    score_input,
)
from analysis.editorial_schemas import EditorialMaterial


def material(**values: object) -> EditorialMaterial:
    return EditorialMaterial.model_validate(
        {
            "content_id": UUID(int=1),
            "content_version_id": UUID(int=2),
            "source_key": "rss_test",
            "source_name": "发布者",
            "source_kind": "rss",
            "tier": "T1",
            "title": "OpenAI 发布新模型",
            "body": "OpenAI published a new model with an API.",
            "url": "https://example.com/item",
            "discovered_at": datetime(2026, 10, 1, tzinfo=UTC),
            **values,
        }
    )


@pytest.mark.parametrize(
    ("tier", "scores", "selected", "score", "understand"),
    [
        ("T1", (59, 60), False, 59, True),
        ("T1", (59, 61), True, 60, True),
        ("T1_5", (64, 65), False, 64, True),
        ("T1_5", (64, 66), True, 65, True),
        ("T2", (75, 77), True, 76, True),
        ("T2", (50, 50), False, 50, False),
        ("T2", (50, 51), False, 50, True),
        ("EXCLUDE_MP", (), False, None, False),
    ],
)
def test_selection_uses_sum_and_strict_understanding_floor(
    tier: str, scores: tuple[int, ...], selected: bool, score: int | None, understand: bool
) -> None:
    result = decide_selection(tier, scores)
    assert (result.selected, result.score, result.understand) == (selected, score, understand)


def test_incomplete_double_score_is_unknown_and_never_selected() -> None:
    result = decide_selection("T1", (100,))
    assert result.score is None and result.selected is False and result.complete is False


def test_title_only_block_continues_as_unknown_without_inventing_evidence() -> None:
    assert normalize_prefilter("BLOCK", material(body="", excerpt="")) == "UNKNOWN"
    assert normalize_prefilter("BLOCK", material()) == "BLOCK"
    assert normalize_prefilter("BLOCK", material(body="", quoted_text="AI research")) == "BLOCK"


def test_score_input_omits_source_tier_and_uses_fallback_time_and_full_capped_body() -> None:
    text = score_input(material(body="x" * 61000))
    assert "2026-10-01T08:00:00+08:00" in text
    assert "发布者" not in text and "tier" not in text and "T1" not in text
    assert text.endswith("x" * 60000) and "x" * 60001 not in text


def test_identity_guard_drops_invented_company_independently_for_title_and_summary() -> None:
    result = finalize_copy(material(), "OpenAI 发布模型", "Anthropic 宣布新模型。")
    assert result.title_zh == "OpenAI 发布模型"
    assert result.summary_zh == ""
    assert result.identity_guard.unsupported_summary_entity_ids == ["anthropic"]
    result = finalize_copy(material(), "Claude 发布模型", "OpenAI 发布模型。")
    assert result.title_zh == material().title and result.summary_zh == "OpenAI 发布模型。"


def test_publisher_domain_is_exact_or_subdomain_and_owner_is_explicit() -> None:
    allowed = finalize_copy(
        material(title="发布更新", body="新版本", url="https://blog.anthropic.com/a"),
        "Claude 更新",
        "Claude 更新。",
    )
    denied = finalize_copy(
        material(title="发布更新", body="新版本", url="https://anthropic.com.example.org/a"),
        "Claude 更新",
        "Claude 更新。",
    )
    assert allowed.identity_guard.outcome == "pass"
    assert denied.identity_guard.outcome == "fallback"


def test_chinese_short_post_keeps_verbatim_but_mixed_text_needs_translation() -> None:
    assert not needs_short_post_translation("这个新模型已经可以直接在本地使用\uff0c效果也很好。")
    assert needs_short_post_translation("新模型 supports multiple input formats and tools")
    assert needs_short_post_translation("これは新しいモデルです")
