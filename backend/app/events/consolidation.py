from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_schemas import FrozenAiRouting
from ai.schemas import AiCallError, AiCompletion, AiFailureCode
from ai.services import AiService, create_ai_client
from analysis.event_reading import load_editorial_event_inputs_for_versions_in_transaction
from content.event_reading import load_event_member_content_in_transaction
from content.observation_inputs import freeze_observation_inputs_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from events.ai_execution import (
    create_event_stage_client,
    event_ai_contract,
    freeze_event_ai_scope_in_transaction,
    load_event_ai_contract_in_transaction,
    load_verified_event_call_in_transaction,
)
from events.corrections import EventCorrectionService
from events.fact_models import (
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingOverride,
)
from events.fact_schemas import EventCorrectionInput
from events.heat import resolve_attention_source
from events.heat_models import EventAttentionSource
from events.models import Event, EventMember
from events.observation_inputs import (
    event_content_reference,
    load_fact_observation_inputs_in_transaction,
)
from events.relations import (
    RelationPairOutput,
    RelationReportInput,
    frames_conflict,
    relation_frame,
    relation_pair_request,
)
from events.story_models import EventStoryLink
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import (
    JobService,
    load_job_execution_configuration,
    load_job_execution_configuration_by_operation,
)
from monitors.services import MonitorTopicService

_NAMESPACE = UUID("62d9a1b1-c6c9-4c80-ad90-7e7cbef088f1")
_POSITIVE = {"SAME_OCCURRENCE", "SAME_STORY"}


class StoryReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    content_id: UUID
    content_version_id: UUID
    event_member_id: UUID
    fact_id: UUID
    event_id: UUID
    participant_key: str
    source_revision: int
    input: RelationReportInput
    observation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = ()


class StoryRoot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID
    topic_id: UUID
    revision: int
    fact_id: UUID
    fact_revision: int
    first_seen_at: datetime
    reports: tuple[StoryReport, ...]


