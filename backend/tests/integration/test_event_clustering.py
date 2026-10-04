from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai.models import AiCall
from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from core.config import Settings
from events.clustering import EVENT_PROMPT_VERSION, candidate_fingerprint
from events.models import Event, EventCandidate, EventMember
from events.schemas import EventDecision
from events.services import (
    EventCandidateConflictError,
    EventCandidateService,
    EventClusterExecutor,
    load_relevant_event_inputs_in_transaction,
)
from jobs.execution import JobExecutionFailure
from jobs.models import Job


@pytest.fixture
def event_context() -> Iterator[
    tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime]
]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    owner_id, topic_id, call_id = uuid4(), uuid4(), uuid4()
    version_ids = tuple(uuid4() for _ in range(4))
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, "
                "current_version, created_at, updated_at) "
                "VALUES (:id, :owner, 'Acme', 'active', 'ready', 1, :now, :now)"
            ),
            {"id": topic_id, "owner": owner_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:topic, 1, :owner, '[\"Acme\"]'::jsonb, "
                "'[]'::jsonb, '[]'::jsonb, :now)"
            ),
            {"topic": topic_id, "owner": owner_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, input_fingerprint, "
                "status, input_tokens, cached_input_tokens, output_tokens, "
                "reasoning_output_tokens, "
                "duration_ms, created_at) "
                "VALUES (:id, :owner, 'events.cluster', 'test', 'fake', :prompt, :fingerprint, "
                "'succeeded', 0, 0, 0, 0, 0, :now)"
            ),
            {
                "id": call_id,
                "owner": owner_id,
                "prompt": EVENT_PROMPT_VERSION,
                "fingerprint": b"a" * 32,
                "now": now,
            },
        )
        records = (
            ("hackernews", "Acme launches new model", now - timedelta(hours=2)),
            ("reddit", "Acme launches a new model", now - timedelta(hours=1)),
            ("mastodon", "Acme opens a restaurant", now - timedelta(hours=1)),
            ("reddit", "Acme launches new model", now - timedelta(hours=80)),
        )
        for version_id, (source, title, observed_at) in zip(version_ids, records, strict=True):
            content_id = uuid4()
            connection.execute(
                text(
                    "INSERT INTO content_records "
                    "(id, owner_id, source_key, object_type, external_id, created_at) "
                    "VALUES (:id, :owner, :source, 'post', :external, :seen)"
                ),
                {
                    "id": content_id,
                    "owner": owner_id,
                    "source": source,
                    "external": str(content_id),
                    "seen": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO content_versions "
                    "(id, owner_id, content_id, fingerprint, text_scope, "
                    "text_origin, title, created_at) "
                    "VALUES (:id, :owner, :content, :fingerprint, 'full', 'source', :title, :seen)"
                ),
                {
                    "id": version_id,
                    "owner": owner_id,
                    "content": content_id,
                    "fingerprint": version_id.bytes * 2,
                    "title": title,
                    "seen": observed_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO content_annotations "
                    "(id, owner_id, content_id, content_version_id, topic_id, topic_rule_version, "
                    "prompt_version, relevant, relevance_reason, sentiment, summary, viewpoints, "
                    "ai_call_id, status, result_state, first_valid_at, created_at, updated_at) "
                    "VALUES (:id, :owner, :content, :version, :topic, 1, :prompt, true, "
                    "'matches Acme', 'neutral', 'Acme news', '[]'::jsonb, :call, "
                    "'annotated', 'valid', :seen, :seen, :seen)"
                ),
                {
                    "id": uuid4(),
                    "owner": owner_id,
                    "content": content_id,
                    "version": version_id,
                    "topic": topic_id,
                    "prompt": ANALYSIS_PROMPT_VERSION,
                    "call": call_id,
                    "seen": observed_at,
                },
            )
    with sessions() as session, session.begin():
        _seed_reading_evidence(session, owner_id, topic_id, version_ids, now)
    try:
        yield sessions, owner_id, topic_id, version_ids, call_id, now
    finally:
        engine.dispose()


