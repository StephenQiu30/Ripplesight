from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ai.adapters.embeddings import (
    compatible_vector,
    create_embedding_client,
)
from ai.embedding_contract import FrozenEmbeddingConfiguration
from ai.embedding_services import load_frozen_embedding_configuration_in_transaction
from ai.schemas import AiCallError, AiCallStatus, AiCompletion, AiFailureCode
from ai.services import AiService, load_saved_ai_call_in_transaction
from content.event_reading import load_event_member_content_in_transaction
from content.report_reading import report_inputs_readable_in_transaction
from content.schemas import EventContentReadReference, EventContentReadView
from core.config import Settings
from events.embedding_models import EventContentEmbedding
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
    BudgetPolicyUnavailableError,
    ComponentPolicyUnavailableError,
    JobService,
    load_job_execution_configuration,
)

_NAMESPACE = UUID("ba194cfa-927a-48bb-b2d7-b7b6c3a6f8f2")
_PROMPT_VERSION = "events-embedding-v1-fixed-material"
_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["vector"],
    "properties": {
        "vector": {"type": "array", "minItems": 1, "maxItems": 3072, "items": {"type": "number"}}
    },
    "additionalProperties": False,
}


def _material(reading: EventContentReadView, settings: Settings) -> tuple[bytes, str] | None:
    version = reading.observation.content_version
    if (
        version is None
        or reading.current_visibility is None
        or reading.current_visibility.status != "visible"
    ):
        return None
    prompt = ((version.title or "") + "\n" + (version.body or "")).strip()[:2000]
    if not prompt:
        return None
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "content_id": str(reading.id),
                "version_id": str(version.id),
                "title": version.title,
                "body": version.body,
                "text_scope": version.text_scope,
                "text_origin": version.text_origin,
                "source": reading.source_key,
                "provider": settings.embedding_base_url.rstrip("/"),
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "prompt_version": _PROMPT_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).digest()
    return fingerprint, prompt


def _guarded_material(
    session: Session,
    *,
    owner_id: UUID,
    reading: EventContentReadView | None,
    settings: Settings,
    now: datetime,
) -> tuple[bytes, str] | None:
    if reading is None or reading.observation.content_version is None:
        return None
    if not report_inputs_readable_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=(reading.observation.content_version.id,),
        observation_ids=(reading.observation.id,),
        now=now,
    ):
        return None
    return _material(reading, settings)


def load_compatible_event_vectors_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    inputs: Sequence[EventInput],
    settings: Settings,
    now: datetime,
) -> dict[UUID, tuple[float, ...]]:
    if not session.in_transaction() or now.utcoffset() is None or len(inputs) > 4000:
        raise ValueError("embedding reads require bounded aware caller transaction")
    if not settings.embeddings_enabled or not settings.ai_enabled:
        return {}
    readings = load_event_member_content_in_transaction(
        session,
        owner_id=owner_id,
        references=tuple(
            EventContentReadReference(item.content_id, item.content_version_id) for item in inputs
        ),
        now=now,
    )
    fingerprints = {}
    for item in inputs:
        reading = readings.get(EventContentReadReference(item.content_id, item.content_version_id))
        material = _guarded_material(
            session, owner_id=owner_id, reading=reading, settings=settings, now=now
        )
        if material:
            fingerprints[item.content_version_id] = material[0]
    rows = list(
        session.scalars(
            select(EventContentEmbedding).where(
                EventContentEmbedding.owner_id == owner_id,
                EventContentEmbedding.content_version_id.in_(fingerprints),
                EventContentEmbedding.model == settings.embedding_model,
                EventContentEmbedding.requested_dimensions == settings.embedding_dimensions,
                EventContentEmbedding.status == "valid",
            )
        )
    )
    rows = [
        row
        for row in rows
        if row.input_fingerprint == fingerprints[row.content_version_id]
        and compatible_vector(row.vector, settings.embedding_dimensions)
        and len(cast(list[float], row.vector)) == row.dimensions
    ]
    # Default dimensions are supplied by the provider. Incompatible rows never form a mixed space.
    if len({row.dimensions for row in rows}) > 1:
        return {}
    return {row.content_version_id: tuple(cast(list[float], row.vector)) for row in rows}


