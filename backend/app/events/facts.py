from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from core.errors import ApplicationError
from events.fact_models import EventDerivedContent, EventFact, EventFactAssignment, EventFactMember
from events.fact_schemas import (
    EventFactMemberView,
    EventFactPageView,
    EventFactView,
    EventPublicationGrouping,
    FactRelation,
)
from events.models import Event, EventMember
from events.observation_inputs import (
    event_content_reference,
    load_fact_observation_inputs_in_transaction,
)


def load_publication_groupings_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_versions: dict[UUID, UUID],
    now: datetime,
    selected_observations: dict[UUID, UUID | None] | None = None,
    topic_id: UUID | None = None,
) -> dict[UUID, EventPublicationGrouping]:
    if not session.in_transaction() or now.tzinfo is None:
        raise RuntimeError("publication grouping read requires caller transaction and aware time")
    if not content_versions:
        return {}
    statement = (
        select(EventMember, EventFactMember, EventFactAssignment, EventFact, Event)
        .join(EventFactMember, EventFactMember.event_member_id == EventMember.id)
        .join(
            EventFactAssignment,
            (EventFactAssignment.fact_id == EventFactMember.fact_id)
            & (EventFactAssignment.event_id == EventMember.event_id)
            & EventFactAssignment.removed_revision.is_(None),
        )
        .join(EventFact, EventFact.id == EventFactMember.fact_id)
        .join(Event, Event.id == EventMember.event_id)
        .where(
            EventMember.owner_id == owner_id,
            EventMember.content_id.in_(content_versions),
            EventMember.removed_revision.is_(None),
            EventFactMember.removed_revision.is_(None),
            EventFactMember.role.in_(("primary", "report")),
            EventFact.status == "confirmed",
            Event.status == "active",
        )
    )
    if topic_id is not None:
        statement = statement.where(EventMember.topic_id == topic_id)
    rows = [
        row
        for row in session.execute(statement)
        if row[0].content_version_id == content_versions[row[0].content_id]
        and row[1].content_version_id == row[0].content_version_id
    ]
    readings = load_event_member_content_in_transaction(
        session,
        owner_id=owner_id,
        references=tuple(event_content_reference(member) for member, *_ in rows),
        now=now,
    )
    by_content: dict[UUID, list[EventPublicationGrouping]] = {}
    fact_inputs = load_fact_observation_inputs_in_transaction(
        session, owner_id=owner_id, fact_ids=tuple({row[3].id for row in rows}), now=now
    )
    for member, fact_member, assignment, fact, event in rows:
        reference = event_content_reference(member)
        if (
            reference not in readings
            or fact.id not in fact_inputs
            or (
                selected_observations is not None
                and member.observation_id != selected_observations.get(member.content_id)
            )
            or readings[reference].representative_comment_state == "unavailable"
        ):
            continue
        by_content.setdefault(member.content_id, []).append(
            EventPublicationGrouping(
                topic_id=event.topic_id,
                event_id=event.id,
                event_revision=event.revision,
                fact_id=fact.id,
                root_fact_id=assignment.root_fact_id,
                fact_revision=fact.revision,
                grouped_at=fact_member.created_at,
                role=cast(Literal["primary", "report"], fact_member.role),
            )
        )
    return {identity: groups[0] for identity, groups in by_content.items() if len(groups) == 1}


def ensure_legacy_facts_in_transaction(session: Session, *, event: Event, now: datetime) -> None:
    """Backfill a legacy confirmed event as one occurrence pending a finer assessment."""
    if not session.in_transaction():
        raise RuntimeError("fact backfill requires caller transaction and locked event")
    members = list(
        session.scalars(
            select(EventMember)
            .where(
                EventMember.owner_id == event.owner_id,
                EventMember.event_id == event.id,
                EventMember.removed_revision.is_(None),
            )
            .order_by(EventMember.created_at, EventMember.id)
        )
    )
    linked = set(
        session.scalars(
            select(EventFactMember.event_member_id).where(
                EventFactMember.owner_id == event.owner_id,
                EventFactMember.event_id == event.id,
                EventFactMember.removed_revision.is_(None),
            )
        )
    )
    missing = [member for member in members if member.id not in linked]
    if not missing:
        return
    root = session.scalar(
        select(EventFactAssignment).where(
            EventFactAssignment.owner_id == event.owner_id,
            EventFactAssignment.event_id == event.id,
            EventFactAssignment.removed_revision.is_(None),
            EventFactAssignment.relation.in_(("root", "roundup")),
        )
    )
    fact = EventFact(
        id=uuid4(),
        owner_id=event.owner_id,
        topic_id=event.topic_id,
        revision=1,
        title=event.title,
        summary=event.summary,
        status="confirmed",
        merged_into_id=None,
        frame=None,
        first_seen_at=event.first_seen_at,
        first_seen_basis=event.first_seen_basis,
        created_at=now,
        updated_at=now,
    )
    session.add(fact)
    session.flush()
    session.add(
        EventFactAssignment(
            id=uuid4(),
            owner_id=event.owner_id,
            topic_id=event.topic_id,
            event_id=event.id,
            fact_id=fact.id,
            root_fact_id=root.fact_id if root else None,
            relation="development" if root else "root",
            added_revision=event.revision,
            removed_revision=None,
            created_at=now,
        )
    )
    for index, member in enumerate(missing):
        session.add(
            EventFactMember(
                id=uuid4(),
                owner_id=event.owner_id,
                topic_id=event.topic_id,
                fact_id=fact.id,
                event_id=event.id,
                event_member_id=member.id,
                content_id=member.content_id,
                content_version_id=member.content_version_id,
                role="primary" if index == 0 else "report",
                assignment_origin="legacy",
                added_revision=1,
                removed_revision=None,
                created_at=now,
            )
        )
    session.flush()


