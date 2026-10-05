from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from ai.services import AiService, create_ai_client
from analysis.event_reading import (
    list_editorial_event_inputs_in_transaction,
    load_editorial_event_inputs_for_versions_in_transaction,
)
from analysis.schemas import EventAnnotationRef
from analysis.services import list_relevant_event_annotation_refs_in_transaction
from content.event_reading import (
    load_event_content_original_times_in_transaction,
    load_event_member_content_in_transaction,
    load_native_event_targets_in_transaction,
)
from content.report_reading import report_inputs_readable_in_transaction
from content.schemas import EventContentReadReference
from content.services import load_event_content_inputs_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from events.ai_execution import (
    create_event_stage_client,
    freeze_event_ai_scope_in_transaction,
    load_verified_event_call_in_transaction,
)
from events.clustering import (
    EVENT_OUTPUT_SCHEMA,
    EVENT_PROMPT_VERSION,
    build_event_prompt,
    candidate_fingerprint,
    plan_event_candidates,
)
from events.fact_models import EventFactAssignment, EventGroupingAssessment, EventGroupingOverride
from events.fact_writer import (
    FactGroupingConflictError,
    freeze_fact_context_in_transaction,
    load_fact_context_in_transaction,
    record_candidate_facts_in_transaction,
)
from events.facts import ensure_legacy_facts_in_transaction, invalidate_event_derived_in_transaction
from events.heat import load_event_input_source_modes_in_transaction
from events.models import Event, EventCandidate, EventMember
from events.observation_inputs import (
    event_content_reference,
    event_member_input_manifest,
    freeze_event_inputs_in_transaction,
    load_frozen_event_inputs_in_transaction,
)
from events.relations import constrain_event_decision
from events.schemas import EventDecision, EventInput, EventTarget
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from monitors.editorial_events import (
    editorial_event_topic_id,
    ensure_editorial_event_topic_in_transaction,
)
from monitors.services import MonitorTopicService, NormalizedMonitorRules, evaluate_monitor_rules

EVENT_OPERATION_NAMESPACE = UUID("d6cd262b-5a2b-470d-a396-9e78968cfd92")
MAX_NEW_SINGLETON_CANDIDATES_PER_SCAN = 100
_RETRYABLE_CANDIDATE_ERRORS = {
    "ai_rate_limited",
    "ai_unavailable",
}


class EventCandidateConflictError(Exception):
    """The frozen candidate no longer matches current content or manual state."""


def load_relevant_event_inputs_in_transaction(
    session: Session,
    *,
    since: datetime,
    version_ids: Sequence[UUID] | None = None,
    exclude_assigned: bool = True,
    now: datetime | None = None,
) -> tuple[EventInput, ...]:
    """Compose owner-scoped analysis, content and topic DTOs."""
    if not session.in_transaction() or since.tzinfo is None:
        raise RuntimeError("event input lookup requires a transaction and aware time")
    now = now or datetime.now(UTC)
    result: list[EventInput] = []
    after = None
    for page_number in range(1, 11):
        page = list_relevant_event_annotation_refs_in_transaction(
            session, since=since, version_ids=version_ids, after=after, limit=2000, now=now
        )
        result.extend(
            _event_inputs_from_refs(
                session, refs=page.items, since=since, exclude_assigned=exclude_assigned, now=now
            )
        )
        if len(result) >= 2000 or (page_number == 10 and page.next_after is not None):
            structlog.get_logger("events").info(
                "event_scan_truncated", pages_read=page_number, input_limit=2000, page_limit=10
            )
            result = result[:2000]
            break
        if page.next_after is None:
            break
        after = page.next_after
    editorial_after = None
    for _ in range(10):
        editorial = list_editorial_event_inputs_in_transaction(
            session,
            since=since,
            now=now,
            version_ids=tuple(version_ids) if version_ids is not None else None,
            after=editorial_after,
            limit=1000,
        )
        for item in editorial.items:
            topic_id = editorial_event_topic_id(item.owner_id)
            if _protected_event_input(
                session,
                owner_id=item.owner_id,
                topic_id=topic_id,
                content_id=item.content_id,
                exclude_assigned=exclude_assigned,
            ):
                continue
            ensure_editorial_event_topic_in_transaction(session, owner_id=item.owner_id, now=now)
            native = load_native_event_targets_in_transaction(
                session,
                owner_id=item.owner_id,
                references=(EventContentReadReference(item.content_id, item.content_version_id),),
                now=now,
            )
            result.append(
                EventInput(
                    owner_id=item.owner_id,
                    topic_id=topic_id,
                    content_id=item.content_id,
                    content_version_id=item.content_version_id,
                    source_key=item.source_key,
                    title=item.title,
                    body=item.summary or item.raw_body,
                    first_seen_at=item.first_seen_at,
                    first_seen_basis=item.first_seen_basis,
                    matched_keywords=frozenset({"editorial-input"}),
                    native_target_content_ids=native.get(item.content_version_id, frozenset()),
                    editorial_frame=item.fact_frame,
                    editorial_scope=item.scope,
                    provenance_fingerprint=item.provenance_fingerprint,
                    observation_id=item.observation_id,
                    input_observation_ids=item.input_observation_ids,
                )
            )
        if editorial.next_after is None or len(result) >= 4000:
            break
        editorial_after = editorial.next_after
    return tuple(result[:4000])


def _protected_event_input(
    session: Session, *, owner_id: UUID, topic_id: UUID, content_id: UUID, exclude_assigned: bool
) -> bool:
    if (
        session.scalar(
            select(EventGroupingOverride.content_id).where(
                EventGroupingOverride.owner_id == owner_id,
                EventGroupingOverride.topic_id == topic_id,
                EventGroupingOverride.content_id == content_id,
                EventGroupingOverride.mode.in_(("standalone", "manual")),
            )
        )
        is not None
    ):
        return True
    return (
        exclude_assigned
        and session.scalar(
            select(EventMember.id).where(
                EventMember.owner_id == owner_id,
                EventMember.topic_id == topic_id,
                EventMember.content_id == content_id,
                EventMember.removed_revision.is_(None),
            )
        )
        is not None
    )


