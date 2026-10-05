from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.config import Settings
from events.clustering import build_event_prompt, candidate_fingerprint, cluster_candidates
from events.schemas import EventDecision, EventInput
from events.services import EventClusterExecutor
from jobs.execution import JobExecutionFailure


def _member(title: str) -> EventInput:
    return EventInput(
        owner_id=uuid4(),
        topic_id=uuid4(),
        content_id=uuid4(),
        content_version_id=uuid4(),
        source_key="hackernews",
        title=title,
        body=None,
        first_seen_at=datetime(2026, 9, 28, tzinfo=UTC),
        first_seen_basis="discovered",
        matched_keywords=frozenset({"Acme"}),
    )


def test_candidate_fingerprint_and_prompt_are_order_independent() -> None:
    topic_id = uuid4()
    first, second = _member("Acme launches a model"), _member("Acme launches new model")
    assert candidate_fingerprint(
        topic_id=topic_id, members=(first, second)
    ) == candidate_fingerprint(topic_id=topic_id, members=(second, first))
    assert build_event_prompt((first, second)) == build_event_prompt((second, first))


def test_scope_changes_fingerprint_and_is_in_the_real_cluster_prompt() -> None:
    member = replace(_member("Acme launches a model"), editorial_scope="single")
    composite = replace(member, editorial_scope="composite")
    assert candidate_fingerprint(
        topic_id=member.topic_id, members=(member,)
    ) != candidate_fingerprint(topic_id=member.topic_id, members=(composite,))
    prompt = build_event_prompt((composite,))
    assert '"scope":"composite"' in prompt
    assert "具体发布对象或具体发生" in prompt
    assert "多个演讲者的会议综述" in prompt


def test_fixed_editorial_context_keeps_scope_provenance_and_actual_observation(monkeypatch):
    from events.models import EventMember
    from events.services import _fixed_context_inputs
    from monitors.editorial_events import editorial_event_topic_id

    item, observation = _member("raw title"), uuid4()
    member = EventMember(
        owner_id=item.owner_id,
        content_id=item.content_id,
        content_version_id=item.content_version_id,
        source_key="rss",
        observation_id=observation,
        observation_source_key="rss",
        input_manifest={
            "basis": "observations_v1",
            "observation_source_key": "rss",
            "input_observation_ids": [str(observation)],
        },
    )
    reading = SimpleNamespace(
        id=item.content_id,
        source_key="rss",
        observation=SimpleNamespace(
            id=observation,
            content_version=SimpleNamespace(
                id=item.content_version_id, title=item.title, body="raw body"
            ),
        ),
        current_visibility=SimpleNamespace(status="visible"),
        representative_comment_state="none",
        representative_comment=None,
    )
    editorial = SimpleNamespace(
        scope="single",
        title="编辑标题",
        summary="编辑摘要",
        raw_body="raw body",
        fact_frame={"object": "Atlas"},
        observation_id=observation,
        provenance_fingerprint="fixed-editorial-result",
    )
    monkeypatch.setattr(
        "events.services.load_event_member_content_in_transaction",
        lambda _s, **kw: {kw["references"][0]: reading},
    )
    monkeypatch.setattr(
        "events.services.load_event_content_original_times_in_transaction",
        lambda *_a, **_kw: {
            item.content_version_id: SimpleNamespace(
                source_time=item.first_seen_at, basis="published"
            )
        },
    )
    monkeypatch.setattr(
        "events.services.load_editorial_event_inputs_for_versions_in_transaction",
        lambda *_a, **_kw: {item.content_version_id: editorial},
    )

    def load():
        return _fixed_context_inputs(
            SimpleNamespace(),
            owner_id=item.owner_id,
            topic_id=editorial_event_topic_id(item.owner_id),
            members=(member,),
            since=item.first_seen_at,
            now=item.first_seen_at,
        )

    context = load()[0]
    assert context.editorial_scope == "single" and context.editorial_frame == {"object": "Atlas"}
    assert context.provenance_fingerprint == "fixed-editorial-result"
    assert context.title == "编辑标题" and context.body == "编辑摘要"
    editorial.observation_id = uuid4()
    assert load() == ()


