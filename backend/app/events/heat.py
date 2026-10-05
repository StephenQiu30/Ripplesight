from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from content.event_reading import (
    load_event_content_original_times_in_transaction,
    load_event_member_content_in_transaction,
)
from content.observation_inputs import freeze_observation_inputs_in_transaction
from content.schemas import EventContentReadReference, EventContentReadView
from content.version_inputs import observations_readable_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from events.attention import compute_attention
from events.fact_models import EventFactMember
from events.heat_models import EventAttentionSignal, EventAttentionSnapshot, EventAttentionSource
from events.heat_schemas import (
    ATTENTION_FORMULA_VERSION,
    AttentionEvidence,
    AttentionSource,
    AttentionSourceInput,
    AttentionSourceView,
    EditionAttentionInputs,
    EventAttentionHistoryView,
    EventAttentionView,
    EventHotPageView,
    EventInteractionView,
)
from events.interaction import compare_interaction_growth, compute_interaction
from events.models import Event, EventMember
from events.observation_inputs import event_content_reference
from events.schemas import EventInput
from jobs.execution import JobCompletion, JobExecutionFailure
from jobs.models import Job
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from monitors.services import MonitorTopicService

_HEAT_NAMESPACE = UUID("18da3322-4a56-43d8-b6a2-6779426cac36")
_EVENT_PAGE_SIZE = 100
_MAX_NEW_HEAT_JOBS = 1000


def _active_events_in_transaction(
    session: Session, *, owner_id: UUID | None = None, topic_id: UUID | None = None
) -> Iterator[Event]:
    after: tuple[UUID, UUID] | None = None
    while True:
        statement = select(Event).where(Event.status == "active")
        if owner_id is not None:
            statement = statement.where(Event.owner_id == owner_id)
        if topic_id is not None:
            statement = statement.where(Event.topic_id == topic_id)
        if after is not None:
            statement = statement.where(tuple_(Event.owner_id, Event.id) > after)
        page = list(
            session.scalars(statement.order_by(Event.owner_id, Event.id).limit(_EVENT_PAGE_SIZE))
        )
        yield from page
        if len(page) < _EVENT_PAGE_SIZE:
            return
        after = page[-1].owner_id, page[-1].id


def _hot_order(result: EventAttentionView) -> tuple[float, float, str]:
    return (
        -result.heat,
        -max(source.source_time.timestamp() for source in result.roster),
        str(result.event_id),
    )


def _source_view(row: EventAttentionSource) -> AttentionSourceView:
    return AttentionSourceView.model_validate(row, from_attributes=True)


def _source(row: EventAttentionSource) -> AttentionSource:
    return AttentionSource(
        id=row.id,
        name=row.name,
        mode=cast(Literal["editorial", "signal", "isolated"], row.mode),
        group_key=row.group_key,
        owner_entity_key=row.owner_entity_key,
        tier=cast(Literal["T1", "T1_5", "T2"] | None, row.tier),
        first_party=row.first_party,
        created_at=row.created_at,
        scheduled=row.scheduled,
        interval_seconds=row.interval_seconds,
        last_successful_fetch_at=row.last_successful_fetch_at,
    )


def _matches_source(row: EventAttentionSource, reading: EventContentReadView) -> bool:
    if row.source_key != reading.source_key:
        return False
    observation = reading.observation
    if row.selector_kind == "native_scope":
        return row.selector_ref in {reading.native_scope, reading.collection_scope}
    reference = {
        "source": reading.source_key,
        "author": observation.author_external_id,
        "native_scope": reading.native_scope,
        "canonical_host": urlsplit(
            observation.canonical_url or observation.final_url or ""
        ).hostname,
    }.get(row.selector_kind)
    return reference == row.selector_ref


def resolve_attention_source(
    sources: Sequence[EventAttentionSource],
    reading: EventContentReadView,
) -> EventAttentionSource | None:
    matches = [row for row in sources if _matches_source(row, reading)]
    priority = {"source": 0, "canonical_host": 1, "native_scope": 2, "author": 3}
    matches.sort(key=lambda row: (-priority[row.selector_kind], str(row.id)))
    if not matches or (
        len(matches) > 1
        and priority[matches[0].selector_kind] == priority[matches[1].selector_kind]
    ):
        return None
    return matches[0] if matches[0].enabled and matches[0].mode != "isolated" else None