def _seed_reading_evidence(session, owner, topic, version_ids, now):
    """Use real observed versions and lifecycle Evidence in controlled PostgreSQL fixtures."""
    from jobs.schemas import JobAcceptanceInput, JobObservationContext
    from jobs.services import JobService
    from sources.contracts import SourceCapability

    rows = session.execute(
        text("SELECT id,content_id FROM content_versions WHERE id=ANY(:ids)"),
        {"ids": list(version_ids)},
    ).all()
    by_source = {}
    for version, content in rows:
        record = session.execute(
            text("SELECT source_key,created_at FROM content_records WHERE id=:id"), {"id": content}
        ).one()
        by_source.setdefault(record.source_key, []).append((version, content, record.created_at))
    for source, versions in by_source.items():
        policy = session.execute(
            text(
                "SELECT id FROM source_access_policies WHERE owner_id=:owner "
                "AND source_key=:source AND capability='search'"
            ),
            {"owner": owner, "source": source},
        ).scalar()
        if policy is None:
            policy = uuid4()
            session.execute(
                text(
                    "INSERT INTO source_access_policies "
                    "(id,owner_id,source_key,capability,status,enabled,access_basis,terms_reference,"
                    "processing_purpose,component_name,component_version,component_license,field_purposes,"
                    "reviewed_at,created_at,updated_at) "
                    "VALUES (:id,:owner,:source,'search','approved',true,"
                    "'manual_import','controlled PG fixture','事件固定阅读测试',"
                    "'controlled','1','MIT',"
                    '\'{"title":"事件证据","body":"事件证据"}\'::jsonb,:at,:at,:at)'
                ),
                {"id": policy, "owner": owner, "source": source, "at": now},
            )
        retention = session.execute(
            text(
                "SELECT id FROM evidence_retention_policies "
                "WHERE owner_id=:owner AND source_policy_id=:policy AND data_class='structured'"
            ),
            {"owner": owner, "policy": policy},
        ).scalar()
        if retention is None:
            retention = uuid4()
            session.execute(
                text(
                    "INSERT INTO evidence_retention_policies "
                    "(id,owner_id,source_policy_id,source_policy_version,data_class,requested_days,"
                    "effective_days,created_at,updated_at) "
                    "VALUES (:id,:owner,:policy,1,'structured',"
                    "30,30,:at,:at)"
                ),
                {"id": retention, "owner": owner, "policy": policy, "at": now},
            )
        job = JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=owner,
            command=JobAcceptanceInput(
                operation_id=uuid5(owner, f"event-test-observation:{source}"),
                kind="content.search",
                scope={},
                observation=JobObservationContext(
                    configuration_ref=f"topic:{topic}",
                    configuration_version=1,
                    source_key=source,
                    source_capability=SourceCapability.SEARCH,
                ),
            ),
        )
        values = [
            {
                "id": uuid4(),
                "owner": owner,
                "content": content,
                "version": version,
                "job": job.id,
                "operation": uuid4(),
                "seen": seen,
                "evidence": uuid4(),
                "policy": policy,
                "retention": retention,
                "expires": now + timedelta(days=30),
            }
            for version, content, seen in versions
        ]
        session.execute(
            text(
                "INSERT INTO content_observations "
                "(id,owner_id,content_id,content_version_id,job_id,source_operation_id,observed_at,received_at)"
                " VALUES (:id,:owner,:content,:version,:job,:operation,:seen,:seen)"
            ),
            values,
        )
        session.execute(
            text(
                "INSERT INTO evidence_resources "
                "(id,owner_id,resource_type,resource_id,source_policy_id,source_policy_version,"
                "retention_policy_id,retention_policy_version,data_class,collected_at,expires_at,created_at)"
                " VALUES (:evidence,:owner,'content_observation',:id,:policy,1,:retention,1,"
                "'structured',"
                ":seen,:expires,:seen)"
            ),
            values,
        )
        session.execute(
            text(
                "INSERT INTO content_visibility_observations "
                "(id,owner_id,content_id,job_id,source_operation_id,observed_at,received_at,status,basis)"
                " VALUES (gen_random_uuid(),:owner,:content,:job,:operation,:seen,:seen,'visible',"
                "'content_returned')"
            ),
            values,
        )
        # Controlled analysis inputs are explicit; legacy NULL annotations without
        # their original analysis Job must remain unavailable.
        from content.analysis_inputs import AnalysisObservationManifest

        for value in values:
            # These controlled original source leaves have no dependency edges.
            # The real scanner still rechecks every fixed manifest and its ALL
            # permissions; fixture construction does not perform 2000 producer reads.
            manifest = AnalysisObservationManifest(
                post_observations={value["version"]: value["id"]},
                comment_observations={},
                input_observation_ids=(value["id"],),
            )
            session.execute(
                text(
                    "UPDATE content_annotations SET input_manifest=CAST(:manifest AS jsonb), "
                    "input_signature=:signature WHERE owner_id=:owner "
                    "AND content_version_id=:version"
                ),
                {
                    "owner": owner,
                    "version": value["version"],
                    "manifest": manifest.model_dump_json(),
                    "signature": manifest.signature,
                },
            )


def _decision(version_ids: tuple[UUID, ...]) -> EventDecision:
    return EventDecision(
        same_event=True,
        member_version_ids=list(version_ids),
        title="Acme 发布新模型",
        summary="两处来源报道了同一次发布。",
    )


def _candidate_for_versions(session, owner, versions):
    candidates = session.scalars(
        select(EventCandidate).where(EventCandidate.owner_id == owner)
    ).all()
    matches = [
        candidate
        for candidate in candidates
        if set(candidate.member_version_ids) == {str(version) for version in versions}
    ]
    assert len(matches) == 1
    return matches[0]


def test_candidate_uses_pg_trgm_window_and_commits_stable_identity(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        assert (
            EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
            == 0
        )
        candidates = session.scalars(
            select(EventCandidate).where(EventCandidate.owner_id == owner)
        ).all()
        assert len(candidates) == 2
        candidate = _candidate_for_versions(session, owner, versions[:2])
        singleton = _candidate_for_versions(session, owner, versions[2:3])
        candidate_id = candidate.id
        assert candidate.job_id is None and singleton.job_id is None
    with sessions() as session, session.begin():
        event_id = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate_id,
            owner_id=owner,
            decision=_decision(versions[:2]),
            ai_call_id=call_id,
            now=now,
        )
        assert event_id is not None
    with sessions() as session, session.begin():
        replay_id = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate_id,
            owner_id=owner,
            decision=_decision(versions[:2]),
            ai_call_id=call_id,
            now=now,
        )
        assert replay_id == event_id
        event = session.get(Event, event_id)
        assert event is not None and event.revision == 1
        assert event.first_seen_basis == "discovered"
        members = session.scalars(select(EventMember).where(EventMember.event_id == event_id)).all()
        assert {member.source_key for member in members} == {"hackernews", "reddit"}
        assert len(members) == 2
        remaining = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(hours=72)
        )
        assert {item.content_version_id for item in remaining} == {versions[2]}
        assert (
            EventCandidateService(session).enqueue_due_in_transaction(
                now=now + timedelta(minutes=30), ai_enabled=False
            )
            == 0
        )
        assert (
            len(
                session.scalars(
                    select(EventCandidate).where(EventCandidate.owner_id == owner)
                ).all()
            )
            == 2
        )


