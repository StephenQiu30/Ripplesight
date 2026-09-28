from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService, create_ai_client
from analysis.services import list_relevant_event_annotation_refs_in_transaction
from content.services import load_event_content_inputs_in_transaction
from core.config import Settings
from events.clustering import (
    EVENT_OUTPUT_SCHEMA,
    EVENT_PROMPT_VERSION,
    build_event_prompt,
    candidate_fingerprint,
    cluster_candidates,
)
from events.models import Event, EventCandidate, EventMember
from events.schemas import EventDecision, EventInput
from jobs.execution import JobCompletion, JobExecutionFailure
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from monitors.services import MonitorTopicService, NormalizedMonitorRules, evaluate_monitor_rules

EVENT_OPERATION_NAMESPACE = UUID("d6cd262b-5a2b-470d-a396-9e78968cfd92")
_RETRYABLE_CANDIDATE_ERRORS = {
    "ai_rate_limited",
    "ai_unavailable",
    "ai_timeout",
    "ai_invalid_output",
    "ai_failed",
    "invalid_model_output",
}


class EventCandidateConflictError(Exception):
    """The frozen candidate no longer matches current content or manual state."""


def load_relevant_event_inputs_in_transaction(
    session: Session,
    *,
    since: datetime,
    version_ids: Sequence[UUID] | None = None,
    exclude_assigned: bool = True,
) -> tuple[EventInput, ...]:
    """Compose owner-scoped analysis, content and topic DTOs."""
    if not session.in_transaction() or since.tzinfo is None:
        raise RuntimeError("event input lookup requires a transaction and aware time")
    refs = list_relevant_event_annotation_refs_in_transaction(
        session, since=since, version_ids=version_ids
    )
    assigned: set[tuple[UUID, UUID, UUID]] = set()
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
    by_owner: dict[UUID, set[UUID]] = {}
    for ref in refs:
        by_owner.setdefault(ref.owner_id, set()).add(ref.content_version_id)
    content = {
        owner: load_event_content_inputs_in_transaction(
            session, owner_id=owner, version_ids=tuple(ids), since=since
        )
        for owner, ids in by_owner.items()
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
                source_key=source.source_key,
                title=source.title,
                body=source.body,
                first_seen_at=source.first_seen_at,
                first_seen_basis=source.first_seen_basis,
                matched_keywords=keywords,
                representative_comment_id=source.representative_comment_id,
            )
        )
    return tuple(result)


class EventCandidateService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def enqueue_due_in_transaction(self, *, now: datetime, ai_enabled: bool) -> int:
        if not self._session.in_transaction() or now.tzinfo is None:
            raise RuntimeError("event scan requires a transaction and aware time")
        if now.minute % 30 != 0:
            return 0
        inputs = load_relevant_event_inputs_in_transaction(
            self._session, since=now - timedelta(hours=72)
        )
        by_topic: dict[tuple[UUID, UUID], list[EventInput]] = {}
        for item in inputs:
            by_topic.setdefault((item.owner_id, item.topic_id), []).append(item)
        accepted = 0
        for (owner_id, topic_id), topic_inputs in by_topic.items():
            for members in cluster_candidates(self._session, topic_inputs):
                fingerprint = candidate_fingerprint(topic_id=topic_id, members=members)
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
                            expected_event_revisions={},
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
                        scope={"candidate_id": str(candidate.id)},
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
        current = load_relevant_event_inputs_in_transaction(
            self._session,
            since=candidate.window_start - timedelta(microseconds=1),
            version_ids=tuple(expected_ids),
            exclude_assigned=False,
        )
        if {item.content_version_id for item in current} != expected_ids:
            raise EventCandidateConflictError("input_changed")
        content_ids = [item.content_id for item in current]
        assigned = self._session.scalar(
            select(EventMember.id)
            .where(
                EventMember.owner_id == owner_id,
                EventMember.topic_id == candidate.topic_id,
                EventMember.content_id.in_(content_ids),
                EventMember.removed_revision.is_(None),
            )
            .limit(1)
        )
        if assigned is not None:
            raise EventCandidateConflictError("manual_revision_conflict")
        candidate.ai_call_id = ai_call_id
        candidate.updated_at = now
        if not decision.same_event:
            candidate.status = "rejected"
            return None
        event_id = uuid4()
        first = min(current, key=lambda item: item.first_seen_at)
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
        for item in current:
            self._session.add(
                EventMember(
                    id=uuid4(),
                    owner_id=owner_id,
                    topic_id=candidate.topic_id,
                    event_id=event_id,
                    content_id=item.content_id,
                    content_version_id=item.content_version_id,
                    source_key=item.source_key,
                    representative_comment_id=item.representative_comment_id,
                    added_revision=1,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=now,
                )
            )
        candidate.event_id = event_id
        candidate.status = "confirmed"
        self._session.flush()
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

    def execute(self, message: JobMessage) -> JobCompletion:
        if message.kind != "events.cluster":
            raise ValueError("event executor received another task kind")
        if not self._settings.events_cluster_enabled:
            raise self._failure(
                "event_clustering_disabled", JobFailureCategory.CONFIGURATION_UNAVAILABLE
            )
        with self._sessions() as session, session.begin():
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
            ):
                raise ValueError("event job configuration does not match the message")
            candidate_id = UUID(str(configuration.scope["candidate_id"]))
            candidate = session.get(EventCandidate, candidate_id)
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
                raise self._failure("event_candidate_not_pending", JobFailureCategory.INVALID_INPUT)
            members = load_relevant_event_inputs_in_transaction(
                session,
                since=candidate.window_start - timedelta(microseconds=1),
                version_ids=tuple(UUID(value) for value in candidate.member_version_ids),
            )
            if {member.content_version_id for member in members} != {
                UUID(value) for value in candidate.member_version_ids
            }:
                raise self._failure("event_input_changed", JobFailureCategory.INVALID_INPUT)
            prompt = build_event_prompt(members)

        try:
            client = create_ai_client(self._settings)
            try:
                with self._sessions() as session:
                    completion = AiService(session, client, clock=self._clock).complete(
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        purpose="events.cluster",
                        prompt_version=EVENT_PROMPT_VERSION,
                        prompt=prompt,
                        output_schema=EVENT_OUTPUT_SCHEMA,
                    )
            finally:
                client.close()
        except AiCallError as error:
            self._mark_failed(
                candidate_id, message.owner_id, f"ai_{error.code.value}", error.call_id
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
            raise self._failure(f"event_ai_{error.code.value}", category) from error

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
            manual_retry_allowed=True,
        )
