"""Project one frozen automatic revision delta through current evidence permissions."""

import json
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from events.fact_models import EventFactAssignment, EventFactMember, EventGroupingAssessment
from events.fact_schemas import EventFactView, EventRevisionDeltaReceipt, EventRevisionDeltaView
from events.models import Event, EventCandidate, EventMember
from events.schemas import EventFactDecision


def _consistent_decisions(
    assessment: EventGroupingAssessment,
    candidate: EventCandidate,
    receipt: EventRevisionDeltaReceipt,
    assignments: list[EventFactAssignment],
) -> bool:
    """Check recorded classifications against frozen judgments and actual identities."""
    if assessment.status == "degraded":
        return not assessment.decisions and all(
            change.kind == "unknown" and change.reason is None
            for change in receipt.material_changes
        )
    try:
        groups = [
            EventFactDecision.model_validate_json(json.dumps(value))
            for value in assessment.decisions
        ]
        frozen = assessment.input_snapshot.get("facts")
        if not isinstance(frozen, list):
            return False
        baseline: dict[UUID, object] = {}
        for value in frozen:
            if not isinstance(value, dict) or value.get("event_id") != str(receipt.event_id):
                return False
            identity = value.get("fact_id")
            relation = value.get("relation")
            if not isinstance(identity, str) or not isinstance(relation, str):
                return False
            baseline[UUID(identity)] = relation
    except (ValidationError, ValueError, KeyError, TypeError):
        return False
    versions = [version for group in groups for version in group.member_version_ids]
    if (
        len(set(versions)) != len(versions)
        or {str(version) for version in versions} != set(candidate.member_version_ids)
        or (receipt.baseline_event_revision == 0 and baseline)
    ):
        return False
    assigned = {assignment.fact_id: assignment for assignment in assignments}
    by_version = {version: group for group in groups for version in group.member_version_ids}
    for change in receipt.material_changes:
        group = by_version.get(change.content_version_id)
        assignment = assigned.get(change.fact_id)
        if group is None or assignment is None or change.unavailable:
            return False
        if group.existing_fact_id is not None and group.existing_fact_id != change.fact_id:
            return False
        if change.kind == "new_fact":
            if (
                group.existing_fact_id is not None
                or group.relation not in {"root", "development"}
                or change.fact_id in baseline
                or assignment.added_revision != receipt.event_revision
                or assignment.relation != group.relation
                or change.reason is not None
            ):
                return False
        elif change.kind in {"supplement", "repeat"} or change.reason is not None:
            judgment = next(
                (
                    item
                    for item in group.evidence_changes
                    if item.member_version_id == change.content_version_id
                ),
                None,
            )
            if (
                group.existing_fact_id != change.fact_id
                or baseline.get(change.fact_id) not in {"root", "development"}
                or assignment.added_revision > receipt.baseline_event_revision
                or judgment is None
                or judgment.kind != change.kind
                or judgment.reason.strip() != change.reason
            ):
                return False
    return True


def load_revision_delta_in_transaction(
    session: Session,
    *,
    event: Event,
    revision: int,
    facts: list[EventFactView],
    members: list[EventMember],
    assignments: list[EventFactAssignment],
) -> tuple[
    Literal["available", "not_recorded", "invalid", "ambiguous"], EventRevisionDeltaView | None
]:
    """Read a verifiable receipt without reconstructing absent historical judgments.

    The caller provides its permission-gated fixed-revision facts and members in
    the same read-only transaction. Any unreadable or changed association loses
    its derived conclusion, including when reading a historical event revision.
    """
    rows = list(
        session.execute(
            select(EventGroupingAssessment, EventCandidate)
            .join(
                EventCandidate,
                (EventCandidate.owner_id == EventGroupingAssessment.owner_id)
                & (EventCandidate.id == EventGroupingAssessment.candidate_id),
            )
            .where(
                EventGroupingAssessment.owner_id == event.owner_id,
                EventGroupingAssessment.topic_id == event.topic_id,
                EventCandidate.event_id == event.id,
                EventCandidate.status == "confirmed",
                EventGroupingAssessment.applied_result.contains(
                    {"event_id": str(event.id), "event_revision": revision}
                ),
            )
            .limit(2)
        ).all()
    )
    if not rows:
        return "not_recorded", None
    if len(rows) != 1:
        return "ambiguous", None
    assessment, candidate = rows[0]
    try:
        receipt = EventRevisionDeltaReceipt.model_validate(assessment.applied_result)
    except ValidationError:
        return "invalid", None
    expected = (
        {str(event.id): receipt.baseline_event_revision} if receipt.baseline_event_revision else {}
    )
    additions = {member.id: member for member in members if member.added_revision == revision}
    if (
        assessment.status not in {"valid", "degraded"}
        or assessment.input_fingerprint != candidate.input_fingerprint
        or assessment.ai_call_id != candidate.ai_call_id
        or candidate.expected_event_revisions != expected
        or not _consistent_decisions(assessment, candidate, receipt, assignments)
        or {change.event_member_id for change in receipt.material_changes} != set(additions)
        or any(
            additions[change.event_member_id].content_version_id != change.content_version_id
            or str(change.content_version_id) not in candidate.member_version_ids
            for change in receipt.material_changes
        )
    ):
        return "invalid", None
    facts_by_id = {fact.id: fact for fact in facts}
    current_links = set(
        session.execute(
            select(EventFactMember.event_member_id, EventFactMember.fact_id)
            .join(
                EventFactAssignment,
                (EventFactAssignment.owner_id == EventFactMember.owner_id)
                & (EventFactAssignment.event_id == EventFactMember.event_id)
                & (EventFactAssignment.fact_id == EventFactMember.fact_id),
            )
            .where(
                EventFactMember.owner_id == event.owner_id,
                EventFactMember.event_id == event.id,
                EventFactMember.event_member_id.in_(
                    [change.event_member_id for change in receipt.material_changes]
                ),
                EventFactMember.removed_revision.is_(None),
                EventFactAssignment.removed_revision.is_(None),
            )
        ).all()
    )
    changes = []
    for change in receipt.material_changes:
        fact = facts_by_id.get(change.fact_id)
        readable = (
            fact is not None
            and additions[change.event_member_id].removed_revision is None
            and (change.event_member_id, change.fact_id) in current_links
            and fact.evidence_state == "complete"
            and fact.title is not None
            and fact.relation in {"root", "development"}
            and any(
                member.event_member_id == change.event_member_id
                and member.content_version_id == change.content_version_id
                and member.availability == "readable"
                and member.role != "mention"
                for member in fact.members
            )
        )
        changes.append(
            change
            if readable
            else change.model_copy(update={"kind": "unknown", "reason": None, "unavailable": True})
        )
    return "available", EventRevisionDeltaView.from_receipt(
        receipt.model_copy(update={"material_changes": changes})
    )