def test_manual_assignment_wins_over_frozen_model_candidate(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        assert candidate is not None
        candidate_id = candidate.id
        source = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(hours=72), version_ids=(versions[0],)
        )[0]
        manual_event_id = uuid4()
        session.add(
            Event(
                id=manual_event_id,
                owner_id=owner,
                topic_id=topic,
                revision=2,
                title="人工事件",
                summary="人工确认",
                first_seen_at=source.first_seen_at,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=manual_event_id,
                content_id=source.content_id,
                content_version_id=source.content_version_id,
                source_key=source.source_key,
                representative_comment_id=None,
                added_revision=2,
                removed_revision=None,
                assignment_origin="manual",
                created_at=now,
            )
        )
    with pytest.raises(EventCandidateConflictError), sessions() as session, session.begin():
        EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate_id,
            owner_id=owner,
            decision=_decision(versions[:2]),
            ai_call_id=call_id,
            now=now,
        )
    with sessions() as session:
        assert (
            session.scalar(select(EventCandidate.status).where(EventCandidate.id == candidate_id))
            == "pending"
        )
        assert (
            session.scalar(select(Event.id).where(Event.owner_id == owner).order_by(Event.id))
            is not None
        )


def test_database_rejects_second_current_assignment(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, topic, versions, _, now = event_context
    with sessions() as session, session.begin():
        source = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(hours=72), version_ids=(versions[0],)
        )[0]
        event_ids = (uuid4(), uuid4())
        for event_id in event_ids:
            session.add(
                Event(
                    id=event_id,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="相同事件",
                    summary="摘要",
                    first_seen_at=source.first_seen_at,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.flush()
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=event_ids[0],
                content_id=source.content_id,
                content_version_id=source.content_version_id,
                source_key=source.source_key,
                representative_comment_id=None,
                added_revision=1,
                removed_revision=None,
                assignment_origin="manual",
                created_at=now,
            )
        )
    with pytest.raises(IntegrityError), sessions() as session, session.begin():
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=event_ids[1],
                content_id=source.content_id,
                content_version_id=source.content_version_id,
                source_key=source.source_key,
                representative_comment_id=None,
                added_revision=2,
                removed_revision=None,
                assignment_origin="model",
                created_at=now,
            )
        )


def test_rejection_and_unknown_member_do_not_create_event(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        assert candidate is not None
        candidate_id = candidate.id
    with (
        pytest.raises(EventCandidateConflictError, match="invalid_member_ids"),
        sessions() as session,
        session.begin(),
    ):
        EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate_id,
            owner_id=owner,
            decision=_decision((versions[0], uuid4())),
            ai_call_id=call_id,
            now=now,
        )
    with sessions() as session, session.begin():
        result = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate_id,
            owner_id=owner,
            decision=EventDecision(
                same_event=False,
                member_version_ids=list(versions[:2]),
                title=None,
                summary=None,
            ),
            ai_call_id=call_id,
            now=now,
        )
        assert result is None
        assert (
            session.scalar(select(EventCandidate.status).where(EventCandidate.id == candidate_id))
            == "rejected"
        )
        assert session.scalar(select(Event.id).where(Event.owner_id == owner)) is None


def test_concurrent_overlapping_candidates_keep_one_current_assignment(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE content_versions SET title='Acme launches new model today' "
                "WHERE id=:version"
            ),
            {"version": versions[2]},
        )
        inputs = load_relevant_event_inputs_in_transaction(session, since=now - timedelta(hours=72))
        by_version = {item.content_version_id: item for item in inputs}
        candidate_ids = (uuid4(), uuid4())
        for candidate_id, pair in zip(
            candidate_ids, ((versions[0], versions[1]), (versions[1], versions[2])), strict=True
        ):
            members = [by_version[version] for version in pair]
            session.add(
                EventCandidate(
                    id=candidate_id,
                    owner_id=owner,
                    topic_id=topic,
                    input_fingerprint=candidate_fingerprint(topic_id=topic, members=members),
                    member_version_ids=sorted(str(version) for version in pair),
                    expected_event_revisions={},
                    window_start=min(item.first_seen_at for item in members),
                    window_end=max(item.first_seen_at for item in members)
                    + timedelta(microseconds=1),
                    prompt_version=EVENT_PROMPT_VERSION,
                    status="pending",
                    ai_call_id=None,
                    job_id=None,
                    event_id=None,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
            )

    barrier = Barrier(2)

    def confirm(candidate_id: UUID, pair: tuple[UUID, UUID]) -> str:
        barrier.wait()
        try:
            with sessions() as session, session.begin():
                EventCandidateService(session).confirm_in_transaction(
                    candidate_id=candidate_id,
                    owner_id=owner,
                    decision=_decision(pair),
                    ai_call_id=call_id,
                    now=now,
                )
            return "confirmed"
        except EventCandidateConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(confirm, candidate_id, pair)
            for candidate_id, pair in zip(
                candidate_ids, ((versions[0], versions[1]), (versions[1], versions[2])), strict=True
            )
        ]
        assert sorted(future.result(timeout=10) for future in futures) == ["confirmed", "conflict"]
    with sessions() as session:
        assert len(session.scalars(select(Event).where(Event.owner_id == owner)).all()) == 1


