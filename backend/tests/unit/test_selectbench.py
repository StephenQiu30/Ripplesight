import pytest

from analysis.evaluation_schemas import SelectBenchImportInput
from analysis.evaluation_services import score_model_report


def _cases():
    return [
        {"case_id": "a", "title": "应选择", "gold": "select", "decision": "select", "score": 80},
        {"case_id": "b", "title": "应拒绝", "gold": "reject", "decision": "select", "score": 70},
        {"case_id": "c", "title": "边界样本", "gold": "either", "decision": "reject", "score": 30},
        {
            "case_id": "d",
            "title": "调用失败",
            "gold": "select",
            "decision": None,
            "error_code": "timeout",
        },
    ]


def test_selectbench_recomputes_errors_either_and_score_thresholds():
    result = score_model_report(_cases())
    assert result["tp"] == 1 and result["fp"] == 1 and result["errors"] == 1
    assert result["either"] == 1 and result["precision"] == 0.5
    assert result["accuracy"] == pytest.approx(1 / 3)
    assert result["error_rate"] == 0.25
    assert [row["threshold"] for row in result["thresholds"]] == list(range(40, 91, 2))
    assert next(row for row in result["thresholds"] if row["threshold"] == 80)["precision"] == 1
    assert result["f1"] == pytest.approx(2 / 3)


def test_selectbench_rejects_different_gold_sets_and_duplicate_cases():
    from uuid import uuid4

    for cases in ([_cases()[0], _cases()[0]], [{**_cases()[0], "gold": "reject"}, *_cases()[1:]]):
        with pytest.raises(ValueError):
            SelectBenchImportInput(
                operation_id=uuid4(),
                label="同批模型",
                prompt_version="selection-v1",
                models={"a": _cases(), "b": cases},
                reason="离线评测",
            )
