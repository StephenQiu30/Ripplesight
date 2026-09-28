from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError, AiFailureCode
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from core.config import Settings
from events.clustering import EVENT_PROMPT_VERSION
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
                "INSERT INTO identity_users "
                "(id, username, password_hash, created_at, updated_at) "
                "VALUES (:id, :name, 'test-only-hash', :now, :now)"
            ),
            {"id": owner_id, "name": f"event-{owner_id.hex}", "now": now},
        )
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
    try:
        yield sessions, owner_id, topic_id, version_ids, call_id, now
    finally:
        with engine.begin() as connection:
            for table in (
                "event_candidates",
                "event_members",
                "events",
                "content_annotations",
                "content_versions",
                "content_records",
                "ai_calls",
                "jobs",
                "monitor_topic_versions",
                "monitor_topics",
                "identity_users",
            ):
                key = (
                    "created_by"
                    if table == "monitor_topic_versions"
                    else ("id" if table == "identity_users" else "owner_id")
                )
                connection.execute(
                    text(f"DELETE FROM {table} WHERE {key}=:owner"), {"owner": owner_id}
                )
        engine.dispose()


def _decision(version_ids: tuple[UUID, ...]) -> EventDecision:
    return EventDecision(
        same_event=True,
        member_version_ids=list(version_ids),
        title="Acme 发布新模型",
        summary="两处来源报道了同一次发布。",
    )


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
        assert len(candidates) == 1
        candidate_id = candidates[0].id
        assert set(candidates[0].member_version_ids) == {str(versions[0]), str(versions[1])}
        assert candidates[0].job_id is None
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
            == 1
        )


def test_manual_assignment_wins_over_frozen_model_candidate(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = session.scalar(select(EventCandidate).where(EventCandidate.owner_id == owner))
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
        candidate = session.scalar(select(EventCandidate).where(EventCandidate.owner_id == owner))
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
                    input_fingerprint=candidate_id.bytes * 2,
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
            EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True) == 1
        )
        candidate = session.scalar(select(EventCandidate).where(EventCandidate.owner_id == owner))
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
