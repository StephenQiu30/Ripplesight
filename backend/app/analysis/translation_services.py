from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast
from uuid import UUID, uuid4

from markdown_it import MarkdownIt
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_services import freeze_ai_job_scope_in_transaction
from ai.schemas import AiCallError
from ai.services import AiService, create_ai_client
from analysis.editorial_schemas import TranslationOutput
from analysis.editorial_translation import (
    TranslationPlan,
    assemble_translation,
    plan_translation,
    unshield,
)
from analysis.prompts import editorial_prompt_version, render_editorial_prompt
from analysis.translation_models import ContentTranslationBatch, ContentTranslationRun
from analysis.translation_schemas import (
    TranslationRequestInput,
    TranslationRunView,
    TranslationState,
)
from content.editorial_reading import require_editorial_content_permission_in_transaction
from content.schemas import EventContentReadReference
from core.config import Settings
from core.errors import ApplicationError
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
    load_job_cancellation_state_in_transaction,
    load_job_execution_configuration,
    load_job_execution_configuration_by_operation,
)
from publication.schemas import FullTextGrantView


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def translation_prompt_version() -> str:
    return editorial_prompt_version("translate-body")


def source_html(body: str, source_format: str) -> str:
    if source_format == "html":
        return body
    if source_format == "markdown":
        return cast(str, MarkdownIt("js-default").render(body))
    return "".join(
        "<p>" + html.escape(part).replace("\n", "<br>") + "</p>" for part in body.split("\n\n")
    )


def _grant(session: Session, record: ContentTranslationRun, now: datetime) -> FullTextGrantView:
    from publication.reading import full_text_grant_in_transaction

    return full_text_grant_in_transaction(
        session,
        owner_id=record.owner_id,
        content_id=record.content_id,
        content_version_id=record.content_version_id,
        policy_revision=record.policy_revision,
        now=now,
        for_translation=True,
    )


def _plan(grant: FullTextGrantView) -> TranslationPlan:
    if not grant.granted or grant.reference is None or grant.body is None:
        raise ApplicationError("translation_material_unavailable")
    return plan_translation(source_html(grant.body, grant.body_format))


def _fingerprint(grant: FullTextGrantView, plan: TranslationPlan) -> str:
    return _hash(
        [
            grant.reference.model_dump(mode="json") if grant.reference else None,
            grant.body_format,
            grant.body_sha256,
            plan.input_fingerprint,
            translation_prompt_version(),
        ]
    )


def _content_reference(record: ContentTranslationRun) -> EventContentReadReference:
    observation_id = record.reference.get("observation_id")
    return EventContentReadReference(
        content_id=record.content_id,
        content_version_id=record.content_version_id,
        observation_id=UUID(observation_id) if observation_id else None,
        input_observation_ids=tuple(
            UUID(i) for i in record.reference.get("input_observation_ids", [])
        ),
        legacy_strict=observation_id is None,
    )


def _valid(
    session: Session,
    record: ContentTranslationRun,
    now: datetime,
    *,
    lock_permissions: bool = True,
) -> bool:
    try:
        require_editorial_content_permission_in_transaction(
            session,
            owner_id=record.owner_id,
            reference=_content_reference(record),
            now=now,
            lock_policies=lock_permissions,
        )
    except ApplicationError:
        return False
    grant = _grant(session, record, now)
    return bool(
        grant.granted
        and grant.reference
        and grant.reference.model_dump(mode="json") == record.reference
        and record.prompt_version == translation_prompt_version()
        and _fingerprint(grant, _plan(grant)) == record.input_fingerprint
    )


