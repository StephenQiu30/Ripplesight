from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from events.clustering import append_candidates
from events.schemas import EventTarget
from tests.unit.test_event_clustering import _member


def test_exact_native_reference_precedes_higher_title_similarity():
    original = _member("original unrelated native title")
    lexical = _member("identical lexical title")
    incoming = replace(
        _member("identical lexical title"),
        owner_id=original.owner_id,
        topic_id=original.topic_id,
        native_target_content_ids=frozenset({original.content_id}),
    )
    native_target = EventTarget(uuid4(), 1, (original,))
    lexical_target = EventTarget(uuid4(), 1, (lexical,))
    session = SimpleNamespace(execute=lambda *_: [(0, 1, 1.0)])
    result = append_candidates(session, (incoming,), (native_target, lexical_target))
    assert len(result) == 1 and result[0][1].event_id == native_target.event_id


def test_native_reference_never_crosses_owner_or_topic():
    original = _member("native")
    incoming = replace(
        _member("incoming"), native_target_content_ids=frozenset({original.content_id})
    )
    target = EventTarget(uuid4(), 1, (original,))
    assert append_candidates(SimpleNamespace(execute=lambda *_: []), (incoming,), (target,)) == ()


def test_pending_regroup_is_not_evidence_for_other_incoming_content():
    from events.clustering import plan_event_candidates

    pending = _member("same title")
    normal = replace(_member("same title"), owner_id=pending.owner_id, topic_id=pending.topic_id)
    session = SimpleNamespace(execute=lambda *_: [(0, 1)] if len(_) == 2 else [])
    groups = plan_event_candidates(
        session, (pending, normal), (), regroup_content_ids=frozenset({pending.content_id})
    )
    assert {tuple(item.content_id for item in members) for members, _ in groups} == {
        (pending.content_id,),
        (normal.content_id,),
    }


def test_waiting_native_signal_cannot_attach_after_48_hours_or_by_title_only():
    from events.clustering import plan_event_candidates

    original = _member("same title")
    late = replace(
        _member("same title"),
        owner_id=original.owner_id,
        topic_id=original.topic_id,
        first_seen_at=original.first_seen_at + timedelta(hours=49),
        native_target_content_ids=frozenset({original.content_id}),
    )
    target = EventTarget(uuid4(), 1, (original,))
    session = SimpleNamespace(execute=lambda *_: [(0, 0, 1.0)])
    groups = plan_event_candidates(
        session, (late,), (target,), native_only_version_ids=frozenset({late.content_version_id})
    )
    assert groups == ()


def test_waiting_native_signal_uses_native_fixed_member_as_context():
    from events.clustering import plan_event_candidates

    original = _member("original")
    newest = replace(
        _member("different development"),
        owner_id=original.owner_id,
        topic_id=original.topic_id,
        first_seen_at=original.first_seen_at + timedelta(hours=1),
    )
    reply = replace(
        _member("reply with entirely different title"),
        owner_id=original.owner_id,
        topic_id=original.topic_id,
        native_target_content_ids=frozenset({original.content_id}),
    )
    target = EventTarget(uuid4(), 1, (original, newest))
    groups = plan_event_candidates(
        SimpleNamespace(execute=lambda *_: []),
        (reply,),
        (target,),
        native_only_version_ids=frozenset({reply.content_version_id}),
    )
    assert len(groups) == 1
    assert groups[0][0][0].content_id == original.content_id