def invalidate_event_derived_in_transaction(
    session: Session, *, event: Event, now: datetime
) -> None:
    if not session.in_transaction():
        raise RuntimeError("derived invalidation requires caller transaction")
    members = list(
        session.scalars(
            select(EventMember)
            .where(
                EventMember.owner_id == event.owner_id,
                EventMember.event_id == event.id,
                EventMember.removed_revision.is_(None),
            )
            .order_by(EventMember.id)
        )
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "event_id": str(event.id),
                "revision": event.revision,
                "members": [
                    (
                        str(member.id),
                        str(member.content_version_id),
                        str(member.representative_comment_id),
                    )
                    for member in members
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).digest()
    derived = session.get(EventDerivedContent, (event.owner_id, event.id))
    if derived is None:
        derived = EventDerivedContent(
            owner_id=event.owner_id,
            event_id=event.id,
            topic_id=event.topic_id,
            event_revision=event.revision,
            input_fingerprint=digest,
            status="stale",
            title=None,
            summary=None,
            latest_progress=None,
            ai_call_id=None,
            job_id=None,
            error_code=None,
            created_at=now,
            updated_at=now,
        )
        session.add(derived)
    else:
        derived.event_revision, derived.input_fingerprint = event.revision, digest
        derived.status = "stale"
        derived.title = derived.summary = derived.latest_progress = None
        derived.ai_call_id = derived.job_id = None
        derived.error_code, derived.updated_at = None, now


class EventFactReadService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_facts(
        self, *, owner_id: UUID, event_id: UUID, revision: int | None = None
    ) -> EventFactPageView:
        now = datetime.now(UTC)
        self._session.rollback()
        with self._session.begin():
            self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            event = self._session.scalar(
                select(Event).where(Event.owner_id == owner_id, Event.id == event_id)
            )
            if event is None:
                raise ApplicationError("resource_not_found")
            visited: set[UUID] = set()
            while revision is None and event.status == "merged":
                if event.id in visited or event.merged_into_id is None:
                    raise ApplicationError("resource_not_found")
                visited.add(event.id)
                event = self._session.scalar(
                    select(Event).where(
                        Event.owner_id == owner_id, Event.id == event.merged_into_id
                    )
                )
                if event is None:
                    raise ApplicationError("resource_not_found")
            selected = event.revision if revision is None else revision
            if not 1 <= selected <= event.revision:
                raise ApplicationError("invalid_event_filter")
            assignments = list(
                self._session.scalars(
                    select(EventFactAssignment)
                    .where(
                        EventFactAssignment.owner_id == owner_id,
                        EventFactAssignment.event_id == event.id,
                        EventFactAssignment.added_revision <= selected,
                        EventFactAssignment.removed_revision.is_(None)
                        | (EventFactAssignment.removed_revision > selected),
                    )
                    .order_by(EventFactAssignment.created_at, EventFactAssignment.fact_id)
                )
            )
            member_rows = list(
                self._session.execute(
                    select(EventFactMember, EventMember)
                    .join(
                        EventMember,
                        EventMember.id == EventFactMember.event_member_id,
                    )
                    .where(
                        EventFactMember.owner_id == owner_id,
                        EventFactMember.event_id == event.id,
                        EventMember.added_revision <= selected,
                        EventMember.removed_revision.is_(None)
                        | (EventMember.removed_revision > selected),
                    )
                )
            )
            references = tuple(event_content_reference(member) for _, member in member_rows)
            readings = load_event_member_content_in_transaction(
                self._session, owner_id=owner_id, references=references, now=now
            )
            if not readings:
                raise ApplicationError("resource_not_found")
            # A frame can originate from another assignment of the same fact.
            # Reuse its ALL-member gate, including original quoted-post inputs.
            fact_inputs = load_fact_observation_inputs_in_transaction(
                self._session,
                owner_id=owner_id,
                fact_ids=tuple(assignment.fact_id for assignment in assignments),
                now=now,
            )
            result = []
            for assignment in assignments:
                fact = self._session.get(EventFact, assignment.fact_id)
                if fact is None:
                    raise RuntimeError("scoped fact foreign key missing")
                rows = [(fm, member) for fm, member in member_rows if fm.fact_id == fact.id]
                fact_references = [event_content_reference(member) for _, member in rows]
                complete = fact.id in fact_inputs and all(
                    reference in readings
                    and readings[reference].representative_comment_state != "unavailable"
                    for reference in fact_references
                )
                available = complete and fact.status == "confirmed" and bool(rows)
                result.append(
                    EventFactView(
                        id=fact.id,
                        revision=fact.revision,
                        relation=cast(FactRelation, assignment.relation),
                        root_fact_id=assignment.root_fact_id,
                        title=fact.title if available else None,
                        summary=fact.summary if available else None,
                        evidence=(fact.frame or {}).get("evidence") if available else None,
                        conditions=(fact.frame or {}).get("conditions", []) if available else [],
                        first_seen_at=fact.first_seen_at,
                        first_seen_basis=cast("object", fact.first_seen_basis),
                        evidence_state="complete" if complete else "partial",
                        members=[
                            EventFactMemberView(
                                content_id=fm.content_id,
                                content_version_id=fm.content_version_id,
                                event_member_id=fm.event_member_id,
                                role=cast("object", fm.role),
                                assignment_origin=cast("object", fm.assignment_origin),
                                availability="readable"
                                if event_content_reference(member) in readings
                                else "unavailable",
                            )
                            for fm, member in rows
                        ],
                    )
                )
            return EventFactPageView(event_id=event.id, event_revision=selected, facts=result)