class ContentTranslationService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        enabled: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.session, self.enabled, self.clock = (
            session,
            enabled,
            clock or (lambda: datetime.now(UTC)),
        )

    def _record(self, owner: UUID, id: UUID, *, lock: bool = False) -> ContentTranslationRun:
        query = select(ContentTranslationRun).where(
            ContentTranslationRun.owner_id == owner, ContentTranslationRun.id == id
        )
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query)
        if row is None:
            raise ApplicationError("resource_not_found")
        return row

    def _latest(
        self, owner: UUID, content: UUID, version: UUID, policy: int
    ) -> ContentTranslationRun | None:
        return self.session.scalar(
            select(ContentTranslationRun)
            .where(
                ContentTranslationRun.owner_id == owner,
                ContentTranslationRun.content_id == content,
                ContentTranslationRun.content_version_id == version,
                ContentTranslationRun.policy_revision == policy,
            )
            .order_by(ContentTranslationRun.revision.desc())
            .limit(1)
        )

    def _view(self, row: ContentTranslationRun) -> TranslationRunView:
        valid = _valid(self.session, row, self.clock(), lock_permissions=False)
        job = load_job_cancellation_state_in_transaction(
            self.session, owner_id=row.owner_id, job_id=row.job_id
        )
        cancelled = bool(
            job
            and (job.requested_at is not None or job.status == JobStatus.CANCELLED)
            and row.status in {"queued", "running"}
        )
        return TranslationRunView(
            id=row.id,
            content_id=row.content_id,
            content_version_id=row.content_version_id,
            policy_revision=row.policy_revision,
            job_id=row.job_id,
            created_at=row.created_at,
            body_html=row.body_html if valid and not cancelled else None,
            status=cast(
                TranslationState, "failed" if cancelled else row.status if valid else "stale"
            ),
            revision=row.revision,
            reason="translation_cancelled"
            if cancelled
            else row.failure_code or ("ready" if valid else "material_changed"),
            complete=row.complete and valid and not cancelled,
            translated_segments=row.translated_segments,
            total_segments=row.total_segments,
        )

    def get(self, *, owner_id: UUID, run_id: UUID) -> TranslationRunView:
        self.session.rollback()
        with self.session.begin():
            self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            return self._view(self._record(owner_id, run_id))

    def request(
        self, *, owner_id: UUID, content_id: UUID, command: TranslationRequestInput
    ) -> TranslationRunView:
        from publication.reading import full_text_grant_in_transaction

        if not self.enabled:
            raise ApplicationError("translation_disabled")
        self.session.rollback()
        with self.session.begin():
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(f"translation:{owner_id}:{command.operation_id}", 0)
                    )
                )
            )
            request_hash = _hash([str(content_id), command.model_dump(mode="json")])
            existing = self.session.scalar(
                select(ContentTranslationRun).where(
                    ContentTranslationRun.owner_id == owner_id,
                    ContentTranslationRun.operation_id == command.operation_id,
                )
            )
            if existing:
                if existing.request_fingerprint != request_hash:
                    raise ApplicationError("idempotency_conflict")
                return self._view(existing)
            cached_job = load_job_execution_configuration_by_operation(
                self.session,
                owner_id=owner_id,
                kind="analysis.translate",
                operation_id=command.operation_id,
            )
            if cached_job is not None:
                if cached_job.scope.get("request_fingerprint") != request_hash:
                    raise ApplicationError("idempotency_conflict")
                cached = self._record(owner_id, UUID(str(cached_job.scope["translation_id"])))
                return self._view(cached).model_copy(update={"job_id": cached_job.job_id})
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(
                            f"translation:{owner_id}:{content_id}:{command.content_version_id}:{command.policy_revision}",
                            0,
                        )
                    )
                )
            )
            grant = full_text_grant_in_transaction(
                self.session,
                owner_id=owner_id,
                content_id=content_id,
                content_version_id=command.content_version_id,
                policy_revision=command.policy_revision,
                now=self.clock(),
                for_translation=True,
            )
            plan = _plan(grant)
            prior = self._latest(
                owner_id, content_id, command.content_version_id, command.policy_revision
            )
            # Repeated fixed identities reuse a finished translation without another paid job.
            if (
                prior
                and prior.status in {"complete", "partial"}
                and _valid(self.session, prior, self.clock())
            ):
                cached_receipt = JobService(self.session, clock=self.clock).accept_in_transaction(
                    owner_id=owner_id,
                    command=JobAcceptanceInput(
                        operation_id=command.operation_id,
                        kind="analysis.translate",
                        observation=JobObservationContext(
                            configuration_ref=f"translation:{prior.id}",
                            configuration_version=prior.revision,
                        ),
                        scope={
                            "translation_id": str(prior.id),
                            "cached": True,
                            "request_fingerprint": request_hash,
                        },
                    ),
                )
                return self._view(prior).model_copy(update={"job_id": cached_receipt.id})
            if (prior.revision if prior else 0) != command.expected_revision:
                raise ApplicationError("translation_revision_conflict")
            id, now = uuid4(), self.clock()
            job = JobService(self.session, clock=self.clock).accept_in_transaction(
                owner_id=owner_id,
                command=JobAcceptanceInput(
                    operation_id=command.operation_id,
                    kind="analysis.translate",
                    observation=JobObservationContext(
                        configuration_ref=f"translation:{id}",
                        configuration_version=command.expected_revision + 1,
                    ),
                    scope={
                        "translation_id": str(id),
                        **freeze_ai_job_scope_in_transaction(
                            self.session, owner_id=owner_id, settings=self.settings
                        ),
                    },
                ),
            )
            assert grant.reference is not None
            row = ContentTranslationRun(
                id=id,
                owner_id=owner_id,
                operation_id=command.operation_id,
                content_id=content_id,
                content_version_id=command.content_version_id,
                policy_revision=command.policy_revision,
                revision=command.expected_revision + 1,
                job_id=job.id,
                prompt_version=translation_prompt_version(),
                input_fingerprint=_fingerprint(grant, plan),
                request_fingerprint=request_hash,
                reference=grant.reference.model_dump(mode="json"),
                source_format=grant.body_format,
                status="queued",
                body_html=None,
                translated_segments=0,
                total_segments=plan.total_segments,
                complete=False,
                failure_code=None,
                reason=command.reason,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            self.session.flush()
            return self._view(row)


class ContentTranslationExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions, self.settings, self.clock = (
            sessions,
            settings,
            clock or (lambda: datetime.now(UTC)),
        )

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_RESPONSE,
            occurred_at=self.clock(),
            next_action="核对固定正文、许可和模型回执, 使用新操作人工恢复。",
        )

    def _guard(self, session: Session, message: JobMessage, lease: ExecutionLease) -> None:
        JobExecutionService(
            session, lease_seconds=self.settings.job_lease_seconds, clock=self.clock
        ).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )

    def _ai_guard(
        self,
        session: Session,
        message: JobMessage,
        lease: ExecutionLease,
        run_id: UUID,
        ordinal: int,
    ) -> None:
        self._guard(session, message, lease)
        service = ContentTranslationService(session, clock=self.clock)
        record = service._record(message.owner_id, run_id, lock=True)
        batch = session.get(ContentTranslationBatch, (run_id, ordinal), with_for_update=True)
        latest = service._latest(
            message.owner_id, record.content_id, record.content_version_id, record.policy_revision
        )
        if (
            record.job_id != message.job_id
            or record.status != "running"
            or batch is None
            or batch.owner_id != message.owner_id
            or batch.status != "running"
            or latest is None
            or latest.id != record.id
            or not _valid(session, record, self.clock())
        ):
            raise self._failure("translation_material_changed")
        try:
            require_editorial_content_permission_in_transaction(
                session,
                owner_id=message.owner_id,
                reference=_content_reference(record),
                now=self.clock(),
            )
        except ApplicationError as error:
            raise self._failure("translation_material_changed") from error

    def execute(
        self, message: JobMessage, lease: ExecutionLease, *, ai: AiService | None = None
    ) -> JobCompletion:
        with self.sessions() as session:
            cfg = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                cfg is None
                or cfg.kind != "analysis.translate"
                or cfg.owner_id != message.owner_id
                or cfg.operation_id != message.operation_id
                or cfg.observation.configuration_ref != message.configuration_ref
                or cfg.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("translation_scope_invalid")
            id = UUID(str(cfg.scope["translation_id"]))
        with self.sessions.begin() as session:
            self._guard(session, message, lease)
            record = ContentTranslationService(session, clock=self.clock)._record(
                message.owner_id, id, lock=True
            )
            if record.job_id != message.job_id and not (
                cfg.scope.get("cached") is True and record.status in {"complete", "partial"}
            ):
                raise self._failure("translation_scope_invalid")
            if not _valid(session, record, self.clock()):
                record.status, record.failure_code = "stale", "translation_material_changed"
                stale = True
            else:
                stale = False
            if record.status in {"unknown", "failed", "stale"}:
                blocked = record.failure_code or "translation_requires_review"
            else:
                blocked = None
            if record.status in {"complete", "partial"} and not blocked:
                return JobCompletion(status=JobStatus.SUCCEEDED)
            if ai is None and not self.settings.ai_enabled and not blocked:
                record.status, record.failure_code = "failed", "translation_disabled"
                blocked = "translation_disabled"
            plan = _plan(_grant(session, record, self.clock())) if not stale else None
            if not blocked:
                record.status, record.updated_at = "running", self.clock()
        if blocked:
            raise self._failure(blocked)
        assert plan is not None
        client = None
        try:
            answers: dict[int, str] = {}
            for ordinal, indices in enumerate(plan.batches):
                with self.sessions.begin() as session:
                    self._guard(session, message, lease)
                    record = ContentTranslationService(session, clock=self.clock)._record(
                        message.owner_id, id, lock=True
                    )
                    if not _valid(session, record, self.clock()):
                        raise self._failure("translation_material_changed")
                    batch = session.get(ContentTranslationBatch, (id, ordinal))
                    if batch and batch.status == "succeeded":
                        if batch.answers is None or len(batch.answers) != len(indices):
                            raise self._failure("translation_receipt_invalid")
                        answers.update(zip(indices, batch.answers, strict=True))
                        continue
                    if batch:
                        if batch.status == "running":
                            batch.status, batch.failure_code = (
                                "unknown",
                                "translation_result_unknown",
                            )
                            record.status, record.failure_code = (
                                "unknown",
                                "translation_result_unknown",
                            )
                        blocked = batch.failure_code or "translation_requires_review"
                    else:
                        blocked = None
                        batch = ContentTranslationBatch(
                            run_id=id,
                            ordinal=ordinal,
                            owner_id=message.owner_id,
                            status="running",
                            ai_call_id=None,
                            answers=None,
                            failure_code=None,
                            created_at=self.clock(),
                            updated_at=self.clock(),
                        )
                        session.add(batch)
                if blocked:
                    raise self._failure(blocked)
                failure = None
                response_id = None
                output = None
                try:
                    if ai is None and client is None:
                        if not self.settings.ai_enabled:
                            raise self._failure("translation_disabled")
                        client = create_ai_client(self.settings)
                    with self.sessions() as ai_session:
                        caller = ai
                        if caller is None:
                            assert client is not None
                            caller = AiService(
                                ai_session,
                                client,
                                clock=self.clock,
                                settings=self.settings,
                                guard=lambda current: self._guard(current, message, lease),
                                execution_epoch=lease.epoch,
                            )
                        caller = caller.with_admission_guard(
                            partial(
                                self._ai_guard,
                                message=message,
                                lease=lease,
                                run_id=id,
                                ordinal=ordinal,
                            ),
                            execution_epoch=lease.epoch,
                        )
                        response = caller.complete(
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            purpose="editorial.translation",
                            prompt_version=translation_prompt_version(),
                            instructions=render_editorial_prompt("translate-body"),
                            prompt=json.dumps(
                                {"fragments": [plan.parts[i].html for i in indices]},
                                ensure_ascii=False,
                            ),
                            output_schema=TranslationOutput.model_json_schema(),
                        )
                    response_id = response.call_id
                    if response_id is None:
                        raise self._failure("translation_call_evidence_missing")
                    output = TranslationOutput.model_validate(response.output).t
                    if len(output) != len(indices) or any(
                        unshield(part, plan.parts[index]) is None
                        for index, part in zip(indices, output, strict=True)
                    ):
                        raise ValueError("translation structure mismatch")
                except AiCallError as error:
                    response_id, failure = error.call_id, "translation_" + error.code.value
                except JobExecutionFailure as error:
                    failure = error.error_code
                except (ValidationError, ValueError):
                    failure = "translation_invalid_output"
                with self.sessions.begin() as session:
                    record = ContentTranslationService(session, clock=self.clock)._record(
                        message.owner_id, id, lock=True
                    )
                    batch = session.get(
                        ContentTranslationBatch, (id, ordinal), with_for_update=True
                    )
                    assert batch is not None
                    batch.ai_call_id, batch.answers, batch.updated_at = (
                        response_id,
                        output if not failure else None,
                        self.clock(),
                    )
                    batch.status = (
                        "unknown"
                        if failure == "translation_timeout"
                        else "failed"
                        if failure
                        else "succeeded"
                    )
                    batch.failure_code = failure
                    if failure:
                        record.status, record.failure_code = batch.status, failure
                if failure:
                    raise self._failure(failure)
                assert output is not None
                answers.update(zip(indices, output, strict=True))
            result = assemble_translation(plan, answers)
            with self.sessions.begin() as session:
                self._guard(session, message, lease)
                record = ContentTranslationService(session, clock=self.clock)._record(
                    message.owner_id, id, lock=True
                )
                latest = ContentTranslationService(session)._latest(
                    message.owner_id,
                    record.content_id,
                    record.content_version_id,
                    record.policy_revision,
                )
                if (
                    latest is None
                    or latest.id != record.id
                    or not _valid(session, record, self.clock())
                ):
                    record.status, record.failure_code = "stale", "translation_material_changed"
                    stale = True
                else:
                    record.body_html, record.translated_segments, record.total_segments = (
                        result.html,
                        result.translated_segments,
                        result.total_segments,
                    )
                    record.complete = result.complete or result.total_segments == 0
                    record.status = "complete" if record.complete else "partial"
                    record.failure_code = None
                    record.updated_at = self.clock()
                    stale = False
            if stale:
                raise self._failure("translation_material_changed")
            return JobCompletion(status=JobStatus.SUCCEEDED)
        finally:
            if client is not None:
                client.close()