def consolidation_decision(
    first: RelationPairOutput,
    second: RelationPairOutput | None,
    *,
    reports: tuple[RelationReportInput, RelationReportInput] | None = None,
) -> Literal["separate", "review", "merge"]:
    if reports is not None and (
        frames_conflict(reports[0].frame, reports[1].frame, independent_updates_only=True)
        or (
            first.relation == "SAME_OCCURRENCE"
            and frames_conflict(reports[0].frame, reports[1].frame)
        )
        or (
            second is not None
            and second.relation == "SAME_OCCURRENCE"
            and frames_conflict(reports[0].frame, reports[1].frame)
        )
    ):
        return "separate"
    if first.relation not in _POSITIVE or first.confidence < 0.8:
        return "separate"
    if second is None:
        return "review"
    return "merge" if second.relation in _POSITIVE and second.confidence >= 0.75 else "separate"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_story_roots_in_transaction(
    session: Session, *, owner_id: UUID, event_ids: tuple[UUID, ...], now: datetime
) -> dict[UUID, StoryRoot]:
    """Read confirmed ordinary roots from real fixed, permitted editorial reports."""
    if not session.in_transaction() or now.utcoffset() is None or len(event_ids) > 100:
        raise ValueError("story roots require a bounded aware caller transaction")
    sources = list(
        session.scalars(
            select(EventAttentionSource).where(EventAttentionSource.owner_id == owner_id)
        )
    )
    result = {}
    for event in session.scalars(
        select(Event).where(
            Event.owner_id == owner_id, Event.id.in_(event_ids), Event.status == "active"
        )
    ):
        root = session.scalar(
            select(EventFactAssignment).where(
                EventFactAssignment.owner_id == owner_id,
                EventFactAssignment.event_id == event.id,
                EventFactAssignment.removed_revision.is_(None),
                EventFactAssignment.relation == "root",
            )
        )
        if root is None:
            continue
        fact = session.get(EventFact, root.fact_id)
        if fact is None or fact.status != "confirmed":
            continue
        members = list(
            session.scalars(
                select(EventFactMember)
                .where(
                    EventFactMember.owner_id == owner_id,
                    EventFactMember.event_id == event.id,
                    EventFactMember.removed_revision.is_(None),
                    EventFactMember.role.in_(("primary", "report")),
                )
                .order_by(
                    EventFactMember.fact_id != root.fact_id,
                    EventFactMember.role != "primary",
                    EventFactMember.created_at,
                )
                .limit(20)
            )
        )
        event_members = {
            member.id: member
            for member in session.scalars(
                select(EventMember).where(
                    EventMember.owner_id == owner_id,
                    EventMember.id.in_({row.event_member_id for row in members}),
                    EventMember.removed_revision.is_(None),
                )
            )
        }
        readings = load_event_member_content_in_transaction(
            session,
            owner_id=owner_id,
            references=tuple(
                event_content_reference(event_members[row.event_member_id])
                for row in members
                if row.event_member_id in event_members
            ),
            now=now,
        )
        reports = []
        editorial = load_editorial_event_inputs_for_versions_in_transaction(
            session,
            owner_id=owner_id,
            since=datetime.min.replace(tzinfo=now.tzinfo),
            now=now,
            version_ids=tuple(member.content_version_id for member in members),
        )
        fact_inputs = load_fact_observation_inputs_in_transaction(
            session, owner_id=owner_id, fact_ids=tuple({row.fact_id for row in members}), now=now
        )
        for member in members:
            if (
                member.content_version_id in editorial
                and editorial[member.content_version_id].scope != "single"
            ):
                continue
            event_member = event_members.get(member.event_member_id)
            if event_member is None:
                continue
            if (event_member.input_manifest or {}).get("editorial_scope") in {
                "composite",
                "unknown",
            }:
                continue
            member_fact = session.get(EventFact, member.fact_id)
            if (
                member_fact is None
                or member_fact.status != "confirmed"
                or member.fact_id not in fact_inputs
            ):
                continue
            reading = readings.get(event_content_reference(event_member))
            source = resolve_attention_source(sources, reading) if reading else None
            if (
                reading is None
                or reading.source_key != event_member.source_key
                or source is None
                or source.mode != "editorial"
                or reading.current_visibility is None
                or reading.current_visibility.status != "visible"
            ):
                continue
            version = reading.observation.content_version
            assert version is not None
            if not version.title:
                continue
            source_identity = (
                "group:" + source.group_key
                if source.group_key
                else "owner:" + source.owner_entity_key
                if source.owner_entity_key
                else "source:" + str(source.id)
            )
            reports.append(
                StoryReport(
                    content_id=member.content_id,
                    content_version_id=member.content_version_id,
                    event_member_id=member.event_member_id,
                    fact_id=member.fact_id,
                    event_id=member.event_id,
                    participant_key=source_identity,
                    source_revision=source.revision,
                    input=RelationReportInput(
                        title=version.title[:500],
                        source=source.name[:200],
                        first_party=source.first_party,
                        published_at=reading.observation.published_at,
                        summary=(version.body or "")[:4000] or None,
                        frame=relation_frame(member_fact.frame),
                    ),
                    observation_id=reading.observation.id,
                    input_observation_ids=freeze_observation_inputs_in_transaction(
                        session,
                        owner_id=owner_id,
                        observation_ids=tuple(
                            dict.fromkeys(
                                (
                                    reading.observation.id,
                                    *event_content_reference(event_member).input_observation_ids,
                                    *fact_inputs[member.fact_id],
                                )
                            )
                        ),
                        now=now,
                    ),
                )
            )
        if reports and reports[0].fact_id == root.fact_id:
            result[event.id] = StoryRoot(
                event_id=event.id,
                topic_id=event.topic_id,
                revision=event.revision,
                fact_id=fact.id,
                fact_revision=fact.revision,
                first_seen_at=fact.first_seen_at,
                reports=tuple(reports),
            )
    return result


def _pair_fingerprint(roots: tuple[StoryRoot, StoryRoot], model: str) -> str:
    version, _, _ = relation_pair_request(roots[0].reports[0].input, roots[1].reports[0].input)
    return _hash(
        {
            "roots": [root.model_dump(mode="json") for root in roots],
            "model": model,
            "prompt_version": version,
        }
    )


