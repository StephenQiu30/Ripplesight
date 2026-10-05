from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from events.clustering import candidate_fingerprint
from events.fact_schemas import FactRelationCandidate
from events.relations import choose_relation, constrain_event_decision, normalize_verdicts
from events.schemas import EventDecision, EventInput


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


def _input(number: int, scope="single", *, object="Atlas", action="发布") -> EventInput:
    return EventInput(
        owner_id=UUID(int=1),
        topic_id=UUID(int=2),
        content_id=UUID(int=number),
        content_version_id=UUID(int=number + 1000),
        source_key="rss",
        title="Acme 发布 " + object,
        body="受控原文",
        first_seen_at=datetime(2026, 10, 2, tzinfo=UTC),
        first_seen_basis="published",
        matched_keywords=frozenset({"Acme"}),
        editorial_scope=scope,
        editorial_frame={
            "subject": "Acme",
            "action": action,
            "object": object,
            "occurredAt": "2026-10-02",
        }
        if scope == "single"
        else None,
    )


def _decision(*items: EventInput) -> EventDecision:
    return EventDecision(
        same_event=True,
        member_version_ids=[i.content_version_id for i in items],
        title="受控模型认为同一事件",
        summary="模型输出",
    )


def test_composite_model_tie_becomes_only_an_existing_fact_mention() -> None:
    single, composite = _input(3), _input(4, "composite")
    result = constrain_event_decision(
        _decision(single, composite), (single, composite), root_fact_id=UUID(int=99)
    )
    mention = result.facts[-1]
    assert mention.member_version_ids == [composite.content_version_id]
    assert mention.existing_fact_id == UUID(int=99)
    assert mention.relation == "same_occurrence"  # Existing identity, member role is mention.
    with pytest.raises(ValueError, match="composite_without_fact"):
        constrain_event_decision(_decision(composite), (composite,))


def test_unknown_scope_does_not_accept_a_controlled_positive_answer() -> None:
    item = _input(3, "unknown")
    with pytest.raises(ValueError, match="scope_unknown"):
        constrain_event_decision(_decision(item), (item,))
    assert choose_relation((), (), query_scope="unknown").kind == "unreviewed"


def test_known_unknown_editorial_scope_also_blocks_the_signal_native_shortcut(monkeypatch):
    from events.signals import load_waiting_signal_inputs_in_transaction

    item = _input(3, "unknown")
    page_item = SimpleNamespace(
        reference=SimpleNamespace(
            content_id=item.content_id, content_version_id=item.content_version_id
        )
    )
    session = SimpleNamespace(
        in_transaction=lambda: True,
        scalars=lambda _statement: [
            SimpleNamespace(enabled=True, mode="signal", owner_id=item.owner_id, source_key="rss")
        ],
    )
    monkeypatch.setattr(
        "events.signals.list_recent_signal_content_in_transaction",
        lambda *_a, **_kw: SimpleNamespace(items=(page_item,), next_after_content_id=None),
    )
    monkeypatch.setattr(
        "events.signals.load_editorial_event_inputs_for_versions_in_transaction",
        lambda *_a, **_kw: {item.content_version_id: SimpleNamespace(scope="unknown")},
    )
    monkeypatch.setattr(
        "events.signals.resolve_attention_source",
        lambda *_a, **_kw: pytest.fail("admitted unknown signal"),
    )
    assert load_waiting_signal_inputs_in_transaction(session, now=item.first_seen_at) == ()


@pytest.mark.parametrize("action", ["发布", "更新"])
def test_same_company_and_day_independent_objects_cannot_merge(action) -> None:
    first, second = _input(3, action=action), _input(4, object="Boreal", action=action)
    with pytest.raises(ValueError, match="independent_updates"):
        constrain_event_decision(_decision(first, second), (first, second))
    same_product_update = replace(
        second, editorial_frame={**first.editorial_frame, "occurredAt": "2026-10-03"}
    )
    with pytest.raises(ValueError, match="independent_updates"):
        constrain_event_decision(
            _decision(first, same_product_update), (first, same_product_update)
        )


def test_composite_cannot_become_a_new_story_even_with_a_positive_pair_verdict() -> None:
    candidates = (_candidate(1),)
    verdicts = normalize_verdicts(
        candidates,
        [{"id": "C1", "relation": "SAME_OCCURRENCE", "confidence": 1.0, "note": "错误同事实"}],
    )
    choice = choose_relation(candidates, verdicts, query_scope="composite")
    assert choice.kind == "mention" and choice.target_fact_id == candidates[0].fact_id
    assert choose_relation((), (), query_scope="composite").kind == "unreviewed"


@pytest.mark.parametrize("mode", ["manual", "standalone"])
def test_newer_manual_override_blocks_fact_writes_before_any_member_mutation(mode) -> None:
    from events.fact_writer import FactGroupingConflictError, record_candidate_facts_in_transaction

    item = _input(3)
    candidate = SimpleNamespace(
        owner_id=item.owner_id, topic_id=item.topic_id, id=UUID(int=99), input_fingerprint=b"x" * 32
    )
    assessment = SimpleNamespace(
        input_snapshot={
            "overrides": [
                {
                    "content_id": str(item.content_id),
                    "revision": 1,
                    "mode": mode,
                }
            ]
        }
    )
    session = SimpleNamespace(
        in_transaction=lambda: True,
        scalar=lambda _statement: assessment,
        get=lambda *_args: SimpleNamespace(revision=2, mode=mode),
        scalars=lambda *_args: pytest.fail("read members after manual conflict"),
        add=lambda *_args: pytest.fail("mutated manual membership"),
    )
    with pytest.raises(FactGroupingConflictError, match="manual_revision_conflict"):
        record_candidate_facts_in_transaction(
            session,
            candidate=candidate,
            event=SimpleNamespace(),
            decision=_decision(item),
            ai_call_id=UUID(int=98),
            now=item.first_seen_at,
            input_times={item.content_version_id: (item.first_seen_at, "published")},
        )


@pytest.mark.parametrize(
    "scope, error", [("composite", "composite_without_fact"), ("unknown", "scope_unknown")]
)
def test_fact_writer_independently_rejects_a_root_using_the_persisted_scope(scope, error) -> None:
    from events.fact_writer import FactGroupingConflictError, record_candidate_facts_in_transaction

    item = _input(3, scope)
    member = SimpleNamespace(
        content_version_id=item.content_version_id, input_manifest={"editorial_scope": scope}
    )
    queries = iter(([member], [], []))
    session = SimpleNamespace(
        in_transaction=lambda: True,
        scalar=lambda _statement: SimpleNamespace(input_snapshot={}),
        scalars=lambda _statement: next(queries),
        add=lambda _row: pytest.fail("created unsupported root"),
    )
    candidate = SimpleNamespace(
        owner_id=item.owner_id, topic_id=item.topic_id, id=UUID(int=99), input_fingerprint=b"x" * 32
    )
    event = SimpleNamespace(owner_id=item.owner_id, id=UUID(int=100))
    with pytest.raises(FactGroupingConflictError, match=error):
        record_candidate_facts_in_transaction(
            session,
            candidate=candidate,
            event=event,
            decision=_decision(item),
            ai_call_id=UUID(int=98),
            now=item.first_seen_at,
            input_times={item.content_version_id: (item.first_seen_at, "published")},
        )
