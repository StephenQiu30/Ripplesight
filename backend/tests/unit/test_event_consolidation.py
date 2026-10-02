from events.consolidation import consolidation_decision
from events.relations import RelationPairOutput


def _answer(relation="SAME_STORY", confidence=0.8):
    return RelationPairOutput(a="A", b="B", relation=relation, confidence=confidence, difference="")


def test_story_merge_requires_two_thresholds_and_never_treats_roundup_as_tie():
    assert consolidation_decision(_answer(confidence=0.799), None) == "separate"
    assert consolidation_decision(_answer(), None) == "review"
    assert consolidation_decision(_answer(), _answer(confidence=0.749)) == "separate"
    assert consolidation_decision(_answer(), _answer(confidence=0.75)) == "merge"
    assert consolidation_decision(_answer("ROUNDUP", 1.0), None) == "separate"
    assert consolidation_decision(_answer(), _answer("UNRELATED", 1.0)) == "separate"