def _event_inputs_from_refs(
    session: Session,
    *,
    refs: Sequence[EventAnnotationRef],
    since: datetime,
    exclude_assigned: bool,
    now: datetime | None = None,
) -> tuple[EventInput, ...]:
    now = now or datetime.now(UTC)
    assigned: set[tuple[UUID, UUID, UUID]] = set()
    protected = (
        {
            (owner_id, topic_id, content_id)
            for owner_id, topic_id, content_id in session.execute(
                select(
                    EventGroupingOverride.owner_id,
                    EventGroupingOverride.topic_id,
                    EventGroupingOverride.content_id,
                ).where(
                    EventGroupingOverride.content_id.in_([ref.content_id for ref in refs]),
                    EventGroupingOverride.mode.in_(("standalone", "manual")),
                )
            )
        }
        if refs
        else set()
    )
    if exclude_assigned and refs:
        assigned = {
            (owner_id, topic_id, content_id)
            for owner_id, topic_id, content_id in session.execute(
                select(EventMember.owner_id, EventMember.topic_id, EventMember.content_id).where(
                    EventMember.removed_revision.is_(None),
                    EventMember.content_id.in_([ref.content_id for ref in refs]),
                )
            )
        }
    refs = tuple(
        ref
        for ref in refs
        if (ref.owner_id, ref.topic_id, ref.content_id) not in assigned | protected
    )
    by_owner: dict[UUID, set[UUID]] = {}
    for ref in refs:
        by_owner.setdefault(ref.owner_id, set()).add(ref.content_version_id)
    content = {
        owner: load_event_content_inputs_in_transaction(
            session, owner_id=owner, version_ids=tuple(ids), since=since
        )
        for owner, ids in by_owner.items()
    }
    fixed_references = {
        ref: EventContentReadReference(
            ref.content_id,
            ref.content_version_id,
            observation_id=ref.observation_id,
            input_observation_ids=ref.input_observation_ids,
        )
        for ref in refs
        if ref.observation_id is not None
    }
    fixed_readings = {
        owner: load_event_member_content_in_transaction(
            session,
            owner_id=owner,
            references=tuple(
                dict.fromkeys(
                    reference
                    for ref, reference in fixed_references.items()
                    if ref.owner_id == owner
                )
            ),
            now=now,
        )
        for owner in by_owner
    }
    native_targets = {
        owner: load_native_event_targets_in_transaction(
            session,
            owner_id=owner,
            references=tuple(
                EventContentReadReference(item.content_id, item.content_version_id)
                for item in items.values()
            ),
            now=now,
        )
        for owner, items in content.items()
    }
    topic_service = MonitorTopicService(session)
    topic_rules: dict[tuple[UUID, UUID], tuple[int, NormalizedMonitorRules]] = {}
    result: list[EventInput] = []
    seen: set[tuple[UUID, UUID, UUID]] = set()
    for ref in refs:
        identity = (ref.owner_id, ref.topic_id, ref.content_id)
        if identity in seen or identity in assigned:
            continue
        source = content[ref.owner_id].get(ref.content_version_id)
        if source is None:
            continue
        fixed_reading = None
        if ref.observation_id is not None:
            fixed_reading = fixed_readings[ref.owner_id].get(fixed_references[ref])
            if fixed_reading is None or fixed_reading.observation.content_version is None:
                continue
        topic_key = (ref.owner_id, ref.topic_id)
        if topic_key not in topic_rules:
            version, rules, _ = topic_service.get_current_topic_rules_and_sources_in_transaction(
                owner_id=ref.owner_id, topic_id=ref.topic_id
            )
            topic_rules[topic_key] = version, rules
        version, rules = topic_rules[topic_key]
        if version != ref.topic_rule_version:
            continue
        match = evaluate_monitor_rules(rules, f"{source.title} {source.body or ''}")
        keywords = frozenset(match.matched_any + match.matched_all)
        if not match.matched or not keywords:
            continue
        seen.add(identity)
        result.append(
            EventInput(
                owner_id=ref.owner_id,
                topic_id=ref.topic_id,
                content_id=source.content_id,
                content_version_id=source.content_version_id,
                source_key=fixed_reading.source_key if fixed_reading else source.source_key,
                title=source.title,
                body=source.body,
                first_seen_at=source.first_seen_at,
                first_seen_basis=source.first_seen_basis,
                matched_keywords=keywords,
                representative_comment_id=(
                    None if ref.observation_id is not None else source.representative_comment_id
                ),
                observation_id=ref.observation_id or source.observation_id,
                representative_comment_observation_id=(
                    None
                    if ref.observation_id is not None
                    else source.representative_comment_observation_id
                ),
                input_observation_ids=ref.input_observation_ids,
                annotation_id=ref.annotation_id,
                native_target_content_ids=native_targets[ref.owner_id].get(
                    source.content_version_id, frozenset()
                ),
            )
        )
    return tuple(result)