def record_source_fetch_success_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    source_key: str,
    selector_kind: Literal["source", "author", "native_scope", "canonical_host"],
    selector_ref: str,
    completed_at: datetime,
) -> int:
    """Exact successful terminal collection only, including an empty complete result."""
    if not session.in_transaction() or completed_at.utcoffset() is None:
        raise RuntimeError("source clocks require an aware caller transaction")
    rows = list(
        session.scalars(
            select(EventAttentionSource)
            .where(
                EventAttentionSource.owner_id == owner_id,
                EventAttentionSource.source_key == source_key,
                EventAttentionSource.selector_kind == selector_kind,
                EventAttentionSource.selector_ref == selector_ref,
            )
            .with_for_update()
        )
    )
    for row in rows:
        if row.last_successful_fetch_at is None or row.last_successful_fetch_at < completed_at:
            row.last_successful_fetch_at = completed_at
            row.updated_at = max(row.updated_at, completed_at)
    return len(rows)


def _live_inputs(
    session: Session,
    *,
    event: Event,
    now: datetime,
    references: tuple[EventContentReadReference, ...] | None = None,
) -> tuple[tuple[AttentionEvidence, ...], dict[str, object]]:
    if references is None:
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
        references = tuple(event_content_reference(row) for row in members)
    sources = list(
        session.scalars(
            select(EventAttentionSource).where(EventAttentionSource.owner_id == event.owner_id)
        )
    )
    readings = load_event_member_content_in_transaction(
        session, owner_id=event.owner_id, references=references, now=now
    )
    times = load_event_content_original_times_in_transaction(
        session, owner_id=event.owner_id, references=references
    )
    fact_ids = {
        row.content_version_id: row.fact_id
        for row in session.scalars(
            select(EventFactMember).where(
                EventFactMember.owner_id == event.owner_id,
                EventFactMember.event_id == event.id,
                EventFactMember.removed_revision.is_(None),
            )
        )
    }
    evidence = []
    manifest_rows = []
    for reference in references:
        reading = readings.get(reference)
        if reading is None:
            continue
        source = resolve_attention_source(sources, reading)
        original = times.get(reference.content_version_id)
        if source is None or original is None:
            continue
        version = reading.observation.content_version
        assert version is not None
        evidence.append(
            AttentionEvidence(
                id=reference.content_version_id,
                source=_source(source),
                content_id=reference.content_id,
                content_version_id=reference.content_version_id,
                source_time=original.source_time,
                kind="editorial" if source.mode == "editorial" else "discussion",
                title=version.title,
                canonical_url=reading.observation.canonical_url,
                fact_id=fact_ids.get(reference.content_version_id),
            )
        )
        manifest_rows.append(
            {
                "content_id": str(reference.content_id),
                "version_id": str(reference.content_version_id),
                "representative_comment_id": str(reference.representative_comment_id)
                if reference.representative_comment_id
                else None,
                "source_id": str(source.id),
                "source_revision": source.revision,
                "source_time": original.source_time.isoformat(),
                "time_basis": original.basis,
                "source": _source_view(source).model_dump(mode="json"),
                "observation_id": str(reading.observation.id),
                "representative_comment_observation_id": (
                    str(reading.representative_comment.observation.id)
                    if reading.representative_comment
                    else None
                ),
            }
        )
    observation_ids = tuple(
        dict.fromkeys(
            (
                *(
                    UUID(str(identity))
                    for row in manifest_rows
                    for identity in (
                        row["observation_id"],
                        row["representative_comment_observation_id"],
                    )
                    if identity is not None
                ),
                *(value for ref in references for value in ref.input_observation_ids),
            )
        )
    )
    closure = (
        freeze_observation_inputs_in_transaction(
            session, owner_id=event.owner_id, observation_ids=observation_ids, now=now
        )
        if observation_ids
        else ()
    )
    return tuple(evidence), {
        "input_basis": "observations_v1",
        "observation_ids": [str(identity) for identity in closure],
        "event_id": str(event.id),
        "event_revision": event.revision,
        "formula_version": ATTENTION_FORMULA_VERSION,
        "inputs": manifest_rows,
    }


