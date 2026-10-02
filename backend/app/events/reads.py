from __future__ import annotations

import hashlib
import json
from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text, tuple_
from sqlalchemy.orm import Session

from content.event_reading import load_event_member_content_in_transaction
from content.schemas import EventContentReadReference, EventContentReadView
from core.errors import ApplicationError
from events.digest import load_event_digest_input_in_transaction
from events.fact_models import EventDerivedContent, EventFact, EventFactAssignment
from events.fact_schemas import (
    EventPublicationMemberReference,
    EventPublicationStoryView,
    StoryIndexingChange,
)
from events.heat import load_event_attention_in_transaction
from events.models import Event, EventMember
from events.schemas import (
    EventMemberPageView,
    EventMemberReadView,
    EventReadView,
    EventRelatedItemView,
    EventRelatedPageView,
)

type Clock = Callable[[], datetime]


def list_story_indexing_changes_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    after: tuple[datetime, UUID] | None,
    until: datetime,
    limit: int = 500,
) -> tuple[StoryIndexingChange, ...]:
    """IDs with a real historic root; public material/policy belongs to publication."""
    if not session.in_transaction() or until.utcoffset() is None:
        raise RuntimeError("story indexing requires caller transaction and aware cutoff")
    if not 1 <= limit <= 500 or (after is not None and after[0].utcoffset() is None):
        raise ValueError("invalid story indexing page")
    historic_root = (
        select(EventFactAssignment.id)
        .where(
            EventFactAssignment.owner_id == owner_id,
            EventFactAssignment.event_id == Event.id,
            EventFactAssignment.relation == "root",
        )
        .exists()
    )
    current_root = (
        select(EventFactAssignment.id)
        .where(
            EventFactAssignment.owner_id == owner_id,
            EventFactAssignment.event_id == Event.id,
            EventFactAssignment.relation == "root",
            EventFactAssignment.removed_revision.is_(None),
        )
        .exists()
    )
    statement = select(Event.id, Event.updated_at, Event.status, current_root).where(
        Event.owner_id == owner_id,
        Event.updated_at <= until,
        historic_root,
    )
    if after is not None:
        statement = statement.where(tuple_(Event.updated_at, Event.id) > after)
    return tuple(
        StoryIndexingChange(identity, at, status == "active" and has_root)
        for identity, at, status, has_root in session.execute(
            statement.order_by(Event.updated_at, Event.id).limit(limit)
        )
    )


def _reference(member: EventMember) -> EventContentReadReference:
    return EventContentReadReference(
        content_id=member.content_id,
        content_version_id=member.content_version_id,
        representative_comment_id=member.representative_comment_id,
    )


def _fingerprint(values: dict[str, str | int | None]) -> str:
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]


def _encode_cursor(*, fingerprint: str, identity: UUID, seen: datetime | None = None) -> str:
    values = {
        "v": 1,
        "filter": fingerprint,
        "id": str(identity),
        "seen": seen.isoformat() if seen else None,
    }
    return (
        urlsafe_b64encode(json.dumps(values, separators=(",", ":")).encode()).decode().rstrip("=")
    )


