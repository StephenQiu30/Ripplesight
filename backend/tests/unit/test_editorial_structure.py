from typing import Any

import pytest

from analysis.editorial_rules import MAX_BODY_CHARS, structure_instructions
from analysis.editorial_schemas import StructureOutput
from analysis.editorial_structure import normalize_structure
from tests.unit.test_editorial_rules import material


def output(**updates: Any) -> dict[str, Any]:
    return {
        "category": "ai-models",
        "tags": ["评测/基准", "推理"],
        "subjects": [" OPENAI ", "openai", "invented"],
        "scope": "single",
        "fact": {
            "title": "评测机构公布排名",
            "subject": "评测机构",
            "action": "公布评测结果",
            "object": "模型排名",
            "occurredAt": None,
            "evidence": "We published the model ranking today.",
            "conditions": [{"quote": "Preview users only."}],
        },
        **updates,
    }


@pytest.mark.parametrize("scope", ["single", "composite", "unknown"])
def test_scope_and_composite_fact_contract(scope: str) -> None:
    result = normalize_structure(
        output(scope=scope),
        material(body="We published the model ranking today. Preview users only."),
    )
    assert result.scope == scope
    assert result.subjects == ["openai"]
    if scope == "composite":
        assert result.fact is None
        assert [(d.field, d.reason) for d in result.discards] == [("fact", "composite")]
        # Even malformed fact output cannot cause a composite analysis to fail.
        assert (
            normalize_structure(output(scope=scope, fact={"invalid": True}), material()).fact
            is None
        )
        assert StructureOutput.model_validate(output(scope=scope)).fact is None
        assert (
            StructureOutput.model_validate(output(scope=scope, fact={"invalid": True})).fact is None
        )
    else:
        assert result.fact is not None and result.fact.conditions[0].quote == "Preview users only."
        assert not result.discards


def test_legacy_missing_scope_and_quotes_are_unknown_without_rewriting_the_fact() -> None:
    data = output()
    del data["scope"]
    del data["fact"]["evidence"]
    del data["fact"]["conditions"]
    result = normalize_structure(data, material())
    assert result.scope == "unknown" and result.fact is not None
    assert result.fact.evidence is None and result.fact.conditions == []


def test_title_and_source_metadata_cannot_supply_missing_original_material() -> None:
    result = normalize_structure(output(), material(body="", excerpt="", quoted_text=""))
    assert result.scope == "unknown" and result.fact is None
    assert [(d.field, d.reason) for d in result.discards] == [
        ("scope", "no_original"),
        ("fact", "no_original"),
    ]


@pytest.mark.parametrize(
    ("quote", "reason"),
    [
        ("Reading is free... Exports consume credits.", "ellipsis"),
        ("Reading is free… Exports consume credits.", "ellipsis"),
        ("Reading is free.\n\nExports consume credits.", "cross_paragraph"),
        ("Reading is free. Exports consume credits.", "not_in_original"),
        ("仅限美国用户。", "not_in_original"),
        ("title-only evidence", "not_in_original"),
        ("source-only evidence", "not_in_original"),
        ("label-only evidence", "not_in_original"),
        (401 * "x", "too_long"),
        ("", "empty"),
        (99, "invalid_type"),
    ],
)
def test_bad_condition_only_discards_itself_and_records_reason(quote: Any, reason: str) -> None:
    data = output()
    data["fact"]["conditions"] = [
        {"quote": quote},
        {"quote": "Reading is free."},
        {"quote": "Exports consume credits."},
    ]
    result = normalize_structure(
        data,
        material(
            title="title-only evidence",
            source_name="source-only evidence",
            source_tags=["label-only evidence"],
            body=(
                "We published the model ranking today.\n\n"
                "Reading is free.\n\nExports consume credits."
            ),
        ),
    )
    assert result.fact is not None
    assert result.fact.evidence == "We published the model ranking today."
    assert [c.quote for c in result.fact.conditions] == [
        "Reading is free.",
        "Exports consume credits.",
    ]
    assert [(d.field, d.reason) for d in result.discards] == [("fact.conditions[0].quote", reason)]
    assert quote not in result.model_dump_json() if isinstance(quote, str) and quote else True


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (601 * "x", "too_long"),
        (False, "invalid_type"),
        ("invented", "not_in_original"),
        ("actual...ellipsis", "ellipsis"),
        ("actual…ellipsis", "ellipsis"),
        ("Preview users only.\nOld release.", "cross_paragraph"),
        ("OpenAI 发布新模型", "not_in_original"),
    ],
)
def test_bad_evidence_preserves_the_fact_and_other_conditions(evidence: Any, reason: str) -> None:
    data = output()
    data["fact"]["evidence"] = evidence
    result = normalize_structure(
        data, material(body="Preview users only. actual...ellipsis actual…ellipsis")
    )
    assert result.fact is not None and result.fact.evidence is None
    assert [c.quote for c in result.fact.conditions] == ["Preview users only."]
    assert result.discards[0].reason == reason


