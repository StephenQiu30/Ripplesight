"""Exercise applied revision receipts against real fixed evidence in owned PostgreSQL."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from tests.integration import test_event_clustering as clustering_tests
from tests.integration.test_event_clustering import _add_event_inputs

from core.errors import ApplicationError
from events.clustering import EVENT_PROMPT_VERSION, candidate_fingerprint
from events.fact_models import EventFactAssignment, EventGroupingAssessment
from events.facts import EventFactReadService
from events.models import EventCandidate
from events.observation_inputs import freeze_event_inputs_in_transaction
from events.schemas import EventDecision, EventEvidenceChangeDecision, EventFactDecision
from events.services import EventCandidateService, load_relevant_event_inputs_in_transaction

event_context = clustering_tests.event_context


def _initial(context, *, explicit=True, relation="root"):
    """Create an initial revision through the real atomic candidate writer."""
    sessions, owner, _, versions, call_id, now = context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = session.scalar(
            select(EventCandidate).where(
                EventCandidate.owner_id == owner,
                EventCandidate.member_version_ids.contains([str(value) for value in versions[:2]]),
            )
        )
        assert candidate is not None
        identity = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate.id,
            owner_id=owner,
            ai_call_id=call_id,
            now=now,
            decision=EventDecision(
                same_event=True,
                member_version_ids=list(versions[:2]),
                title="发布",
                summary="同一发生",
                facts=(
                    [
                        EventFactDecision(
                            member_version_ids=[versions[0]],
                            title="根发生",
                            summary="根",
                            relation="root",
                        ),
                        EventFactDecision(
                            member_version_ids=[versions[1]],
                            title="背景",
                            summary="背景",
                            relation="background",
                            root_member_version_id=versions[0],
                        ),
                    ]
                    if relation == "background"
                    else [
                        EventFactDecision(
                            member_version_ids=list(versions[:2]),
                            title="发布",
                            summary="同一发生",
                            relation=relation,
                        )
                    ]
                )
                if explicit
                else [],
            ),
        )
        assert identity is not None
        return identity, candidate.id


def _append(context, event_id, *, target_relation="root", development=False):
    """Freeze one context material and three new materials, then classify two."""
    sessions, owner, topic, versions, call_id, now = context
    with sessions() as session, session.begin():
        added = _add_event_inputs(session, owner, topic, call_id, now, count=3)
        frozen = (versions[1] if target_relation == "background" else versions[0], *added)
        inputs = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(days=1), version_ids=frozen, exclude_assigned=False
        )
        assert len(inputs) == 4
        inputs, manifest = freeze_event_inputs_in_transaction(
            session, owner_id=owner, inputs=inputs, now=now
        )
        candidate = EventCandidate(
            id=uuid4(),
            owner_id=owner,
            topic_id=topic,
            input_fingerprint=candidate_fingerprint(
                topic_id=topic, members=inputs, expected_event_revisions={str(event_id): 1}
            ),
            member_version_ids=sorted(str(value) for value in frozen),
            input_manifest=manifest,
            expected_event_revisions={str(event_id): 1},
            window_start=now - timedelta(hours=3),
            window_end=now + timedelta(seconds=1),
            prompt_version=EVENT_PROMPT_VERSION,
            status="pending",
            ai_call_id=None,
            job_id=None,
            event_id=None,
            error_code=None,
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        session.flush()
        root = session.scalar(
            select(EventFactAssignment.fact_id).where(
                EventFactAssignment.owner_id == owner,
                EventFactAssignment.event_id == event_id,
                EventFactAssignment.relation == target_relation,
                EventFactAssignment.removed_revision.is_(None),
            )
        )
        assert root is not None
        decision = EventDecision(
            same_event=True,
            member_version_ids=list(frozen),
            title="发布更新",
            summary="补充材料",
            facts=[
                EventFactDecision(
                    member_version_ids=list(frozen),
                    title="发布",
                    summary="同一次发生",
                    relation="same_occurrence",
                    existing_fact_id=root,
                    evidence_changes=[
                        EventEvidenceChangeDecision(
                            member_version_id=added[0], kind="supplement", reason="提供额外证据"
                        ),
                        EventEvidenceChangeDecision(
                            member_version_id=added[1], kind="repeat", reason="仅转述已知发布"
                        ),
                        # Context judgments must never become new-member metrics.
                        EventEvidenceChangeDecision(
                            member_version_id=frozen[0], kind="repeat", reason="上下文"
                        ),
                    ],
                )
            ],
        )
        if development:
            first = decision.facts[0].model_copy(update={"member_version_ids": list(frozen[:-1])})
            decision = decision.model_copy(
                update={
                    "facts": [
                        first,
                        EventFactDecision(
                            member_version_ids=[added[-1]],
                            title="后续进展",
                            summary="新的发生",
                            relation="development",
                            root_fact_id=root,
                        ),
                    ]
                }
            )
        EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate.id,
            owner_id=owner,
            ai_call_id=call_id,
            now=now,
            decision=decision,
        )
        return candidate.id, decision


def _read(context, event_id, revision=None):
    sessions, owner, *_ = context
    with sessions() as session:
        return EventFactReadService(session).list_facts(
            owner_id=owner, event_id=event_id, revision=revision
        )


def test_initial_receipt_counts_distinct_facts_and_actual_members(event_context):
    event_id, _ = _initial(event_context)
    page = _read(event_context, event_id)
    assert page.delta_state == "available" and page.delta is not None
    delta = page.delta
    assert (delta.baseline_event_revision, delta.event_revision) == (0, 1)
    assert (delta.new_fact_count, delta.new_fact_material_count, delta.material_count) == (1, 2, 2)
    assert delta.supplement_count == delta.repeat_count == delta.unknown_count == 0


def test_append_partitions_only_new_materials_and_replay_preserves_receipt(event_context):
    event_id, _ = _initial(event_context)
    candidate_id, decision = _append(event_context, event_id)
    sessions, owner, _, _, call_id, now = event_context
    before = _read(event_context, event_id)
    assert before.delta is not None
    assert before.delta.baseline_event_revision == 1 and before.event_revision == 2
    assert (before.delta.new_fact_count, before.delta.new_fact_material_count) == (0, 0)
    assert (
        before.delta.material_count,
        before.delta.supplement_count,
        before.delta.repeat_count,
        before.delta.unknown_count,
    ) == (3, 1, 1, 1)
    with sessions() as session, session.begin():
        assert (
            EventCandidateService(session).confirm_in_transaction(
                candidate_id=candidate_id,
                owner_id=owner,
                ai_call_id=call_id,
                now=now,
                decision=decision,
            )
            == event_id
        )
    assert _read(event_context, event_id).model_dump() == before.model_dump()
    historical = _read(event_context, event_id, 1)
    assert historical.delta is not None and historical.delta.event_revision == 1
    assert historical.delta.material_count == 2


def test_legacy_decision_keeps_new_members_unclassified(event_context):
    event_id, _ = _initial(event_context, explicit=False)
    delta = _read(event_context, event_id).delta
    assert delta is not None
    assert delta.new_fact_count == 0 and delta.unknown_count == delta.material_count == 2


@pytest.mark.parametrize(
    "corruption", ["missing", "version", "baseline", "member", "material_version", "reason"]
)
def test_old_or_corrupted_receipt_never_fabricates_zero_changes(event_context, corruption):
    event_id, candidate_id = _initial(event_context)
    sessions, *_ = event_context
    with sessions() as session, session.begin():
        row = session.scalar(
            select(EventGroupingAssessment).where(
                EventGroupingAssessment.candidate_id == candidate_id
            )
        )
        receipt = dict(row.applied_result)
        if corruption == "missing":
            row.applied_result = None
        else:
            if corruption == "version":
                receipt["version"] = "future_delta"
            elif corruption == "baseline":
                receipt["baseline_event_revision"] = True
            elif corruption == "member":
                receipt["material_changes"] = [
                    {**receipt["material_changes"][0], "event_member_id": str(uuid4())}
                ]
            elif corruption == "material_version":
                receipt["material_changes"] = [
                    {**value, "content_version_id": str(uuid4())}
                    for value in receipt["material_changes"]
                ]
            else:
                receipt["material_changes"] = [
                    {**receipt["material_changes"][0], "kind": "supplement", "reason": " "}
                ]
            row.applied_result = receipt
    page = _read(event_context, event_id)
    assert page.delta is None
    assert page.delta_state == ("not_recorded" if corruption == "missing" else "invalid")


def test_owner_isolation_and_readonly_complete_rows(event_context):
    event_id, _ = _initial(event_context)
    sessions, *_ = event_context
    tables = [
        "event_grouping_assessments",
        "event_candidates",
        "events",
        "event_facts",
        "event_members",
        "event_fact_members",
        "event_fact_assignments",
        "outbox_messages",
        "resource_usage_attempts",
    ]

    def snapshot():
        with sessions() as session:
            return {
                table: session.execute(
                    text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text"),
                )
                .scalars()
                .all()
                for table in tables
            }

    before = snapshot()
    _read(event_context, event_id)
    with sessions() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        EventFactReadService(session).list_facts(owner_id=uuid4(), event_id=event_id)
    assert snapshot() == before


def test_schema_rejects_nonobject_applied_result(event_context):
    _, candidate_id = _initial(event_context)
    sessions, *_ = event_context
    with sessions() as session:
        column = session.execute(
            text(
                "SELECT data_type,is_nullable FROM information_schema.columns "
                "WHERE table_name='event_grouping_assessments' "
                "AND column_name='applied_result'"
            )
        ).one()
        assert tuple(column) == ("jsonb", "YES")
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname='event_grouping_assessments_applied_check'"
                )
            )
            == 1
        )
    with sessions() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(
            text(
                "UPDATE event_grouping_assessments SET applied_result='[]'::jsonb "
                "WHERE candidate_id=:candidate"
            ),
            {"candidate": candidate_id},
        )


@pytest.mark.parametrize("corruption", ["new_fact", "wrong_kind", "wrong_reason", "wrong_fact"])
def test_classification_must_match_frozen_judgment_and_baseline(event_context, corruption):
    event_id, _ = _initial(event_context)
    candidate_id, _ = _append(event_context, event_id)
    sessions, *_ = event_context
    with sessions() as session, session.begin():
        row = session.scalar(
            select(EventGroupingAssessment).where(
                EventGroupingAssessment.candidate_id == candidate_id
            )
        )
        receipt = dict(row.applied_result)
        changes = [dict(value) for value in receipt["material_changes"]]
        change = next(value for value in changes if value["kind"] == "supplement")
        if corruption == "new_fact":
            change.update(kind="new_fact", reason=None)
        elif corruption == "wrong_kind":
            change["kind"] = "repeat"
        elif corruption == "wrong_reason":
            change["reason"] = "篡改判断"
        else:
            change["fact_id"] = str(uuid4())
        receipt["material_changes"] = changes
        row.applied_result = receipt
    page = _read(event_context, event_id)
    assert page.delta_state == "invalid" and page.delta is None


@pytest.mark.parametrize("relation", ["background", "roundup"])
def test_existing_background_does_not_contribute_supplement_or_repeat(event_context, relation):
    event_id, _ = _initial(event_context, relation=relation)
    _append(event_context, event_id, target_relation=relation)
    page = _read(event_context, event_id)
    assert page.delta is not None
    assert page.delta.unknown_count == page.delta.material_count == 3
    assert page.delta.supplement_count == page.delta.repeat_count == page.delta.new_fact_count == 0


def test_revoke_one_old_input_hides_all_derived_delta_reasons(event_context):
    event_id, _ = _initial(event_context)
    _append(event_context, event_id, development=True)
    sessions, owner, *_ = event_context
    with sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE source_access_policies SET status='blocked',enabled=false "
                "WHERE owner_id=:owner AND source_key='hackernews'"
            ),
            {"owner": owner},
        )
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(event_context, event_id, 1)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(event_context, event_id, 2)


@pytest.mark.parametrize("changed", [False, True])
def test_v4_frozen_fingerprint_is_still_checked(event_context, changed):
    from dataclasses import replace

    from events.services import _candidate_material_matches

    sessions, owner, topic, versions, _, now = event_context
    with sessions() as session, session.begin():
        inputs = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(days=1), version_ids=versions[:2]
        )
        inputs, _ = freeze_event_inputs_in_transaction(
            session, owner_id=owner, inputs=inputs, now=now
        )
        version = EVENT_PROMPT_VERSION.replace("v5-fact-delta@", "v4-scope@")
        candidate = EventCandidate(
            owner_id=owner,
            topic_id=topic,
            member_version_ids=[str(value) for value in versions[:2]],
            expected_event_revisions={},
            prompt_version=version,
            input_fingerprint=candidate_fingerprint(
                topic_id=topic, members=inputs, prompt_version=version
            ),
        )
        if changed:
            inputs = (replace(inputs[0], title="changed"), *inputs[1:])
        assert (
            _candidate_material_matches(session, candidate=candidate, members=inputs) is not changed
        )


def test_old_pending_prompt_does_not_start_a_new_model_request(event_context, monkeypatch):
    from events.services import _load_candidate_inputs
    from jobs.execution import JobExecutionFailure

    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = clustering_tests._candidate_for_versions(session, owner, versions[:2])
        candidate.prompt_version = EVENT_PROMPT_VERSION.replace("v5-fact-delta@", "v4-scope@")
        inputs = _load_candidate_inputs(session, candidate=candidate, now=now)
        candidate.input_fingerprint = candidate_fingerprint(
            topic_id=candidate.topic_id, members=inputs, prompt_version=candidate.prompt_version
        )
        message = clustering_tests._event_message(session, candidate)
    prompts = clustering_tests._fake_event_model(monkeypatch, sessions, call_id, versions[:2])
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        clustering_tests._event_executor(sessions, now).execute(message)
    assert prompts == []


def test_saved_v4_response_recovers_without_requesting_v5(event_context, monkeypatch):
    from events.services import _load_candidate_inputs

    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = clustering_tests._candidate_for_versions(session, owner, versions[:2])
        message = clustering_tests._event_message(session, candidate)
        identity = candidate.id
    prompts = clustering_tests._fake_event_model(monkeypatch, sessions, call_id, versions[:2])
    original = EventCandidateService.confirm_in_transaction
    monkeypatch.setattr(
        EventCandidateService,
        "confirm_in_transaction",
        lambda *_a, **_kw: (_ for _ in ()).throw(SystemExit()),
    )
    executor = clustering_tests._event_executor(sessions, now)
    with pytest.raises(SystemExit):
        executor.execute(message)
    monkeypatch.setattr(EventCandidateService, "confirm_in_transaction", original)
    with sessions() as session, session.begin():
        candidate = session.get(EventCandidate, identity)
        assessment = session.scalar(
            select(EventGroupingAssessment).where(EventGroupingAssessment.candidate_id == identity)
        )
        candidate.prompt_version = EVENT_PROMPT_VERSION.replace("v5-fact-delta@", "v4-scope@")
        inputs = _load_candidate_inputs(session, candidate=candidate, now=now)
        candidate.input_fingerprint = candidate_fingerprint(
            topic_id=candidate.topic_id, members=inputs, prompt_version=candidate.prompt_version
        )
        assessment.prompt_version = candidate.prompt_version
        assessment.input_fingerprint = candidate.input_fingerprint
        from ai.models import AiCall

        session.get(AiCall, assessment.ai_call_id).prompt_version = candidate.prompt_version
    monkeypatch.setattr(
        "events.services.build_event_prompt",
        lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("new prompt must not be built")),
    )
    executor.execute(message)
    assert len(prompts) == 1
    with sessions() as session:
        assert session.get(EventCandidate, identity).status == "confirmed"


def test_receipt_rolls_back_with_the_event_transaction(event_context, monkeypatch):
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = clustering_tests._candidate_for_versions(session, owner, versions[:2])
        identity = candidate.id

    from events import services

    original_writer = services.record_candidate_facts_in_transaction

    def fail_after_receipt(*args, **kwargs):
        original_writer(*args, **kwargs)
        assessment = args[0].scalar(
            select(EventGroupingAssessment).where(EventGroupingAssessment.candidate_id == identity)
        )
        assert assessment.applied_result is not None
        raise RuntimeError("controlled failure after fact persistence")

    monkeypatch.setattr("events.services.record_candidate_facts_in_transaction", fail_after_receipt)
    decision = EventDecision(
        same_event=True,
        member_version_ids=list(versions[:2]),
        title="发布",
        summary="同一次发生",
        facts=[
            EventFactDecision(
                member_version_ids=list(versions[:2]),
                title="发布",
                summary="同一次发生",
                relation="root",
            )
        ],
    )
    with (
        sessions() as session,
        pytest.raises(RuntimeError, match="controlled failure"),
        session.begin(),
    ):
        EventCandidateService(session).confirm_in_transaction(
            candidate_id=identity, owner_id=owner, ai_call_id=call_id, now=now, decision=decision
        )
    with sessions() as session:
        candidate = session.get(EventCandidate, identity)
        assert candidate.status == "pending" and candidate.event_id is None
        assessment = session.scalar(
            select(EventGroupingAssessment).where(EventGroupingAssessment.candidate_id == identity)
        )
        assert assessment is None or assessment.applied_result is None
        assert (
            session.scalar(
                text("SELECT count(*) FROM events WHERE owner_id=:owner"), {"owner": owner}
            )
            == 0
        )


def test_manual_detach_has_no_automatic_receipt_and_historical_conclusion_is_gated(event_context):
    from events.corrections import EventCorrectionService
    from events.fact_schemas import EventCorrectionInput
    from events.models import EventMember

    event_id, _ = _initial(event_context)
    sessions, owner, *_ = event_context
    with sessions() as session:
        member = session.scalar(select(EventMember).where(EventMember.event_id == event_id))
        command = EventCorrectionInput(
            operation_id=uuid4(),
            kind="detach",
            reason="人工移除错误材料",
            content_ids=[member.content_id],
            expected_revisions={event_id: 1},
        )
        EventCorrectionService(session).correct(owner_id=owner, actor_id=owner, command=command)
    page = _read(event_context, event_id, 2)
    assert page.delta_state == "not_recorded" and page.delta is None
    history = _read(event_context, event_id, 1)
    assert history.delta is not None
    removed = next(
        change for change in history.delta.material_changes if change.event_member_id == member.id
    )
    assert removed.kind == "unknown" and removed.unavailable and removed.reason is None