def _live_interaction(
    session: Session, *, event: Event, now: datetime
) -> tuple[EventInteractionView, dict[str, object]]:
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
    readings = load_event_member_content_in_transaction(
        session,
        owner_id=event.owner_id,
        references=tuple(event_content_reference(row) for row in members),
        now=now,
    )
    metrics = {}
    observations = {}
    for member in members:
        reading = readings.get(event_content_reference(member))
        if reading is None:
            continue
        values = reading.observation.metrics
        metrics[str(member.content_version_id)] = {
            key: getattr(values, key)
            for key in ("like_count", "comment_count", "repost_count", "view_count")
        }
        observations[str(member.content_version_id)] = {
            "id": str(reading.observation.id),
            "observed_at": reading.observation.observed_at.isoformat(),
            "metrics": metrics[str(member.content_version_id)],
        }
    result = compute_interaction(metrics)
    lineage = {
        "versions": [str(member.content_version_id) for member in members],
        "unknown_masks": result.unknown_masks,
    }
    manifest: dict[str, object] = {"lineage": lineage, "observations": observations}
    roots = tuple(
        dict.fromkeys(
            (
                *(UUID(str(value["id"])) for value in observations.values()),
                *(
                    value
                    for member in members
                    for value in event_content_reference(member).input_observation_ids
                ),
            )
        )
    )
    if roots:
        manifest["input_basis"] = "observations_v1"
        manifest["observation_ids"] = [
            str(value)
            for value in freeze_observation_inputs_in_transaction(
                session, owner_id=event.owner_id, observation_ids=roots, now=now
            )
        ]
    history = []
    for snapshot in session.scalars(
        select(EventAttentionSnapshot)
        .where(
            EventAttentionSnapshot.owner_id == event.owner_id,
            EventAttentionSnapshot.event_id == event.id,
            EventAttentionSnapshot.event_revision == event.revision,
            EventAttentionSnapshot.formula_version == "interaction-v1-ln",
            EventAttentionSnapshot.window_end >= now - timedelta(hours=28),
            EventAttentionSnapshot.window_end < now,
        )
        .order_by(EventAttentionSnapshot.window_end.desc())
    ):
        historical_observations = []
        try:
            if snapshot.input_manifest.get("input_basis") == "observations_v1":
                historical_observations = [
                    UUID(str(value))
                    for value in cast(list[object], snapshot.input_manifest["observation_ids"])
                ]
            else:
                historical_observations = [
                    UUID(str(value["id"]))
                    for value in cast(
                        dict[str, dict[str, object]],
                        snapshot.input_manifest.get("observations", {}),
                    ).values()
                ]
        except (ValueError, KeyError, TypeError):
            continue
        if not historical_observations or not observations_readable_in_transaction(
            session,
            owner_id=event.owner_id,
            observation_ids=tuple(historical_observations),
            now=now,
        ):
            continue
        score = snapshot.result.get("score")
        if snapshot.input_manifest.get("lineage") == lineage and isinstance(score, (float, int)):
            history.append((snapshot.window_end, float(score)))
    return compare_interaction_growth(result, history, at=now), manifest


def load_event_attention_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    event_id: UUID,
    now: datetime,
) -> EventAttentionView | None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("event attention reads require an aware caller transaction")
    event = session.scalar(
        select(Event).where(
            Event.owner_id == owner_id, Event.id == event_id, Event.status == "active"
        )
    )
    if event is None:
        return None
    evidence, _ = _live_inputs(session, event=event, now=now)
    result = compute_attention(evidence, at=now, first_report_at=event.first_seen_at)
    interaction, _ = _live_interaction(session, event=event, now=now)
    return result.model_copy(
        update={"event_id": event.id, "event_revision": event.revision, "interaction": interaction}
    )


