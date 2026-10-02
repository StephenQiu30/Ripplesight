# ruff: noqa: F811
from sqlalchemy import select
from tests.integration.test_event_clustering import (
    _candidate_for_versions,
    _decision,
    event_context,  # noqa: F401
)

from events.fact_models import EventFactMember
from events.heat import EventHeatService
from events.heat_schemas import AttentionSourceInput
from events.models import EventCandidate
from events.services import EventCandidateService


def _configure(sessions, owner, source_key, mode):
    with sessions() as session:
        return EventHeatService(session).upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key=source_key,
                selector_kind="source",
                selector_ref=source_key,
                name=source_key,
                mode=mode,
                scheduled=False,
            ),
        )


def test_signal_only_cannot_create_candidates_or_model_jobs(event_context):
    sessions, owner, _, _, _, now = event_context
    for source in ("hackernews", "reddit", "mastodon"):
        _configure(sessions, owner, source, "signal")
    with sessions() as session, session.begin():
        assert (
            EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=True) == 0
        )
        assert session.scalar(select(EventCandidate)) is None


def test_similar_signal_title_does_not_create_or_join_an_editorial_fact(event_context):
    sessions, owner, _, versions, call, now = event_context
    _configure(sessions, owner, "hackernews", "editorial")
    _configure(sessions, owner, "reddit", "signal")
    _configure(sessions, owner, "mastodon", "signal")
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = _candidate_for_versions(session, owner, versions[:1])
        event = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate.id,
            owner_id=owner,
            decision=_decision(versions[:1]),
            ai_call_id=call,
            now=now,
        )
        rows = session.scalars(
            select(EventFactMember).where(EventFactMember.event_id == event)
        ).all()
        roles = {row.content_version_id: row.role for row in rows}
        assert roles == {versions[0]: "primary"}
