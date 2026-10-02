from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_services import freeze_ai_job_scope_in_transaction
from ai.editorial_vision import prepare_editorial_vision_input
from ai.schemas import AiCallError, AiFailureCode, AiImageInput
from ai.services import AiService, create_ai_client
from analysis.editorial_corrections import apply_editorial_correction
from analysis.editorial_models import (
    EditorialContentState,
    EditorialOverride,
    EditorialRun,
    EditorialSource,
    EditorialSourceVersion,
    EditorialStage,
)
from analysis.editorial_pipeline import EditorialStep, next_editorial_step
from analysis.editorial_rules import ENTITIES, pipeline_version
from analysis.editorial_schemas import (
    EditorialMaterial,
    EditorialOverrideInput,
    EditorialResultView,
    EditorialRunInput,
    EditorialRunView,
    EditorialSourceInput,
    EditorialSourceView,
)
from content.editorial_reading import (
    editorial_first_received_at_in_transaction,
    frozen_editorial_content_in_transaction,
    latest_editorial_references_in_transaction,
    latest_quoted_reference_in_transaction,
    require_editorial_content_permission_in_transaction,
)
from content.editorial_vision import read_editorial_vision_grant_in_transaction
from content.schemas import EventContentReadReference
from core.config import Settings
from core.errors import ApplicationError
from evidence.services import load_readable_resources_in_transaction
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, ResourceBudgetService, load_job_execution_configuration

_EDITORIAL_NAMESPACE = UUID("7c5f7b45-2b25-4ae4-8dc7-a5a5bb8c2d83")


def _fingerprint(value: Any) -> bytes:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).digest()