def _load_event_targets(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    since: datetime,
    now: datetime | None = None,
) -> tuple[EventTarget, ...]:
    now = now or datetime.now(UTC)
    events = session.scalars(
        select(Event)
        .where(
            Event.owner_id == owner_id,
            Event.topic_id == topic_id,
            Event.status == "active",
        )
        .order_by(Event.id)
    ).all()
    if not events:
        return ()
    members = session.scalars(
        select(EventMember).where(
            EventMember.owner_id == owner_id,
            EventMember.topic_id == topic_id,
            EventMember.event_id.in_([event.id for event in events]),
            EventMember.removed_revision.is_(None),
        )
    ).all()
    # Fixed context is evidence even if its source later created a newer version.
    by_version = {
        item.content_version_id: item
        for item in _fixed_context_inputs(
            session,
            owner_id=owner_id,
            topic_id=topic_id,
            members=members,
            since=since,
            now=now,
        )
    }
    recent_members: dict[UUID, list[EventInput]] = {}
    for member in members:
        if member.content_version_id in by_version and by_version[
            member.content_version_id
        ].editorial_scope not in {"composite", "unknown"}:
            recent_members.setdefault(member.event_id, []).append(
                by_version[member.content_version_id]
            )
    return tuple(
        EventTarget(
            event_id=event.id,
            revision=event.revision,
            members=tuple(recent_members[event.id]),
        )
        for event in events
        if event.id in recent_members
    )


def _candidate_context_members(
    session: Session, candidate: EventCandidate
) -> tuple[EventMember, ...]:
    if not candidate.expected_event_revisions:
        return ()
    if len(candidate.expected_event_revisions) != 1:
        raise EventCandidateConflictError("manual_revision_conflict")
    event_id, revision = next(iter(candidate.expected_event_revisions.items()))
    # The revision interval freezes context identity without a second stored member list.
    # Keep removed historical rows so removal cannot turn context into a new addition.
    return tuple(
        session.scalars(
            select(EventMember).where(
                EventMember.owner_id == candidate.owner_id,
                EventMember.topic_id == candidate.topic_id,
                EventMember.event_id == UUID(event_id),
                EventMember.content_version_id.in_(
                    [UUID(value) for value in candidate.member_version_ids]
                ),
                EventMember.added_revision <= revision,
                (
                    EventMember.removed_revision.is_(None)
                    | (EventMember.removed_revision > revision)
                ),
            )
        ).all()
    )


def _fixed_context_inputs(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    members: Sequence[EventMember],
    since: datetime,
    now: datetime,
    apply_topic_rules: bool = True,
) -> tuple[EventInput, ...]:
    references = tuple(event_content_reference(row) for row in members)
    readable = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    times = load_event_content_original_times_in_transaction(
        session, owner_id=owner_id, references=references
    )
    internal = topic_id == editorial_event_topic_id(owner_id)
    editorial_by_version = (
        load_editorial_event_inputs_for_versions_in_transaction(
            session,
            owner_id=owner_id,
            since=since,
            now=now,
            version_ids=tuple(reference.content_version_id for reference in references),
        )
        if internal
        else {}
    )
    rules = None
    if not internal and apply_topic_rules:
        _, rules, _ = MonitorTopicService(
            session
        ).get_current_topic_rules_and_sources_in_transaction(owner_id=owner_id, topic_id=topic_id)
    result = []
    for reference in references:
        reading = readable.get(reference)
        original = times.get(reference.content_version_id)
        if (
            reading is None
            or original is None
            or original.source_time < since
            or reading.current_visibility is None
            or reading.current_visibility.status != "visible"
            or reading.representative_comment_state == "unavailable"
        ):
            continue
        version = reading.observation.content_version
        if version is None or not version.title:
            continue
        editorial = editorial_by_version.get(version.id)
        if internal and (editorial is None or editorial.observation_id != reading.observation.id):
            continue
        if rules is not None:
            match = evaluate_monitor_rules(rules, f"{version.title} {version.body or ''}")
            keywords = frozenset(match.matched_any + match.matched_all)
            if not match.matched or not keywords:
                continue
        else:
            keywords = frozenset({"editorial-input"})
        result.append(
            EventInput(
                owner_id=owner_id,
                topic_id=topic_id,
                content_id=reading.id,
                content_version_id=version.id,
                source_key=reading.source_key,
                title=editorial.title if editorial else version.title,
                body=(editorial.summary or editorial.raw_body) if editorial else version.body,
                first_seen_at=original.source_time,
                first_seen_basis=original.basis,
                matched_keywords=keywords,
                representative_comment_id=reference.representative_comment_id,
                observation_id=reading.observation.id,
                representative_comment_observation_id=(
                    reading.representative_comment.observation.id
                    if reading.representative_comment
                    else None
                ),
                input_observation_ids=reference.input_observation_ids,
                editorial_scope=(
                    editorial_by_version[version.id].scope
                    if version.id in editorial_by_version
                    else "unknown"
                    if internal
                    else None
                ),
                editorial_frame=(
                    editorial_by_version[version.id].fact_frame
                    if version.id in editorial_by_version
                    else None
                ),
                provenance_fingerprint=editorial.provenance_fingerprint if editorial else None,
            )
        )
    return tuple(result)


