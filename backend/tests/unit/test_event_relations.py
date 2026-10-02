from datetime import UTC, datetime
from uuid import UUID

from events.clustering import candidate_fingerprint
from events.fact_schemas import FactRelationCandidate
from events.relations import choose_relation, normalize_verdicts
from events.schemas import EventInput


def _candidate(number: int, *, root: bool = True, score: float = 0.5) -> FactRelationCandidate:
    return FactRelationCandidate(
        fact_id=UUID(int=number),
        event_id=UUID(int=100 + number),
        revision=1,
        story_root=root,
        recall_score=score,
    )


def test_same_occurrence_precedes_development_and_orders_confidence_then_recall() -> None:
    candidates = (_candidate(1, score=0.9), _candidate(2, score=0.4), _candidate(3))
    verdicts = normalize_verdicts(
        candidates,
        [
            {"id": "C1", "relation": "SAME_OCCURRENCE", "confidence": 0.7, "note": "同发布"},
            {"id": "C2", "relation": "SAME_OCCURRENCE", "confidence": 0.9, "note": "同发布"},
            {"id": "C3", "relation": "SAME_STORY", "confidence": 1.0, "note": "后续"},
        ],
    )
    result = choose_relation(candidates, verdicts)
    assert result.kind == "same_occurrence"
    assert result.target_fact_id == UUID(int=2)


def test_development_cannot_chain_through_an_existing_development() -> None:
    candidates = (_candidate(1, root=False, score=0.99), _candidate(2, score=0.3))
    verdicts = normalize_verdicts(
        candidates,
        [
            {"id": "C1", "relation": "SAME_STORY", "confidence": 0.95, "note": "进展的进展"},
            {"id": "C2", "relation": "SAME_STORY", "confidence": 0.8, "note": "直接进展"},
        ],
    )
    assert choose_relation(candidates, verdicts).target_fact_id == UUID(int=2)


def test_missing_or_malformed_verdict_retains_diagnostic_instead_of_unrelated() -> None:
    candidates = (_candidate(1), _candidate(2))
    verdicts = normalize_verdicts(
        candidates,
        [
            {"id": "C1", "relation": "INVENTED", "confidence": 0.9},
            {"id": "C2", "relation": "UNRELATED", "confidence": "0.5"},
        ],
    )
    assert [verdict.state for verdict in verdicts] == ["invalid", "invalid"]
    assert choose_relation(candidates, verdicts).kind == "unreviewed"
    assert choose_relation(candidates, normalize_verdicts(candidates, [])).kind == "unreviewed"


def test_roundup_requires_nonempty_all_roundup_and_signal_never_creates_story() -> None:
    candidates = (_candidate(1),)
    verdicts = normalize_verdicts(
        candidates,
        [
            {"id": "C1", "relation": "ROUNDUP", "confidence": 1.0, "note": "盘点"},
        ],
    )
    assert choose_relation(candidates, verdicts).kind == "roundup"
    assert choose_relation((), ()).kind == "new_story"
    assert choose_relation(candidates, verdicts, signal_only=True).kind == "signal_unmatched"


def test_signal_reaction_requires_confidence_point_eight() -> None:
    candidates = (_candidate(1),)
    for confidence, expected in ((0.79, "signal_unmatched"), (0.8, "signal")):
        verdicts = normalize_verdicts(
            candidates,
            [
                {"id": "C1", "relation": "SAME_STORY", "confidence": confidence, "note": "讨论"},
            ],
        )
        assert choose_relation(candidates, verdicts, signal_only=True).kind == expected


def test_signal_same_occurrence_also_requires_confidence_point_eight() -> None:
    candidates = (_candidate(1),)
    verdicts = normalize_verdicts(
        candidates, [{"id": "C1", "relation": "SAME_OCCURRENCE", "confidence": 0.79, "note": ""}]
    )
    assert choose_relation(candidates, verdicts, signal_only=True).kind == "signal_unmatched"


def test_single_report_candidate_has_stable_fingerprint_for_model_fact_review() -> None:
    item = EventInput(
        owner_id=UUID(int=1),
        topic_id=UUID(int=2),
        content_id=UUID(int=3),
        content_version_id=UUID(int=4),
        source_key="rss",
        title="独立发布",
        body="证据",
        first_seen_at=datetime(2026, 10, 2, tzinfo=UTC),
        first_seen_basis="published",
        matched_keywords=frozenset({"发布"}),
    )
    assert len(candidate_fingerprint(topic_id=item.topic_id, members=(item,))) == 32