def test_exact_quote_boundaries_limits_and_visible_input_are_enforced() -> None:
    data = output()
    data["fact"]["evidence"] = "e" * 600
    data["fact"]["conditions"] = [{"quote": "c" * 400}, {"quote": "late detail"}]
    result = normalize_structure(
        data, material(body="e" * 600 + "c" * 400 + "x" * MAX_BODY_CHARS + "late detail")
    )
    assert result.fact is not None and result.fact.evidence == "e" * 600
    assert [c.quote for c in result.fact.conditions] == ["c" * 400]
    assert result.discards[0].reason == "not_in_model_input"


def test_conditions_are_independent_bounded_and_cannot_join_main_and_quoted_posts() -> None:
    data = output()
    data["fact"]["conditions"] = [None, {"quote": "only. Old"}]
    data["fact"]["conditions"] += [{"quote": f"Rule {i}."} for i in range(5)]
    result = normalize_structure(
        data,
        material(
            body="Preview users only. " + " ".join(f"Rule {i}." for i in range(5)),
            quoted_text="Old release.",
        ),
    )
    assert result.fact is not None and len(result.fact.conditions) == 4
    assert [d.reason for d in result.discards] == [
        "not_in_original",
        "invalid_type",
        "not_in_original",
        "too_many",
    ]


def test_x_new_benchmark_action_is_kept_instead_of_the_quoted_old_release() -> None:
    result = normalize_structure(
        output(),
        material(
            source_kind="x_search",
            body="We published the model ranking today. Preview users only.",
            quoted_text="OpenAI released the model last week.",
        ),
    )
    assert result.fact is not None and result.fact.action == "公布评测结果"
    assert result.fact.subject == "评测机构"
    assert result.fact.evidence == "We published the model ranking today."
    instructions = structure_instructions()
    assert "fact 必须是主帖的这次动作" in instructions
    assert "引用的旧发布帖只说明" in instructions


def test_pure_quote_introduction_can_keep_an_original_quoted_post_sentence() -> None:
    data = output()
    data["fact"]["evidence"] = "OpenAI released the model last week."
    data["fact"]["conditions"] = []
    result = normalize_structure(
        data, material(body="See the announcement.", quoted_text=data["fact"]["evidence"])
    )
    assert result.fact is not None and result.fact.evidence == data["fact"]["evidence"]


@pytest.mark.parametrize(
    ("category", "tags", "normalized", "rule"),
    [
        ("ai-models", ["模型", "推理"], "模型发布", "首次开放权重"),
        ("ai-models", ["评测/基准"], "评测/基准", "公布一次跑分不是发布新基准"),
        ("ai-products", ["产品"], "产品更新", "硬件适配组件仍是产品"),
        ("paper", ["研究"], "论文/研究", "研究数据集"),
        ("industry", ["行业"], "行业动态", "真实安全事故及调查进展"),
        ("tip", ["教程"], "教程/实践", "工程实践复盘"),
        ("opinion", ["观点"], "大佬观点", "作者的解释、判断"),
    ],
)
def test_category_guides_and_tag_mapping(
    category: str, tags: list[str], normalized: str, rule: str
) -> None:
    result = normalize_structure(output(category=category, tags=tags, fact=None), material())
    assert result.category == category and result.tags[0] == normalized
    assert rule in structure_instructions()


@pytest.mark.parametrize(
    "conditions", [None, "Preview users only.", {"quote": "Preview users only."}]
)
def test_invalid_conditions_container_preserves_fact_and_evidence(conditions: Any) -> None:
    data = output()
    data["fact"]["conditions"] = conditions
    result = normalize_structure(data, material(body=data["fact"]["evidence"]))
    assert result.fact is not None and result.fact.evidence == data["fact"]["evidence"]
    assert result.fact.conditions == []
    assert [(d.field, d.reason) for d in result.discards] == [("fact.conditions", "invalid_type")]


@pytest.mark.parametrize("scope", [None, "invented", 123, ["single"]])
def test_invalid_scope_falls_back_to_unknown_without_losing_grounded_fact(scope: Any) -> None:
    result = normalize_structure(
        output(scope=scope),
        material(body="We published the model ranking today. Preview users only."),
    )
    assert result.scope == "unknown" and result.fact is not None
    assert [(d.field, d.reason) for d in result.discards] == [("scope", "invalid_scope")]


def test_excerpt_and_quoted_post_are_grounded_only_within_the_visible_original() -> None:
    data = output()
    data["fact"]["conditions"] = [{"quote": "late quoted detail"}]
    result = normalize_structure(
        data,
        material(
            body="", excerpt=data["fact"]["evidence"], quoted_text="x" * 2000 + "late quoted detail"
        ),
    )
    assert result.fact is not None and result.fact.evidence == data["fact"]["evidence"]
    assert result.fact.conditions == [] and result.discards[0].reason == "not_in_model_input"


def test_stage_recovery_preserves_program_discards_and_ignores_model_discards() -> None:
    data = output()
    data["fact"]["evidence"] = "invented"
    data["discards"] = [{"field": "untrusted model diagnostic", "reason": "invalid_type"}]
    item = material(body="Preview users only.")
    stored = normalize_structure(data, item)
    restored = normalize_structure(
        StructureOutput.model_validate(stored.model_dump(mode="json", by_alias=True)), item
    )
    assert stored == restored
    assert [(d.field, d.reason) for d in restored.discards] == [
        ("fact.evidence", "not_in_original")
    ]