def test_composite_and_unknown_do_not_found_a_story_or_supply_recall_context():
    from events.clustering import append_candidates, plan_event_candidates
    from events.schemas import EventTarget

    member = _member("Acme launch")
    composite = replace(
        member, content_id=uuid4(), content_version_id=uuid4(), editorial_scope="composite"
    )
    unknown = replace(composite, editorial_scope="unknown")
    session = SimpleNamespace(
        execute=lambda *_args: pytest.fail("unsupported new candidate recall")
    )
    assert plan_event_candidates(session, (composite, unknown), ()) == ()
    target = EventTarget(uuid4(), 1, (composite, unknown))
    assert append_candidates(session, (member,), (target,)) == ()
    session.execute = lambda *_args: [(0, 0, 0.9)]
    target = EventTarget(uuid4(), 1, (member,))
    assert plan_event_candidates(session, (composite,), (target,)) == (
        ((member, composite), {str(target.event_id): 1}),
    )


@pytest.mark.parametrize("mode", ["manual", "standalone"])
def test_manual_assignment_and_exclusion_stay_out_of_automatic_inputs(mode):
    from events.services import _protected_event_input

    item = _member("Acme")
    statements = []

    def scalar(statement):
        statements.append(str(statement))
        assert mode in statement.compile().params["mode_1"]
        return item.content_id  # Matching protected override of either mode.

    assert _protected_event_input(
        SimpleNamespace(scalar=scalar),
        owner_id=item.owner_id,
        topic_id=item.topic_id,
        content_id=item.content_id,
        exclude_assigned=False,
    )
    assert len(statements) == 1 and "event_grouping_overrides.mode IN" in statements[0]


def test_candidate_batches_keep_all_21_members_without_singleton() -> None:
    members = tuple(_member("Acme launches a model") for _ in range(21))
    session = cast(
        Session,
        SimpleNamespace(
            execute=lambda *_args, **_kwargs: [
                (i, j) for i in range(len(members)) for j in range(i + 1, len(members))
            ]
        ),
    )

    batches = cluster_candidates(session, members)

    assert [len(batch) for batch in batches] == [19, 2]
    assert {item.content_version_id for batch in batches for item in batch} == {
        item.content_version_id for item in members
    }


def test_candidate_batches_preserve_valid_pairs_across_a_long_similarity_chain() -> None:
    start = datetime(2026, 9, 28, tzinfo=UTC)
    members = tuple(
        replace(_member("Acme launches a model"), first_seen_at=start + timedelta(hours=50 * i))
        for i in range(3)
    )
    session = cast(
        Session,
        SimpleNamespace(
            execute=lambda *_args, **_kwargs: [
                (i, j) for i in range(len(members)) for j in range(i + 1, len(members))
            ]
        ),
    )

    batches = cluster_candidates(session, members)

    assert [len(batch) for batch in batches] == [2, 2]
    assert all(
        batch[-1].first_seen_at - batch[0].first_seen_at <= timedelta(hours=72) for batch in batches
    )
    assert {item.content_version_id for batch in batches for item in batch} == {
        item.content_version_id for item in members
    }


def test_model_confirmation_rejects_blank_title_and_duplicate_members() -> None:
    first, second = uuid4(), uuid4()
    with pytest.raises(ValidationError):
        EventDecision(
            same_event=True,
            member_version_ids=[first, second],
            title=" ",
            summary="摘要",
        )
    with pytest.raises(ValidationError):
        EventDecision(
            same_event=True,
            member_version_ids=[first, first],
            title="事件",
            summary="摘要",
        )


def test_event_executor_does_not_open_storage_or_model_when_disabled() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test",
        ai_enabled=True,
        events_cluster_enabled=False,
    )
    executor = EventClusterExecutor(
        SimpleNamespace(__call__=lambda: pytest.fail("opened event storage")), settings
    )
    with pytest.raises(JobExecutionFailure, match="event_clustering_disabled"):
        executor.execute(SimpleNamespace(kind="events.cluster"))


def test_similarity_uses_one_set_query() -> None:
    members = tuple(_member("Acme launches a model") for _ in range(30))
    calls: list[str] = []

    def scalar(statement: object, *_args: object) -> float:
        calls.append(str(statement))
        return 1.0

    def execute(statement: object, *_args: object) -> list[tuple[int, int]]:
        calls.append(str(statement))
        return [(i, j) for i in range(30) for j in range(i + 1, 30)]

    session = cast(Session, SimpleNamespace(scalar=scalar, execute=execute))
    assert len(cluster_candidates(session, members)) == 2
    assert len(calls) == 1
    assert "unnest" in calls[0].lower()