def test_database_rejects_member_with_wrong_source(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, topic, versions, _, now = event_context
    with sessions() as session, session.begin():
        source = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(hours=72), version_ids=(versions[0],)
        )[0]
        event_id = uuid4()
        session.add(
            Event(
                id=event_id,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="事件",
                summary="摘要",
                first_seen_at=source.first_seen_at,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    with pytest.raises(IntegrityError), sessions() as session, session.begin():
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=event_id,
                content_id=source.content_id,
                content_version_id=source.content_version_id,
                source_key="wrong_source",
                observation_source_key="wrong_source",
                observation_id=source.observation_id,
                representative_comment_id=None,
                added_revision=1,
                removed_revision=None,
                assignment_origin="model",
                created_at=now,
            )
        )


def test_event_worker_records_budget_denial_without_model_request(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        assert (
            EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True) == 2
        )
        candidate = _candidate_for_versions(session, owner, versions[:2])
        assert candidate is not None and candidate.job_id is not None
        candidate_id = candidate.id
        job = session.get(Job, candidate.job_id)
        assert job is not None
        message = SimpleNamespace(
            kind="events.cluster",
            owner_id=owner,
            job_id=job.id,
            operation_id=job.operation_id,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )

    fake_client = SimpleNamespace(close=lambda: None, provider="fake", model="fake")
    monkeypatch.setattr("events.services.create_ai_client", lambda _settings: fake_client)

    def denied(*_args: object, **_kwargs: object) -> None:
        raise AiCallError(AiFailureCode.RATE_LIMITED, "budget denied")

    monkeypatch.setattr("events.services.AiService.complete", denied)
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1:15434/hotkey_test",
        ai_enabled=True,
        events_cluster_enabled=True,
    )
    with pytest.raises(JobExecutionFailure, match="event_ai_rate_limited"):
        EventClusterExecutor(sessions, settings).execute(message)
    with sessions() as session:
        candidate = session.get(EventCandidate, candidate_id)
        assert candidate is not None and candidate.status == "failed"
        assert candidate.error_code == "ai_rate_limited"
        assert session.scalar(select(Event.id).where(Event.owner_id == owner)) is None

    def complete_after_retry(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            call_id=call_id,
            output={
                "same_event": True,
                "member_version_ids": [str(version) for version in versions[:2]],
                "title": "Acme 发布新模型",
                "summary": "两处来源报道同一次发布。",
            },
        )

    monkeypatch.setattr("events.services.AiService.complete", complete_after_retry)
    message.retry_count = 1
    assert EventClusterExecutor(sessions, settings).execute(message).status.value == "succeeded"
    with sessions() as session:
        candidate = session.get(EventCandidate, candidate_id)
        assert candidate is not None and candidate.status == "confirmed"
        assert session.scalar(select(Event.id).where(Event.owner_id == owner)) == candidate.event_id


def _add_event_inputs(session, owner, topic, call_id, now, count=1):
    """Persist controlled source identities; never contact a source or model."""
    rows = [
        {
            "id": uuid4(),
            "version": uuid4(),
            "annotation": uuid4(),
            "owner": owner,
            "topic": topic,
            "call": call_id,
            "seen": now,
            "prompt": ANALYSIS_PROMPT_VERSION,
        }
        for _ in range(count)
    ]
    session.execute(
        text(
            "INSERT INTO content_records "
            "(id, owner_id, source_key, object_type, external_id, created_at) "
            "VALUES (:id, :owner, 'rss_36kr', 'post', CAST(:id AS text), :seen)"
        ),
        rows,
    )
    session.execute(
        text(
            "INSERT INTO content_versions "
            "(id, owner_id, content_id, fingerprint, text_scope, text_origin, title, created_at) "
            "VALUES (:version, :owner, :id, decode(repeat('ab',32),'hex'), 'full', 'source', "
            "'Acme launches new model', :seen)"
        ),
        rows,
    )
    session.execute(
        text(
            "INSERT INTO content_annotations "
            "(id, owner_id, content_id, content_version_id, topic_id, topic_rule_version, "
            "prompt_version, relevant, relevance_reason, sentiment, summary, viewpoints, "
            "ai_call_id, status, result_state, first_valid_at, created_at, updated_at) "
            "VALUES (:annotation, :owner, :id, :version, :topic, 1, :prompt, true, 'Acme', "
            "'neutral', 'Acme', '[]'::jsonb, :call, 'annotated', 'valid', :seen, :seen, :seen)"
        ),
        rows,
    )
    _seed_reading_evidence(session, owner, topic, tuple(row["version"] for row in rows), now)
    return tuple(row["version"] for row in rows)