def _load_candidate_inputs(
    session: Session, *, candidate: EventCandidate, now: datetime
) -> tuple[EventInput, ...]:
    if candidate.input_manifest is not None:
        inputs = load_frozen_event_inputs_in_transaction(
            session,
            owner_id=candidate.owner_id,
            topic_id=candidate.topic_id,
            manifest=candidate.input_manifest,
            now=now,
        )
        if not inputs or candidate.topic_id == editorial_event_topic_id(candidate.owner_id):
            return inputs
        from analysis.reads import relevant_event_annotation_ids_in_transaction

        context_ids = {
            row.content_version_id for row in _candidate_context_members(session, candidate)
        }
        current_version, _, _ = MonitorTopicService(
            session
        ).get_current_topic_rules_and_sources_in_transaction(
            owner_id=candidate.owner_id, topic_id=candidate.topic_id
        )
        annotations: dict[UUID, tuple[UUID, UUID]] = {}
        for item in inputs:
            if item.content_version_id in context_ids:
                continue
            if (
                item.annotation_id is None
                or item.observation_id is None
                or item.annotation_id in annotations
            ):
                return ()
            annotations[item.annotation_id] = (item.content_version_id, item.observation_id)
        if relevant_event_annotation_ids_in_transaction(
            session,
            owner_id=candidate.owner_id,
            topic_id=candidate.topic_id,
            topic_rule_version=current_version,
            references=annotations,
            now=now,
        ) != frozenset(annotations):
            return ()
        return inputs
    expected = {UUID(value) for value in candidate.member_version_ids}
    context = _candidate_context_members(session, candidate)
    context_ids = {row.content_version_id for row in context}
    additions = load_relevant_event_inputs_in_transaction(
        session,
        since=candidate.window_start - timedelta(microseconds=1),
        now=now,
        version_ids=tuple(expected - context_ids),
        exclude_assigned=False,
    )
    fixed = (
        _fixed_context_inputs(
            session,
            owner_id=candidate.owner_id,
            topic_id=candidate.topic_id,
            members=context,
            since=candidate.window_start - timedelta(microseconds=1),
            now=now,
        )
        if context
        else ()
    )
    inputs = tuple(
        item
        for item in (*additions, *fixed)
        if item.owner_id == candidate.owner_id and item.topic_id == candidate.topic_id
    )
    if not inputs:
        return ()
    references = tuple(event_content_reference(item) for item in inputs)
    readings = load_event_member_content_in_transaction(
        session, owner_id=candidate.owner_id, references=references, now=now
    )
    versions = {item.content_version_id for item in inputs}
    observations = set()
    for reference in references:
        reading = readings.get(reference)
        if reading is None or reading.representative_comment_state == "unavailable":
            return ()
        observations.add(reading.observation.id)
        if reading.representative_comment is not None:
            comment_version = reading.representative_comment.observation.content_version
            if comment_version is None:
                return ()
            versions.add(comment_version.id)
            observations.add(reading.representative_comment.observation.id)
    if not report_inputs_readable_in_transaction(
        session,
        owner_id=candidate.owner_id,
        content_version_ids=tuple(versions),
        observation_ids=tuple(observations),
        now=now,
    ):
        return ()
    return inputs


def _candidate_material_matches(
    session: Session, *, candidate: EventCandidate, members: Sequence[EventInput]
) -> bool:
    if candidate.prompt_version != EVENT_PROMPT_VERSION:
        return True
    requests = {
        str(row.content_id): str(row.operation_id)
        for row in session.scalars(
            select(EventGroupingOverride).where(
                EventGroupingOverride.owner_id == candidate.owner_id,
                EventGroupingOverride.topic_id == candidate.topic_id,
                EventGroupingOverride.content_id.in_([item.content_id for item in members]),
                EventGroupingOverride.mode == "regroup_pending",
            )
        )
    }
    return (
        candidate_fingerprint(
            topic_id=candidate.topic_id,
            members=members,
            expected_event_revisions=candidate.expected_event_revisions,
            regroup_requests=requests,
        )
        == candidate.input_fingerprint
    )


