from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService, create_ai_client
from content.event_reading import load_event_member_content_in_transaction
from content.observation_inputs import freeze_observation_inputs_in_transaction
from content.report_reading import report_inputs_readable_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from events.ai_execution import (
    create_event_stage_client,
    freeze_event_ai_scope_in_transaction,
    load_verified_event_call_in_transaction,
)
from events.digest_prompts import (
    LEGACY_DIGEST_PROMPT_VERSION,
    event_digest_prompt_version,
    render_event_digest_prompt,
    serialize_event_digest_data,
    validate_event_digest_summary,
)
from events.fact_models import EventDerivedContent, EventFact, EventFactAssignment, EventFactMember
from events.models import Event, EventMember
from events.observation_inputs import (
    event_content_reference,
    load_fact_observation_inputs_in_transaction,
)
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from monitors.services import MonitorTopicService

_DIGEST_NAMESPACE = UUID("651428a3-ad32-47bd-ad36-3240ba709d27")


class EventDigestNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=30)
    summary: str = Field(min_length=100, max_length=4000)
    latest_progress: str | None = Field(default=None, max_length=60)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return validate_event_digest_summary(value)


@dataclass(frozen=True, slots=True)
class EventDigestInput:
    fingerprint: bytes
    prompt: str
    input_manifest: dict[str, object]
    prompt_version: str


