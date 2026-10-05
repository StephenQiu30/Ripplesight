from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.services import load_event_content_inputs_in_transaction
from events.fact_models import (
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingAssessment,
    EventGroupingOverride,
)
from events.models import Event, EventCandidate, EventMember
from events.schemas import EventDecision, EventFactDecision


class FactGroupingConflictError(Exception):
    pass


def load_fact_context_in_transaction(
    session: Session, *, candidate: EventCandidate
) -> dict[str, object]:
    if not session.in_transaction():
        raise RuntimeError("fact assessment context requires caller transaction")
    event_ids = [UUID(value) for value in candidate.expected_event_revisions]
    assignments = list(
        session.scalars(
            select(EventFactAssignment)
            .where(
                EventFactAssignment.owner_id == candidate.owner_id,
                EventFactAssignment.event_id.in_(event_ids),
                EventFactAssignment.removed_revision.is_(None),
            )
            .order_by(EventFactAssignment.fact_id, EventFactAssignment.event_id)
        )
    )
    frozen_facts: list[dict[str, object]] = []
    for assignment in assignments:
        fact = session.get(EventFact, assignment.fact_id)
        if fact is None:
            raise RuntimeError("scoped fact foreign key missing")
        frozen_facts.append(
            {
                "fact_id": str(assignment.fact_id),
                "event_id": str(assignment.event_id),
                "revision": fact.revision,
                "relation": assignment.relation,
                "root_fact_id": str(assignment.root_fact_id) if assignment.root_fact_id else None,
            }
        )
    snapshot: dict[str, object] = {
        "member_version_ids": candidate.member_version_ids,
        "expected_event_revisions": candidate.expected_event_revisions,
        "facts": frozen_facts,
        "overrides": [
            {
                "content_id": str(row.content_id),
                "revision": row.revision,
                "operation_id": str(row.operation_id),
                "mode": row.mode,
            }
            for row in session.scalars(
                select(EventGroupingOverride)
                .where(
                    EventGroupingOverride.owner_id == candidate.owner_id,
                    EventGroupingOverride.topic_id == candidate.topic_id,
                    EventGroupingOverride.content_id.in_(
                        [
                            item.content_id
                            for item in load_event_content_inputs_in_transaction(
                                session,
                                owner_id=candidate.owner_id,
                                version_ids=tuple(
                                    UUID(value) for value in candidate.member_version_ids
                                ),
                                since=candidate.window_start - timedelta(microseconds=1),
                            ).values()
                        ]
                    ),
                )
                .order_by(EventGroupingOverride.content_id)
            )
        ],
    }
    return snapshot


