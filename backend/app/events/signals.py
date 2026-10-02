"""Native 48h waiting and existing-vector 6h recall, committed through the original Job lease."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import cast
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai.adapters.embeddings import cosine
from ai.capability_schemas import FrozenAiRouting
from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService, create_ai_client
from content.event_reading import (
    list_recent_signal_content_in_transaction,
    load_event_member_content_in_transaction,
    load_native_event_targets_in_transaction,
)
from content.report_reading import report_inputs_readable_in_transaction
from content.schemas import EventContentReadReference
from core.config import Settings
from events.ai_execution import (
    create_event_stage_client,
    event_ai_contract,
    freeze_event_ai_scope_in_transaction,
    load_event_ai_contract_in_transaction,
    load_verified_event_call_in_transaction,
)
from events.embedding_execution import load_compatible_event_vectors_in_transaction
from events.fact_models import (
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingOverride,
)
from events.facts import invalidate_event_derived_in_transaction
from events.heat import resolve_attention_source
from events.heat_models import EventAttentionSource
from events.models import Event, EventMember
from events.relations import RelationPairOutput, RelationReportInput, relation_pair_request
from events.schemas import EventInput
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import (
    ComponentPolicyUnavailableError,
    JobService,
    load_job_execution_configuration,
    load_job_execution_configuration_by_operation,
)
from monitors.editorial_events import editorial_event_topic_id
from monitors.services import MonitorTopicService

_NAMESPACE = UUID("6b5679fd-4c06-4a0a-b7fc-3fb984e760fb")


class SignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_id: UUID
    content_id: UUID
    content_version_id: UUID
    source_key: str
    source_id: UUID
    source_revision: int
    first_received_at: datetime
    source_time: datetime
    time_basis: str
    input: RelationReportInput
    native_targets: tuple[UUID, ...]
    regroup_requests: dict[str, str]


class SignalFact(BaseModel):
    owner_id: UUID
    source_key: str
    model_config = ConfigDict(extra="forbid", frozen=True)
    fact_id: UUID
    fact_revision: int
    event_id: UUID
    event_revision: int
    topic_id: UUID
    root_fact_id: UUID
    content_id: UUID
    content_version_id: UUID
    event_member_id: UUID
    source_id: UUID
    source_revision: int
    input: RelationReportInput
    recall_score: float = 0


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def _as_event_input(item: SignalInput | SignalFact) -> EventInput:
    return EventInput(
        owner_id=item.owner_id,
        topic_id=editorial_event_topic_id(item.owner_id)
        if isinstance(item, SignalInput)
        else item.topic_id,
        content_id=item.content_id,
        content_version_id=item.content_version_id,
        source_key=item.source_key,
        title=item.input.title,
        body=item.input.summary,
        first_seen_at=item.source_time
        if isinstance(item, SignalInput)
        else item.input.published_at or datetime.now(UTC),
        first_seen_basis="published",
        matched_keywords=frozenset(),
    )


def load_waiting_signal_inputs_in_transaction(
    session: Session, *, now: datetime, content_id: UUID | None = None
) -> tuple[SignalInput, ...]:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("signal inputs require aware caller transaction")
    sources = list(session.scalars(select(EventAttentionSource)))
    owners: dict[UUID, list[EventAttentionSource]] = {}
    for row in sources:
        if row.enabled and row.mode == "signal":
            owners.setdefault(row.owner_id, []).append(row)
    result = []
    for owner, signal_sources in owners.items():
        after = None
        for _ in range(4):
            page = list_recent_signal_content_in_transaction(
                session,
                owner_id=owner,
                source_keys=tuple(sorted({row.source_key for row in signal_sources})),
                since=now - timedelta(hours=48),
                now=now,
                after_content_id=after,
            )
            for item in page.items:
                if content_id is not None and item.reference.content_id != content_id:
                    continue
                source = resolve_attention_source(
                    [row for row in sources if row.owner_id == owner], item.reading
                )
                if source is None or source.mode != "signal":
                    continue
                if (
                    session.scalar(
                        select(EventMember.id)
                        .where(
                            EventMember.owner_id == owner,
                            EventMember.content_id == item.reference.content_id,
                            EventMember.removed_revision.is_(None),
                        )
                        .limit(1)
                    )
                    is not None
                ):
                    continue
                overrides = list(
                    session.scalars(
                        select(EventGroupingOverride).where(
                            EventGroupingOverride.owner_id == owner,
                            EventGroupingOverride.content_id == item.reference.content_id,
                        )
                    )
                )
                if any(row.mode in {"manual", "standalone"} for row in overrides):
                    continue
                version = item.reading.observation.content_version
                if version is None or not (version.title or version.body or "").strip():
                    continue
                native = load_native_event_targets_in_transaction(
                    session, owner_id=owner, references=(item.reference,), now=now
                ).get(item.reference.content_version_id, frozenset())
                result.append(
                    SignalInput(
                        owner_id=owner,
                        content_id=item.reference.content_id,
                        content_version_id=item.reference.content_version_id,
                        source_key=source.source_key,
                        source_id=source.id,
                        source_revision=source.revision,
                        first_received_at=item.first_received_at,
                        source_time=item.source_time,
                        time_basis=item.time_basis,
                        input=RelationReportInput(
                            title=(version.title or version.body or "")[:500],
                            source=source.name[:200],
                            summary=(version.body or "")[:300] or None,
                            published_at=item.source_time,
                            first_party=source.first_party,
                        ),
                        native_targets=tuple(sorted(native, key=str)),
                        regroup_requests={
                            str(row.topic_id): str(row.operation_id)
                            for row in overrides
                            if row.mode == "regroup_pending"
                        },
                    )
                )
            if page.next_after_content_id is None or len(result) >= 4000:
                break
            after = page.next_after_content_id
    return tuple(result[:4000])


def _fact_reports(session: Session, *, owner_id: UUID, now: datetime) -> tuple[SignalFact, ...]:
    roots = {
        row.event_id: row.fact_id
        for row in session.scalars(
            select(EventFactAssignment)
            .join(EventFact, EventFact.id == EventFactAssignment.fact_id)
            .where(
                EventFactAssignment.owner_id == owner_id,
                EventFactAssignment.relation == "root",
                EventFactAssignment.removed_revision.is_(None),
                EventFact.owner_id == owner_id,
                EventFact.status == "confirmed",
            )
        )
    }
    if not roots:
        return ()
    rows = session.execute(
        select(EventFactMember, EventFact, Event, EventMember)
        .join(EventFact, EventFact.id == EventFactMember.fact_id)
        .join(Event, Event.id == EventFactMember.event_id)
        .join(EventMember, EventMember.id == EventFactMember.event_member_id)
        .join(
            EventFactAssignment,
            (EventFactAssignment.fact_id == EventFact.id)
            & (EventFactAssignment.event_id == Event.id),
        )
        .where(
            EventFactMember.owner_id == owner_id,
            EventFact.owner_id == owner_id,
            Event.owner_id == owner_id,
            EventMember.owner_id == owner_id,
            EventFactMember.event_id.in_(roots),
            EventFactAssignment.owner_id == owner_id,
            EventFactAssignment.removed_revision.is_(None),
            EventFactAssignment.relation.in_(("root", "development", "background")),
            EventFactMember.role.in_(("primary", "report")),
            EventFactMember.removed_revision.is_(None),
            EventMember.removed_revision.is_(None),
            EventFact.status == "confirmed",
            Event.status == "active",
            EventFact.first_seen_at >= now - timedelta(days=14),
        )
        .order_by(
            EventFactMember.role != "primary", EventFact.first_seen_at.desc(), EventFactMember.id
        )
        .limit(2000)
    ).all()
    references = tuple(
        EventContentReadReference(
            member.content_id, member.content_version_id, event_member.representative_comment_id
        )
        for member, _, _, event_member in rows
    )
    readings = load_event_member_content_in_transaction(
        session, owner_id=owner_id, references=references, now=now
    )
    sources = list(
        session.scalars(
            select(EventAttentionSource).where(EventAttentionSource.owner_id == owner_id)
        )
    )
    protected = set(
        session.scalars(
            select(EventGroupingOverride.content_id).where(
                EventGroupingOverride.owner_id == owner_id,
                EventGroupingOverride.mode == "regroup_pending",
            )
        )
    )
    result = []
    for (member, fact, event, event_member), reference in zip(rows, references, strict=True):
        reading = readings.get(reference)
        source = resolve_attention_source(sources, reading) if reading else None
        if (
            member.content_id in protected
            or reading is None
            or source is None
            or source.mode != "editorial"
            or reading.current_visibility is None
            or reading.current_visibility.status != "visible"
            or reading.representative_comment_state == "unavailable"
        ):
            continue
        version = reading.observation.content_version
        if version is None or not (version.title or version.body or "").strip():
            continue
        if not report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=(reference.content_version_id,),
            observation_ids=(reading.observation.id,),
            now=now,
        ):
            continue
        result.append(
            SignalFact(
                owner_id=owner_id,
                source_key=source.source_key,
                fact_id=fact.id,
                fact_revision=fact.revision,
                event_id=event.id,
                event_revision=event.revision,
                topic_id=event.topic_id,
                root_fact_id=roots[event.id],
                content_id=member.content_id,
                content_version_id=member.content_version_id,
                event_member_id=event_member.id,
                source_id=source.id,
                source_revision=source.revision,
                input=RelationReportInput(
                    title=(version.title or version.body or "")[:500],
                    source=source.name[:200],
                    first_party=source.first_party,
                    published_at=fact.first_seen_at,
                    summary=(version.body or "")[:300] or None,
                    frame=fact.frame,
                ),
            )
        )
    return tuple(result)


def _recall(
    session: Session, *, signal: SignalInput, settings: Settings, now: datetime
) -> tuple[str, tuple[SignalFact, ...]]:
    reports = _fact_reports(session, owner_id=signal.owner_id, now=now)
    if signal.regroup_requests:
        reports = tuple(row for row in reports if str(row.topic_id) in signal.regroup_requests)
    native = sorted(
        (row for row in reports if row.content_id in signal.native_targets),
        key=lambda row: (row.input.published_at, str(row.fact_id), str(row.event_member_id)),
    )
    if native:
        return "native", (native[0].model_copy(update={"recall_score": 1.0}),)
    if (
        signal.first_received_at < now - timedelta(hours=6)
        or not settings.ai_enabled
        or not settings.embeddings_enabled
    ):
        return "unmatched", ()
    versions = load_compatible_event_vectors_in_transaction(
        session,
        owner_id=signal.owner_id,
        inputs=(_as_event_input(signal), *tuple(_as_event_input(item) for item in reports)),
        settings=settings,
        now=now,
    )
    mine = versions.get(signal.content_version_id)
    if mine is None:
        return "unmatched", ()
    best: dict[UUID, SignalFact] = {}
    for report in reports:
        vector = versions.get(report.content_version_id)
        score = cosine(mine, vector) if vector is not None else 0
        if score >= 0.72 and (
            report.fact_id not in best or best[report.fact_id].recall_score < score
        ):
            best[report.fact_id] = report.model_copy(update={"recall_score": score})
    candidates = tuple(
        sorted(best.values(), key=lambda row: (-row.recall_score, str(row.fact_id)))[:4]
    )
    return (
        "automatic" if candidates and candidates[0].recall_score >= 0.92 else "review"
    ), candidates


def _material_fingerprint(
    signal: SignalInput,
    mode: str,
    candidates: tuple[SignalFact, ...],
    settings: Settings,
    *,
    ai_contract: str | None = None,
) -> str:
    return _hash(
        {
            "signal": signal.model_dump(mode="json"),
            "mode": mode,
            "candidates": [row.model_dump(mode="json") for row in candidates],
            "relation_prompt": relation_pair_request(signal.input, signal.input)[0],
            "embedding_model": settings.embedding_model if mode != "native" else None,
            "embedding_dimensions": settings.embedding_dimensions if mode != "native" else None,
            "embedding_provider": settings.embedding_base_url if mode != "native" else None,
            "review_model": (ai_contract or settings.ai_model) if mode == "review" else None,
        }
    )


class EventSignalService:
    def __init__(self, session: Session, settings: Settings):
        self._session, self._settings = session, settings

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        if not self._session.in_transaction() or now.utcoffset() is None:
            raise ValueError("signal scan requires aware caller transaction")
        if not self._settings.events_cluster_enabled:
            return 0
        accepted = 0
        for signal in load_waiting_signal_inputs_in_transaction(self._session, now=now):
            mode, candidates = _recall(
                self._session, signal=signal, settings=self._settings, now=now
            )
            if not candidates or (
                mode == "review" and (not ai_enabled or not self._settings.ai_enabled)
            ):
                continue
            ai_scope = (
                freeze_event_ai_scope_in_transaction(
                    self._session, owner_id=signal.owner_id, settings=self._settings
                )
                if mode == "review"
                else {}
            )
            ai_contract = (
                event_ai_contract(
                    FrozenAiRouting.model_validate_json(ai_scope["ai_routing"]),
                    ("events.signal-relation",),
                )
                if ai_scope
                else None
            )
            fingerprint = _material_fingerprint(
                signal, mode, candidates, self._settings, ai_contract=ai_contract
            )
            operation = uuid5(_NAMESPACE, f"{signal.owner_id}:{fingerprint}")
            if (
                load_job_execution_configuration_by_operation(
                    self._session,
                    owner_id=signal.owner_id,
                    operation_id=operation,
                    kind="events.signals",
                )
                is not None
            ):
                continue
            JobService(self._session, clock=lambda: now).accept_in_transaction(
                owner_id=signal.owner_id,
                command=JobAcceptanceInput(
                    operation_id=operation,
                    kind="events.signals",
                    observation=JobObservationContext(
                        configuration_ref=f"signal:{signal.content_id.hex}", configuration_version=1
                    ),
                    scope={
                        "content_id": str(signal.content_id),
                        "input_fingerprint": fingerprint,
                        "mode": mode,
                        "material": json.dumps(
                            {
                                "signal": signal.model_dump(mode="json"),
                                "candidates": [row.model_dump(mode="json") for row in candidates],
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        **ai_scope,
                    },
                ),
            )
            accepted += 1
            if accepted >= 100:
                break
        return accepted


class EventSignalExecutor:
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
            next_action="核对讨论证据、原任务回执和人工分组",
        )

    def _load(
        self, session: Session, message: JobMessage, lease: ExecutionLease
    ) -> tuple[ExecutionLease, SignalInput, str, tuple[SignalFact, ...], dict[str, object]]:
        current = self._execution(session).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )
        configuration = load_job_execution_configuration(session, job_id=message.job_id)
        if (
            configuration is None
            or message.kind != "events.signals"
            or configuration.kind != message.kind
            or configuration.owner_id != message.owner_id
            or configuration.observation.configuration_ref != message.configuration_ref
            or configuration.observation.configuration_version != message.configuration_version
        ):
            raise self._failure("event_signal_input_changed")
        frozen = json.loads(str(configuration.scope["material"]))
        signal = SignalInput.model_validate(frozen["signal"])
        candidates = tuple(SignalFact.model_validate(row) for row in frozen["candidates"])
        mode = str(configuration.scope["mode"])
        state = json.loads(str(current.checkpoint.get("signal_state", '{"outputs":{}}')))
        if signal.owner_id != message.owner_id or not candidates or len(candidates) > 4:
            raise self._failure("event_signal_input_changed")
        if state.get("complete"):
            return current, signal, mode, candidates, state
        live = next(
            (
                row
                for row in load_waiting_signal_inputs_in_transaction(
                    session, now=self._clock(), content_id=signal.content_id
                )
                if row.owner_id == message.owner_id
            ),
            None,
        )
        if live is None:
            raise self._failure("event_signal_input_changed")
        live_mode, live_candidates = _recall(
            session, signal=live, settings=self._settings, now=self._clock()
        )
        ai_contract = (
            load_event_ai_contract_in_transaction(
                session,
                owner_id=message.owner_id,
                job_id=message.job_id,
                purposes=("events.signal-relation",),
                legacy_model=self._settings.ai_model,
            )
            if mode == "review"
            else None
        )
        if (
            _material_fingerprint(
                live, live_mode, live_candidates, self._settings, ai_contract=ai_contract
            )
            != configuration.scope["input_fingerprint"]
        ):
            raise self._failure("event_signal_input_changed")
        return current, signal, mode, candidates, state

    def _save(self, session: Session, current: ExecutionLease, state: dict[str, object]) -> None:
        self._execution(session).save_checkpoint_in_transaction(
            current,
            sequence=current.checkpoint_sequence + 1,
            checkpoint={
                **current.checkpoint,
                "signal_state": json.dumps(state, sort_keys=True, separators=(",", ":")),
            },
        )

    def _ai_admission_guard(
        self, session: Session, message: JobMessage, lease: ExecutionLease, stage: int
    ) -> None:
        _, _, mode, _, state = self._load(session, message, lease)
        if (
            mode != "review"
            or state.get("complete")
            or state.get("unknown")
            or state.get("pending_stage") != stage
        ):
            raise self._failure("event_signal_input_changed")

    def _attach(
        self, session: Session, *, signal: SignalInput, target: SignalFact, now: datetime
    ) -> None:
        MonitorTopicService(session).lock_topic_for_event_commit_in_transaction(
            owner_id=signal.owner_id, topic_id=target.topic_id
        )
        event = session.scalar(
            select(Event)
            .where(Event.id == target.event_id, Event.owner_id == signal.owner_id)
            .with_for_update()
        )
        fact = session.scalar(
            select(EventFact)
            .where(EventFact.id == target.fact_id, EventFact.owner_id == signal.owner_id)
            .with_for_update()
        )
        if (
            event is None
            or fact is None
            or event.revision != target.event_revision
            or fact.revision != target.fact_revision
        ):
            raise self._failure("event_signal_input_changed")
        # The topic lock serializes manual detach/merge with this final check.
        if (
            session.scalar(
                select(EventGroupingOverride.content_id).where(
                    EventGroupingOverride.owner_id == signal.owner_id,
                    EventGroupingOverride.content_id == signal.content_id,
                    EventGroupingOverride.mode.in_(("manual", "standalone")),
                )
            )
            is not None
        ):
            raise self._failure("event_signal_input_changed")
        if (
            session.scalar(
                select(EventMember.id).where(
                    EventMember.owner_id == signal.owner_id,
                    EventMember.content_id == signal.content_id,
                    EventMember.removed_revision.is_(None),
                )
            )
            is not None
        ):
            raise self._failure("event_signal_input_changed")
        event.revision += 1
        event.updated_at = now
        fact.revision += 1
        fact.updated_at = now
        member = EventMember(
            id=uuid4(),
            owner_id=signal.owner_id,
            topic_id=target.topic_id,
            event_id=event.id,
            content_id=signal.content_id,
            content_version_id=signal.content_version_id,
            source_key=signal.source_key,
            representative_comment_id=None,
            added_revision=event.revision,
            removed_revision=None,
            assignment_origin="model",
            created_at=now,
        )
        session.add(member)
        session.flush()
        session.add(
            EventFactMember(
                id=uuid4(),
                owner_id=signal.owner_id,
                topic_id=target.topic_id,
                fact_id=fact.id,
                event_id=event.id,
                event_member_id=member.id,
                content_id=signal.content_id,
                content_version_id=signal.content_version_id,
                role="mention",
                assignment_origin="model",
                added_revision=fact.revision,
                removed_revision=None,
                created_at=now,
            )
        )
        invalidate_event_derived_in_transaction(session, event=event, now=now)
        for row in session.scalars(
            select(EventGroupingOverride).where(
                EventGroupingOverride.owner_id == signal.owner_id,
                EventGroupingOverride.content_id == signal.content_id,
                EventGroupingOverride.mode == "regroup_pending",
            )
        ):
            if signal.regroup_requests.get(str(row.topic_id)) != str(row.operation_id):
                raise self._failure("event_signal_input_changed")
            session.delete(row)
        session.flush()

    def _prepare(
        self, message: JobMessage, lease: ExecutionLease
    ) -> tuple[str, str, str, int] | None:
        with self._sessions() as session, session.begin():
            current, signal, mode, candidates, state = self._load(session, message, lease)
            if state.get("complete"):
                return None
            if state.get("pending_stage") is not None or state.get("unknown"):
                raise self._failure("event_signal_result_unknown")
            outputs = cast(dict[str, dict[str, object]], state["outputs"])
            if mode in {"native", "automatic"}:
                target = candidates[0]
            else:
                target = None
                valid = []
                for index, candidate in enumerate(candidates):
                    raw = outputs.get(str(index))
                    if raw is None:
                        prompt_version, instructions, prompt = relation_pair_request(
                            signal.input, candidate.input
                        )
                        state["pending_stage"] = index
                        self._save(session, current, state)
                        return prompt_version, instructions, prompt, index
                    try:
                        call_id = UUID(str(raw["ai_call_id"]))
                    except (KeyError, ValueError):
                        raise self._failure("event_signal_invalid_saved_output") from None
                    if (
                        load_verified_event_call_in_transaction(
                            session,
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            call_id=call_id,
                            purpose="events.signal-relation",
                        )
                        is None
                    ):
                        raise self._failure("event_signal_invalid_saved_output")
                    try:
                        verdict = RelationPairOutput.model_validate(raw["output"])
                    except (ValidationError, KeyError, TypeError):
                        raise self._failure("event_signal_invalid_saved_output") from None
                    if (
                        verdict.relation in {"SAME_OCCURRENCE", "SAME_STORY"}
                        and verdict.confidence >= 0.8
                    ):
                        valid.append((verdict.confidence, candidate.recall_score, candidate))
                if valid:
                    valid.sort(key=lambda row: (-row[0], -row[1], str(row[2].fact_id)))
                    target = valid[0][2]
            if target is not None:
                self._attach(session, signal=signal, target=target, now=self._clock())
            state["complete"] = True
            state["result"] = "signal-" + mode if target else "signal-unmatched"
            state["event_id"] = str(target.event_id) if target else None
            self._save(session, current, state)
            return None

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if not self._settings.events_cluster_enabled:
            raise self._failure("event_signal_disabled")
        for _ in range(5):
            step = self._prepare(message, lease)
            if step is None:
                return JobCompletion(status=JobStatus.SUCCEEDED)
            if not self._settings.ai_enabled:
                raise self._failure("event_signal_disabled")
            client = None
            try:
                client = create_event_stage_client(
                    self._sessions,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    purpose="events.signal-relation",
                    settings=self._settings,
                    legacy_factory=create_ai_client,
                )
                with self._sessions() as session:
                    completion = (
                        AiService(
                            session,
                            client,
                            clock=self._clock,
                            settings=self._settings,
                            guard=lambda current_session: self._guard(
                                current_session, message, lease
                            ),
                            execution_epoch=lease.epoch,
                        )
                        .with_admission_guard(
                            partial(
                                self._ai_admission_guard,
                                message=message,
                                lease=lease,
                                stage=step[3],
                            )
                        )
                        .complete(
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            purpose="events.signal-relation",
                            prompt_version=step[0],
                            instructions=step[1],
                            prompt=step[2],
                            output_schema=RelationPairOutput.model_json_schema(),
                        )
                    )
                with self._sessions() as session, session.begin():
                    current, _, _, _, state = self._load(session, message, lease)
                    if state.get("pending_stage") != step[3] or completion.call_id is None:
                        raise self._failure("event_signal_input_changed")
                    outputs = cast(dict[str, dict[str, object]], state["outputs"])
                    outputs[str(step[3])] = {
                        "output": completion.output,
                        "ai_call_id": str(completion.call_id),
                    }
                    state["outputs"], state["pending_stage"] = outputs, None
                    self._save(session, current, state)
            except (AiCallError, ComponentPolicyUnavailableError) as caught:
                known = isinstance(caught, ComponentPolicyUnavailableError) or caught.code in {
                    AiFailureCode.RATE_LIMITED,
                    AiFailureCode.UNAVAILABLE,
                }
                with self._sessions() as session, session.begin():
                    current, _, _, _, state = self._load(session, message, lease)
                    if known:
                        state["pending_stage"] = None
                    else:
                        state["unknown"] = True
                    self._save(session, current, state)
                raise self._failure(
                    "event_signal_unavailable" if known else "event_signal_result_unknown",
                    retry=known,
                ) from None
            finally:
                if client is not None:
                    client.close()
        raise self._failure("event_signal_stage_limit")