def load_event_digest_input_in_transaction(
    session: Session,
    *,
    event: Event,
    now: datetime,
    prompt_version: str | None = None,
    render_prompt: bool = True,
) -> EventDigestInput | None:
    """Hash real fixed evidence and root relations; permission changes invalidate text."""
    if not session.in_transaction():
        raise RuntimeError("event digest input requires caller transaction")
    version_name = prompt_version if prompt_version is not None else event_digest_prompt_version()
    legacy = version_name == LEGACY_DIGEST_PROMPT_VERSION
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
    if not members:
        return None
    readings = load_event_member_content_in_transaction(
        session,
        owner_id=event.owner_id,
        references=tuple(event_content_reference(member) for member in members),
        now=now,
    )
    if len(readings) != len(members) or any(
        reading.representative_comment_state == "unavailable" for reading in readings.values()
    ):
        return None
    versions: set[UUID] = set()
    observations: set[UUID] = set()
    for member in members:
        observations.update(event_content_reference(member).input_observation_ids)
    for reading in readings.values():
        version = reading.observation.content_version
        if version is None:
            return None
        versions.add(version.id)
        observations.add(reading.observation.id)
        if reading.representative_comment is not None:
            comment = reading.representative_comment.observation
            if comment.content_version is None:
                return None
            versions.add(comment.content_version.id)
            observations.add(comment.id)
    if not report_inputs_readable_in_transaction(
        session,
        owner_id=event.owner_id,
        content_version_ids=tuple(versions),
        observation_ids=tuple(observations),
        now=now,
    ):
        return None
    content_payload: list[dict[str, object]] = []
    try:
        closure = freeze_observation_inputs_in_transaction(
            session,
            owner_id=event.owner_id,
            observation_ids=tuple(sorted(observations, key=str)),
            now=now,
        )
    except (ApplicationError, ValueError):
        return None
    for member in members:
        reading = readings[event_content_reference(member)]
        version = reading.observation.content_version
        assert version is not None
        if reading.source_key != member.source_key:
            return None
        representative = reading.representative_comment
        comment_version = representative.observation.content_version if representative else None
        content_payload.append(
            {
                "member_id": str(member.id),
                "content_id": str(member.content_id),
                "version_id": str(member.content_version_id),
                "source": member.source_key,
                "title": version.title,
                "body": version.body,
                "text_scope": version.text_scope,
                "origin": version.text_origin,
                "published_at": str(reading.observation.published_at),
                "representative_comment_version": str(comment_version.id)
                if comment_version
                else None,
                "representative_comment": comment_version.body if comment_version else None,
                **(
                    {
                        "observation_id": str(member.observation_id),
                        "representative_comment_observation_id": (
                            str(member.representative_comment_observation_id)
                            if member.representative_comment_observation_id
                            else None
                        ),
                        "input_observation_ids": [str(identity) for identity in closure],
                    }
                    if member.observation_id is not None
                    else {}
                ),
            }
        )
    facts_payload: list[dict[str, object]] = []
    assignments = session.execute(
        select(EventFactAssignment, EventFact)
        .join(EventFact, EventFact.id == EventFactAssignment.fact_id)
        .where(
            EventFactAssignment.owner_id == event.owner_id,
            EventFactAssignment.event_id == event.id,
            EventFactAssignment.removed_revision.is_(None),
        )
        .order_by(EventFactAssignment.fact_id)
    ).all()
    fact_members: dict[UUID, list[dict[str, object]]] = {}
    if not legacy:
        fact_ids = tuple(fact.id for _, fact in assignments)
        fact_inputs = load_fact_observation_inputs_in_transaction(
            session, owner_id=event.owner_id, fact_ids=fact_ids, now=now
        )
        # A frame may derive from members outside this event. Keep its ALL gate.
        if any(
            fact.status == "confirmed" and fact.id not in fact_inputs for _, fact in assignments
        ):
            return None
        for identities in fact_inputs.values():
            observations.update(identities)
        try:
            closure = freeze_observation_inputs_in_transaction(
                session,
                owner_id=event.owner_id,
                observation_ids=tuple(sorted(observations, key=str)),
                now=now,
            )
        except (ApplicationError, ValueError):
            return None
        # Include the expanded ALL closure in every fixed member's fingerprint.
        for member_payload in content_payload:
            if "input_observation_ids" in member_payload:
                member_payload["input_observation_ids"] = [str(identity) for identity in closure]
        for fact_member in session.scalars(
            select(EventFactMember)
            .where(
                EventFactMember.owner_id == event.owner_id,
                EventFactMember.fact_id.in_(fact_ids),
                EventFactMember.removed_revision.is_(None),
            )
            .order_by(EventFactMember.id)
        ):
            fact_members.setdefault(fact_member.fact_id, []).append(
                {
                    "member_id": str(fact_member.event_member_id),
                    "content_id": str(fact_member.content_id),
                    "version_id": str(fact_member.content_version_id),
                    "role": fact_member.role,
                }
            )
    for assignment, fact in assignments:
        facts_payload.append(
            {
                "id": str(fact.id),
                "revision": fact.revision,
                "relation": assignment.relation,
                "root_fact_id": str(assignment.root_fact_id),
                "title": fact.title if fact.status == "confirmed" else None,
                "summary": fact.summary if fact.status == "confirmed" else None,
                "status": fact.status,
                "first_seen_at": fact.first_seen_at.isoformat(),
                **(
                    {
                        "frame": fact.frame if fact.status == "confirmed" else None,
                        "members": fact_members.get(fact.id, []),
                    }
                    if not legacy
                    else {}
                ),
            }
        )
    payload = {
        "event_id": str(event.id),
        "revision": event.revision,
        "prompt_version": version_name,
        "members": content_payload,
        "facts": facts_payload,
    }
    if not legacy:
        payload["input_observation_ids"] = [str(identity) for identity in closure]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # The fingerprint covers every fixed input; only the presentation context is capped.
    try:
        prompt = (
            render_event_digest_prompt(serialize_event_digest_data(content_payload, facts_payload))
            if render_prompt
            else ""
        )
    except ValueError:
        return None
    return EventDigestInput(
        hashlib.sha256(encoded.encode()).digest(),
        prompt,
        {
            "input_basis": "observations_v1",
            "prompt_version": version_name,
            "event_revision": event.revision,
            "observation_ids": [str(identity) for identity in closure],
            "members": [
                {
                    "content_id": str(member.content_id),
                    "content_version_id": str(member.content_version_id),
                    "observation_id": str(readings[event_content_reference(member)].observation.id),
                }
                for member in members
            ],
        },
        version_name,
    )