class EventEmbeddingService:
    def __init__(self, session: Session, settings: Settings):
        self._session, self._settings = session, settings

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        from events.services import load_relevant_event_inputs_in_transaction

        if not self._session.in_transaction() or now.utcoffset() is None:
            raise ValueError("embedding scan requires aware caller transaction")
        if (
            not ai_enabled
            or not self._settings.ai_enabled
            or not self._settings.embeddings_enabled
            or self._settings.embedding_api_key is None
        ):
            return 0
        inputs = load_relevant_event_inputs_in_transaction(
            self._session, since=now - timedelta(days=14), exclude_assigned=False, now=now
        )
        from collections import defaultdict

        from events.models import Event, EventMember
        from events.services import _fixed_context_inputs
        from events.signals import _as_event_input, load_waiting_signal_inputs_in_transaction

        signals = load_waiting_signal_inputs_in_transaction(self._session, now=now)
        all_members = list(
            self._session.scalars(
                select(EventMember)
                .join(Event, Event.id == EventMember.event_id)
                .where(EventMember.removed_revision.is_(None), Event.status == "active")
                .order_by(EventMember.created_at.desc())
                .limit(4000)
            )
        )
        grouped = defaultdict(list)
        for member in all_members:
            grouped[(member.owner_id, member.topic_id)].append(member)
        contexts = tuple(
            item
            for (owner, topic), members in grouped.items()
            for item in _fixed_context_inputs(
                self._session,
                owner_id=owner,
                topic_id=topic,
                members=members,
                since=now - timedelta(days=14),
                now=now,
                apply_topic_rules=False,
            )
        )
        inputs = (*inputs, *contexts, *tuple(_as_event_input(item) for item in signals))
        owners: dict[UUID, list[EventInput]] = {}
        for item in inputs:
            owners.setdefault(item.owner_id, []).append(item)
        accepted = 0
        for owner, items in owners.items():
            readings = load_event_member_content_in_transaction(
                self._session,
                owner_id=owner,
                references=tuple(
                    EventContentReadReference(item.content_id, item.content_version_id)
                    for item in items
                ),
                now=now,
            )
            for ref, reading in readings.items():
                material = _guarded_material(
                    self._session,
                    owner_id=owner,
                    reading=reading,
                    settings=self._settings,
                    now=now,
                )
                if material is None:
                    continue
                fingerprint, _ = material
                identity = uuid5(
                    _NAMESPACE, f"{owner}:{ref.content_version_id}:{fingerprint.hex()}"
                )
                row = self._session.get(EventContentEmbedding, identity)
                if row is not None:
                    continue
                job = JobService(self._session, clock=lambda: now).accept_in_transaction(
                    owner_id=owner,
                    command=JobAcceptanceInput(
                        operation_id=identity,
                        kind="events.embed",
                        observation=JobObservationContext(
                            configuration_ref=f"embedding:{ref.content_version_id.hex}",
                            configuration_version=1,
                        ),
                        scope={
                            "embedding_id": str(identity),
                            "input_fingerprint": fingerprint.hex(),
                            **FrozenEmbeddingConfiguration.from_settings(self._settings).scope(),
                        },
                    ),
                )
                created = self._session.scalar(
                    insert(EventContentEmbedding)
                    .values(
                        id=identity,
                        owner_id=owner,
                        content_id=ref.content_id,
                        content_version_id=ref.content_version_id,
                        model=self._settings.embedding_model,
                        requested_dimensions=self._settings.embedding_dimensions,
                        input_fingerprint=fingerprint,
                        status="pending",
                        vector=None,
                        dimensions=None,
                        ai_call_id=None,
                        job_id=job.id,
                        error_code=None,
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=[EventContentEmbedding.id])
                    .returning(EventContentEmbedding.id)
                )
                if created is None:
                    continue
                accepted += 1
                if accepted >= 100:
                    return accepted
        return accepted