def load_edition_attention_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    references: tuple[EventContentReadReference, ...],
    event_ids: tuple[UUID, ...],
    start: datetime,
    end: datetime,
    now: datetime,
) -> EditionAttentionInputs:
    """Exact daily participants, without the heat roster's 48h/per-participant reduction."""
    if not session.in_transaction() or not start < end <= now:
        raise RuntimeError("edition attention requires a caller transaction and complete window")
    sources = list(
        session.scalars(
            select(EventAttentionSource).where(EventAttentionSource.owner_id == owner_id)
        )
    )
    participants = {}
    for offset in range(0, len(references), 500):
        readings = load_event_member_content_in_transaction(
            session, owner_id=owner_id, references=references[offset : offset + 500], now=now
        )
        for ref, reading in readings.items():
            source = resolve_attention_source(sources, reading)
            if source is not None:
                participants[ref.content_id] = _source(source).participant_key
    fact_sources: dict[UUID, set[str]] = defaultdict(set)
    event_participants: dict[UUID, frozenset[str]] = {}
    for event_id in event_ids:
        event = session.scalar(
            select(Event).where(
                Event.owner_id == owner_id, Event.id == event_id, Event.status == "active"
            )
        )
        if event is None:
            continue
        evidence, _ = _live_inputs(session, event=event, now=now)
        reported_facts = {
            row.content_version_id: row.fact_id
            for row in session.scalars(
                select(EventFactMember).where(
                    EventFactMember.owner_id == owner_id,
                    EventFactMember.event_id == event_id,
                    EventFactMember.removed_revision.is_(None),
                    EventFactMember.role.in_(("primary", "report")),
                )
            )
        }
        event_participants[event_id] = frozenset(
            e.source.participant_key for e in evidence if start <= e.source_time < end
        )
        for e in evidence:
            fact = reported_facts.get(e.content_version_id)
            if fact and e.source.mode == "editorial" and e.source_time < end:
                fact_sources[fact].add(e.source.participant_key)
    return EditionAttentionInputs(
        participants, {id: frozenset(p) for id, p in fact_sources.items()}, event_participants
    )


