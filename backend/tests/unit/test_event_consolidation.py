from events.consolidation import consolidation_decision
from events.relations import RelationPairOutput, RelationReportInput, relation_frame


def _answer(relation="SAME_STORY", confidence=0.8):
    return RelationPairOutput(a="A", b="B", relation=relation, confidence=confidence, difference="")


def test_story_merge_requires_two_thresholds_and_never_treats_roundup_as_tie():
    assert consolidation_decision(_answer(confidence=0.799), None) == "separate"
    assert consolidation_decision(_answer(), None) == "review"
    assert consolidation_decision(_answer(), _answer(confidence=0.749)) == "separate"
    assert consolidation_decision(_answer(), _answer(confidence=0.75)) == "merge"
    assert consolidation_decision(_answer("ROUNDUP", 1.0), None) == "separate"
    assert consolidation_decision(_answer(), _answer("UNRELATED", 1.0)) == "separate"


def test_independent_release_frames_veto_two_controlled_positive_judgements():
    reports = tuple(
        RelationReportInput(
            title="发布",
            source="官方",
            frame={
                "subject": "Acme",
                "action": "发布",
                "object": product,
                "occurredAt": "2026-10-02",
            },
        )
        for product in ("Atlas", "Boreal")
    )
    for label in ("SAME_OCCURRENCE", "SAME_STORY"):
        assert (
            consolidation_decision(_answer(label, 1), _answer(label, 1), reports=reports)
            == "separate"
        )


def test_relation_pair_frame_keeps_identity_and_omits_nested_quote_fields():
    assert relation_frame(
        {
            "subject": "Acme",
            "action": "发布",
            "object": "Atlas",
            "occurredAt": None,
            "evidence": "quote",
            "conditions": [{"quote": "condition"}],
        }
    ) == {
        "subject": "Acme",
        "action": "发布",
        "object": "Atlas",
        "occurredAt": None,
    }