class EventEmbeddingExecutor:
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
            next_action="核对固定材料、模型维数、原任务回执和预算",
        )

    def _load(
        self, session: Session, message: JobMessage, lease: ExecutionLease
    ) -> tuple[ExecutionLease, EventContentEmbedding, tuple[bytes, str] | None]:
        current = self._execution(session).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )
        configuration = load_job_execution_configuration(session, job_id=message.job_id)
        if (
            configuration is None
            or message.kind != "events.embed"
            or configuration.kind != message.kind
            or configuration.owner_id != message.owner_id
            or configuration.observation.configuration_ref != message.configuration_ref
            or configuration.observation.configuration_version != message.configuration_version
        ):
            raise self._failure("event_embedding_input_changed")
        frozen = load_frozen_embedding_configuration_in_transaction(
            session, owner_id=message.owner_id, job_id=message.job_id
        )
        if frozen is None or frozen != FrozenEmbeddingConfiguration.from_settings(self._settings):
            raise self._failure("event_embedding_input_changed")
        row = session.scalar(
            select(EventContentEmbedding)
            .where(
                EventContentEmbedding.owner_id == message.owner_id,
                EventContentEmbedding.id == UUID(str(configuration.scope["embedding_id"])),
                EventContentEmbedding.job_id == message.job_id,
            )
            .with_for_update()
        )
        if row is None or row.input_fingerprint.hex() != configuration.scope["input_fingerprint"]:
            raise self._failure("event_embedding_input_changed")
        reading = load_event_member_content_in_transaction(
            session,
            owner_id=message.owner_id,
            references=(EventContentReadReference(row.content_id, row.content_version_id),),
            now=self._clock(),
        ).get(EventContentReadReference(row.content_id, row.content_version_id))
        material = _guarded_material(
            session,
            owner_id=message.owner_id,
            reading=reading,
            settings=self._settings,
            now=self._clock(),
        )
        if (
            material is None
            or material[0] != row.input_fingerprint
            or row.model != self._settings.embedding_model
            or row.requested_dimensions != self._settings.embedding_dimensions
        ):
            material = None
        return current, row, material

    def _checkpoint(
        self, session: Session, current: ExecutionLease, row: EventContentEmbedding
    ) -> None:
        self._execution(session).save_checkpoint_in_transaction(
            current,
            sequence=current.checkpoint_sequence + 1,
            checkpoint={
                **current.checkpoint,
                "embedding_stage": row.status,
                "embedding_id": str(row.id),
            },
        )

    def _ai_admission_guard(
        self, session: Session, message: JobMessage, lease: ExecutionLease
    ) -> None:
        _, row, material = self._load(session, message, lease)
        if material is None or row.status != "running":
            raise self._failure("event_embedding_input_changed")

    def _prepare(self, message: JobMessage, lease: ExecutionLease) -> str | None:
        code = None
        with self._sessions() as session, session.begin():
            current, row, material = self._load(session, message, lease)
            if material is None:
                row.status, row.vector, row.dimensions = "stale", None, None
                row.error_code, code = "input_changed", "event_embedding_input_changed"
            elif row.status in {"valid", "response_saved"}:
                call = (
                    load_saved_ai_call_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        call_id=row.ai_call_id,
                        purpose="events.embedding",
                    )
                    if row.ai_call_id
                    else None
                )
                frozen = FrozenEmbeddingConfiguration.from_settings(self._settings)
                if (
                    call is None
                    or call.status != AiCallStatus.SUCCEEDED
                    or call.provider != frozen.provider
                    or call.model != frozen.model
                    or call.model_key != "embedding"
                    or call.routing_hash != frozen.sha256
                    or not compatible_vector(row.vector, row.requested_dimensions)
                ):
                    row.status, row.vector, row.dimensions = "failed", None, None
                    row.error_code, code = "invalid_saved_vector", "event_embedding_invalid_vector"
                else:
                    row.status, row.error_code, row.updated_at = "valid", None, self._clock()
                    self._checkpoint(session, current, row)
                    return None
            elif row.status in {"running", "unknown"}:
                row.status, row.error_code = "unknown", "result_unknown"
                code = "event_embedding_result_unknown"
            elif row.status != "pending":
                code = "event_embedding_not_pending"
            else:
                row.status, row.error_code, row.updated_at = "running", None, self._clock()
                self._checkpoint(session, current, row)
                return material[1]
            row.updated_at = self._clock()
            self._checkpoint(session, current, row)
        raise self._failure(code)

    def _save_response(
        self, message: JobMessage, lease: ExecutionLease, completion: AiCompletion
    ) -> None:
        vector = completion.output.get("vector")
        code = None
        with self._sessions() as session, session.begin():
            current, row, material = self._load(session, message, lease)
            if material is None or row.status != "running" or completion.call_id is None:
                raise self._failure("event_embedding_input_changed")
            if completion.model != self._settings.embedding_model or not compatible_vector(
                vector, self._settings.embedding_dimensions
            ):
                code = "event_embedding_invalid_vector"
            if code is None and row.requested_dimensions == 0:
                session.execute(
                    select(
                        func.pg_advisory_xact_lock(
                            func.hashtextextended(
                                f"event-embedding-space:{message.owner_id}:{row.model}", 0
                            )
                        )
                    )
                )
                stored_dimensions = set(
                    session.scalars(
                        select(EventContentEmbedding.dimensions).where(
                            EventContentEmbedding.owner_id == message.owner_id,
                            EventContentEmbedding.model == row.model,
                            EventContentEmbedding.requested_dimensions == 0,
                            EventContentEmbedding.status.in_(("valid", "response_saved")),
                        )
                    )
                )
                if stored_dimensions and stored_dimensions != {len(cast(list[float], vector))}:
                    code = "event_embedding_incompatible_dimensions"
            row.ai_call_id, row.updated_at = completion.call_id, self._clock()
            if code is not None:
                row.status, row.error_code, row.vector, row.dimensions = "failed", code, None, None
            else:
                row.vector, row.dimensions = (
                    list(cast(list[float], vector)),
                    len(cast(list[float], vector)),
                )
                row.status, row.error_code = "response_saved", None
            self._checkpoint(session, current, row)
        if code is not None:
            raise self._failure(code)

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if not self._settings.embeddings_enabled or not self._settings.ai_enabled:
            raise self._failure("event_embedding_disabled")
        prompt = self._prepare(message, lease)
        if prompt is None:
            return JobCompletion(status=JobStatus.SUCCEEDED)
        client = None
        try:
            client = create_embedding_client(self._settings)
            if client.embedding_configuration != FrozenEmbeddingConfiguration.from_settings(
                self._settings
            ):
                raise AiCallError(AiFailureCode.UNAVAILABLE, "embedding client contract differs")
            with self._sessions() as session:
                completion = (
                    AiService(
                        session,
                        client,
                        clock=self._clock,
                        settings=self._settings,
                        guard=lambda current_session: self._guard(current_session, message, lease),
                        execution_epoch=lease.epoch,
                    )
                    .with_admission_guard(
                        lambda current_session: self._ai_admission_guard(
                            current_session, message, lease
                        )
                    )
                    .complete(
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        purpose="events.embedding",
                        prompt_version=_PROMPT_VERSION,
                        prompt=prompt,
                        output_schema=_SCHEMA,
                    )
                )
            self._save_response(message, lease, completion)
        except (
            AiCallError,
            ComponentPolicyUnavailableError,
            BudgetPolicyUnavailableError,
        ) as caught:
            error = (
                caught
                if isinstance(caught, AiCallError)
                else AiCallError(AiFailureCode.UNAVAILABLE, "embedding component is not approved")
            )
            retry = error.code in {AiFailureCode.UNAVAILABLE, AiFailureCode.RATE_LIMITED}
            with self._sessions() as session, session.begin():
                current, row, _ = self._load(session, message, lease)
                row.status = "pending" if retry else "unknown"
                row.error_code, row.ai_call_id, row.updated_at = (
                    f"ai_{error.code.value}" if retry else "result_unknown",
                    error.call_id,
                    self._clock(),
                )
                self._checkpoint(session, current, row)
            raise self._failure(
                f"ai_{error.code.value}" if retry else "event_embedding_result_unknown", retry=retry
            ) from None
        finally:
            if client is not None:
                client.close()
        self._prepare(message, lease)
        return JobCompletion(status=JobStatus.SUCCEEDED)