def _event_message(session, candidate):
    job = session.get(Job, candidate.job_id)
    assert job is not None
    return SimpleNamespace(
        kind="events.cluster",
        owner_id=job.owner_id,
        job_id=job.id,
        operation_id=job.operation_id,
        configuration_ref=job.configuration_ref,
        configuration_version=job.configuration_version,
    )


def _fake_event_model(
    monkeypatch, sessions, call_id, versions, *, same_event=True, before_return=None
):
    from tests.integration.test_ai_calls import _enable_ai_budget

    prompts = []
    with sessions() as session:
        owner = session.scalar(select(AiCall.owner_id).where(AiCall.id == call_id))
    _enable_ai_budget(sessions.kw["bind"], owner)

    class ControlledClient:
        provider, model = "fake", "fake"

        def complete(self, **kwargs):
            prompts.append(kwargs["prompt"])
            if before_return:
                before_return()
            return AiCompletion(
                provider=self.provider,
                model=self.model,
                usage=AiTokenUsage(),
                duration_ms=0,
                output={
                    "same_event": same_event,
                    "member_version_ids": [str(v) for v in versions],
                    "title": "模型新标题" if same_event else None,
                    "summary": "模型新摘要" if same_event else None,
                },
            )

        def close(self):
            pass

    monkeypatch.setattr("events.services.create_ai_client", lambda _: ControlledClient())
    return prompts


def _event_executor(sessions, now):
    return EventClusterExecutor(
        sessions,
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test",
            ai_enabled=True,
            events_cluster_enabled=True,
        ),
        clock=lambda: now,
    )


def test_event_saved_response_resumes_without_another_model_call(event_context, monkeypatch):
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        message = _event_message(session, candidate)
        candidate_id = candidate.id
    prompts = _fake_event_model(monkeypatch, sessions, call_id, versions[:2])
    original_confirm = EventCandidateService.confirm_in_transaction
    monkeypatch.setattr(
        EventCandidateService,
        "confirm_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SystemExit()),
    )
    executor = _event_executor(sessions, now)
    with pytest.raises(SystemExit):
        executor.execute(message)
    monkeypatch.setattr(EventCandidateService, "confirm_in_transaction", original_confirm)
    executor.execute(message)
    assert len(prompts) == 1
    with sessions() as session:
        assert session.get(EventCandidate, candidate_id).status == "confirmed"


def test_event_started_request_is_unknown_and_cannot_repeat(event_context, monkeypatch):
    from events.fact_models import EventGroupingAssessment
    from events.fact_writer import freeze_fact_context_in_transaction

    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        message = _event_message(session, candidate)
        freeze_fact_context_in_transaction(session, candidate=candidate, now=now)
        assessment = session.scalar(
            select(EventGroupingAssessment).where(
                EventGroupingAssessment.candidate_id == candidate.id
            )
        )
        assessment.error_code = "request_started"
        candidate_id = candidate.id
    prompts = _fake_event_model(monkeypatch, sessions, call_id, versions[:2])
    with pytest.raises(JobExecutionFailure, match="event_result_unknown") as failure:
        _event_executor(sessions, now).execute(message)
    assert not failure.value.manual_retry_allowed
    assert not prompts
    with sessions() as session:
        assert session.get(EventCandidate, candidate_id).error_code == "result_unknown"


def test_review_scan_pages_deduplicates_and_drains_next_slot(event_context, monkeypatch):

    from analysis.services import list_relevant_event_annotation_refs_in_transaction

    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        # 2002 valid content identities plus an older annotation for the same content.
        extra = _add_event_inputs(session, owner, topic, call_id, now, count=1999)
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "SELECT topic_id, 2, created_by, match_any, match_all, exclude, created_at "
                "FROM monitor_topic_versions WHERE topic_id=:topic AND version=1"
            ),
            {"topic": topic},
        )
        session.execute(
            text(
                "INSERT INTO content_annotations "
                "(id, owner_id, content_id, content_version_id, topic_id, topic_rule_version, "
                "prompt_version, relevant, relevance_reason, sentiment, summary, viewpoints, "
                "ai_call_id, status, result_state, first_valid_at, created_at, updated_at, "
                "input_manifest, input_signature) "
                "SELECT :id, owner_id, content_id, content_version_id, "
                "topic_id, 2, prompt_version, "
                "true, relevance_reason, sentiment, summary, viewpoints, ai_call_id, status, "
                "result_state, first_valid_at, created_at - interval '1 minute', updated_at, "
                "input_manifest, input_signature "
                "FROM content_annotations WHERE content_version_id=:version"
            ),
            {"id": uuid4(), "version": extra[0]},
        )
        page = list_relevant_event_annotation_refs_in_transaction(
            session, since=now - timedelta(hours=72), limit=2000
        )
        assert len(page.items) == 2000
        assert {ref.content_version_id for ref in page.items[:1999]} == set(extra)
        tail = list_relevant_event_annotation_refs_in_transaction(
            session, since=now - timedelta(hours=72), after=page.next_after, limit=2000
        )
        assert len(tail.items) == 2
        assert all(ref.topic_rule_version == 1 for ref in (*page.items, *tail.items))
        assert len({ref.content_id for ref in (*page.items, *tail.items)}) == 2002
        logs = []
        with monkeypatch.context() as patches:
            patches.setattr(
                "events.services.structlog.get_logger",
                lambda _name: SimpleNamespace(
                    info=lambda name, **fields: logs.append({"event": name, **fields})
                ),
            )
            inputs = load_relevant_event_inputs_in_transaction(
                session, since=now - timedelta(hours=72)
            )
        assert len(inputs) == 2000
        assert any(log["event"] == "event_scan_truncated" for log in logs)
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidates = session.scalars(
            select(EventCandidate).where(EventCandidate.owner_id == owner)
        ).all()
        confirmed_versions = {
            UUID(version) for candidate in candidates for version in candidate.member_version_ids
        }
        for candidate in candidates:
            EventCandidateService(session).confirm_in_transaction(
                candidate_id=candidate.id,
                owner_id=owner,
                decision=_decision(tuple(UUID(v) for v in candidate.member_version_ids)),
                ai_call_id=call_id,
                now=now,
            )
    with sessions() as session, session.begin():
        remaining = load_relevant_event_inputs_in_transaction(
            session, since=now - timedelta(hours=72)
        )
        # Descending scans retain the latest inputs; unassigned older rows remain discoverable.
        assert {item.content_version_id for item in remaining} == (
            set((*versions[:3], *extra)) - confirmed_versions
        )
        EventCandidateService(session).enqueue_due_in_transaction(
            now=now + timedelta(minutes=30), ai_enabled=False
        )
        pending = session.scalars(
            select(EventCandidate).where(
                EventCandidate.owner_id == owner, EventCandidate.status == "pending"
            )
        ).all()
        assert pending
        assert {
            str(item.content_version_id)
            for item in remaining
            if item.content_version_id != versions[2]
        } <= {v for candidate in pending for v in candidate.member_version_ids}


