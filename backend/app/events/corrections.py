from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from core.errors import ApplicationError
from events.fact_models import (
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingOverride,
    EventRevisionOperation,
)
from events.fact_schemas import EventCorrectionInput, EventCorrectionView
from events.facts import ensure_legacy_facts_in_transaction, invalidate_event_derived_in_transaction
from events.models import Event, EventMember
from events.observation_inputs import event_content_reference
from monitors.services import MonitorTopicService


class EventCorrectionService:
    """Atomic, revision-checked manual edits preserve fixed membership history."""

    def __init__(self, session: Session, *, clock: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def correct(
        self, *, owner_id: UUID, actor_id: UUID, command: EventCorrectionInput
    ) -> EventCorrectionView:
        fingerprint = hashlib.sha256(
            json.dumps(
                command.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).digest()
        self._session.rollback()
        with self._session.begin():
            initial = list(
                self._session.scalars(
                    select(Event).where(
                        Event.owner_id == owner_id, Event.id.in_(command.expected_revisions)
                    )
                )
            )
            if (
                len(initial) != len(command.expected_revisions)
                or len({event.topic_id for event in initial}) != 1
            ):
                raise ApplicationError("resource_not_found")
            topic_id = initial[0].topic_id
            MonitorTopicService(self._session).lock_topic_for_event_commit_in_transaction(
                owner_id=owner_id, topic_id=topic_id
            )
            previous = self._session.scalar(
                select(EventRevisionOperation).where(
                    EventRevisionOperation.owner_id == owner_id,
                    EventRevisionOperation.operation_id == command.operation_id,
                )
            )
            if previous is not None:
                if previous.input_fingerprint != fingerprint:
                    raise ApplicationError("idempotency_conflict")
                return EventCorrectionView.model_validate(previous.result).model_copy(
                    update={"replayed": True}
                )
            events = {
                event.id: event
                for event in self._session.scalars(
                    select(Event)
                    .where(
                        Event.owner_id == owner_id,
                        Event.topic_id == topic_id,
                        Event.id.in_(command.expected_revisions),
                    )
                    .order_by(Event.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            }
            if any(
                event.revision != command.expected_revisions[event.id] or event.status != "active"
                for event in events.values()
            ):
                raise ApplicationError("event_revision_conflict")
            now = self._clock()
            for event in events.values():
                ensure_legacy_facts_in_transaction(self._session, event=event, now=now)
            return self._correct_locked(
                owner_id=owner_id,
                actor_id=actor_id,
                topic_id=topic_id,
                events=events,
                command=command,
                fingerprint=fingerprint,
                now=now,
            )

    def _correct_locked(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID,
        topic_id: UUID,
        events: dict[UUID, Event],
        command: EventCorrectionInput,
        fingerprint: bytes,
        now: datetime,
        automatic: bool = False,
    ) -> EventCorrectionView:
        members = list(
            self._session.scalars(
                select(EventMember)
                .where(
                    EventMember.owner_id == owner_id,
                    EventMember.event_id.in_(events),
                    EventMember.removed_revision.is_(None),
                )
                .order_by(EventMember.created_at, EventMember.id)
            )
        )
        assignments = list(
            self._session.scalars(
                select(EventFactAssignment).where(
                    EventFactAssignment.owner_id == owner_id,
                    EventFactAssignment.event_id.in_(events),
                    EventFactAssignment.removed_revision.is_(None),
                )
            )
        )
        fact_members = list(
            self._session.scalars(
                select(EventFactMember).where(
                    EventFactMember.owner_id == owner_id,
                    EventFactMember.event_id.in_(events),
                    EventFactMember.removed_revision.is_(None),
                )
            )
        )
        facts = {
            fact.id: fact
            for fact in self._session.scalars(
                select(EventFact).where(
                    EventFact.owner_id == owner_id,
                    EventFact.id.in_([row.fact_id for row in assignments]),
                )
            )
        }
        by_content = {member.content_id: member for member in members}
        by_fact_member = {row.content_id: row for row in fact_members}
        fact_for = {row.content_id: row.fact_id for row in fact_members}
        event_for = {row.content_id: row.event_id for row in members}
        fact_events = {row.fact_id: row.event_id for row in assignments}
        relations = {row.fact_id: row.relation for row in assignments}
        overrides = {
            row.content_id: row
            for row in self._session.scalars(
                select(EventGroupingOverride).where(
                    EventGroupingOverride.owner_id == owner_id,
                    EventGroupingOverride.topic_id == topic_id,
                    EventGroupingOverride.content_id.in_(command.content_ids),
                )
            )
        }
        source_ids = set(events) - ({command.target_event_id} if command.target_event_id else set())
        selected = set(command.content_ids)
        if command.kind == "merge":
            selected = set(by_content)
        elif command.kind == "merge_facts":
            if not set(command.fact_ids) <= set(facts):
                raise ApplicationError("invalid_event_correction")
            selected = {content for content, fact in fact_for.items() if fact in command.fact_ids}
        elif command.kind == "regroup":
            # Explicit regroup can release a standalone override. A manual membership still wins.
            selected = {
                identity
                for identity in selected
                if identity not in overrides or overrides[identity].mode != "manual"
            }
            for identity in selected - set(by_content):
                historical = self._session.scalar(
                    select(EventMember)
                    .where(
                        EventMember.owner_id == owner_id,
                        EventMember.topic_id == topic_id,
                        EventMember.event_id.in_(events),
                        EventMember.content_id == identity,
                    )
                    .order_by(EventMember.added_revision.desc())
                    .limit(1)
                )
                if (
                    historical is None
                    or identity not in overrides
                    or overrides[identity].mode != "standalone"
                ):
                    raise ApplicationError("invalid_event_correction")
                by_content[identity] = historical
        if command.kind in {"split", "move", "detach"} and (
            not selected <= set(by_content)
            or any(by_content[identity].event_id not in source_ids for identity in selected)
        ):
            raise ApplicationError("invalid_event_correction")
        if not selected:
            raise ApplicationError("invalid_event_correction")
        references = tuple(event_content_reference(by_content[identity]) for identity in selected)
        readable = load_event_member_content_in_transaction(
            self._session, owner_id=owner_id, references=references, now=now
        )
        if len(readable) != len(references):
            raise ApplicationError("resource_not_found")
        before = self._state(events, members, assignments)
        created_facts: list[UUID] = []
        target_id = command.target_event_id
        if command.kind == "split":
            source = events[next(iter(source_ids))]
            target_id = uuid4()
            target = Event(
                id=target_id,
                owner_id=owner_id,
                topic_id=topic_id,
                revision=1,
                title=source.title,
                summary=source.summary,
                first_seen_at=source.first_seen_at,
                first_seen_basis=source.first_seen_basis,
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
            events[target_id] = target
            self._session.add(target)
            self._session.flush()
        old_fact_ids = set(facts)
        if command.kind == "merge":
            assert target_id is not None
            for identity in event_for:
                event_for[identity] = target_id
            fact_events = dict.fromkeys(fact_events, target_id)
        elif command.kind in {"split", "move"}:
            assert target_id is not None
            for fact_id in {fact_for[identity] for identity in selected}:
                whole = {identity for identity, value in fact_for.items() if value == fact_id}
                moving = whole & selected
                destination_fact = fact_id
                if moving != whole:
                    old_fact = facts[fact_id]
                    new = EventFact(
                        id=uuid4(),
                        owner_id=owner_id,
                        topic_id=topic_id,
                        revision=1,
                        title=old_fact.title,
                        summary=old_fact.summary,
                        status="unreviewed",
                        merged_into_id=None,
                        frame=None,
                        first_seen_at=old_fact.first_seen_at,
                        first_seen_basis=old_fact.first_seen_basis,
                        created_at=now,
                        updated_at=now,
                    )
                    facts[new.id] = new
                    self._session.add(new)
                    destination_fact = new.id
                    created_facts.append(new.id)
                    old_fact.status = "unreviewed"
                fact_events[destination_fact] = target_id
                for identity in moving:
                    fact_for[identity] = destination_fact
                    event_for[identity] = target_id
        elif command.kind in {"detach", "regroup"}:
            for identity in selected:
                if identity in fact_for:
                    facts[fact_for[identity]].status = "unreviewed"
                fact_for.pop(identity, None)
                event_for.pop(identity, None)
        elif command.kind == "merge_facts":
            target_fact = command.target_fact_id
            assert target_fact is not None
            for identity in selected:
                fact_for[identity] = target_fact
            for identity in command.fact_ids:
                if identity != target_fact:
                    facts[identity].status, facts[identity].merged_into_id = "merged", target_fact
                    fact_events.pop(identity, None)
            if not automatic:
                facts[target_fact].status = "unreviewed"
        new_event_id = target_id if command.kind == "split" else None
        for event in events.values():
            if event.id != new_event_id:
                event.revision += 1
            event.updated_at = now
            if (
                event.id in source_ids
                and target_id is not None
                and not any(value == event.id for value in event_for.values())
            ):
                event.status, event.merged_into_id = "merged", target_id
        for member in members:
            member.removed_revision = events[member.event_id].revision
        for assignment in assignments:
            assignment.removed_revision = events[assignment.event_id].revision
        for fact_id in old_fact_ids:
            facts[fact_id].revision += 1
            facts[fact_id].updated_at = now
        for fact_member in fact_members:
            fact_member.removed_revision = facts[fact_member.fact_id].revision
        # Flush closures before opening current partial-unique rows.
        self._session.flush()
        remaining_facts = set(fact_for.values())
        fact_events = {
            identity: event
            for identity, event in fact_events.items()
            if identity in remaining_facts
        }
        facts_by_event: dict[UUID, list[UUID]] = defaultdict(list)
        for fact_id, event_id in fact_events.items():
            facts_by_event[event_id].append(fact_id)
        for event_id, fact_ids in facts_by_event.items():
            original_root = next(
                (
                    row.fact_id
                    for row in assignments
                    if row.event_id == event_id
                    and row.relation in {"root", "roundup"}
                    and row.fact_id in fact_ids
                ),
                None,
            )
            root = original_root or min(
                fact_ids, key=lambda identity: (facts[identity].first_seen_at, identity.hex)
            )
            for fact_id in fact_ids:
                relation = (
                    (
                        "roundup"
                        if relations.get(fact_id) == "roundup" and len(fact_ids) == 1
                        else "root"
                    )
                    if fact_id == root
                    else "development"
                )
                self._session.add(
                    EventFactAssignment(
                        id=uuid4(),
                        owner_id=owner_id,
                        topic_id=topic_id,
                        event_id=event_id,
                        fact_id=fact_id,
                        root_fact_id=None if fact_id == root else root,
                        relation=relation,
                        added_revision=events[event_id].revision,
                        removed_revision=None,
                        created_at=now,
                    )
                )
        opened: dict[UUID, EventMember] = {}
        for identity, event_id in event_for.items():
            old_member = by_content[identity]
            row = EventMember(
                id=uuid4(),
                owner_id=owner_id,
                topic_id=topic_id,
                event_id=event_id,
                content_id=identity,
                content_version_id=old_member.content_version_id,
                observation_id=old_member.observation_id,
                observation_source_key=old_member.observation_source_key,
                source_key=old_member.source_key,
                representative_comment_id=old_member.representative_comment_id,
                representative_comment_observation_id=(
                    old_member.representative_comment_observation_id
                ),
                input_manifest=old_member.input_manifest,
                added_revision=events[event_id].revision,
                removed_revision=None,
                assignment_origin="manual"
                if identity in selected and not automatic
                else old_member.assignment_origin,
                created_at=now,
            )
            opened[identity] = row
            self._session.add(row)
        self._session.flush()
        members_by_fact: dict[UUID, list[UUID]] = defaultdict(list)
        for identity, fact_id in fact_for.items():
            members_by_fact[fact_id].append(identity)
        for fact_id, identities in members_by_fact.items():
            primary = next(
                (identity for identity in identities if by_fact_member[identity].role == "primary"),
                identities[0],
            )
            for identity in identities:
                row = opened[identity]
                old_fact_member = by_fact_member[identity]
                self._session.add(
                    EventFactMember(
                        id=uuid4(),
                        owner_id=owner_id,
                        topic_id=topic_id,
                        event_id=row.event_id,
                        event_member_id=row.id,
                        fact_id=fact_id,
                        content_id=identity,
                        content_version_id=row.content_version_id,
                        role="primary"
                        if identity == primary
                        else "mention"
                        if old_fact_member.role == "mention"
                        else "report",
                        assignment_origin="manual"
                        if identity in selected and not automatic
                        else old_fact_member.assignment_origin,
                        added_revision=facts[fact_id].revision,
                        removed_revision=None,
                        created_at=now,
                    )
                )
        for identity in selected if not automatic else ():
            override = overrides.get(identity) or self._session.get(
                EventGroupingOverride, (owner_id, topic_id, identity)
            )
            mode = (
                "standalone"
                if command.kind == "detach"
                else "regroup_pending"
                if command.kind == "regroup"
                else "manual"
            )
            if override is None:
                self._session.add(
                    EventGroupingOverride(
                        owner_id=owner_id,
                        topic_id=topic_id,
                        content_id=identity,
                        mode=mode,
                        revision=1,
                        reason=command.reason.strip(),
                        actor_id=actor_id,
                        operation_id=command.operation_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                override.mode, override.revision = mode, override.revision + 1
                override.reason, override.actor_id = command.reason.strip(), actor_id
                override.operation_id, override.updated_at = command.operation_id, now
        self._session.flush()
        for event in events.values():
            invalidate_event_derived_in_transaction(self._session, event=event, now=now)
        result = EventCorrectionView(
            operation_id=command.operation_id,
            kind=command.kind,
            event_revisions={identity: event.revision for identity, event in events.items()},
            target_event_id=target_id,
            affected_content_ids=sorted(selected, key=lambda identity: identity.hex),
            created_fact_ids=created_facts,
        )
        current_assignments = list(
            self._session.scalars(
                select(EventFactAssignment).where(
                    EventFactAssignment.owner_id == owner_id,
                    EventFactAssignment.event_id.in_(events),
                    EventFactAssignment.removed_revision.is_(None),
                )
            )
        )
        self._session.add(
            EventRevisionOperation(
                id=uuid4(),
                owner_id=owner_id,
                topic_id=topic_id,
                operation_id=command.operation_id,
                kind=command.kind,
                input_fingerprint=fingerprint,
                actor_id=actor_id,
                reason=command.reason.strip(),
                before_state=before,
                after_state=self._state(events, list(opened.values()), current_assignments),
                result=result.model_dump(mode="json"),
                created_at=now,
            )
        )
        self._session.flush()
        return result

    @staticmethod
    def _state(
        events: dict[UUID, Event],
        members: list[EventMember],
        assignments: list[EventFactAssignment],
    ) -> dict[str, object]:
        return {
            "events": {
                str(identity): {
                    "revision": event.revision,
                    "status": event.status,
                    "merged_into_id": str(event.merged_into_id) if event.merged_into_id else None,
                }
                for identity, event in events.items()
            },
            "members": [
                {
                    "id": str(member.id),
                    "event_id": str(member.event_id),
                    "content_id": str(member.content_id),
                    "version_id": str(member.content_version_id),
                    "observation_id": str(member.observation_id) if member.observation_id else None,
                    "input_observation_ids": [
                        str(value)
                        for value in event_content_reference(member).input_observation_ids
                    ],
                }
                for member in members
            ],
            "facts": [
                {
                    "id": str(row.fact_id),
                    "event_id": str(row.event_id),
                    "relation": row.relation,
                    "root_fact_id": str(row.root_fact_id) if row.root_fact_id else None,
                }
                for row in assignments
            ],
        }
