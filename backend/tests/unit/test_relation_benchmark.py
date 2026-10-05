import pytest

from analysis.evaluation_relations import compare_relation_versions
from analysis.evaluation_schemas import RelationGoldCaseInput, RelationPredictionInput
from analysis.prompts import editorial_prompt_version


def test_relation_gold_reports_line_errors_and_same_story_is_distinct_from_occurrence():
    from analysis.evaluation_relations import parse_relation_gold_jsonl, relation_metrics

    text = (
        '{"caseId":"a","a":{"title":"launch","source":"one"},'
        '"b":{"title":"review","source":"two"},"gold":{"relation":"SAME_STORY"}}'
    )
    rows = parse_relation_gold_jsonl(text)
    assert rows[0].gold_relation == "SAME_STORY"
    with pytest.raises(ValueError, match=r"line 2.*duplicate"):
        parse_relation_gold_jsonl(text + "\n" + text)
    result = relation_metrics(
        [
            {"gold": "SAME_STORY", "relation": "SAME_OCCURRENCE", "confidence": 0.9},
            {"gold": "UNRELATED", "relation": None, "confidence": None},
        ]
    )
    assert result["evaluated"] == 1 and result["errors"] == 1
    assert result["confusion_matrix"]["SAME_STORY"]["SAME_OCCURRENCE"] == 1
    assert result["story_ties"][0]["tp"] == 1
    assert result["story_ties"][0]["errors"] == 1


def _comparison():
    labels = [
        "SAME_OCCURRENCE",
        "SAME_OCCURRENCE",
        "SAME_STORY",
        "UNRELATED",
        "ROUNDUP",
        "UNRELATED",
    ]
    cases = [
        RelationGoldCaseInput(
            case_id=str(index),
            a={"title": "A", "source": "rss"},
            b={"title": "B", "source": "rss"},
            gold_relation=label,
        )
        for index, label in enumerate(labels)
    ]
    old, new = "group-pair@frozen-old", editorial_prompt_version("group-pair")
    predictions = {}
    for version, outputs in (
        (old, ["SAME_OCCURRENCE", "SAME_STORY", "SAME_STORY", "SAME_OCCURRENCE", "SAME_STORY"]),
        (new, labels[:5]),
    ):
        predictions[version] = [
            RelationPredictionInput(
                case_id=str(index),
                relation=label,
                confidence=0.77 if index == 2 else 0.9,
            )
            for index, label in enumerate(outputs)
        ] + [RelationPredictionInput(case_id="5", error_code="controlled_failure")]
    return cases, predictions, old, new


def test_old_and_new_prompt_outputs_compare_identical_gold_and_thresholds():
    cases, predictions, old, new = _comparison()
    result = compare_relation_versions(cases, predictions, baseline_version=old)
    baseline, candidate = result["by_version"][old], result["by_version"][new]
    assert baseline["sample_size"] == candidate["sample_size"] == 6
    assert baseline["evaluated"] == candidate["evaluated"] == 5
    assert baseline["errors"] == candidate["errors"] == 1
    assert baseline["accuracy"] == 0.4 and baseline["macro_f1"] == 0.25
    assert candidate["accuracy"] == candidate["macro_f1"] == 1
    assert baseline["confusion_matrix"]["ROUNDUP"]["SAME_STORY"] == 1
    assert baseline["per_class"]["SAME_OCCURRENCE"] == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "support": 2,
    }
    assert result["changed_cases"] == ["1", "3", "4"]
    delta = result["delta_from_baseline"][new]
    assert delta["accuracy"] == pytest.approx(0.6) and delta["macro_f1"] == 0.75
    assert delta["errors"] == 0
    assert [(tie["threshold"], tie["fp"]) for tie in delta["story_ties"]] == [
        (0.75, -2),
        (0.8, -2),
        (0.85, -2),
        (0.9, -2),
        (0.95, 0),
    ]
    reversed_result = compare_relation_versions(
        cases[::-1], {v: p[::-1] for v, p in predictions.items()}, baseline_version=old
    )
    assert reversed_result == result


@pytest.mark.parametrize("corruption", ["missing", "extra", "duplicate"])
def test_version_comparison_rejects_different_or_duplicated_cases(corruption):
    cases, predictions, old, new = _comparison()
    if corruption == "missing":
        predictions[new] = predictions[new][:-1]
    elif corruption == "extra":
        predictions[new].append(RelationPredictionInput(case_id="extra", error_code="failed"))
    else:
        predictions[new][-1] = predictions[new][0]
    with pytest.raises(ValueError, match="same unique cases"):
        compare_relation_versions(cases, predictions, baseline_version=old)


def test_all_failed_candidate_outputs_preserve_errors_and_unknown_accuracy():
    cases, predictions, old, new = _comparison()
    predictions[new] = [
        RelationPredictionInput(case_id=case.case_id, error_code="failed") for case in cases
    ]
    result = compare_relation_versions(cases, predictions, baseline_version=old)
    assert result["by_version"][new]["accuracy"] is None
    assert result["by_version"][new]["errors"] == 6
    assert result["delta_from_baseline"][new]["accuracy"] is None
