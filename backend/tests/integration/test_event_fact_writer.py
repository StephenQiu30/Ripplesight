# ruff: noqa: F811
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_event_clustering import event_context  # noqa: F401

from events.fact_models import (
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingAssessment,
)
from events.models import EventCandidate
from events.schemas import EventDecision, EventFactDecision
from events.services import EventCandidateService


def test_original_cluster_writer_persists_root_and_direct_development(
    event_context: tuple[sessionmaker[Session], UUID, UUID, tuple[UUID, ...], UUID, datetime],
) -> None:
    sessions, owner, _, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        EventCandidateService(session).enqueue_due_in_transaction(now=now, ai_enabled=False)
        candidate = session.scalar(select(EventCandidate))
        assert candidate is not None
        event_id = EventCandidateService(session).confirm_in_transaction(
            candidate_id=candidate.id,
            owner_id=owner,
            ai_call_id=call_id,
            now=now,
            decision=EventDecision(
                same_event=True,
                member_version_ids=list(versions[:2]),
                title="发布及评测",
                summary="发布之后的直接评测进展",
                facts=[
                    EventFactDecision(
                        member_version_ids=[versions[0]],
                        title="发布",
                        summary="发布模型",
                        relation="root",
                    ),
                    EventFactDecision(
                        member_version_ids=[versions[1]],
                        title="评测",
                        summary="发布之后的评测",
                        relation="development",
                        root_member_version_id=versions[0],
                    ),
                ],
            ),
        )
    with sessions() as session:
        assignments = list(
            session.scalars(
                select(EventFactAssignment).where(EventFactAssignment.event_id == event_id)
            )
        )
        assert len(assignments) == 2
        root = next(row for row in assignments if row.relation == "root")
        development = next(row for row in assignments if row.relation == "development")
        assert development.root_fact_id == root.fact_id
        assert len(session.scalars(select(EventFact)).all()) == 2
        assert len(session.scalars(select(EventFactMember)).all()) == 2
        assessment = session.scalar(select(EventGroupingAssessment))
        assert assessment is not None and assessment.status == "valid"
        assert assessment.ai_call_id == call_id