def load_recorded_event_digest_input_in_transaction(
    session: Session, *, event: Event, derived: EventDerivedContent, now: datetime
) -> EventDigestInput | None:
    """Read historical results using their original version, never today's template hash."""
    if derived.job_id is None:
        return None
    configuration = load_job_execution_configuration(session, job_id=derived.job_id)
    if (
        configuration is None
        or configuration.owner_id != event.owner_id
        or configuration.kind != "events.digest"
        or configuration.scope.get("event_id") != str(event.id)
        or str(configuration.scope.get("event_revision")) != str(derived.event_revision)
        or configuration.scope.get("input_fingerprint") != derived.input_fingerprint.hex()
    ):
        return None
    version = configuration.scope.get("prompt_version", LEGACY_DIGEST_PROMPT_VERSION)
    if not isinstance(version, str) or not version:
        return None
    return load_event_digest_input_in_transaction(
        session, event=event, now=now, prompt_version=version, render_prompt=False
    )


class EventDigestService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        if not self._session.in_transaction() or now.tzinfo is None:
            raise RuntimeError("digest scan requires caller transaction and aware time")
        if not ai_enabled:
            return 0
        accepted = 0
        for event in self._session.scalars(
            select(Event)
            .where(Event.status == "active")
            .order_by(Event.owner_id, Event.topic_id, Event.id)
            .limit(1000)
        ):
            derived = self._session.get(EventDerivedContent, (event.owner_id, event.id))
            if derived is not None and derived.status == "pending":
                continue
            inputs = load_event_digest_input_in_transaction(self._session, event=event, now=now)
            if inputs is None:
                continue
            if (
                derived is not None
                and derived.status in {"valid", "failed"}
                and derived.event_revision == event.revision
                and derived.input_fingerprint == inputs.fingerprint
            ):
                continue
            version, _, _ = MonitorTopicService(
                self._session
            ).get_current_topic_rules_and_sources_in_transaction(
                owner_id=event.owner_id, topic_id=event.topic_id
            )
            job = JobService(self._session).accept_in_transaction(
                owner_id=event.owner_id,
                command=JobAcceptanceInput(
                    operation_id=uuid5(
                        _DIGEST_NAMESPACE, f"{event.id}:{event.revision}:{inputs.fingerprint.hex()}"
                    ),
                    kind="events.digest",
                    observation=JobObservationContext(
                        configuration_ref=f"topic:{event.topic_id}", configuration_version=version
                    ),
                    scope={
                        "event_id": str(event.id),
                        "event_revision": event.revision,
                        "input_fingerprint": inputs.fingerprint.hex(),
                        "prompt_version": inputs.prompt_version,
                        "input_manifest": json.dumps(inputs.input_manifest, sort_keys=True),
                        **(
                            freeze_event_ai_scope_in_transaction(
                                self._session, owner_id=event.owner_id, settings=self._settings
                            )
                            if self._settings is not None
                            else {}
                        ),
                    },
                ),
            )
            if derived is None:
                derived = EventDerivedContent(
                    owner_id=event.owner_id,
                    event_id=event.id,
                    topic_id=event.topic_id,
                    event_revision=event.revision,
                    input_fingerprint=inputs.fingerprint,
                    status="pending",
                    title=None,
                    summary=None,
                    latest_progress=None,
                    ai_call_id=None,
                    job_id=job.id,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(derived)
            else:
                derived.event_revision, derived.input_fingerprint = (
                    event.revision,
                    inputs.fingerprint,
                )
                derived.status, derived.job_id = "pending", job.id
                derived.title = derived.summary = derived.latest_progress = None
                derived.ai_call_id, derived.error_code, derived.updated_at = None, None, now
            accepted += 1
        self._session.flush()
        return accepted

    def commit_in_transaction(
        self,
        *,
        owner_id: UUID,
        event_id: UUID,
        job_id: UUID,
        expected_revision: int,
        expected_fingerprint: bytes,
        narrative: EventDigestNarrative,
        ai_call_id: UUID,
        now: datetime,
    ) -> bool:
        if not self._session.in_transaction():
            raise RuntimeError("digest commit requires caller transaction")
        event = self._session.scalar(
            select(Event).where(Event.owner_id == owner_id, Event.id == event_id)
        )
        if event is None:
            return False
        MonitorTopicService(self._session).lock_topic_for_event_commit_in_transaction(
            owner_id=owner_id, topic_id=event.topic_id
        )
        event = self._session.scalar(
            select(Event)
            .where(Event.owner_id == owner_id, Event.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        derived = self._session.get(EventDerivedContent, (owner_id, event_id))
        if event is None or derived is None or derived.job_id != job_id:
            return False
        inputs = load_event_digest_input_in_transaction(self._session, event=event, now=now)
        if (
            event.status != "active"
            or event.revision != expected_revision
            or inputs is None
            or inputs.fingerprint != expected_fingerprint
            or derived.input_fingerprint != expected_fingerprint
        ):
            derived.status = "stale"
            derived.title = derived.summary = derived.latest_progress = None
            derived.updated_at = now
            return False
        if not narrative.title.strip() or not narrative.summary.strip():
            raise ValueError("digest text cannot be blank")
        validate_event_digest_summary(narrative.summary)
        derived.status, derived.title, derived.summary = (
            "valid",
            narrative.title.strip(),
            narrative.summary.strip(),
        )
        derived.latest_progress, derived.ai_call_id = narrative.latest_progress, ai_call_id
        derived.error_code, derived.updated_at = None, now
        event.title, event.summary = derived.title, derived.summary
        event.updated_at = now
        self._session.flush()
        return True


class EventDigestExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions, self._settings = sessions, settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, message: JobMessage, lease: ExecutionLease | None = None) -> JobCompletion:
        if message.kind != "events.digest":
            raise ValueError("digest executor received another kind")
        if not self._settings.events_cluster_enabled:
            raise self._failure(
                "event_digest_disabled", JobFailureCategory.CONFIGURATION_UNAVAILABLE
            )
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("event_digest_job_mismatch", JobFailureCategory.INVALID_INPUT)
            event_id = UUID(str(configuration.scope["event_id"]))
            revision = int(str(configuration.scope["event_revision"]))
            fingerprint = bytes.fromhex(str(configuration.scope["input_fingerprint"]))
            event = session.scalar(
                select(Event).where(Event.owner_id == message.owner_id, Event.id == event_id)
            )
            derived = session.get(EventDerivedContent, (message.owner_id, event_id))
            inputs = (
                load_event_digest_input_in_transaction(session, event=event, now=self._clock())
                if event
                else None
            )
            changed = (
                event is None
                or event.status != "active"
                or event.revision != revision
                or derived is None
                or derived.job_id != message.job_id
                or inputs is None
                or inputs.fingerprint != fingerprint
            )
            if changed and derived is not None and derived.job_id == message.job_id:
                derived.status = "stale"
                derived.title = derived.summary = derived.latest_progress = None
                derived.error_code = "input_changed"
                derived.updated_at = self._clock()
            replayed = not changed and derived is not None and derived.status == "valid"
            if replayed and derived is not None:
                saved = (
                    load_verified_event_call_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        call_id=derived.ai_call_id,
                        purpose="events.digest",
                    )
                    if derived.ai_call_id
                    else None
                )
                if saved is None:
                    replayed = False
                    derived.error_code = "result_unknown"
            unknown = (
                not changed
                and not replayed
                and derived is not None
                and derived.error_code in {"request_started", "result_unknown"}
            )
            if unknown and derived is not None:
                derived.status, derived.error_code, derived.updated_at = (
                    "failed",
                    "result_unknown",
                    self._clock(),
                )
                derived.title = derived.summary = derived.latest_progress = None
            elif not changed and not replayed and derived is not None:
                derived.error_code, derived.updated_at = "request_started", self._clock()
        if changed:
            raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)
        if replayed:
            return JobCompletion(status=JobStatus.SUCCEEDED)
        if unknown:
            raise self._failure("event_digest_result_unknown", JobFailureCategory.INVALID_RESPONSE)
        assert inputs is not None
        try:
            client = create_event_stage_client(
                self._sessions,
                owner_id=message.owner_id,
                job_id=message.job_id,
                purpose="events.digest",
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
                                current_session, message, lease, event_id, revision, fingerprint
                            )
                        )
                        .complete(
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            purpose="events.digest",
                            prompt_version=inputs.prompt_version,
                            prompt=inputs.prompt,
                            output_schema=EventDigestNarrative.model_json_schema(),
                        )
                    )
            finally:
                client.close()
            narrative = EventDigestNarrative.model_validate(completion.output)
        except JobExecutionFailure as error:
            if error.error_code == "event_digest_input_changed":
                with self._sessions() as session, session.begin():
                    derived = session.get(EventDerivedContent, (message.owner_id, event_id))
                    if derived is not None and derived.job_id == message.job_id:
                        derived.status, derived.error_code, derived.updated_at = (
                            "stale",
                            "input_changed",
                            self._clock(),
                        )
                        derived.title = derived.summary = derived.latest_progress = None
            raise
        except (AiCallError, ValidationError, ValueError) as error:
            code = (
                f"ai_{error.code.value}"
                if isinstance(error, AiCallError)
                else "invalid_model_output"
            )
            unknown = isinstance(error, AiCallError) and error.code in {
                AiFailureCode.TIMEOUT,
                AiFailureCode.FAILED,
            }
            if unknown:
                code = "result_unknown"
            with self._sessions() as session, session.begin():
                derived = session.get(EventDerivedContent, (message.owner_id, event_id))
                if derived is not None and derived.job_id == message.job_id:
                    derived.status, derived.error_code, derived.updated_at = (
                        "failed",
                        code,
                        self._clock(),
                    )
                    derived.title = derived.summary = derived.latest_progress = None
                    derived.ai_call_id = (
                        error.call_id if isinstance(error, AiCallError) else completion.call_id
                    )
            category = (
                JobFailureCategory.CONFIGURATION_UNAVAILABLE
                if isinstance(error, AiCallError) and error.code == AiFailureCode.UNAVAILABLE
                else JobFailureCategory.RATE_LIMITED
                if isinstance(error, AiCallError) and error.code == AiFailureCode.RATE_LIMITED
                else JobFailureCategory.INVALID_RESPONSE
                if not isinstance(error, AiCallError)
                else JobFailureCategory.TRANSIENT
            )
            raise self._failure(
                f"event_digest_{code}", JobFailureCategory.INVALID_RESPONSE if unknown else category
            ) from error
        assert completion.call_id is not None
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            committed = EventDigestService(session).commit_in_transaction(
                owner_id=message.owner_id,
                event_id=event_id,
                job_id=message.job_id,
                expected_revision=revision,
                expected_fingerprint=fingerprint,
                narrative=narrative,
                ai_call_id=completion.call_id,
                now=self._clock(),
            )
        if not committed:
            raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)
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
        event_id: UUID,
        revision: int,
        fingerprint: bytes,
    ) -> None:
        self._guard(session, lease)
        if lease is not None:
            if lease.job_id != message.job_id:
                raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)
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
            or configuration.scope.get("event_id") != str(event_id)
            or str(configuration.scope.get("event_revision")) != str(revision)
            or configuration.scope.get("input_fingerprint") != fingerprint.hex()
        ):
            raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)
        event = session.scalar(
            select(Event).where(Event.owner_id == message.owner_id, Event.id == event_id)
        )
        if event is None:
            raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)
        MonitorTopicService(session).lock_topic_for_event_commit_in_transaction(
            owner_id=message.owner_id, topic_id=event.topic_id
        )
        event = session.scalar(
            select(Event)
            .where(Event.owner_id == message.owner_id, Event.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        derived = session.get(EventDerivedContent, (message.owner_id, event_id))
        inputs = (
            load_event_digest_input_in_transaction(session, event=event, now=self._clock())
            if event
            else None
        )
        if (
            event is None
            or event.status != "active"
            or event.revision != revision
            or derived is None
            or derived.job_id != message.job_id
            or derived.status != "pending"
            or derived.error_code != "request_started"
            or derived.input_fingerprint != fingerprint
            or inputs is None
            or inputs.fingerprint != fingerprint
        ):
            raise self._failure("event_digest_input_changed", JobFailureCategory.INVALID_INPUT)

    def _failure(self, code: str, category: JobFailureCategory) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self._clock(),
            next_action="核对事件修订、固定证据与模型预算后重试",
            manual_retry_allowed=code != "event_digest_result_unknown",
        )