def test_append_fingerprint_includes_target_revision() -> None:
    members = (_member("Acme launch"), _member("Acme launch"))
    topic, target = uuid4(), uuid4()
    first = candidate_fingerprint(
        topic_id=topic, members=members, expected_event_revisions={str(target): 1}
    )
    assert first != candidate_fingerprint(
        topic_id=topic, members=members, expected_event_revisions={str(target): 2}
    )
    assert first != candidate_fingerprint(topic_id=topic, members=members)


def test_annotation_page_accepts_bounded_keyset_cursor() -> None:
    from analysis.services import list_relevant_event_annotation_refs_in_transaction

    statements = []

    def scalars(statement):
        statements.append(statement)
        return SimpleNamespace(all=lambda: [])

    now = datetime(2026, 9, 28, tzinfo=UTC)
    session = SimpleNamespace(in_transaction=lambda: True, scalars=scalars)
    page = list_relevant_event_annotation_refs_in_transaction(
        session, since=now, after=(now, uuid4()), limit=100
    )
    assert page.items == () and page.next_after is None
    assert len(statements) == 1
    with pytest.raises(ValueError):
        list_relevant_event_annotation_refs_in_transaction(session, since=now, limit=2001)


def test_preflight_input_failure_marks_candidate_after_rollback(monkeypatch) -> None:
    from contextlib import contextmanager

    candidate_id, owner, job_id, operation = uuid4(), uuid4(), uuid4(), uuid4()
    versions = [str(uuid4()), str(uuid4())]
    now = datetime(2026, 9, 28, tzinfo=UTC)
    active = False
    failures = []

    @contextmanager
    def begin():
        nonlocal active
        active = True
        try:
            yield
        finally:
            active = False

    candidate = SimpleNamespace(
        owner_id=owner,
        job_id=job_id,
        status="pending",
        member_version_ids=versions,
        input_manifest=None,
        window_start=now,
        expected_event_revisions={},
        topic_id=uuid4(),
    )

    @contextmanager
    def sessions():
        def scalar(statement):
            assert active
            assert "event_candidates" in str(statement) and "FOR UPDATE" in str(statement)
            return candidate

        yield SimpleNamespace(begin=begin, scalar=scalar)

    configuration = SimpleNamespace(
        owner_id=owner,
        operation_id=operation,
        kind="events.cluster",
        observation=SimpleNamespace(configuration_ref="topic:test", configuration_version=1),
        scope={"candidate_id": str(candidate_id)},
    )
    monkeypatch.setattr(
        "events.services.load_job_execution_configuration", lambda *_a, **_kw: configuration
    )
    monkeypatch.setattr(
        "events.services.load_relevant_event_inputs_in_transaction", lambda *_a, **_kw: ()
    )
    monkeypatch.setattr("events.services.create_ai_client", lambda _s: pytest.fail("model called"))
    executor = EventClusterExecutor(
        sessions,
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test",
            events_cluster_enabled=True,
        ),
    )

    def mark_failed(*args):
        assert not active
        failures.append(args)

    monkeypatch.setattr(executor, "_mark_failed", mark_failed)
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        executor.execute(
            SimpleNamespace(
                kind="events.cluster",
                owner_id=owner,
                job_id=job_id,
                operation_id=operation,
                configuration_ref="topic:test",
                configuration_version=1,
            )
        )
    assert failures == [(candidate_id, owner, "input_changed", None)]


def test_scan_stops_after_ten_assigned_pages_and_logs(monkeypatch) -> None:
    from events.services import load_relevant_event_inputs_in_transaction

    calls = []
    now = datetime(2026, 9, 28, tzinfo=UTC)

    def page(_session, **kwargs):
        calls.append(kwargs["after"])
        return SimpleNamespace(items=(), next_after=(now, uuid4()))

    monkeypatch.setattr("events.services.list_relevant_event_annotation_refs_in_transaction", page)
    monkeypatch.setattr("events.services._event_inputs_from_refs", lambda *_a, **_kw: ())
    monkeypatch.setattr(
        "events.services.list_editorial_event_inputs_in_transaction",
        lambda *_a, **_kw: SimpleNamespace(items=(), next_after=None),
    )
    logs = []
    monkeypatch.setattr(
        "events.services.structlog.get_logger",
        lambda _name: SimpleNamespace(
            info=lambda name, **fields: logs.append({"event": name, **fields})
        ),
    )
    result = load_relevant_event_inputs_in_transaction(
        SimpleNamespace(in_transaction=lambda: True), since=now
    )
    assert result == () and len(calls) == 10
    assert calls[0] is None and all(cursor is not None for cursor in calls[1:])
    assert logs[-1]["event"] == "event_scan_truncated"
    assert logs[-1]["pages_read"] == 10