def _decode_cursor(cursor: str, fingerprint: str) -> tuple[UUID, datetime | None]:
    try:
        decoded = json.loads(
            b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(decoded, dict)
            or decoded.get("v") != 1
            or decoded.get("filter") != fingerprint
        ):
            raise ValueError("cursor scope mismatch")
        identity = UUID(decoded["id"])
        seen = datetime.fromisoformat(decoded["seen"]) if decoded["seen"] else None
        if seen is not None and seen.utcoffset() is None:
            raise ValueError("cursor time must be timezone-aware")
        return identity, seen
    except (
        Base64Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ApplicationError("invalid_event_cursor") from error


class EventReadService:
    """Confirmed event reads own a transaction and consume content-domain DTOs only."""

    def __init__(self, session: Session, *, clock: Clock | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_events(
        self,
        *,
        owner_id: UUID,
        cursor: str | None,
        limit: int,
        topic_id: UUID | None = None,
        source_key: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        query: str | None = None,
    ) -> tuple[list[EventReadView], str | None]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if (
            (starts_at is None) != (ends_at is None)
            or (
                starts_at is not None
                and ends_at is not None
                and (
                    starts_at.utcoffset() is None
                    or ends_at.utcoffset() is None
                    or not starts_at < ends_at <= starts_at + timedelta(days=31)
                )
            )
            or (query is not None and (not query.strip() or len(query) > 200))
        ):
            raise ApplicationError("invalid_event_filter")
        fingerprint = _fingerprint(
            {
                "owner_id": str(owner_id),
                "topic_id": str(topic_id) if topic_id else None,
                "source_key": source_key,
                "query": query.casefold() if query else None,
                "starts_at": starts_at.astimezone(UTC).isoformat() if starts_at else None,
                "ends_at": ends_at.astimezone(UTC).isoformat() if ends_at else None,
            }
        )
        scan_cursor = _decode_cursor(cursor, fingerprint) if cursor else None
        if scan_cursor is not None and scan_cursor[1] is None:
            raise ApplicationError("invalid_event_cursor")
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            self._begin_read_snapshot()
            selected: list[EventReadView] = []
            while len(selected) <= limit:
                statement = select(Event).where(
                    Event.owner_id == owner_id, Event.status == "active"
                )
                if topic_id is not None:
                    statement = statement.where(Event.topic_id == topic_id)
                if starts_at is not None and ends_at is not None:
                    statement = statement.where(
                        Event.first_seen_at >= starts_at, Event.first_seen_at < ends_at
                    )
                if scan_cursor is not None:
                    identity, seen = scan_cursor
                    statement = statement.where(
                        or_(
                            Event.first_seen_at < seen,
                            and_(Event.first_seen_at == seen, Event.id > identity),
                        )
                    )
                events = list(
                    self._session.scalars(
                        statement.order_by(Event.first_seen_at.desc(), Event.id).limit(100)
                    )
                )
                if not events:
                    break
                members, readings, derived_available = self._members_and_readings(
                    owner_id=owner_id,
                    events={event.id: event.revision for event in events},
                    now=now,
                )
                for event in events:
                    event_members = members.get(event.id, [])
                    view = self._view(event, event_members, readings, derived_available[event.id])
                    if view is None or (source_key and source_key not in view.source_counts):
                        continue
                    if query is not None:
                        texts = [view.title or "", view.summary or ""]
                        for member in event_members:
                            reading = readings.get(_reference(member))
                            if (
                                reading is not None
                                and reading.observation.content_version is not None
                            ):
                                version = reading.observation.content_version
                                texts.extend([version.title or "", version.body or ""])
                        if not any(query.casefold() in text.casefold() for text in texts):
                            continue
                    selected.append(view)
                    if len(selected) > limit:
                        break
                scan_cursor = (events[-1].id, events[-1].first_seen_at)
                if len(events) < 100:
                    break
            page = selected[:limit]
            next_cursor = (
                _encode_cursor(
                    fingerprint=fingerprint, identity=page[-1].id, seen=page[-1].first_seen_at
                )
                if len(selected) > limit
                else None
            )
            return page, next_cursor

    def get_event(self, *, owner_id: UUID, event_id: UUID) -> EventReadView:
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            self._begin_read_snapshot()
            event = self._resolve_current_event(owner_id=owner_id, event_id=event_id)
            members, readings, derived_available = self._members_and_readings(
                owner_id=owner_id, events={event.id: event.revision}, now=now
            )
            view = self._view(
                event, members.get(event.id, []), readings, derived_available[event.id]
            )
            if view is None:
                raise ApplicationError("resource_not_found")
            if event.id != event_id:
                view = view.model_copy(update={"redirected_from_event_id": event_id})
            return view

    def list_related(self, *, owner_id: UUID, event_id: UUID) -> EventRelatedPageView:
        from events.consolidation import load_related_story_ids_in_transaction

        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            self._begin_read_snapshot()
            event = self._resolve_current_event(owner_id=owner_id, event_id=event_id)
            ids = load_related_story_ids_in_transaction(
                self._session, owner_id=owner_id, event_id=event.id, now=now
            )
            events = list(
                self._session.scalars(
                    select(Event).where(
                        Event.owner_id == owner_id, Event.id.in_(ids), Event.status == "active"
                    )
                )
            )
            members, readings, derived_available = self._members_and_readings(
                owner_id=owner_id, events={row.id: row.revision for row in events}, now=now
            )
            items = []
            for row in events:
                view = self._view(row, members.get(row.id, []), readings, derived_available[row.id])
                if view is not None:
                    items.append(
                        EventRelatedItemView(event=view, supporting_report_count=ids[row.id])
                    )
            items.sort(key=lambda item: (-item.event.first_seen_at.timestamp(), item.event.id.hex))
            return EventRelatedPageView(event_id=event.id, items=items)

    def list_members(
        self,
        *,
        owner_id: UUID,
        event_id: UUID,
        revision: int | None,
        cursor: str | None,
        limit: int,
    ) -> EventMemberPageView:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            self._begin_read_snapshot()
            event = (
                self._resolve_current_event(owner_id=owner_id, event_id=event_id)
                if revision is None
                else self._get_event(owner_id=owner_id, event_id=event_id)
            )
            selected_revision = revision if revision is not None else event.revision
            if not 1 <= selected_revision <= event.revision:
                raise ApplicationError("invalid_event_filter")
            fingerprint = _fingerprint(
                {
                    "owner_id": str(owner_id),
                    "event_id": str(event_id),
                    "revision": selected_revision,
                    "kind": "members",
                }
            )
            cursor_values = _decode_cursor(cursor, fingerprint) if cursor else None
            if cursor_values is not None and cursor_values[1] is not None:
                raise ApplicationError("invalid_event_cursor")
            members, readings, _ = self._members_and_readings(
                owner_id=owner_id, events={event.id: selected_revision}, now=now
            )
            all_members = members.get(event.id, [])
            readable_count = sum(_reference(member) in readings for member in all_members)
            if not readable_count:
                raise ApplicationError("resource_not_found")
            start = 0
            if cursor_values is not None:
                identities = [member.id for member in all_members]
                try:
                    start = identities.index(cursor_values[0]) + 1
                except ValueError as error:
                    raise ApplicationError("invalid_event_cursor") from error
            page = all_members[start : start + limit]
            items = [
                EventMemberReadView(
                    id=member.id,
                    content_id=member.content_id,
                    content_version_id=member.content_version_id,
                    source_key=member.source_key,
                    assignment_origin=cast(Literal["model", "manual"], member.assignment_origin),
                    added_revision=member.added_revision,
                    removed_revision=member.removed_revision,
                    availability="readable" if _reference(member) in readings else "unavailable",
                    content=readings.get(_reference(member)),
                )
                for member in page
            ]
            return EventMemberPageView(
                event_id=event.id,
                revision=selected_revision,
                current_revision=event.revision,
                redirected_from_event_id=event_id if event.id != event_id else None,
                evidence_state="complete" if readable_count == len(all_members) else "partial",
                items=items,
                next_cursor=_encode_cursor(fingerprint=fingerprint, identity=page[-1].id)
                if start + limit < len(all_members)
                else None,
            )

    def _begin_read_snapshot(self) -> None:
        self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))

    def _resolve_current_event(self, *, owner_id: UUID, event_id: UUID) -> Event:
        event = self._get_event(owner_id=owner_id, event_id=event_id)
        seen: set[UUID] = set()
        while event.status == "merged":
            if event.id in seen or event.merged_into_id is None:
                raise ApplicationError("resource_not_found")
            seen.add(event.id)
            event = self._get_event(owner_id=owner_id, event_id=event.merged_into_id)
        return event

    def _get_event(self, *, owner_id: UUID, event_id: UUID) -> Event:
        event = self._session.scalar(
            select(Event).where(Event.owner_id == owner_id, Event.id == event_id)
        )
        if event is None:
            raise ApplicationError("resource_not_found")
        return event

    def _members_and_readings(
        self,
        *,
        owner_id: UUID,
        events: dict[UUID, int],
        now: datetime,
    ) -> tuple[
        dict[UUID, list[EventMember]],
        dict[EventContentReadReference, EventContentReadView],
        dict[UUID, bool],
    ]:
        rows = self._session.scalars(
            select(EventMember)
            .where(
                EventMember.owner_id == owner_id,
                EventMember.event_id.in_(events),
            )
            .order_by(EventMember.id)
        ).all()
        members: dict[UUID, list[EventMember]] = {}
        for member in rows:
            revision = events[member.event_id]
            if member.added_revision <= revision and (
                member.removed_revision is None or member.removed_revision > revision
            ):
                members.setdefault(member.event_id, []).append(member)
        readings = load_event_member_content_in_transaction(
            self._session,
            owner_id=owner_id,
            references=tuple(_reference(member) for member in rows),
            now=now,
        )
        # Derived text has no separate lineage table yet. Conservatively require all
        # historical member versions, including removed members, to remain readable.
        derived_available = {event_id: True for event_id in events}
        valid_derived: dict[UUID, EventDerivedContent] = {}
        for derived in self._session.scalars(
            select(EventDerivedContent).where(
                EventDerivedContent.owner_id == owner_id,
                EventDerivedContent.event_id.in_(events),
            )
        ):
            if derived.status != "valid" or derived.event_revision != events[derived.event_id]:
                derived_available[derived.event_id] = False
            else:
                valid_derived[derived.event_id] = derived
        for member in rows:
            reading = readings.get(_reference(member))
            if reading is None or reading.representative_comment_state == "unavailable":
                derived_available[member.event_id] = False
        for event_id, derived in valid_derived.items():
            event = self._session.get(Event, event_id)
            assert event is not None
            current_input = load_event_digest_input_in_transaction(
                self._session, event=event, now=now
            )
            derived_available[event_id] = (
                current_input is not None and current_input.fingerprint == derived.input_fingerprint
            )
        return members, readings, derived_available

    def _view(
        self,
        event: Event,
        members: list[EventMember],
        readings: dict[EventContentReadReference, EventContentReadView],
        derived_available: bool,
    ) -> EventReadView | None:
        readable = [member for member in members if _reference(member) in readings]
        if not readable:
            return None
        complete = len(readable) == len(members)
        derived = self._session.get(EventDerivedContent, (event.owner_id, event.id))
        latest_fact_at = self._session.scalar(
            select(func.max(EventFact.first_seen_at))
            .join(EventFactAssignment, EventFactAssignment.fact_id == EventFact.id)
            .where(
                EventFactAssignment.owner_id == event.owner_id,
                EventFactAssignment.event_id == event.id,
                EventFactAssignment.removed_revision.is_(None),
            )
        )
        age = self._clock() - (latest_fact_at or event.first_seen_at)
        phase = (
            "active"
            if age < timedelta(hours=24)
            else "watching"
            if age < timedelta(hours=72)
            else "settled"
        )
        return EventReadView(
            id=event.id,
            topic_id=event.topic_id,
            revision=event.revision,
            title=event.title if complete and derived_available else None,
            summary=event.summary if complete and derived_available else None,
            first_seen_at=event.first_seen_at,
            first_seen_basis=cast(Literal["published", "discovered"], event.first_seen_basis),
            status=cast(Literal["active", "merged"], event.status),
            merged_into_id=event.merged_into_id,
            evidence_state="complete" if complete else "partial",
            derived_text_available=complete and derived_available,
            latest_progress=derived.latest_progress
            if derived and complete and derived_available
            else None,
            phase=cast(Literal["active", "watching", "settled"], phase),
            member_count=len(members),
            readable_member_count=len(readable),
            source_counts=dict(Counter(member.source_key for member in readable)),
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


def load_publication_stories_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    event_ids: tuple[UUID, ...],
    now: datetime,
) -> dict[UUID, EventPublicationStoryView]:
    """Freeze readable canonical stories in the publication caller's one snapshot."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("publication story reads require an aware caller transaction")
    if len(event_ids) > 100:
        raise ValueError("publication story reads support at most 100 identities")
    service = EventReadService(session, clock=lambda: now)
    events = list(
        session.scalars(
            select(Event).where(
                Event.owner_id == owner_id, Event.id.in_(event_ids), Event.status == "active"
            )
        )
    )
    members, readings, available = service._members_and_readings(
        owner_id=owner_id, events={event.id: event.revision for event in events}, now=now
    )
    result = {}
    for event in events:
        active = members.get(event.id, [])
        view = service._view(event, active, readings, available[event.id])
        if view is None or not view.derived_text_available or not view.title or not view.summary:
            continue
        attention = load_event_attention_in_transaction(
            session, owner_id=owner_id, event_id=event.id, now=now
        )
        result[event.id] = EventPublicationStoryView(
            event_id=event.id,
            topic_id=event.topic_id,
            revision=event.revision,
            title=view.title,
            summary=view.summary,
            latest_progress=view.latest_progress,
            phase=view.phase,
            first_seen_at=view.first_seen_at,
            heat=attention.heat if attention and attention.participant_count else None,
            attention=attention if attention and attention.participant_count else None,
            members=tuple(
                EventPublicationMemberReference(
                    member.content_id, member.content_version_id, member.representative_comment_id
                )
                for member in active
            ),
        )
    return result