@pytest.mark.parametrize(
    "outcome", ["confirm", "reject", "revision", "removed", "assigned", "inactive"]
)
def test_review_append_to_existing_event(event_context, monkeypatch, outcome):
    from sqlalchemy import event as sqlalchemy_event

    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        # Rebuild the controlled source fixture coherently before it enters event ownership.
        # Record identity, original collection Job and admission policy must agree.
        session.execute(
            text(
                "UPDATE content_records SET source_key='google_news' "
                "WHERE owner_id=:owner AND source_key='reddit'"
            ),
            {"owner": owner},
        )
        session.execute(
            text(
                "UPDATE jobs SET source_key='google_news' "
                "WHERE owner_id=:owner AND source_key='reddit'"
            ),
            {"owner": owner},
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET source_key='google_news' "
                "WHERE owner_id=:owner AND source_key='reddit'"
            ),
            {"owner": owner},
        )
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        initial = _candidate_for_versions(session, owner, versions[:2])
        event_id = EventCandidateService(session).confirm_in_transaction(
            candidate_id=initial.id,
            owner_id=owner,
            decision=_decision(versions[:2]),
            ai_call_id=call_id,
            now=now,
        )
        added = _add_event_inputs(session, owner, topic, call_id, now - timedelta(hours=3))
    with sessions() as session, session.begin():
        statements = []

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            if "similarity(" in statement.lower():
                statements.append(statement)

        connection = session.connection()
        sqlalchemy_event.listen(connection, "before_cursor_execute", capture)
        try:
            EventCandidateService(session).enqueue_due_in_transaction(
                now=now + timedelta(minutes=30), ai_enabled=True
            )
        finally:
            sqlalchemy_event.remove(connection, "before_cursor_execute", capture)
        assert len(statements) == 1 and "unnest" in statements[0].lower()
        candidate = session.scalar(
            select(EventCandidate).where(
                EventCandidate.owner_id == owner,
                EventCandidate.status == "pending",
                EventCandidate.expected_event_revisions.contains({str(event_id): 1}),
            )
        )
        assert candidate is not None
        assert candidate.expected_event_revisions == {str(event_id): 1}
        frozen = tuple(UUID(v) for v in candidate.member_version_ids)
        assert set(added) < set(frozen) <= set((*versions[:2], *added))
        assert versions[1] in frozen  # Most recent context first.
        candidate_id, message = candidate.id, _event_message(session, candidate)

    def manual_change():
        with sessions() as session, session.begin():
            target = session.get(Event, event_id)
            if outcome == "revision":
                target.revision = 7
            elif outcome == "removed":
                member = session.scalar(
                    select(EventMember).where(
                        EventMember.event_id == event_id,
                        EventMember.content_version_id.in_(set(frozen) - set(added)),
                    )
                )
                member.removed_revision = 2
            elif outcome == "inactive":
                other = Event(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="人工目标",
                    summary="人工目标",
                    first_seen_at=now,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(other)
                session.flush()
                target.status, target.merged_into_id = "merged", other.id
            elif outcome == "assigned":
                source = load_relevant_event_inputs_in_transaction(
                    session, since=now - timedelta(hours=72), version_ids=added
                )[0]
                session.add(
                    EventMember(
                        id=uuid4(),
                        owner_id=owner,
                        topic_id=topic,
                        event_id=event_id,
                        content_id=source.content_id,
                        content_version_id=source.content_version_id,
                        source_key=source.source_key,
                        added_revision=2,
                        removed_revision=None,
                        assignment_origin="manual",
                        representative_comment_id=None,
                        created_at=now,
                    )
                )

    prompts = _fake_event_model(
        monkeypatch,
        sessions,
        call_id,
        frozen,
        same_event=outcome != "reject",
        before_return=manual_change,
    )
    executor = _event_executor(sessions, now + timedelta(minutes=31))
    if outcome in {"revision", "removed", "assigned", "inactive"}:
        with pytest.raises(JobExecutionFailure):
            executor.execute(message)
    else:
        executor.execute(message)
        executor.execute(message)
    assert len(prompts) == 1
    assert "上下文" in prompts[0]
    with sessions() as session:
        candidate = session.get(EventCandidate, candidate_id)
        target = session.get(Event, event_id)
        assert target.title == "Acme 发布新模型"
        assert target.summary == "两处来源报道了同一次发布。"
        members = session.scalars(select(EventMember).where(EventMember.event_id == event_id)).all()
        if outcome == "confirm":
            assert candidate.event_id == event_id and candidate.status == "confirmed"
            assert target.revision == 2 and len(members) == 3
            assert target.first_seen_at == now - timedelta(hours=3)
            assert target.first_seen_basis == "discovered"
            assert target.updated_at == now + timedelta(minutes=31)
            added_member = next(m for m in members if m.source_key == "rss_36kr")
            assert added_member.added_revision == 2 and added_member.assignment_origin == "model"
        elif outcome == "reject":
            assert candidate.status == "rejected" and target.revision == 1
            assert len(members) == 2 and target.updated_at == now
        else:
            assert (
                candidate.status == "failed" and candidate.error_code == "manual_revision_conflict"
            )
            assert target.revision == (7 if outcome == "revision" else 1)
        assert len(session.scalars(select(Event).where(Event.owner_id == owner)).all()) == (
            2 if outcome == "inactive" else 1
        )


def test_review_input_changed_is_persisted_before_model(event_context, monkeypatch):
    sessions, owner, _, versions, _, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        candidate_id, message = candidate.id, _event_message(session, candidate)
        session.execute(
            text(
                "UPDATE content_annotations SET relevant=false, sentiment=NULL "
                "WHERE content_version_id=:id"
            ),
            {"id": versions[0]},
        )
    monkeypatch.setattr(
        "events.services.create_ai_client", lambda _settings: pytest.fail("model called")
    )
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        _event_executor(sessions, now).execute(message)
    with sessions() as session:
        candidate = session.get(EventCandidate, candidate_id)
        assert candidate.status == "failed" and candidate.error_code == "input_changed"
        assert candidate.ai_call_id is None
    with pytest.raises(JobExecutionFailure, match="event_candidate_not_pending"):
        _event_executor(sessions, now).execute(message)


def test_review_similarity_round_trips_are_constant(event_context):
    from sqlalchemy import event as sqlalchemy_event

    from events.clustering import cluster_candidates

    sessions, owner, topic, _, call_id, now = event_context
    with sessions() as session, session.begin():
        _add_event_inputs(session, owner, topic, call_id, now, count=25)
        inputs = load_relevant_event_inputs_in_transaction(session, since=now - timedelta(hours=72))
        statements = []

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            if "similarity(" in statement.lower():
                statements.append(statement)

        connection = session.connection()
        sqlalchemy_event.listen(connection, "before_cursor_execute", capture)
        try:
            cluster_candidates(session, inputs)
            assert len(statements) == 1
            assert "unnest" in statements[0].lower()
        finally:
            sqlalchemy_event.remove(connection, "before_cursor_execute", capture)


def test_review_scan_is_not_limited_to_target_minute(event_context):
    sessions, owner, _, _, _, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(
            now=now + timedelta(minutes=1, seconds=40), ai_enabled=False
        )
        assert session.scalar(select(EventCandidate.id).where(EventCandidate.owner_id == owner))


def test_rework_new_pair_is_not_starved_by_old_singletons(event_context):
    import hashlib

    sessions, owner, topic, _, call_id, now = event_context
    with sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE content_annotations SET relevant=false, sentiment=NULL "
                "WHERE owner_id=:owner"
            ),
            {"owner": owner},
        )
        older = _add_event_inputs(
            session, owner, topic, call_id, now - timedelta(hours=2), count=2001
        )
        session.execute(
            text("UPDATE content_versions SET title=:title WHERE id=:id"),
            [
                {"id": version, "title": "Acme " + hashlib.sha256(str(index).encode()).hexdigest()}
                for index, version in enumerate(older)
            ],
        )
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        singletons = session.scalars(
            select(EventCandidate).where(EventCandidate.owner_id == owner)
        ).all()
        assert len(singletons) == 100
        assert all(len(candidate.member_version_ids) == 1 for candidate in singletons)
    later = now + timedelta(minutes=30)
    with sessions() as session, session.begin():
        pair = _add_event_inputs(session, owner, topic, call_id, later, count=2)
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=later, ai_enabled=False)
        candidates = session.scalars(
            select(EventCandidate).where(EventCandidate.owner_id == owner)
        ).all()
        assert len(candidates) <= 201
        candidate = _candidate_for_versions(session, owner, pair)
        assert candidate.expected_event_revisions == {}