class EventHeatService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] | None = None) -> None:
        self._session, self._clock = session, clock or (lambda: datetime.now(UTC))

    def upsert_source(
        self, *, owner_id: UUID, command: AttentionSourceInput
    ) -> AttentionSourceView:
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            # Serialize absent natural identities as well as existing rows.
            lock = f"{owner_id}:{command.source_key}:{command.selector_kind}:{command.selector_ref}"
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": lock}
            )
            row = self._session.scalar(
                select(EventAttentionSource)
                .where(
                    EventAttentionSource.owner_id == owner_id,
                    EventAttentionSource.source_key == command.source_key,
                    EventAttentionSource.selector_kind == command.selector_kind,
                    EventAttentionSource.selector_ref == command.selector_ref,
                )
                .with_for_update()
            )
            if row is None:
                if command.expected_revision is not None:
                    raise ApplicationError("event_revision_conflict")
                row = EventAttentionSource(
                    id=uuid4(),
                    owner_id=owner_id,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    last_successful_fetch_at=None,
                )
                self._session.add(row)
            else:
                if command.expected_revision != row.revision:
                    raise ApplicationError("event_revision_conflict")
                row.revision += 1
                row.updated_at = now
            for key, value in command.model_dump(exclude={"expected_revision"}).items():
                setattr(row, key, value)
            self._session.flush()
            return _source_view(row)

    def list_sources(self, *, owner_id: UUID) -> list[AttentionSourceView]:
        self._session.rollback()
        with self._session.begin():
            return [
                _source_view(row)
                for row in self._session.scalars(
                    select(EventAttentionSource)
                    .where(EventAttentionSource.owner_id == owner_id)
                    .order_by(EventAttentionSource.source_key, EventAttentionSource.name)
                    .limit(1000)
                )
            ]

    def get_attention(self, *, owner_id: UUID, event_id: UUID) -> EventAttentionView:
        self._session.rollback()
        with self._session.begin():
            self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            result = load_event_attention_in_transaction(
                self._session, owner_id=owner_id, event_id=event_id, now=self._clock()
            )
            if result is None:
                raise ApplicationError("resource_not_found")
            # A heat DTO must not expose a story after all its current evidence is revoked.
            event = self._session.get(Event, event_id)
            assert event is not None
            members = list(
                self._session.scalars(
                    select(EventMember).where(
                        EventMember.owner_id == owner_id,
                        EventMember.event_id == event_id,
                        EventMember.removed_revision.is_(None),
                    )
                )
            )
            readings = load_event_member_content_in_transaction(
                self._session,
                owner_id=owner_id,
                references=tuple(event_content_reference(row) for row in members),
                now=self._clock(),
            )
            if not readings:
                raise ApplicationError("resource_not_found")
            return result

    def list_hot(self, *, owner_id: UUID, topic_id: UUID | None) -> EventHotPageView:
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            items: list[EventAttentionView] = []
            for event in _active_events_in_transaction(
                self._session, owner_id=owner_id, topic_id=topic_id
            ):
                result = load_event_attention_in_transaction(
                    self._session, owner_id=owner_id, event_id=event.id, now=now
                )
                if result is not None and result.eligible:
                    items.append(result)
                    # Keep only the exact best ten while scanning every permitted event.
                    # Memory does not grow with the number of eligible stories.
                    items.sort(key=_hot_order)
                    del items[10:]
            return EventHotPageView(window_end=now, items=items)

    def list_history(
        self, *, owner_id: UUID, event_id: UUID, limit: int = 48
    ) -> EventAttentionHistoryView:
        if not 1 <= limit <= 168:
            raise ApplicationError("invalid_event_filter")
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            self._session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            event = self._session.scalar(
                select(Event).where(
                    Event.owner_id == owner_id, Event.id == event_id, Event.status == "active"
                )
            )
            if event is None:
                raise ApplicationError("resource_not_found")
            snapshots = self._session.scalars(
                select(EventAttentionSnapshot)
                .where(
                    EventAttentionSnapshot.owner_id == owner_id,
                    EventAttentionSnapshot.event_id == event_id,
                    EventAttentionSnapshot.event_revision == event.revision,
                    EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
                    EventAttentionSnapshot.window_end >= now - timedelta(days=7),
                )
                .order_by(
                    EventAttentionSnapshot.window_end.desc(),
                    EventAttentionSnapshot.computed_at.desc(),
                )
            )
            items = []
            seen = set()
            for snapshot in snapshots:
                if snapshot.window_end in seen:
                    continue
                seen.add(snapshot.window_end)
                observation_ids: tuple[UUID, ...] = ()
                if snapshot.input_manifest.get("input_basis") == "observations_v1":
                    try:
                        observation_ids = tuple(
                            UUID(str(identity))
                            for identity in cast(
                                list[object], snapshot.input_manifest["observation_ids"]
                            )
                        )
                        if not observations_readable_in_transaction(
                            self._session,
                            owner_id=owner_id,
                            observation_ids=observation_ids,
                            now=now,
                        ):
                            continue
                    except (ValueError, KeyError, TypeError):
                        continue
                references = tuple(
                    EventContentReadReference(
                        UUID(str(row["content_id"])),
                        UUID(str(row["version_id"])),
                        UUID(str(row["representative_comment_id"]))
                        if row.get("representative_comment_id")
                        else None,
                        UUID(str(row["observation_id"])) if row.get("observation_id") else None,
                        UUID(str(row["representative_comment_observation_id"]))
                        if row.get("representative_comment_observation_id")
                        else None,
                        observation_ids,
                        legacy_strict=not bool(row.get("observation_id")),
                    )
                    for row in cast(list[dict[str, object]], snapshot.input_manifest["inputs"])
                )
                evidence, _ = _live_inputs(
                    self._session, event=event, now=now, references=references
                )
                result = compute_attention(
                    evidence,
                    at=snapshot.window_end,
                    historical=True,
                    first_report_at=event.first_seen_at,
                )
                items.append(
                    result.model_copy(
                        update={"event_id": event.id, "event_revision": event.revision}
                    )
                )
                if len(items) == limit:
                    break
            return EventAttentionHistoryView(
                event_id=event.id, event_revision=event.revision, items=items
            )

    def refresh_in_transaction(
        self, *, owner_id: UUID, event_id: UUID, at: datetime, historical: bool = False
    ) -> EventAttentionView | None:
        event = self._session.scalar(
            select(Event).where(Event.owner_id == owner_id, Event.id == event_id)
        )
        if event is None or event.status != "active":
            return None
        MonitorTopicService(self._session).lock_topic_for_event_commit_in_transaction(
            owner_id=owner_id, topic_id=event.topic_id
        )
        event = self._session.scalar(
            select(Event)
            .where(Event.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert event is not None
        evidence, manifest = _live_inputs(self._session, event=event, now=self._clock())
        live_inputs = {
            (UUID(str(row["version_id"])), UUID(str(row["observation_id"])))
            for row in cast(list[dict[str, object]], manifest["inputs"])
        }
        for signal in self._session.scalars(
            select(EventAttentionSignal).where(
                EventAttentionSignal.owner_id == owner_id, EventAttentionSignal.event_id == event.id
            )
        ):
            if (signal.content_version_id, signal.observation_id) not in live_inputs:
                signal.status, signal.updated_at = "withdrawn", self._clock()
        for row in evidence:
            original = next(
                item
                for item in cast(list[dict[str, object]], manifest["inputs"])
                if item["version_id"] == str(row.content_version_id)
            )
            self._session.execute(
                insert(EventAttentionSignal)
                .values(
                    id=uuid4(),
                    owner_id=owner_id,
                    topic_id=event.topic_id,
                    event_id=event.id,
                    fact_id=row.fact_id,
                    source_id=row.source.id,
                    content_id=row.content_id,
                    content_version_id=row.content_version_id,
                    observation_id=UUID(str(original["observation_id"])),
                    kind=row.kind,
                    source_time=row.source_time,
                    time_basis=original["time_basis"],
                    status="active",
                    created_at=self._clock(),
                    updated_at=self._clock(),
                )
                .on_conflict_do_update(
                    constraint="event_attention_signals_input_key",
                    set_={
                        "source_id": row.source.id,
                        "fact_id": row.fact_id,
                        "status": "active",
                        "updated_at": self._clock(),
                    },
                )
            )
        result = compute_attention(
            evidence, at=at, historical=historical, first_report_at=event.first_seen_at
        )
        result = result.model_copy(update={"event_id": event.id, "event_revision": event.revision})
        fingerprint = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).digest()
        self._session.execute(
            insert(EventAttentionSnapshot)
            .values(
                id=uuid4(),
                owner_id=owner_id,
                topic_id=event.topic_id,
                event_id=event.id,
                event_revision=event.revision,
                window_end=at,
                formula_version=ATTENTION_FORMULA_VERSION,
                input_fingerprint=fingerprint,
                input_manifest=manifest,
                result=result.model_dump(mode="json"),
                complete=result.complete,
                computed_at=self._clock(),
            )
            .on_conflict_do_nothing(constraint="event_attention_snapshots_input_key")
        )
        if not historical:
            sample_at = self._clock()
            interaction, interaction_manifest = _live_interaction(
                self._session, event=event, now=sample_at
            )
            interaction_hash = hashlib.sha256(
                json.dumps(interaction_manifest, sort_keys=True, separators=(",", ":")).encode()
            ).digest()
            self._session.execute(
                insert(EventAttentionSnapshot)
                .values(
                    id=uuid4(),
                    owner_id=owner_id,
                    topic_id=event.topic_id,
                    event_id=event.id,
                    event_revision=event.revision,
                    window_end=sample_at,
                    formula_version="interaction-v1-ln",
                    input_fingerprint=interaction_hash,
                    input_manifest=interaction_manifest,
                    result=interaction.model_dump(mode="json"),
                    complete=all(not values for values in interaction.unknown_masks.values()),
                    computed_at=sample_at,
                )
                .on_conflict_do_nothing(constraint="event_attention_snapshots_input_key")
            )
            result = result.model_copy(update={"interaction": interaction})
        return result

    def enqueue_due_in_transaction(self, *, now: datetime, enabled: bool) -> int:
        if not self._session.in_transaction():
            raise RuntimeError("attention scheduler requires caller transaction")
        if not enabled:
            return 0
        at = now.replace(minute=0, second=0, microsecond=0)
        accepted = 0
        for event in _active_events_in_transaction(self._session):
            operation = uuid5(
                _HEAT_NAMESPACE, f"{event.owner_id}:{event.id}:{event.revision}:{at.isoformat()}"
            )
            if self._session.scalar(
                select(EventAttentionSnapshot.id).where(
                    EventAttentionSnapshot.owner_id == event.owner_id,
                    EventAttentionSnapshot.event_id == event.id,
                    EventAttentionSnapshot.event_revision == event.revision,
                    EventAttentionSnapshot.window_end == at,
                )
            ):
                continue
            if self._session.scalar(
                select(Job.id).where(Job.owner_id == event.owner_id, Job.operation_id == operation)
            ):
                continue
            version, _, _ = MonitorTopicService(
                self._session
            ).get_current_topic_rules_and_sources_in_transaction(
                owner_id=event.owner_id, topic_id=event.topic_id
            )
            JobService(self._session).accept_in_transaction(
                owner_id=event.owner_id,
                command=JobAcceptanceInput(
                    operation_id=operation,
                    kind="events.heat",
                    scope={
                        "event_id": str(event.id),
                        "event_revision": event.revision,
                        "window_end": at.isoformat(),
                    },
                    observation=JobObservationContext(
                        configuration_ref=f"topic:{event.topic_id}", configuration_version=version
                    ),
                ),
            )
            accepted += 1
            if accepted >= _MAX_NEW_HEAT_JOBS:
                return accepted
        return accepted


class EventHeatExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._sessions, self._settings, self._clock = (
            sessions,
            settings,
            clock or (lambda: datetime.now(UTC)),
        )

    def execute(self, message: JobMessage) -> JobCompletion:
        if message.kind != "events.heat":
            raise ValueError("heat executor received another kind")
        if not self._settings.events_cluster_enabled:
            raise self._failure("event_heat_disabled", JobFailureCategory.CONFIGURATION_UNAVAILABLE)
        with self._sessions() as session, session.begin():
            config = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                config is None
                or config.owner_id != message.owner_id
                or config.operation_id != message.operation_id
                or config.kind != message.kind
                or config.observation.configuration_ref != message.configuration_ref
                or config.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("event_heat_job_mismatch", JobFailureCategory.INVALID_INPUT)
            event_id = UUID(str(config.scope["event_id"]))
            event = session.scalar(
                select(Event).where(Event.owner_id == message.owner_id, Event.id == event_id)
            )
            if event is None or event.revision != int(str(config.scope["event_revision"])):
                raise self._failure("event_heat_input_changed", JobFailureCategory.INVALID_INPUT)
            at = datetime.fromisoformat(str(config.scope["window_end"]))
            service = EventHeatService(session, clock=self._clock)
            service.refresh_in_transaction(
                owner_id=message.owner_id,
                event_id=event_id,
                at=at,
                historical=at < self._clock() - timedelta(hours=1),
            )
            # Backfill only incomplete hours; a later successful collection can repair clocks.
            pending = list(
                session.scalars(
                    select(EventAttentionSnapshot)
                    .where(
                        EventAttentionSnapshot.owner_id == message.owner_id,
                        EventAttentionSnapshot.event_id == event_id,
                        EventAttentionSnapshot.event_revision == event.revision,
                        EventAttentionSnapshot.complete.is_(False),
                        EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
                        EventAttentionSnapshot.window_end >= self._clock() - timedelta(hours=48),
                    )
                    .order_by(EventAttentionSnapshot.window_end)
                    .limit(48)
                )
            )
            for snapshot in pending:
                service.refresh_in_transaction(
                    owner_id=message.owner_id,
                    event_id=event_id,
                    at=snapshot.window_end,
                    historical=True,
                )
            from sqlalchemy import delete

            session.execute(
                delete(EventAttentionSnapshot).where(
                    EventAttentionSnapshot.owner_id == message.owner_id,
                    EventAttentionSnapshot.computed_at < self._clock() - timedelta(days=30),
                )
            )
        return JobCompletion(status=JobStatus.SUCCEEDED)

    def _failure(self, code: str, category: JobFailureCategory) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self._clock(),
            next_action="核对事件修订与来源成功采集时钟后重试",
            manual_retry_allowed=True,
        )


