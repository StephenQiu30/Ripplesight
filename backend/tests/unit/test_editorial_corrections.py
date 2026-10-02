from uuid import uuid4

from analysis.editorial_corrections import apply_editorial_correction
from analysis.editorial_schemas import EditorialOverrideInput
from tests.unit.test_editorial_rules import material


def test_category_and_public_reason_are_partial_clearable_without_changing_paid_evidence():
    automatic = {
        "relevance": "pass",
        "selected": True,
        "scores": [90, 90],
        "structure": {"category": "ai-models", "tags": [], "subjects": [], "fact": None},
        "writing": {
            "kind": "understand",
            "title_zh": "模型发布",
            "summary_zh": "一个新的模型发布了。",
            "reason_zh": "原自动理由",
            "identity_guard": {
                "outcome": "pass",
                "unsupported_title_entity_ids": [],
                "unsupported_summary_entity_ids": [],
            },
        },
    }
    changed = apply_editorial_correction(
        material=material(),
        automatic=automatic,
        current=automatic,
        command=EditorialOverrideInput(
            operation_id=uuid4(),
            expected_manual_version=0,
            category="paper",
            reason_zh="公开推荐理由",
            reason="私有纠正审计",
        ),
    )
    assert changed["structure"]["category"] == "paper"
    assert changed["writing"]["reason_zh"] == "公开推荐理由"
    assert (
        changed["scores"] == automatic["scores"]
        and automatic["structure"]["category"] == "ai-models"
    )
    partial = apply_editorial_correction(
        material=material(),
        automatic=automatic,
        current=changed,
        command=EditorialOverrideInput(
            operation_id=uuid4(),
            expected_manual_version=1,
            clear_fields=["category"],
            reason="恢复分类",
        ),
    )
    assert (
        partial["structure"]["category"] == "ai-models"
        and partial["writing"]["reason_zh"] == "公开推荐理由"
    )
    cleared = apply_editorial_correction(
        material=material(),
        automatic=automatic,
        current=partial,
        command=EditorialOverrideInput(
            operation_id=uuid4(), expected_manual_version=2, action="clear", reason="恢复全部"
        ),
    )
    assert cleared["writing"] == automatic["writing"] and cleared["manual"] is False


def test_private_correction_reason_does_not_replace_public_reason_when_editing_copy():
    automatic = {
        "relevance": "pass",
        "writing": {
            "kind": "understand",
            "title_zh": "模型发布",
            "summary_zh": "一个新的模型发布了。",
            "reason_zh": "公开自动理由",
        },
    }
    changed = apply_editorial_correction(
        material=material(),
        automatic=automatic,
        current=automatic,
        command=EditorialOverrideInput(
            operation_id=uuid4(),
            expected_manual_version=0,
            title_zh="新模型发布",
            reason="私有错误处理细节",
        ),
    )
    assert changed["writing"]["reason_zh"] == "公开自动理由"