@pytest.mark.parametrize("recent_member", ["current", "expired", "removed"])
def test_rework_old_event_requires_recent_current_member(event_context, monkeypatch, recent_member):
    sessions, owner, topic, versions, call_id, now = event_context
    old_time = now - timedelta(hours=80)
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        initial = _candidate_for_versions(session, owner, versions[:2])
        event_id = EventCandidateService(session).confirm_in_transaction(
            candidate_id=initial.id,
            owner_id=owner,
            decision=_decision(versions[:2]),
            ai_call_id=call_id,
            now=now,
        )
        target = session.get(Event, event_id)
        target.first_seen_at = old_time
        session.execute(
            text(
                "UPDATE content_observations SET observed_at=:old,received_at=:old "
                "WHERE content_version_id=:version"
            ),
            {"old": old_time, "version": versions[0]},
        )
        if recent_member == "expired":
            session.execute(
                text(
                    "UPDATE content_observations SET observed_at=:old,received_at=:old "
                    "WHERE content_version_id=:version"
                ),
                {"old": old_time, "version": versions[1]},
            )
        elif recent_member == "removed":
            target.revision = 2
            member = session.scalar(
                select(EventMember).where(
                    EventMember.event_id == event_id, EventMember.content_version_id == versions[1]
                )
            )
            member.removed_revision = 2
            # Exclude the removed content from new candidate inputs while retaining its evidence.
            session.execute(
                text(
                    "UPDATE content_annotations SET relevant=false, sentiment=NULL "
                    "WHERE content_version_id=:version"
                ),
                {"version": versions[1]},
            )
        added = _add_event_inputs(session, owner, topic, call_id, now, count=2)
    later = now + timedelta(minutes=30)
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=later, ai_enabled=True)
        if recent_member == "current":
            candidate = session.scalar(
                select(EventCandidate).where(
                    EventCandidate.owner_id == owner,
                    EventCandidate.status == "pending",
                    EventCandidate.expected_event_revisions.contains({str(event_id): 1}),
                )
            )
        else:
            candidate = _candidate_for_versions(session, owner, added)
        assert candidate is not None
        frozen = tuple(UUID(value) for value in candidate.member_version_ids)
        if recent_member == "current":
            assert candidate.expected_event_revisions == {str(event_id): 1}
            assert set(frozen) == {versions[1], *added}
        else:
            assert candidate.expected_event_revisions == {}
            assert set(frozen) == set(added)
        candidate_id, message = candidate.id, _event_message(session, candidate)
    _fake_event_model(monkeypatch, sessions, call_id, frozen)
    _event_executor(sessions, later).execute(message)
    with sessions() as session:
        candidate = session.get(EventCandidate, candidate_id)
        target = session.get(Event, event_id)
        assert candidate.status == "confirmed"
        assert target.first_seen_at == old_time
        assert target.title == "Acme 发布新模型"
        event_count = len(session.scalars(select(Event).where(Event.owner_id == owner)).all())
        if recent_member == "current":
            assert candidate.event_id == event_id and target.revision == 2
            assert event_count == 1
            assert (
                len(
                    session.scalars(
                        select(EventMember).where(EventMember.event_id == event_id)
                    ).all()
                )
                == 4
            )
        else:
            assert candidate.event_id != event_id and event_count == 2
            assert target.revision == (2 if recent_member == "removed" else 1)