class EventCandidateService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        if not self._session.in_transaction() or now.tzinfo is None:
            raise RuntimeError("event scan requires a transaction and aware time")
        inputs = load_relevant_event_inputs_in_transaction(
            self._session, since=now - timedelta(hours=72), now=now
        )
        by_topic: dict[tuple[UUID, UUID], list[EventInput]] = {}
        for item in inputs:
            by_topic.setdefault((item.owner_id, item.topic_id), []).append(item)
        accepted = 0
        for (owner_id, topic_id), topic_inputs in by_topic.items():
            targets = _load_event_targets(
                self._session,
                owner_id=owner_id,
                topic_id=topic_id,
                since=now - timedelta(hours=72),
                now=now,
            )
            regroup_requests = {
                row.content_id: str(row.operation_id)
                for row in self._session.scalars(
                    select(EventGroupingOverride).where(
                        EventGroupingOverride.owner_id == owner_id,
                        EventGroupingOverride.topic_id == topic_id,
                        EventGroupingOverride.mode == "regroup_pending",
                    )
                )
            }
            source_modes = load_event_input_source_modes_in_transaction(
                self._session, owner_id=owner_id, inputs=topic_inputs, now=now
            )
            # Without an embedding provider, discussion rematch only follows a verified
            # native reference. Similar titles cannot substitute for the disabled 6h recall.
            topic_inputs = [
                item
                for item in topic_inputs
                if source_modes.get(item.content_version_id) != "isolated"
                and (
                    source_modes.get(item.content_version_id) != "signal"
                    or item.first_seen_at >= now - timedelta(hours=48)
                )
            ]
            groups = plan_event_candidates(
                self._session,
                topic_inputs,
                targets,
                regroup_content_ids=frozenset(regroup_requests),
                native_only_version_ids=frozenset(
                    item.content_version_id
                    for item in topic_inputs
                    if source_modes.get(item.content_version_id) == "signal"
                ),
            )
            new_singletons = 0
            for members, revisions in groups:
                if any(source_modes.get(item.content_version_id) == "isolated" for item in members):
                    continue
                if not revisions and all(
                    source_modes.get(item.content_version_id) == "signal" for item in members
                ):
                    continue
                if len(members) == 1 and new_singletons >= MAX_NEW_SINGLETON_CANDIDATES_PER_SCAN:
                    break
                try:
                    members, input_manifest = freeze_event_inputs_in_transaction(
                        self._session, owner_id=owner_id, inputs=tuple(members), now=now
                    )
                except ApplicationError:
                    continue
                fingerprint = candidate_fingerprint(
                    topic_id=topic_id,
                    members=members,
                    expected_event_revisions=revisions,
                    regroup_requests={
                        str(item.content_id): regroup_requests[item.content_id]
                        for item in members
                        if item.content_id in regroup_requests
                    },
                )
                candidate = self._session.scalar(
                    select(EventCandidate).where(
                        EventCandidate.owner_id == owner_id,
                        EventCandidate.topic_id == topic_id,
                        EventCandidate.input_fingerprint == fingerprint,
                    )
                )
                if candidate is None:
                    created_id = self._session.scalar(
                        insert(EventCandidate)
                        .values(
                            id=uuid4(),
                            owner_id=owner_id,
                            topic_id=topic_id,
                            input_fingerprint=fingerprint,
                            member_version_ids=sorted(
                                str(item.content_version_id) for item in members
                            ),
                            input_manifest=input_manifest,
                            expected_event_revisions=revisions,
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
                        .on_conflict_do_nothing(constraint="event_candidates_fingerprint_key")
                        .returning(EventCandidate.id)
                    )
                    candidate = (
                        self._session.get(EventCandidate, created_id) if created_id else None
                    )
                if len(members) == 1 and candidate is not None and candidate.job_id is None:
                    new_singletons += 1
                if (
                    candidate is None
                    or candidate.status != "pending"
                    or candidate.job_id is not None
                ):
                    continue
                if not ai_enabled:
                    continue
                version, _, _ = MonitorTopicService(
                    self._session
                ).get_current_topic_rules_and_sources_in_transaction(
                    owner_id=owner_id, topic_id=topic_id
                )
                operation_id = uuid5(EVENT_OPERATION_NAMESPACE, str(candidate.id))
                job = JobService(self._session, clock=self._clock).accept_in_transaction(
                    owner_id=owner_id,
                    command=JobAcceptanceInput(
                        operation_id=operation_id,
                        kind="events.cluster",
                        observation=JobObservationContext(
                            configuration_ref=f"topic:{topic_id}",
                            configuration_version=int(version),
                        ),
                        scope={
                            "candidate_id": str(candidate.id),
                            **(
                                freeze_event_ai_scope_in_transaction(
                                    self._session, owner_id=owner_id, settings=self._settings
                                )
                                if self._settings is not None
                                else {}
                            ),
                        },
                    ),
                )
                candidate.job_id = job.id
                candidate.updated_at = now
                accepted += 1
        return accepted

    def confirm_in_transaction(
        self,
        *,
        candidate_id: UUID,
        owner_id: UUID,
        decision: EventDecision,
        ai_call_id: UUID,
        now: datetime,
    ) -> UUID | None:
        if not self._session.in_transaction():
            raise RuntimeError("event confirmation requires the caller's transaction")
        candidate = self._session.scalar(
            select(EventCandidate).where(
                EventCandidate.id == candidate_id,
                EventCandidate.owner_id == owner_id,
            )
        )
        if candidate is None:
            raise EventCandidateConflictError("candidate_missing")
        # Use one lock order for automatic and future manual changes: topic, then candidate.
        MonitorTopicService(self._session).lock_topic_for_event_commit_in_transaction(
            owner_id=owner_id, topic_id=candidate.topic_id
        )
        candidate = self._session.scalar(
            select(EventCandidate)
            .where(EventCandidate.id == candidate_id, EventCandidate.owner_id == owner_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if candidate is None:
            raise EventCandidateConflictError("candidate_missing")
        if candidate.status == "confirmed":
            return candidate.event_id
        if candidate.status == "rejected":
            return None
        if candidate.status != "pending":
            raise EventCandidateConflictError("candidate_not_pending")
        expected_ids = {UUID(value) for value in candidate.member_version_ids}
        if set(decision.member_version_ids) != expected_ids:
            raise EventCandidateConflictError("invalid_member_ids")
        target: Event | None = None
        context: tuple[EventMember, ...] = ()
        if candidate.expected_event_revisions:
            if len(candidate.expected_event_revisions) != 1:
                raise EventCandidateConflictError("manual_revision_conflict")
            target_id, revision = next(iter(candidate.expected_event_revisions.items()))
            target = self._session.scalar(
                select(Event)
                .where(
                    Event.id == UUID(target_id),
                    Event.owner_id == owner_id,
                    Event.topic_id == candidate.topic_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if target is None or target.status != "active" or target.revision != revision:
                raise EventCandidateConflictError("manual_revision_conflict")
            context = _candidate_context_members(self._session, candidate)
            if not context or any(member.removed_revision is not None for member in context):
                raise EventCandidateConflictError("manual_revision_conflict")
        current = _load_candidate_inputs(self._session, candidate=candidate, now=now)
        if {item.content_version_id for item in current} != expected_ids:
            raise EventCandidateConflictError("input_changed")
        if not _candidate_material_matches(self._session, candidate=candidate, members=current):
            raise EventCandidateConflictError("input_changed")
        context_ids = {member.content_version_id for member in context}
        additions = [item for item in current if item.content_version_id not in context_ids]
        if not additions:
            raise EventCandidateConflictError("manual_revision_conflict")
        assigned = self._session.scalar(
            select(EventMember.id)
            .where(
                EventMember.owner_id == owner_id,
                EventMember.topic_id == candidate.topic_id,
                EventMember.content_id.in_([item.content_id for item in additions]),
                EventMember.removed_revision.is_(None),
            )
            .limit(1)
        )
        if assigned is not None:
            raise EventCandidateConflictError("manual_revision_conflict")
        protected = self._session.scalar(
            select(EventGroupingOverride.content_id)
            .where(
                EventGroupingOverride.owner_id == owner_id,
                EventGroupingOverride.topic_id == candidate.topic_id,
                EventGroupingOverride.content_id.in_([item.content_id for item in additions]),
                EventGroupingOverride.mode.in_(("manual", "standalone")),
            )
            .limit(1)
        )
        if protected is not None:
            raise EventCandidateConflictError("manual_revision_conflict")
        source_modes = load_event_input_source_modes_in_transaction(
            self._session, owner_id=owner_id, inputs=current, now=now
        )
        if any(source_modes[item.content_version_id] == "isolated" for item in additions):
            raise EventCandidateConflictError("source_role_changed")
        if target is None and all(
            source_modes[item.content_version_id] == "signal" for item in additions
        ):
            raise EventCandidateConflictError("signal_only")
        candidate.ai_call_id = ai_call_id
        candidate.updated_at = now
        if target is not None and decision.same_event:
            ensure_legacy_facts_in_transaction(self._session, event=target, now=now)
        root_fact_id = (
            self._session.scalar(
                select(EventFactAssignment.fact_id).where(
                    EventFactAssignment.owner_id == owner_id,
                    EventFactAssignment.event_id == target.id,
                    EventFactAssignment.relation == "root",
                    EventFactAssignment.removed_revision.is_(None),
                )
            )
            if target is not None
            else None
        )
        try:
            decision = constrain_event_decision(decision, current, root_fact_id=root_fact_id)
        except ValueError as error:
            raise EventCandidateConflictError(str(error)) from error
        if not decision.same_event:
            candidate.status = "rejected"
            return None
        first = min(
            (item for item in current if item.editorial_scope != "composite"),
            key=lambda item: item.first_seen_at,
        )
        if target is not None:
            event_id = target.id
            target.revision += 1
            added_revision = target.revision
            if first.first_seen_at < target.first_seen_at:
                target.first_seen_at = first.first_seen_at
                target.first_seen_basis = first.first_seen_basis
            target.updated_at = now
        else:
            event_id = uuid4()
            self._session.add(
                Event(
                    id=event_id,
                    owner_id=owner_id,
                    topic_id=candidate.topic_id,
                    revision=1,
                    title=decision.title.strip() if decision.title else "",
                    summary=decision.summary.strip() if decision.summary else "",
                    first_seen_at=first.first_seen_at,
                    first_seen_basis=first.first_seen_basis,
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            added_revision = 1
        for item in additions:
            self._session.add(
                EventMember(
                    id=uuid4(),
                    owner_id=owner_id,
                    topic_id=candidate.topic_id,
                    event_id=event_id,
                    content_id=item.content_id,
                    content_version_id=item.content_version_id,
                    observation_id=item.observation_id,
                    observation_source_key=item.observation_source_key,
                    input_manifest=event_member_input_manifest(item),
                    source_key=item.source_key,
                    representative_comment_id=item.representative_comment_id,
                    representative_comment_observation_id=(
                        item.representative_comment_observation_id
                    ),
                    added_revision=added_revision,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=now,
                )
            )
        candidate.event_id = event_id
        candidate.status = "confirmed"
        self._session.flush()
        event = self._session.get(Event, event_id)
        assert event is not None
        try:
            record_candidate_facts_in_transaction(
                self._session,
                candidate=candidate,
                event=event,
                decision=decision,
                ai_call_id=ai_call_id,
                now=now,
                signal_version_ids=frozenset(
                    identity for identity, mode in source_modes.items() if mode == "signal"
                ),
                input_frames={item.content_version_id: item.editorial_frame for item in current},
                input_scopes={item.content_version_id: item.editorial_scope for item in current},
                input_times={
                    item.content_version_id: (item.first_seen_at, item.first_seen_basis)
                    for item in current
                },
            )
        except FactGroupingConflictError as error:
            raise EventCandidateConflictError(str(error)) from error
        if target is not None:
            invalidate_event_derived_in_transaction(self._session, event=event, now=now)
        for override in self._session.scalars(
            select(EventGroupingOverride).where(
                EventGroupingOverride.owner_id == owner_id,
                EventGroupingOverride.topic_id == candidate.topic_id,
                EventGroupingOverride.content_id.in_([item.content_id for item in additions]),
                EventGroupingOverride.mode == "regroup_pending",
            )
        ):
            self._session.delete(override)
        return event_id

    def fail_in_transaction(
        self,
        *,
        candidate_id: UUID,
        owner_id: UUID,
        error_code: str,
        ai_call_id: UUID | None,
        now: datetime,
    ) -> None:
        candidate = self._session.scalar(
            select(EventCandidate)
            .where(EventCandidate.id == candidate_id, EventCandidate.owner_id == owner_id)
            .with_for_update()
        )
        if candidate is not None and candidate.status == "pending":
            candidate.status = "failed"
            candidate.error_code = error_code
            candidate.ai_call_id = ai_call_id
            candidate.updated_at = now
            assessment = self._session.scalar(
                select(EventGroupingAssessment).where(
                    EventGroupingAssessment.owner_id == owner_id,
                    EventGroupingAssessment.candidate_id == candidate_id,
                )
            )
            if assessment is not None:
                assessment.status = (
                    "stale"
                    if error_code
                    in {"input_changed", "manual_revision_conflict", "fact_revision_conflict"}
                    else "failed"
                )
                assessment.error_code = error_code
                assessment.ai_call_id = ai_call_id
                assessment.updated_at = now


class EventClusterExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, message: JobMessage, lease: ExecutionLease | None = None) -> JobCompletion:
        if message.kind != "events.cluster":
            raise ValueError("event executor received another task kind")
        if not self._settings.events_cluster_enabled:
            raise self._failure(
                "event_clustering_disabled", JobFailureCategory.CONFIGURATION_UNAVAILABLE
            )
        completion: AiCompletion | None = None
        try:
            with self._sessions() as session, session.begin():
                self._guard(session, lease)
                configuration = load_job_execution_configuration(session, job_id=message.job_id)
                if (
                    configuration is None
                    or configuration.owner_id != message.owner_id
                    or configuration.operation_id != message.operation_id
                    or configuration.kind != message.kind
                    or configuration.observation.configuration_ref != message.configuration_ref
                    or configuration.observation.configuration_version
                    != message.configuration_version
                ):
                    raise ValueError("event job configuration does not match the message")
                candidate_id = UUID(str(configuration.scope["candidate_id"]))
                candidate = session.scalar(
                    select(EventCandidate)
                    .where(EventCandidate.id == candidate_id)
                    .with_for_update()
                )
                if (
                    candidate is None
                    or candidate.owner_id != message.owner_id
                    or candidate.job_id != message.job_id
                ):
                    raise ValueError("event candidate does not belong to the job")
                if candidate.status in {"confirmed", "rejected"}:
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                if (
                    candidate.status == "failed"
                    and getattr(message, "retry_count", 0) > 0
                    and candidate.error_code in _RETRYABLE_CANDIDATE_ERRORS
                ):
                    candidate.status = "pending"
                    candidate.error_code = None
                    candidate.ai_call_id = None
                    candidate.updated_at = self._clock()
                if candidate.status != "pending":
                    raise self._failure(
                        "event_candidate_not_pending", JobFailureCategory.INVALID_INPUT
                    )
                members = _load_candidate_inputs(session, candidate=candidate, now=self._clock())
                if {member.content_version_id for member in members} != {
                    UUID(value) for value in candidate.member_version_ids
                }:
                    raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
                if not _candidate_material_matches(session, candidate=candidate, members=members):
                    raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
                context = _candidate_context_members(session, candidate)
                if any(member.removed_revision is not None for member in context):
                    raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
                MonitorTopicService(session).lock_topic_for_event_commit_in_transaction(
                    owner_id=message.owner_id, topic_id=candidate.topic_id
                )
                for target_id in sorted(candidate.expected_event_revisions):
                    target = session.scalar(
                        select(Event)
                        .where(Event.owner_id == message.owner_id, Event.id == UUID(target_id))
                        .with_for_update()
                    )
                    if (
                        target is None
                        or target.status != "active"
                        or target.revision != (candidate.expected_event_revisions[target_id])
                    ):
                        raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
                    ensure_legacy_facts_in_transaction(session, event=target, now=self._clock())
                assessment = session.scalar(
                    select(EventGroupingAssessment)
                    .where(
                        EventGroupingAssessment.owner_id == message.owner_id,
                        EventGroupingAssessment.candidate_id == candidate.id,
                    )
                    .with_for_update()
                )
                if assessment is not None and assessment.error_code in {
                    "request_started",
                    "result_unknown",
                }:
                    raise self._failure("event_result_unknown", JobFailureCategory.INVALID_RESPONSE)
                if (
                    assessment is not None
                    and assessment.status == "pending"
                    and assessment.error_code == "response_saved"
                ):
                    saved = assessment.decisions[0] if len(assessment.decisions) == 1 else {}
                    output = saved.get("model_output")
                    if not isinstance(output, dict) or assessment.ai_call_id is None:
                        raise self._failure(
                            "event_result_unknown", JobFailureCategory.INVALID_RESPONSE
                        )
                    saved_call = load_verified_event_call_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        call_id=assessment.ai_call_id,
                        purpose="events.cluster",
                    )
                    if saved_call is None:
                        raise self._failure(
                            "event_result_unknown", JobFailureCategory.INVALID_RESPONSE
                        )
                    completion = AiCompletion(
                        provider=saved_call.provider,
                        model=saved_call.model,
                        call_id=assessment.ai_call_id,
                        output=output,
                        usage=AiTokenUsage(),
                        duration_ms=0,
                    )
                    fact_context = assessment.input_snapshot
                else:
                    fact_context = freeze_fact_context_in_transaction(
                        session, candidate=candidate, now=self._clock()
                    )
                    assessment = session.scalar(
                        select(EventGroupingAssessment).where(
                            EventGroupingAssessment.candidate_id == candidate.id
                        )
                    )
                    assert assessment is not None
                    assessment.error_code, assessment.updated_at = "request_started", self._clock()
                prompt = build_event_prompt(
                    members,
                    context_version_ids=tuple(member.content_version_id for member in context),
                    fact_context=fact_context,
                )
        except JobExecutionFailure as error:
            if error.error_code == "event_input_changed":
                self._mark_failed(candidate_id, message.owner_id, "input_changed", None)
            if error.error_code == "event_result_unknown":
                self._mark_failed(candidate_id, message.owner_id, "result_unknown", None)
            raise

        try:
            if completion is None:
                client = create_event_stage_client(
                    self._sessions,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    purpose="events.cluster",
                    settings=self._settings,
                    legacy_factory=create_ai_client,
                )
                try:
                    with self._sessions() as session:
                        completion = (
                            AiService(
                                session,
                                client,
                                clock=self._clock,
                                settings=self._settings,
                                guard=(lambda current_session: self._guard(current_session, lease))
                                if lease is not None
                                else None,
                                execution_epoch=lease.epoch if lease is not None else None,
                            )
                            .with_admission_guard(
                                lambda current_session: self._ai_admission_guard(
                                    current_session, message, lease, candidate_id, fact_context
                                )
                            )
                            .complete(
                                owner_id=message.owner_id,
                                job_id=message.job_id,
                                purpose="events.cluster",
                                prompt_version=EVENT_PROMPT_VERSION,
                                prompt=prompt,
                                output_schema=EVENT_OUTPUT_SCHEMA,
                            )
                        )
                finally:
                    client.close()
                # The complete response, not ledger metadata, is the recoverable stage.
                with self._sessions() as session, session.begin():
                    self._guard(session, lease)
                    assessment = session.scalar(
                        select(EventGroupingAssessment)
                        .where(
                            EventGroupingAssessment.owner_id == message.owner_id,
                            EventGroupingAssessment.candidate_id == candidate_id,
                        )
                        .with_for_update()
                    )
                    if (
                        assessment is None
                        or assessment.status != "pending"
                        or assessment.error_code != "request_started"
                    ):
                        raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
                    assessment.decisions = [{"model_output": completion.output}]
                    assessment.ai_call_id = completion.call_id
                    assessment.error_code, assessment.updated_at = "response_saved", self._clock()
        except JobExecutionFailure as error:
            if error.error_code == "event_input_changed":
                self._mark_failed(candidate_id, message.owner_id, "input_changed", None)
            raise
        except AiCallError as error:
            unknown = error.code in {AiFailureCode.TIMEOUT, AiFailureCode.FAILED}
            self._mark_failed(
                candidate_id,
                message.owner_id,
                "result_unknown" if unknown else f"ai_{error.code.value}",
                error.call_id,
            )
            category = (
                JobFailureCategory.RATE_LIMITED
                if error.code is AiFailureCode.RATE_LIMITED
                else JobFailureCategory.CONFIGURATION_UNAVAILABLE
                if error.code is AiFailureCode.UNAVAILABLE
                else JobFailureCategory.INVALID_RESPONSE
                if error.code is AiFailureCode.INVALID_OUTPUT
                else JobFailureCategory.TRANSIENT
            )
            raise self._failure(
                "event_result_unknown" if unknown else f"event_ai_{error.code.value}",
                JobFailureCategory.INVALID_RESPONSE if unknown else category,
            ) from error

        try:
            decision = EventDecision.model_validate_json(json.dumps(completion.output))
        except (ValidationError, TypeError, ValueError) as error:
            self._mark_failed(
                candidate_id, message.owner_id, "invalid_model_output", completion.call_id
            )
            raise self._failure(
                "event_invalid_model_output", JobFailureCategory.INVALID_RESPONSE
            ) from error
        if completion.call_id is None:
            raise RuntimeError("AI ledger returned no call id")
        try:
            with self._sessions() as session, session.begin():
                self._guard(session, lease)
                EventCandidateService(session, clock=self._clock).confirm_in_transaction(
                    candidate_id=candidate_id,
                    owner_id=message.owner_id,
                    decision=decision,
                    ai_call_id=completion.call_id,
                    now=self._clock(),
                )
        except EventCandidateConflictError as error:
            code = str(error)
            self._mark_failed(candidate_id, message.owner_id, code, completion.call_id)
            raise self._failure(f"event_{code}", JobFailureCategory.INVALID_INPUT) from error
        return JobCompletion(status=JobStatus.SUCCEEDED)

    def _guard(self, session: Session, lease: ExecutionLease | None) -> None:
        if lease is not None:
            JobExecutionService(
                session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
            ).require_current_lease_in_transaction(lease)

    def _ai_admission_guard(
        self,
        session: Session,
        message: JobMessage,
        lease: ExecutionLease | None,
        candidate_id: UUID,
        fact_context: dict[str, object],
    ) -> None:
        self._guard(session, lease)
        if lease is not None:
            if lease.job_id != message.job_id:
                raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
            JobExecutionService(
                session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
            ).require_current_operation_in_transaction(
                lease, owner_id=message.owner_id, operation_id=message.operation_id
            )
        configuration = load_job_execution_configuration(session, job_id=message.job_id)
        if (
            configuration is None
            or configuration.owner_id != message.owner_id
            or configuration.operation_id != message.operation_id
            or configuration.kind != message.kind
            or configuration.observation.configuration_ref != message.configuration_ref
            or configuration.observation.configuration_version != message.configuration_version
            or configuration.scope.get("candidate_id") != str(candidate_id)
        ):
            raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
        candidate = session.scalar(
            select(EventCandidate)
            .where(EventCandidate.id == candidate_id, EventCandidate.owner_id == message.owner_id)
            .with_for_update()
        )
        if candidate is None or candidate.job_id != message.job_id or candidate.status != "pending":
            raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
        MonitorTopicService(session).lock_topic_for_event_commit_in_transaction(
            owner_id=message.owner_id, topic_id=candidate.topic_id
        )
        members = _load_candidate_inputs(session, candidate=candidate, now=self._clock())
        if (
            {member.content_version_id for member in members}
            != {UUID(value) for value in candidate.member_version_ids}
            or not _candidate_material_matches(session, candidate=candidate, members=members)
            or any(
                member.removed_revision is not None
                for member in _candidate_context_members(session, candidate)
            )
        ):
            raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
        for identity, revision in sorted(candidate.expected_event_revisions.items()):
            target = session.scalar(
                select(Event)
                .where(Event.owner_id == message.owner_id, Event.id == UUID(identity))
                .with_for_update()
            )
            if target is None or target.status != "active" or target.revision != revision:
                raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
        assessment = session.scalar(
            select(EventGroupingAssessment)
            .where(
                EventGroupingAssessment.owner_id == message.owner_id,
                EventGroupingAssessment.candidate_id == candidate_id,
            )
            .with_for_update()
        )
        if (
            assessment is None
            or assessment.status != "pending"
            or assessment.error_code != "request_started"
            or assessment.input_snapshot != fact_context
            or load_fact_context_in_transaction(session, candidate=candidate) != fact_context
        ):
            raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)

    def _mark_failed(
        self, candidate_id: UUID, owner_id: UUID, code: str, call_id: UUID | None
    ) -> None:
        with self._sessions() as session, session.begin():
            EventCandidateService(session, clock=self._clock).fail_in_transaction(
                candidate_id=candidate_id,
                owner_id=owner_id,
                error_code=code,
                ai_call_id=call_id,
                now=self._clock(),
            )

    def _failure(self, code: str, category: JobFailureCategory) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self._clock(),
            next_action="检查候选、输入版本与模型预算后人工重试",
            manual_retry_allowed=code != "event_result_unknown",
        )