def freeze_fact_context_in_transaction(
    session: Session, *, candidate: EventCandidate, now: datetime
) -> dict[str, object]:
    snapshot = load_fact_context_in_transaction(session, candidate=candidate)
    assessment = session.scalar(
        select(EventGroupingAssessment).where(
            EventGroupingAssessment.owner_id == candidate.owner_id,
            EventGroupingAssessment.candidate_id == candidate.id,
            EventGroupingAssessment.input_fingerprint == candidate.input_fingerprint,
        )
    )
    if assessment is None:
        session.add(
            EventGroupingAssessment(
                id=uuid4(),
                owner_id=candidate.owner_id,
                topic_id=candidate.topic_id,
                candidate_id=candidate.id,
                input_fingerprint=candidate.input_fingerprint,
                input_snapshot=snapshot,
                decisions=[],
                status="pending",
                confidence=None,
                ai_call_id=None,
                error_code=None,
                prompt_version=candidate.prompt_version,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        assessment.input_snapshot, assessment.status = snapshot, "pending"
        assessment.decisions, assessment.error_code = [], None
        assessment.updated_at = now
    session.flush()
    return snapshot


def record_candidate_facts_in_transaction(
    session: Session,
    *,
    candidate: EventCandidate,
    event: Event,
    decision: EventDecision,
    ai_call_id: UUID,
    now: datetime,
    input_times: dict[UUID, tuple[datetime, str]],
    signal_version_ids: frozenset[UUID] = frozenset(),
    input_frames: dict[UUID, dict[str, object] | None] | None = None,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("fact writer requires caller transaction")
    assessment = session.scalar(
        select(EventGroupingAssessment).where(
            EventGroupingAssessment.owner_id == candidate.owner_id,
            EventGroupingAssessment.candidate_id == candidate.id,
            EventGroupingAssessment.input_fingerprint == candidate.input_fingerprint,
        )
    )
    if assessment is None:
        freeze_fact_context_in_transaction(session, candidate=candidate, now=now)
        assessment = session.scalar(
            select(EventGroupingAssessment).where(
                EventGroupingAssessment.owner_id == candidate.owner_id,
                EventGroupingAssessment.candidate_id == candidate.id,
            )
        )
    assert assessment is not None
    for raw in cast(list[dict[str, object]], assessment.input_snapshot.get("overrides", [])):
        override = session.get(
            EventGroupingOverride,
            (candidate.owner_id, candidate.topic_id, UUID(str(raw["content_id"]))),
        )
        if override is None or override.revision != raw["revision"]:
            raise FactGroupingConflictError("manual_revision_conflict")
    for raw in cast(list[dict[str, object]], assessment.input_snapshot.get("facts", [])):
        fact = session.get(EventFact, UUID(str(raw["fact_id"])))
        if fact is None or fact.revision != raw["revision"] or fact.status == "merged":
            raise FactGroupingConflictError("fact_revision_conflict")
    members = list(
        session.scalars(
            select(EventMember).where(
                EventMember.owner_id == event.owner_id,
                EventMember.event_id == event.id,
                EventMember.removed_revision.is_(None),
                EventMember.content_version_id.in_(decision.member_version_ids),
            )
        )
    )
    linked = {
        row.event_member_id: row
        for row in session.scalars(
            select(EventFactMember).where(
                EventFactMember.owner_id == event.owner_id,
                EventFactMember.event_id == event.id,
                EventFactMember.removed_revision.is_(None),
            )
        )
    }
    assignments = list(
        session.scalars(
            select(EventFactAssignment).where(
                EventFactAssignment.owner_id == event.owner_id,
                EventFactAssignment.event_id == event.id,
                EventFactAssignment.removed_revision.is_(None),
            )
        )
    )
    root = next((row for row in assignments if row.relation in {"root", "roundup"}), None)
    groups = list(decision.facts)
    if not groups:
        groups = [
            EventFactDecision(
                member_version_ids=decision.member_version_ids,
                title=decision.title or event.title,
                summary=decision.summary or event.summary,
                relation="same_occurrence" if root else "root",
                existing_fact_id=root.fact_id if root else None,
            )
        ]
    created_by_version: dict[UUID, UUID] = {}
    new_fact_groups: list[tuple[EventFact, EventFactDecision]] = []
    for group in groups:
        if group.existing_fact_id is not None:
            existing = next(
                (row for row in assignments if row.fact_id == group.existing_fact_id), None
            )
            if existing is None:
                raise FactGroupingConflictError("fact_target_changed")
            target_fact = session.get(EventFact, existing.fact_id)
            assert target_fact is not None
        else:
            if set(group.member_version_ids) <= signal_version_ids:
                raise FactGroupingConflictError("signal_only_fact")
            if any(
                member.id in linked and member.content_version_id in group.member_version_ids
                for member in members
            ):
                raise FactGroupingConflictError("context_fact_changed")
            first_time, first_basis = min(
                (input_times[identity] for identity in group.member_version_ids),
                key=lambda item: item[0],
            )
            target_fact = EventFact(
                id=uuid4(),
                owner_id=event.owner_id,
                topic_id=event.topic_id,
                revision=1,
                title=group.title.strip(),
                summary=group.summary.strip(),
                status="unreviewed" if group.relation == "unreviewed" else "confirmed",
                merged_into_id=None,
                frame=next(
                    (
                        (input_frames or {}).get(identity)
                        for identity in group.member_version_ids
                        if (input_frames or {}).get(identity) is not None
                    ),
                    None,
                ),
                first_seen_at=first_time,
                first_seen_basis=first_basis,
                created_at=now,
                updated_at=now,
            )
            session.add(target_fact)
            new_fact_groups.append((target_fact, group))
            created_by_version.update(dict.fromkeys(group.member_version_ids, target_fact.id))
        new_members = [
            member
            for member in members
            if member.content_version_id in group.member_version_ids and member.id not in linked
        ]
        context = [
            member
            for member in members
            if member.content_version_id in group.member_version_ids and member.id in linked
        ]
        if any(linked[member.id].fact_id != target_fact.id for member in context):
            raise FactGroupingConflictError("context_fact_changed")
        if group.existing_fact_id is not None and new_members:
            target_fact.revision += 1
            target_fact.updated_at = now
        session.flush()
        has_primary = (
            session.scalar(
                select(EventFactMember.id).where(
                    EventFactMember.owner_id == event.owner_id,
                    EventFactMember.fact_id == target_fact.id,
                    EventFactMember.role == "primary",
                    EventFactMember.removed_revision.is_(None),
                )
            )
            is not None
        )
        for index, member in enumerate(
            sorted(
                new_members,
                key=lambda row: (
                    row.content_version_id in signal_version_ids,
                    row.created_at,
                    row.id.hex,
                ),
            )
        ):
            session.add(
                EventFactMember(
                    id=uuid4(),
                    owner_id=event.owner_id,
                    topic_id=event.topic_id,
                    fact_id=target_fact.id,
                    event_id=event.id,
                    event_member_id=member.id,
                    content_id=member.content_id,
                    content_version_id=member.content_version_id,
                    role="mention"
                    if member.content_version_id in signal_version_ids
                    else "primary"
                    if not has_primary and index == 0
                    else "report",
                    assignment_origin="model",
                    added_revision=target_fact.revision,
                    removed_revision=None,
                    created_at=now,
                )
            )
    new_roots = [
        (fact, group) for fact, group in new_fact_groups if group.relation in {"root", "roundup"}
    ]
    if len(new_roots) + (1 if root else 0) > 1:
        raise FactGroupingConflictError("multiple_story_roots")
    root_id = new_roots[0][0].id if new_roots else root.fact_id if root else None
    for fact, group in new_fact_groups:
        direct_root = group.root_fact_id or (
            created_by_version.get(group.root_member_version_id)
            if group.root_member_version_id is not None
            else None
        )
        if group.relation in {"development", "background"} and (
            direct_root is None or direct_root != root_id or direct_root == fact.id
        ):
            raise FactGroupingConflictError("development_root_changed")
        if group.relation == "roundup" and (len(new_fact_groups) != 1 or root is not None):
            raise FactGroupingConflictError("roundup_mixed_with_story")
        session.add(
            EventFactAssignment(
                id=uuid4(),
                owner_id=event.owner_id,
                topic_id=event.topic_id,
                event_id=event.id,
                fact_id=fact.id,
                root_fact_id=direct_root,
                relation=group.relation,
                added_revision=event.revision,
                removed_revision=None,
                created_at=now,
            )
        )
    assessment.decisions = [group.model_dump(mode="json") for group in decision.facts]
    assessment.status = "valid" if decision.facts else "degraded"
    assessment.error_code = None if decision.facts else "legacy_fact_semantics"
    assessment.ai_call_id, assessment.updated_at = ai_call_id, now
    session.flush()