def test_queued_legacy_annotation_candidate_rechecks_source_permission_before_pay(
    event_context, monkeypatch
):
    sessions, owner, _, versions, _, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        message = _event_message(session, candidate)
        identity = candidate.id
        session.execute(
            text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
            {"owner": owner},
        )
    monkeypatch.setattr(
        "events.services.create_ai_client", lambda _: pytest.fail("source permission withdrawn")
    )
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        _event_executor(sessions, now).execute(message)
    with sessions() as session:
        candidate = session.get(EventCandidate, identity)
        assert candidate.status == "failed" and candidate.error_code == "input_changed"
        assert candidate.ai_call_id is None
        assert session.scalar(select(Event)) is None


def test_cluster_revocation_after_prepare_denies_ai_and_budget_reservation(
    event_context, monkeypatch
):
    from events import services
    from jobs.execution import JobExecutionService

    sessions, owner, _, versions, call_id, now = event_context
    with sessions.begin() as session:
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True)
        candidate = _candidate_for_versions(session, owner, versions[:2])
        message = _event_message(session, candidate)
        session.execute(
            text("UPDATE jobs SET created_at=:at,updated_at=:at WHERE id=:job"),
            {"at": now, "job": message.job_id},
        )
    prompts = _fake_event_model(monkeypatch, sessions, call_id, versions[:2])
    original_factory = services.create_ai_client
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: now).acquire(
            job_id=message.job_id, worker_id="controlled-cluster-admission"
        )
        calls = session.execute(text("SELECT count(*) FROM ai_calls")).scalar()
        reservations = session.execute(
            text("SELECT count(*) FROM resource_budget_reservations")
        ).scalar()

    def revoke_after_prepare(settings):
        with sessions.begin() as session:
            session.execute(text("UPDATE source_access_policies SET enabled=false"))
        return original_factory(settings)

    monkeypatch.setattr(services, "create_ai_client", revoke_after_prepare)
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        _event_executor(sessions, now).execute(message, lease)
    assert prompts == []
    with sessions() as session:
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar() == calls
        assert (
            session.execute(text("SELECT count(*) FROM resource_budget_reservations")).scalar()
            == reservations
        )