def _automatic_merge(
    session: Session,
    *,
    owner_id: UUID,
    roots: tuple[StoryRoot, StoryRoot],
    operation_id: UUID,
    same_occurrence: bool,
    now: datetime,
) -> None:
    topic = roots[0].topic_id
    MonitorTopicService(session).lock_topic_for_event_commit_in_transaction(
        owner_id=owner_id, topic_id=topic
    )
    events = {
        row.id: row
        for row in session.scalars(
            select(Event)
            .where(Event.owner_id == owner_id, Event.id.in_([r.event_id for r in roots]))
            .order_by(Event.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    if len(events) != 2 or any(
        events[root.event_id].revision != root.revision or events[root.event_id].status != "active"
        for root in roots
    ):
        raise ApplicationError("event_revision_conflict")
    members = list(
        session.scalars(
            select(EventMember).where(
                EventMember.owner_id == owner_id,
                EventMember.event_id.in_(events),
                EventMember.removed_revision.is_(None),
            )
        )
    )
    if (
        any(member.assignment_origin == "manual" for member in members)
        or session.scalar(
            select(EventGroupingOverride.content_id)
            .where(
                EventGroupingOverride.owner_id == owner_id,
                EventGroupingOverride.topic_id == topic,
                EventGroupingOverride.content_id.in_([row.content_id for row in members]),
                EventGroupingOverride.mode.in_(("manual", "standalone", "regroup_pending")),
            )
            .limit(1)
        )
        is not None
    ):
        raise ApplicationError("event_revision_conflict")
    command = EventCorrectionInput(
        operation_id=operation_id,
        kind="merge",
        reason="自动故事融合: 两轮固定根报道复核通过",
        expected_revisions={root.event_id: root.revision for root in roots},
        target_event_id=roots[0].event_id,
    )
    service = EventCorrectionService(session)
    service._correct_locked(
        owner_id=owner_id,
        actor_id=owner_id,
        topic_id=topic,
        events=events,
        command=command,
        fingerprint=bytes.fromhex(_hash(command.model_dump(mode="json"))),
        now=now,
        automatic=True,
    )
    if same_occurrence:
        command = EventCorrectionInput(
            operation_id=uuid5(operation_id, "same-occurrence"),
            kind="merge_facts",
            reason="自动事实融合: 两轮同一次发生复核通过",
            expected_revisions={roots[0].event_id: events[roots[0].event_id].revision},
            fact_ids=[root.fact_id for root in roots],
            target_fact_id=roots[0].fact_id,
        )
        service._correct_locked(
            owner_id=owner_id,
            actor_id=owner_id,
            topic_id=topic,
            events={roots[0].event_id: events[roots[0].event_id]},
            command=command,
            fingerprint=bytes.fromhex(_hash(command.model_dump(mode="json"))),
            now=now,
            automatic=True,
        )


def _contacts(roots: tuple[StoryRoot, StoryRoot]) -> tuple[tuple[StoryReport, StoryRoot], ...]:
    contacts, participants = [], set()
    for index, root in enumerate(roots):
        for report in root.reports:
            if report.participant_key not in participants:
                participants.add(report.participant_key)
                contacts.append((report, roots[1 - index]))
    return tuple(contacts[:2])


class EventConsolidationService:
    def __init__(self, session: Session, settings: Settings):
        self._session, self._settings = session, settings

    def _candidate_pairs(self, *, now: datetime) -> Iterator[tuple[UUID, UUID, UUID]]:
        after: tuple[UUID, UUID, UUID] | None = None
        while True:
            parameters: dict[str, object] = {"since": now - timedelta(days=14)}
            continuation = ""
            if after is not None:
                continuation = "AND (a.owner_id,a.id,b.id) > (:owner,:left,:right) "
                parameters.update(owner=after[0], left=after[1], right=after[2])
            pairs = [
                cast(tuple[UUID, UUID, UUID], tuple(row))
                for row in self._session.execute(
                    text(
                        "SELECT a.owner_id,a.id,b.id FROM events a JOIN events b ON "
                        "a.owner_id=b.owner_id AND a.topic_id=b.topic_id AND a.id<b.id "
                        "WHERE a.status='active' AND b.status='active' "
                        "AND a.updated_at>:since AND b.updated_at>:since "
                        "AND similarity(a.title,b.title)>=0.4 "
                        + continuation
                        + "ORDER BY a.owner_id,a.id,b.id LIMIT 100"
                    ),
                    parameters,
                )
            ]
            yield from pairs
            if len(pairs) < 100:
                return
            # Admitted or unreadable roots still consume raw candidate positions.
            # Continue past them rather than letting a fixed first page hide new pairs.
            after = pairs[-1]

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        if not self._session.in_transaction() or now.utcoffset() is None:
            raise ValueError("consolidation scan requires caller transaction")
        if not ai_enabled:
            return 0
        accepted = 0
        for owner, left, right in self._candidate_pairs(now=now):
            roots_by_id = load_story_roots_in_transaction(
                self._session, owner_id=owner, event_ids=(left, right), now=now
            )
            if len(roots_by_id) != 2:
                continue
            roots = cast(
                tuple[StoryRoot, StoryRoot],
                tuple(
                    sorted(
                        roots_by_id.values(),
                        key=lambda root: (root.first_seen_at, root.event_id.hex),
                    )
                ),
            )
            ai_scope = freeze_event_ai_scope_in_transaction(
                self._session, owner_id=owner, settings=self._settings
            )
            contract = event_ai_contract(
                FrozenAiRouting.model_validate_json(ai_scope["ai_routing"]),
                ("events.consolidate.judge", "events.consolidate.review"),
            )
            fingerprint = _pair_fingerprint(roots, contract)
            version, _, _ = MonitorTopicService(
                self._session
            ).get_current_topic_rules_and_sources_in_transaction(
                owner_id=owner, topic_id=roots[0].topic_id
            )
            operation_id = uuid5(_NAMESPACE, fingerprint)
            previous = load_job_execution_configuration_by_operation(
                self._session, owner_id=owner, operation_id=operation_id, kind="events.consolidate"
            )
            if previous is not None:
                continue
            JobService(self._session).accept_in_transaction(
                owner_id=owner,
                command=JobAcceptanceInput(
                    operation_id=operation_id,
                    kind="events.consolidate",
                    observation=JobObservationContext(
                        configuration_ref=f"topic:{roots[0].topic_id}",
                        configuration_version=version,
                    ),
                    scope={
                        "first_event_id": str(roots[0].event_id),
                        "second_event_id": str(roots[1].event_id),
                        "input_fingerprint": fingerprint,
                        "model": contract,
                        **ai_scope,
                    },
                ),
            )
            if previous is None:
                accepted += 1
                if accepted >= 20:
                    break
        return accepted


def load_related_story_ids_in_transaction(
    session: Session, *, owner_id: UUID, event_id: UUID, now: datetime
) -> dict[UUID, int]:
    """Links grant no membership: recheck both roots and every frozen contact report."""
    rows = list(
        session.scalars(
            select(EventStoryLink)
            .where(
                EventStoryLink.owner_id == owner_id,
                (EventStoryLink.first_event_id == event_id)
                | (EventStoryLink.second_event_id == event_id),
            )
            .limit(99)
        )
    )
    identities = {event_id} | {
        identity for row in rows for identity in (row.first_event_id, row.second_event_id)
    }
    roots = load_story_roots_in_transaction(
        session, owner_id=owner_id, event_ids=tuple(identities), now=now
    )
    result = {}
    for row in rows:
        left, right = roots.get(row.first_event_id), roots.get(row.second_event_id)
        if (
            left is None
            or right is None
            or left.revision != row.first_revision
            or right.revision != row.second_revision
        ):
            continue
        current = {
            str(report.content_id): report.model_dump(mode="json")
            for root in (left, right)
            for report in root.reports
        }
        participants, reports = set(), set()
        valid = True
        for frozen in row.evidence:
            report = {
                key: value for key, value in frozen.items() if key not in {"call_id", "answer"}
            }
            answer = RelationPairOutput.model_validate(frozen["answer"])
            if (
                current.get(str(frozen["content_id"])) != report
                or answer.relation not in _POSITIVE
                or answer.confidence < 0.8
            ):
                valid = False
                break
            participants.add(str(frozen["participant_key"]))
            reports.add(str(frozen["content_id"]))
        if valid and len(participants) >= 2 and len(reports) >= 2:
            result[
                row.second_event_id if row.first_event_id == event_id else row.first_event_id
            ] = len(reports)
    return result


class EventConsolidationExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._sessions, self._settings = sessions, settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def _execution(self, session: Session) -> JobExecutionService:
        return JobExecutionService(
            session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
        )

    def _guard(self, session: Session, message: JobMessage, lease: ExecutionLease) -> None:
        self._execution(session).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )

    def _failure(self, code: str, *, retry: bool = False) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_RESPONSE,
            occurred_at=self._clock(),
            manual_retry_allowed=retry,
            next_action="核对固定根报道、阶段回执及人工修订后重试",
        )

    def _load(
        self, session: Session, message: JobMessage, lease: ExecutionLease
    ) -> tuple[ExecutionLease, dict[str, Any], tuple[StoryRoot, StoryRoot] | None]:
        current = self._execution(session).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )
        configuration = load_job_execution_configuration(session, job_id=message.job_id)
        if (
            configuration is None
            or message.kind != "events.consolidate"
            or configuration.kind != message.kind
            or configuration.owner_id != message.owner_id
            or configuration.observation.configuration_ref != message.configuration_ref
            or configuration.observation.configuration_version != message.configuration_version
        ):
            raise self._failure("event_consolidation_input_changed")
        state = json.loads(str(current.checkpoint.get("consolidation_state", '{"outputs":{}}')))
        if state.get("completed"):
            return current, state, None
        for stage, saved in state.get("outputs", {}).items():
            try:
                call_id = UUID(str(saved["call_id"]))
            except (KeyError, TypeError, ValueError):
                raise self._failure("event_consolidation_invalid_saved_output") from None
            if (
                load_verified_event_call_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    call_id=call_id,
                    purpose=f"events.consolidate.{stage}",
                )
                is None
            ):
                raise self._failure("event_consolidation_invalid_saved_output")
        event_ids = (
            UUID(str(configuration.scope["first_event_id"])),
            UUID(str(configuration.scope["second_event_id"])),
        )
        by_id = load_story_roots_in_transaction(
            session, owner_id=message.owner_id, event_ids=event_ids, now=self._clock()
        )
        if len(by_id) != 2:
            raise self._failure("event_consolidation_input_changed")
        roots = (by_id[event_ids[0]], by_id[event_ids[1]])
        contract = load_event_ai_contract_in_transaction(
            session,
            owner_id=message.owner_id,
            job_id=message.job_id,
            purposes=("events.consolidate.judge", "events.consolidate.review"),
            legacy_model=self._settings.ai_model,
        )
        if (
            _pair_fingerprint(roots, contract) != configuration.scope["input_fingerprint"]
            or configuration.scope["model"] != contract
        ):
            raise self._failure("event_consolidation_input_changed")
        return current, state, roots

    def _save(self, session: Session, current: ExecutionLease, state: dict[str, Any]) -> None:
        self._execution(session).save_checkpoint_in_transaction(
            current,
            sequence=current.checkpoint_sequence + 1,
            checkpoint={
                **current.checkpoint,
                "consolidation_state": json.dumps(
                    state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            },
        )

    def _prepare(
        self, message: JobMessage, lease: ExecutionLease
    ) -> tuple[str, RelationReportInput, RelationReportInput] | None:
        with self._sessions() as session, session.begin():
            current, state, roots = self._load(session, message, lease)
            if roots is None:
                return None
            if state.get("pending_stage"):
                state["error"] = "event_consolidation_result_unknown"
                self._save(session, current, state)
                unknown = True
            else:
                unknown = False
                outputs = state["outputs"]
                if "judge" not in outputs:
                    step = ("judge", roots[0].reports[0].input, roots[1].reports[0].input)
                else:
                    first = RelationPairOutput.model_validate(outputs["judge"]["answer"])
                    second = (
                        RelationPairOutput.model_validate(outputs["review"]["answer"])
                        if "review" in outputs
                        else None
                    )
                    decision = consolidation_decision(
                        first,
                        second,
                        reports=(
                            roots[0].reports[0].input,
                            roots[1].reports[0].input,
                        ),
                    )
                    if decision == "review":
                        step = ("review", roots[1].reports[0].input, roots[0].reports[0].input)
                    elif decision == "merge":
                        assert second is not None
                        _automatic_merge(
                            session,
                            owner_id=message.owner_id,
                            roots=roots,
                            operation_id=message.operation_id,
                            same_occurrence=(
                                first.relation == "SAME_OCCURRENCE"
                                and second.relation == "SAME_OCCURRENCE"
                            ),
                            now=self._clock(),
                        )
                        state.update(
                            completed=True, result="merged", target_event_id=str(roots[0].event_id)
                        )
                        self._save(session, current, state)
                        return None
                    else:
                        contacts = _contacts(roots)
                        pending = next(
                            (
                                (index, pair)
                                for index, pair in enumerate(contacts)
                                if f"contact_{index}" not in outputs
                            ),
                            None,
                        )
                        if len(contacts) >= 2 and pending is not None:
                            index, (report, target) = pending
                            step = (f"contact_{index}", report.input, target.reports[0].input)
                        else:
                            evidence = []
                            for index, (report, _) in enumerate(contacts):
                                saved = outputs.get(f"contact_{index}")
                                if saved:
                                    answer = RelationPairOutput.model_validate(saved["answer"])
                                    if answer.relation in _POSITIVE and answer.confidence >= 0.8:
                                        evidence.append(
                                            {
                                                **report.model_dump(mode="json"),
                                                "call_id": saved["call_id"],
                                                "answer": saved["answer"],
                                            }
                                        )
                            if len(evidence) >= 2:
                                left, right = sorted(roots, key=lambda root: root.event_id.hex)
                                row = session.get(
                                    EventStoryLink,
                                    (message.owner_id, left.event_id, right.event_id),
                                )
                                if row is None:
                                    row = EventStoryLink(
                                        owner_id=message.owner_id,
                                        topic_id=left.topic_id,
                                        first_event_id=left.event_id,
                                        second_event_id=right.event_id,
                                        created_at=self._clock(),
                                    )
                                    session.add(row)
                                row.first_revision, row.second_revision = (
                                    left.revision,
                                    right.revision,
                                )
                                row.evidence, row.updated_at = evidence, self._clock()
                            state.update(
                                completed=True,
                                result="related" if len(evidence) >= 2 else "separate",
                            )
                            self._save(session, current, state)
                            return None
                state["pending_stage"] = step[0]
                self._save(session, current, state)
                return step
        if unknown:
            raise self._failure("event_consolidation_result_unknown")
        raise self._failure("event_consolidation_input_changed")

    def _save_response(
        self, message: JobMessage, lease: ExecutionLease, stage: str, completion: AiCompletion
    ) -> None:
        answer = RelationPairOutput.model_validate(completion.output)
        with self._sessions() as session, session.begin():
            current, state, _ = self._load(session, message, lease)
            if state.get("pending_stage") != stage or completion.call_id is None:
                raise self._failure("event_consolidation_input_changed")
            state["outputs"][stage] = {
                "answer": answer.model_dump(mode="json"),
                "call_id": str(completion.call_id),
            }
            state["pending_stage"] = None
            self._save(session, current, state)

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if not self._settings.events_cluster_enabled or not self._settings.ai_enabled:
            raise self._failure("event_clustering_disabled")
        for _ in range(5):
            try:
                step = self._prepare(message, lease)
                if step is None:
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                stage, first, second = step
                version, instructions, prompt = relation_pair_request(first, second)
                purpose = f"events.consolidate.{stage}"
                client = create_event_stage_client(
                    self._sessions,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    purpose=purpose,
                    settings=self._settings,
                    legacy_factory=create_ai_client,
                )
                try:
                    with self._sessions() as session:
                        completion = AiService(
                            session,
                            client,
                            clock=self._clock,
                            settings=self._settings,
                            guard=lambda current_session: self._guard(
                                current_session, message, lease
                            ),
                            execution_epoch=lease.epoch,
                        ).complete(
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            purpose=purpose,
                            prompt_version=version,
                            prompt=prompt,
                            instructions=instructions,
                            output_schema=RelationPairOutput.model_json_schema(),
                        )
                    self._save_response(message, lease, stage, completion)
                finally:
                    client.close()
            except AiCallError as error:
                known = error.code in {AiFailureCode.UNAVAILABLE, AiFailureCode.RATE_LIMITED}
                if known:
                    with self._sessions() as session, session.begin():
                        current, state, _ = self._load(session, message, lease)
                        state["pending_stage"] = None
                        state["error"] = f"ai_{error.code.value}"
                        self._save(session, current, state)
                raise self._failure(
                    f"ai_{error.code.value}" if known else "event_consolidation_result_unknown",
                    retry=known,
                ) from None
            except (ValidationError, ApplicationError) as error:
                raise self._failure(
                    "event_consolidation_input_changed"
                    if isinstance(error, ApplicationError)
                    else "event_consolidation_invalid_output"
                ) from None
        raise self._failure("event_consolidation_stage_limit")