class EditorialService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
        indexing_enabled: bool = False,
    ) -> None:
        self.settings = settings
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))
        self.indexing_enabled = indexing_enabled

    def _operation_lock(self, owner: UUID, operation_id: UUID) -> None:
        """Serialize operation admission, including the first insert without a row to lock."""
        self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"editorial-operation:{owner}:{operation_id}", 0)
                )
            )
        )

    def _source(self, owner: UUID, key: str, *, lock: bool = False) -> EditorialSource:
        statement = select(EditorialSource).where(
            EditorialSource.owner_id == owner, EditorialSource.source_key == key
        )
        if lock:
            statement = statement.with_for_update()
        source = self.session.scalar(statement)
        if source is None:
            raise ApplicationError("resource_not_found")
        return source

    @staticmethod
    def _source_view(
        source: EditorialSource,
        configuration: dict[str, Any] | None = None,
        revision: int | None = None,
    ) -> EditorialSourceView:
        return EditorialSourceView.model_validate(
            {
                "source_key": source.source_key,
                "revision": revision or source.revision,
                **(configuration or source.configuration),
            }
        )

    def save_source(
        self, *, owner_id: UUID, source_key: str, command: EditorialSourceInput
    ) -> EditorialSourceView:
        self.session.rollback()
        with self.session.begin():
            return self.save_source_in_transaction(
                owner_id=owner_id, source_key=source_key, command=command
            )

    def get_source_in_transaction(
        self, *, owner_id: UUID, source_key: str
    ) -> EditorialSourceView | None:
        if not self.session.in_transaction():
            raise RuntimeError("editorial source reads require caller transaction")
        row = self.session.get(EditorialSource, (owner_id, source_key))
        return self._source_view(row) if row is not None else None

    def save_source_in_transaction(
        self, *, owner_id: UUID, source_key: str, command: EditorialSourceInput
    ) -> EditorialSourceView:
        if not self.session.in_transaction():
            raise RuntimeError("editorial source writes require caller transaction")
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", source_key) is None or (
            command.owner_entity_id is not None and command.owner_entity_id not in ENTITIES
        ):
            raise ApplicationError("invalid_editorial_input")
        digest = _fingerprint({"source_key": source_key, **command.model_dump(mode="json")})
        configuration = command.model_dump(
            mode="json", exclude={"operation_id", "expected_revision"}
        )
        self._operation_lock(owner_id, command.operation_id)
        self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"editorial-source:{owner_id}:{source_key}", 0)
                )
            )
        )
        existing = self.session.scalar(
            select(EditorialSourceVersion).where(
                EditorialSourceVersion.owner_id == owner_id,
                EditorialSourceVersion.operation_id == command.operation_id,
            )
        )
        if existing is not None:
            if existing.input_fingerprint != digest:
                raise ApplicationError("idempotency_conflict")
            return EditorialSourceView.model_validate(
                {
                    "source_key": existing.source_key,
                    "revision": existing.revision,
                    **existing.configuration,
                }
            )
        source = self.session.scalar(
            select(EditorialSource)
            .where(EditorialSource.owner_id == owner_id, EditorialSource.source_key == source_key)
            .with_for_update()
        )
        now = self.clock()
        if source is None:
            if command.expected_revision != 0:
                raise ApplicationError("editorial_version_conflict")
            source = EditorialSource(
                owner_id=owner_id,
                source_key=source_key,
                revision=1,
                configuration=configuration,
                scan_cursor=None,
                created_at=now,
                updated_at=now,
            )
            self.session.add(source)
            self.session.flush()
        else:
            if source.revision != command.expected_revision:
                raise ApplicationError("editorial_version_conflict")
            source.revision += 1
            source.configuration = configuration
            source.scan_cursor = None
            source.updated_at = now
        self.session.add(
            EditorialSourceVersion(
                owner_id=owner_id,
                source_key=source_key,
                revision=source.revision,
                operation_id=command.operation_id,
                input_fingerprint=digest,
                configuration=configuration,
                created_at=now,
            )
        )
        return self._source_view(source)

    def list_sources(self, *, owner_id: UUID) -> list[EditorialSourceView]:
        self.session.rollback()
        with self.session.begin():
            return [
                self._source_view(source)
                for source in self.session.scalars(
                    select(EditorialSource)
                    .where(EditorialSource.owner_id == owner_id)
                    .order_by(EditorialSource.source_key)
                )
            ]

    def _load_material(self, run: EditorialRun) -> EditorialMaterial:
        reference = EventContentReadReference(
            content_id=run.content_id, content_version_id=run.content_version_id
        )
        now = self.clock()
        item = frozen_editorial_content_in_transaction(
            self.session, owner_id=run.owner_id, reference=reference, now=now
        )
        profile = self.session.get(
            EditorialSourceVersion, (run.owner_id, run.source_key, run.source_revision)
        )
        if (
            item is None
            or profile is None
            or item.source_key != run.source_key
            or item.observation.content_version is None
        ):
            raise ApplicationError("editorial_material_unavailable")
        version = item.observation.content_version
        quoted_text, quoted_author = "", ""
        quote = run.input_manifest.get("quote")
        if quote:
            quote_ref = EventContentReadReference(
                content_id=UUID(quote["content_id"]),
                content_version_id=UUID(quote["content_version_id"]),
            )
            quoted = frozen_editorial_content_in_transaction(
                self.session, owner_id=run.owner_id, reference=quote_ref, now=now
            )
            if quoted is None or quoted.observation.content_version is None:
                raise ApplicationError("editorial_material_unavailable")
            quoted_text = (
                quoted.observation.content_version.body
                or quoted.observation.content_version.title
                or ""
            )
            quoted_author = quoted.observation.author_external_id or ""
        return EditorialMaterial.model_validate(
            {
                "content_id": run.content_id,
                "content_version_id": run.content_version_id,
                "source_key": run.source_key,
                "source_name": profile.configuration["name"],
                "source_kind": profile.configuration["source_kind"],
                "tier": profile.configuration["tier"],
                "title": version.title or "",
                "body": version.body or "",
                "body_complete": version.text_scope.value == "full",
                "url": item.observation.canonical_url or item.observation.final_url or "",
                "author": item.observation.author_external_id,
                "published_at": item.observation.published_at,
                "discovered_at": editorial_first_received_at_in_transaction(
                    self.session, owner_id=run.owner_id, reference=reference
                )
                or item.observation.received_at,
                "first_party": profile.configuration["first_party"],
                "owner_entity_id": profile.configuration["owner_entity_id"],
                "source_tags": profile.configuration["tags"],
                "quoted_text": quoted_text,
                "quoted_author": quoted_author,
            }
        )

    def request_run(
        self, *, owner_id: UUID, content_id: UUID, source_key: str, command: EditorialRunInput
    ) -> EditorialRunView:
        self.session.rollback()
        with self.session.begin():
            return self.request_run_in_transaction(
                owner_id=owner_id, content_id=content_id, source_key=source_key, command=command
            )

    def request_run_in_transaction(
        self, *, owner_id: UUID, content_id: UUID, source_key: str, command: EditorialRunInput
    ) -> EditorialRunView:
        if not self.session.in_transaction():
            raise RuntimeError("editorial admission requires caller transaction")
        self._operation_lock(owner_id, command.operation_id)
        digest = _fingerprint(
            {"content_id": content_id, "source_key": source_key, **command.model_dump(mode="json")}
        )
        existing = self.session.scalar(
            select(EditorialRun).where(
                EditorialRun.owner_id == owner_id, EditorialRun.operation_id == command.operation_id
            )
        )
        if existing is not None:
            if existing.request_fingerprint != digest:
                raise ApplicationError("idempotency_conflict")
            return EditorialRunView.model_validate(existing)
        source = self._source(owner_id, source_key, lock=True)
        if not source.configuration["enabled"]:
            raise ApplicationError("editorial_source_disabled")
        state = self.session.get(
            EditorialContentState, (owner_id, content_id), with_for_update=True
        )
        manual_version = state.manual_version if state is not None else 0
        if manual_version != command.expected_manual_version:
            raise ApplicationError("editorial_version_conflict")
        now = self.clock()
        run = EditorialRun(
            id=uuid4(),
            owner_id=owner_id,
            operation_id=command.operation_id,
            content_id=content_id,
            content_version_id=command.content_version_id,
            source_key=source_key,
            source_revision=source.revision,
            job_id=None,
            prompt_version=pipeline_version(),
            input_fingerprint=bytes(32),
            request_fingerprint=digest,
            input_manifest={},
            stages=command.stages,
            manual_version=manual_version,
            execution_token=None,
            status="queued",
            result=None,
            failure_code=None,
            created_at=now,
            updated_at=now,
        )
        main = frozen_editorial_content_in_transaction(
            self.session,
            owner_id=owner_id,
            reference=EventContentReadReference(
                content_id=content_id, content_version_id=command.content_version_id
            ),
            now=now,
        )
        if main is None or main.source_key != source_key:
            raise ApplicationError("editorial_material_unavailable")
        quote = latest_quoted_reference_in_transaction(
            self.session, owner_id=owner_id, main=main, now=now
        )
        if quote is not None:
            run.input_manifest = {
                "quote": {
                    "content_id": str(quote.content_id),
                    "content_version_id": str(quote.content_version_id),
                }
            }
        run.input_fingerprint = _fingerprint(self._load_material(run).model_dump(mode="json"))
        self.session.add(run)
        self.session.flush()
        if state is None:
            self.session.add(
                EditorialContentState(
                    owner_id=owner_id,
                    content_id=content_id,
                    current_run_id=run.id,
                    manual_version=manual_version,
                    updated_at=now,
                )
            )
        else:
            state.current_run_id, state.updated_at = run.id, now
        job = JobService(self.session, clock=self.clock).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=command.operation_id,
                kind="analysis.editorial",
                observation=JobObservationContext(
                    configuration_ref=f"editorial:{run.id}", configuration_version=source.revision
                ),
                scope={
                    "run_id": str(run.id),
                    "prompt_version": run.prompt_version,
                    **freeze_ai_job_scope_in_transaction(
                        self.session, owner_id=owner_id, settings=self.settings
                    ),
                },
            ),
        )
        run.job_id = job.id
        return EditorialRunView.model_validate(run)

    def get_current_run(self, *, owner_id: UUID, content_id: UUID) -> EditorialRunView:
        self.session.rollback()
        with self.session.begin():
            state = self.session.get(EditorialContentState, (owner_id, content_id))
            if state is None:
                raise ApplicationError("resource_not_found")
            run = self._run(owner_id, state.current_run_id)
            self._load_material(run)
            return EditorialRunView.model_validate(run)

    def get_run(self, *, owner_id: UUID, run_id: UUID) -> EditorialRunView:
        self.session.rollback()
        with self.session.begin():
            run = self._run(owner_id, run_id)
            self._load_material(run)
            return EditorialRunView.model_validate(run)

    def _run(self, owner: UUID, run_id: UUID, *, lock: bool = False) -> EditorialRun:
        statement = select(EditorialRun).where(
            EditorialRun.owner_id == owner, EditorialRun.id == run_id
        )
        if lock:
            statement = statement.with_for_update()
        run = self.session.scalar(statement)
        if run is None:
            raise ApplicationError("resource_not_found")
        return run

    def enqueue_due_in_transaction(self, *, now: datetime, limit: int = 100) -> int:
        if not self.session.in_transaction() or not 1 <= limit <= 100:
            raise ValueError("editorial scan requires bounded caller transaction")
        count = 0
        sources = self.session.scalars(
            select(EditorialSource)
            .order_by(EditorialSource.owner_id, EditorialSource.source_key)
            .with_for_update(skip_locked=True)
        )
        for source in sources:
            if not source.configuration["enabled"]:
                continue
            candidates = latest_editorial_references_in_transaction(
                self.session,
                owner_id=source.owner_id,
                source_key=source.source_key,
                now=now,
                after=source.scan_cursor,
                limit=100,
            )
            for reference in candidates:
                operation = uuid5(
                    _EDITORIAL_NAMESPACE,
                    f"{source.owner_id}:{reference.content_version_id}:{source.revision}:{pipeline_version()}",
                )
                if (
                    self.session.scalar(
                        select(EditorialRun.id).where(
                            EditorialRun.owner_id == source.owner_id,
                            EditorialRun.operation_id == operation,
                        )
                    )
                    is not None
                ):
                    continue
                state = self.session.get(
                    EditorialContentState, (source.owner_id, reference.content_id)
                )
                # An explicit human correction is not overwritten by a background scan.
                if state is not None:
                    current = self.session.get(EditorialRun, state.current_run_id)
                    if current is not None and (current.result or {}).get("manual"):
                        continue
                try:
                    with self.session.begin_nested():
                        self.request_run_in_transaction(
                            owner_id=source.owner_id,
                            content_id=reference.content_id,
                            source_key=source.source_key,
                            command=EditorialRunInput(
                                operation_id=operation,
                                content_version_id=reference.content_version_id,
                                expected_manual_version=state.manual_version if state else 0,
                            ),
                        )
                except ApplicationError as error:
                    if error.code != "editorial_material_unavailable":
                        raise
                    continue
                count += 1
                if count >= limit:
                    source.scan_cursor = reference.content_id
                    return count
            source.scan_cursor = candidates[-1].content_id if len(candidates) == 100 else None
        return count

    def override(
        self, *, owner_id: UUID, run_id: UUID, command: EditorialOverrideInput
    ) -> EditorialRunView:
        digest = _fingerprint({"run_id": run_id, **command.model_dump(mode="json")})
        self.session.rollback()
        with self.session.begin():
            self._operation_lock(owner_id, command.operation_id)
            old = self.session.scalar(
                select(EditorialOverride).where(
                    EditorialOverride.owner_id == owner_id,
                    EditorialOverride.operation_id == command.operation_id,
                )
            )
            if old is not None:
                if old.input_fingerprint != digest:
                    raise ApplicationError("idempotency_conflict")
                original_run = self._run(owner_id, old.run_id)
                self._load_material(original_run)
                return EditorialRunView.model_validate(original_run).model_copy(
                    update={
                        "manual_version": old.revision,
                        "result": EditorialResultView.model_validate(old.after),
                        "updated_at": old.created_at,
                        "status": "blocked"
                        if old.after.get("relevance") == "block"
                        else "complete",
                        "failure_code": None,
                    }
                )
            preliminary = self._run(owner_id, run_id)
            self._source(owner_id, preliminary.source_key, lock=True)
            state = self.session.get(
                EditorialContentState, (owner_id, preliminary.content_id), with_for_update=True
            )
            run = self._run(owner_id, run_id, lock=True)
            if (
                state is None
                or state.current_run_id != run.id
                or state.manual_version != command.expected_manual_version
            ):
                raise ApplicationError("editorial_version_conflict")
            material = self._load_material(run)
            before = run.result
            first_override = self.session.scalar(
                select(EditorialOverride)
                .where(EditorialOverride.owner_id == owner_id, EditorialOverride.run_id == run.id)
                .order_by(EditorialOverride.revision, EditorialOverride.id)
                .limit(1)
            )
            result = apply_editorial_correction(
                material=material,
                automatic=first_override.before if first_override else before,
                current=before,
                command=command,
            )
            revision = state.manual_version + 1
            saved_at = self.clock()
            self.session.add(
                EditorialOverride(
                    id=uuid4(),
                    owner_id=owner_id,
                    run_id=run.id,
                    operation_id=command.operation_id,
                    input_fingerprint=digest,
                    revision=revision,
                    before=before,
                    after=result,
                    reason=command.reason,
                    created_at=saved_at,
                )
            )
            state.manual_version = run.manual_version = revision
            run.result, run.status, run.failure_code, run.updated_at = (
                result,
                "blocked" if result.get("relevance") == "block" else "complete",
                None,
                saved_at,
            )
            state.updated_at = saved_at
            from publication.services import PublicationService

            self.session.flush()
            PublicationService(
                self.session, indexing_enabled=self.indexing_enabled
            ).publish_in_transaction(owner_id=owner_id, content_id=run.content_id, now=saved_at)
            return EditorialRunView.model_validate(run)


class EditorialExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, message: JobMessage, lease: ExecutionLease, *, ai: AiService | None = None
    ) -> JobCompletion:
        with self.sessions() as session:
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.kind != "analysis.editorial"
            ):
                raise self._failure("editorial_scope_invalid")
            try:
                run_id = UUID(cast(str, configuration.scope["run_id"]))
            except (KeyError, ValueError, TypeError) as error:
                raise self._failure("editorial_scope_invalid") from error
        client = None
        if ai is None and self.settings.ai_enabled:
            try:
                client = create_ai_client(self.settings)
            except AiCallError as error:
                raise self._failure("editorial_model_disabled") from error
            with self.sessions() as session:
                ai = AiService(
                    session,
                    client,
                    clock=self.clock,
                    settings=self.settings,
                    guard=lambda current: self._lease(current, message, lease),
                    execution_epoch=lease.epoch,
                )
        try:
            return self._execute(message, lease, run_id, ai)
        finally:
            if client is not None:
                client.close()

    def _lease(self, session: Session, message: JobMessage, lease: ExecutionLease) -> None:
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
        *,
        expected_manual_version: int | None = None,
    ) -> None:
        self._lease(session, message, lease)
        try:
            run, _ = self._locked(
                EditorialService(session, settings=self.settings, clock=self.clock), message, run_id
            )
        except ApplicationError as error:
            raise self._failure("editorial_material_changed") from error
        if expected_manual_version is not None and run.manual_version != expected_manual_version:
            raise self._failure("editorial_stale_input")
        vision = run.input_manifest.get("vision")
        if vision and vision.get("mode") == "image":
            grant = read_editorial_vision_grant_in_transaction(
                session,
                owner_id=message.owner_id,
                reference=EventContentReadReference(
                    content_id=run.content_id, content_version_id=run.content_version_id
                ),
                now=self.clock(),
            )
            evidence_id = UUID(vision["evidence_id"])
            resource_id = UUID(vision["resource_id"])
            current = load_readable_resources_in_transaction(
                session,
                owner_id=message.owner_id,
                resource_type="ai_vision_input",
                resource_ids={resource_id},
                now=self.clock(),
            )
            if (
                grant is None
                or grant.rendered_sha256 != vision["rendered_sha256"]
                or resource_id not in current
                or current[resource_id].id != evidence_id
            ):
                raise self._failure("editorial_vision_permission_changed")

    def _locked(
        self, service: EditorialService, message: JobMessage, run_id: UUID
    ) -> tuple[EditorialRun, EditorialMaterial]:
        preliminary = service._run(message.owner_id, run_id)
        source = service._source(message.owner_id, preliminary.source_key, lock=True)
        state = service.session.get(
            EditorialContentState, (message.owner_id, preliminary.content_id), with_for_update=True
        )
        run = service._run(message.owner_id, run_id, lock=True)
        if run.job_id != message.job_id or run.operation_id != message.operation_id:
            raise self._failure("editorial_scope_invalid")
        if (
            state is None
            or state.current_run_id != run.id
            or state.manual_version != run.manual_version
            or source.revision != run.source_revision
            or not source.configuration["enabled"]
            or run.prompt_version != pipeline_version()
        ):
            raise self._failure("editorial_stale_input")
        material = service._load_material(run)
        if _fingerprint(material.model_dump(mode="json")) != run.input_fingerprint:
            raise self._failure("editorial_stale_input")
        references = [
            EventContentReadReference(
                content_id=run.content_id, content_version_id=run.content_version_id
            )
        ]
        quote = run.input_manifest.get("quote")
        if quote:
            references.append(
                EventContentReadReference(
                    content_id=UUID(quote["content_id"]),
                    content_version_id=UUID(quote["content_version_id"]),
                )
            )
        try:
            for reference in references:
                require_editorial_content_permission_in_transaction(
                    service.session,
                    owner_id=message.owner_id,
                    reference=reference,
                    now=self.clock(),
                )
        except ApplicationError as error:
            raise self._failure("editorial_material_changed") from error
        return run, material

    def _execute(
        self, message: JobMessage, lease: ExecutionLease, run_id: UUID, ai: AiService | None
    ) -> JobCompletion:
        token = uuid5(message.job_id, str(lease.epoch))
        for _ in range(8):
            with self.sessions.begin() as session:
                self._lease(session, message, lease)
                service = EditorialService(session, settings=self.settings, clock=self.clock)
                run, material = self._locked(service, message, run_id)
                if run.status in {"complete", "blocked"}:
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                if run.status in {"failed", "unknown", "stale"}:
                    raise self._failure(run.failure_code or "editorial_requires_review")
                stages = {
                    stage.stage_key: stage
                    for stage in session.scalars(
                        select(EditorialStage).where(
                            EditorialStage.owner_id == message.owner_id,
                            EditorialStage.run_id == run.id,
                        )
                    )
                }
                outputs = {
                    key: row.output
                    for key, row in stages.items()
                    if row.status == "succeeded" and row.output is not None
                }
                plan = next_editorial_step(
                    material, outputs, now=run.created_at, selection_only=run.stages == "selection"
                )
                if isinstance(plan, dict):
                    run.result, run.status, run.failure_code, run.updated_at = (
                        plan,
                        "blocked" if plan["relevance"] == "block" else "complete",
                        None,
                        self.clock(),
                    )
                    from publication.services import PublicationService

                    session.flush()
                    PublicationService(
                        session, indexing_enabled=self.settings.publication_indexing_enabled
                    ).publish_in_transaction(
                        owner_id=message.owner_id, content_id=run.content_id, now=self.clock()
                    )
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                old = stages.get(plan.key)
                if old is not None:
                    # Preserve ambiguous execution without paying again.
                    if old.status == "running" and plan.key == "understand":
                        ResourceBudgetService(
                            session, clock=self.clock
                        ).recover_abandoned_attempts_in_transaction(
                            owner_id=message.owner_id,
                            operation_id=message.operation_id,
                            component_key="ai.vision.fetch",
                            stage=f"ai.vision.http:{old.id.hex}",
                            finished_at=self.clock(),
                        )
                    old.status = "unknown" if old.status == "running" else old.status
                    run.status, run.failure_code, run.updated_at = (
                        "unknown",
                        "editorial_result_unknown",
                        self.clock(),
                    )
                    stage_unknown = True
                    stage_id = old.id
                else:
                    stage_id = uuid4()
                    digest = _fingerprint(
                        {
                            "instructions": plan.instructions,
                            "prompt": plan.prompt,
                            "schema": plan.output_type.model_json_schema(),
                            "version": plan.prompt_version,
                        }
                    )
                    session.add(
                        EditorialStage(
                            id=stage_id,
                            owner_id=message.owner_id,
                            run_id=run.id,
                            stage_key=plan.key,
                            prompt_version=plan.prompt_version,
                            input_fingerprint=digest,
                            status="running",
                            output=None,
                            ai_call_id=None,
                            failure_code=None,
                            started_at=self.clock(),
                            completed_at=None,
                        )
                    )
                    run.status, run.execution_token, run.updated_at = "running", token, self.clock()
                    stage_unknown = False
                captured_manual_version = run.manual_version
            if stage_unknown:
                raise self._failure("editorial_result_unknown")
            assert isinstance(plan, EditorialStep)
            call_id = None
            failure: str | None = None
            output: dict[str, Any] | None = None
            try:
                if ai is None:
                    raise AiCallError(AiFailureCode.UNAVAILABLE, "AI calls are paused")
                images: tuple[AiImageInput, ...] = ()
                if plan.key == "understand":
                    vision = prepare_editorial_vision_input(
                        self.sessions,
                        settings=self.settings,
                        message=message,
                        lease=lease,
                        reference=EventContentReadReference(
                            content_id=material.content_id,
                            content_version_id=material.content_version_id,
                        ),
                        stage_id=stage_id,
                        guard=partial(
                            self._ai_guard,
                            message=message,
                            lease=lease,
                            run_id=run_id,
                            expected_manual_version=captured_manual_version,
                        ),
                        clock=self.clock,
                    )
                    if vision.image is not None:
                        images = (vision.image,)
                    with self.sessions.begin() as session:
                        self._ai_guard(
                            session,
                            message,
                            lease,
                            run_id,
                            expected_manual_version=captured_manual_version,
                        )
                        stored = session.get(EditorialRun, run_id, with_for_update=True)
                        assert stored is not None
                        stored.input_manifest = {
                            **stored.input_manifest,
                            "vision": {
                                "mode": vision.mode,
                                "image_sha256": vision.image.sha256 if vision.image else None,
                                "evidence_id": str(vision.evidence_id)
                                if vision.evidence_id
                                else None,
                                "resource_id": str(vision.resource_id)
                                if vision.resource_id
                                else None,
                                "rendered_sha256": vision.rendered_sha256,
                            },
                        }
                caller = ai.with_admission_guard(
                    partial(
                        self._ai_guard,
                        message=message,
                        lease=lease,
                        run_id=run_id,
                        expected_manual_version=captured_manual_version,
                    ),
                    execution_epoch=lease.epoch,
                )
                response = caller.complete(
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    purpose=f"editorial.{plan.key}",
                    prompt_version=plan.prompt_version,
                    prompt=plan.prompt,
                    output_schema=plan.output_type.model_json_schema(),
                    instructions=plan.instructions,
                    images=images,
                )
                call_id = response.call_id
                if call_id is None:
                    failure = "editorial_call_evidence_missing"
                else:
                    output = plan.output_type.model_validate(response.output).model_dump(
                        mode="json", by_alias=True
                    )
            except AiCallError as error:
                call_id = error.call_id
                failure = (
                    "editorial_timeout"
                    if error.outcome_unknown
                    else f"editorial_{error.code.value}"
                )
            except JobExecutionFailure as error:
                failure = error.error_code
            except ValidationError:
                failure = "editorial_invalid_output"
            with self.sessions.begin() as session:
                row = session.get(EditorialStage, stage_id, with_for_update=True)
                if row is None:
                    raise self._failure("editorial_stage_missing")
                row.output, row.ai_call_id, row.failure_code, row.completed_at = (
                    output,
                    call_id,
                    failure,
                    self.clock(),
                )
                row.status = (
                    "succeeded"
                    if output is not None
                    else "unknown"
                    if failure in {"editorial_timeout", "editorial_call_evidence_missing"}
                    else "failed"
                )
                failure_status = row.status
            if failure is not None:
                with self.sessions.begin() as session:
                    service = EditorialService(session, settings=self.settings, clock=self.clock)
                    preliminary = service._run(message.owner_id, run_id)
                    service._source(message.owner_id, preliminary.source_key, lock=True)
                    state = session.get(
                        EditorialContentState,
                        (message.owner_id, preliminary.content_id),
                        with_for_update=True,
                    )
                    failed_run = service._run(message.owner_id, run_id, lock=True)
                    if (
                        state is not None
                        and state.current_run_id == run_id
                        and state.manual_version == captured_manual_version
                        and failed_run.manual_version == captured_manual_version
                        and failed_run.execution_token == token
                    ):
                        failed_run.status = failure_status
                        failed_run.failure_code = failure
                        failed_run.updated_at = self.clock()
                raise self._failure(failure)
        raise self._failure("editorial_stage_limit")

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_RESPONSE,
            occurred_at=self.clock(),
            next_action="核对阶段证据与当前材料后, 显式发起新评价。",
            manual_retry_allowed=False,
        )