def load_event_input_source_modes_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    inputs: Sequence[EventInput],
    now: datetime,
) -> dict[UUID, str]:
    """Configured roles gate automated grouping; unknown legacy sources remain explicit."""
    if not session.in_transaction():
        raise RuntimeError("source role lookup requires caller transaction")
    sources = list(
        session.scalars(
            select(EventAttentionSource).where(EventAttentionSource.owner_id == owner_id)
        )
    )
    readings = load_event_member_content_in_transaction(
        session,
        owner_id=owner_id,
        references=tuple(event_content_reference(item, include_comment=False) for item in inputs),
        now=now,
    )
    result = {}
    for item in inputs:
        reading = readings.get(event_content_reference(item, include_comment=False))
        if reading is not None:
            matched = [row for row in sources if _matches_source(row, reading)]
            priority = {"source": 0, "canonical_host": 1, "native_scope": 2, "author": 3}
            matched.sort(key=lambda row: (-priority[row.selector_kind], str(row.id)))
            row = matched[0] if matched else None
        else:
            # Source-wide roles need no private author/body fallback to identify their scope.
            row = next(
                (
                    row
                    for row in sources
                    if row.source_key == item.source_key
                    and row.selector_kind == "source"
                    and row.selector_ref == item.source_key
                ),
                None,
            )
        result[item.content_version_id] = (
            row.mode if row and row.enabled else "isolated" if row else "legacy"
        )
    return result
