import pytest


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