def test_append_uses_highest_score_latest_context_and_bounded_batches() -> None:
    from events.clustering import append_candidates
    from events.schemas import EventTarget

    old, recent = _member("Acme launch"), _member("Acme launch")
    recent = replace(
        recent,
        owner_id=old.owner_id,
        topic_id=old.topic_id,
        first_seen_at=recent.first_seen_at + timedelta(hours=1),
    )
    inputs = tuple(
        replace(_member("Acme launch"), owner_id=old.owner_id, topic_id=old.topic_id)
        for _ in range(40)
    )
    low = EventTarget(event_id=uuid4(), revision=1, members=(old,))
    high = EventTarget(event_id=uuid4(), revision=2, members=(old, recent))
    calls = []

    def execute(statement, parameters):
        calls.append(str(statement))
        return [(i, j, score) for i in range(40) for j, score in enumerate((0.5, 0.8, 0.7))]

    batches = append_candidates(SimpleNamespace(execute=execute), inputs, (low, high))
    assert len(calls) == 1 and "unnest" in calls[0]
    assert [len(members) for members, _ in batches] == [20, 20, 3]
    assert all(target == high and members[0] == recent for members, target in batches)
    assert {item.content_version_id for members, _ in batches for item in members[1:]} == {
        item.content_version_id for item in inputs
    }


def test_append_filters_keyword_and_window_before_choosing_target() -> None:
    from events.clustering import append_candidates
    from events.schemas import EventTarget

    incoming = _member("Acme launch")
    context = replace(incoming, content_id=uuid4(), content_version_id=uuid4())
    too_old = replace(context, first_seen_at=context.first_seen_at - timedelta(hours=73))
    other_keyword = replace(context, matched_keywords=frozenset({"Other"}))
    targets = tuple(
        EventTarget(event_id=uuid4(), revision=1, members=(member,))
        for member in (too_old, other_keyword, context)
    )
    session = SimpleNamespace(execute=lambda *_args: [(0, 0, 1.0), (0, 1, 1.0), (0, 2, 0.5)])
    batches = append_candidates(session, (incoming,), targets)
    assert len(batches) == 1 and batches[0][1] == targets[2]


def test_rework_annotation_cursor_is_latest_first() -> None:
    from sqlalchemy.dialects import postgresql

    from analysis.services import list_relevant_event_annotation_refs_in_transaction

    statements = []

    def scalars(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(all=lambda: [])

    now = datetime(2026, 9, 28, tzinfo=UTC)
    list_relevant_event_annotation_refs_in_transaction(
        SimpleNamespace(in_transaction=lambda: True, scalars=scalars),
        since=now - timedelta(hours=72),
        after=(now, uuid4()),
        limit=20,
    )
    assert "(content_annotations.created_at, content_annotations.id) <" in statements[0]
    assert (
        statements[0]
        .rsplit("ORDER BY", 1)[1]
        .startswith(" content_annotations.created_at DESC, content_annotations.id DESC")
    )


def test_rework_old_event_uses_recent_member_dto(monkeypatch) -> None:
    from events.services import _load_event_targets

    recent = _member("Acme launches a model")
    target = SimpleNamespace(id=uuid4(), revision=3)
    member = SimpleNamespace(event_id=target.id, content_version_id=recent.content_version_id)
    statements = []

    def scalars(statement):
        statements.append(str(statement))
        return SimpleNamespace(all=lambda: [target] if len(statements) == 1 else [member])

    since = recent.first_seen_at - timedelta(hours=72)
    calls = []

    def load_content(_session, **kwargs):
        calls.append(kwargs)
        return (recent,)

    monkeypatch.setattr("events.services._fixed_context_inputs", load_content)
    monkeypatch.setattr(
        "events.services.MonitorTopicService",
        lambda _session: SimpleNamespace(
            get_current_topic_rules_and_sources_in_transaction=lambda **_kw: (1, object(), ())
        ),
    )
    monkeypatch.setattr(
        "events.services.evaluate_monitor_rules",
        lambda *_args: SimpleNamespace(matched=True, matched_any=("Acme",), matched_all=()),
    )
    targets = _load_event_targets(
        SimpleNamespace(scalars=scalars),
        owner_id=recent.owner_id,
        topic_id=recent.topic_id,
        since=since,
    )
    assert "events.first_seen_at >=" not in statements[0]
    assert calls[0]["since"] == since
    assert calls[0]["members"] == [member]
    assert targets[0].event_id == target.id and targets[0].members == (recent,)
