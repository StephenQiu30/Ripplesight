"""Original fenced Job execution for local private exports; no provider collection or delivery."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from core.errors import ApplicationError
from evidence.export_cleanup import attach_export_cleanup_targets_in_transaction
from evidence.schemas import ProvenanceManifestInput, ProvenanceResourceRef
from evidence.services import (
    ProvenanceService,
    ResourceUnavailableError,
    load_readable_resources_in_transaction,
)
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionError,
    JobExecutionFailure,
    JobExecutionService,
)
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration
from reports.export_rendering import ExportArtifact, ExportRenderError, render_export
from reports.export_schemas import (
    EXPORT_MAX_BYTES,
    EXPORT_TIMEOUT_SECONDS,
    ExportFormat,
    ExportKind,
)
from reports.export_services import (
    ExportStorage,
    PrivateExportService,
    document_for_record,
    object_name,
)


class PrivateExportExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: ExportStorage | None,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] | None = None,
        renderer: Callable[..., ExportArtifact] = render_export,
    ) -> None:
        self.sessions, self.storage, self.lease_seconds = sessions, storage, lease_seconds
        self.clock, self.renderer = clock or (lambda: datetime.now(UTC)), renderer

    def _lease(self, session: Session, message: JobMessage, lease: ExecutionLease) -> None:
        JobExecutionService(
            session, clock=self.clock, lease_seconds=self.lease_seconds
        ).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )

    def _failure(
        self, code: str, category: JobFailureCategory = JobFailureCategory.INVALID_RESPONSE
    ) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self.clock(),
            next_action="复核固定输入、当前导出用途、对象存储及本机渲染器后使用原任务人工重试。",
            manual_retry_allowed=True,
        )

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> JobCompletion | None:
        deadline = time.monotonic() + EXPORT_TIMEOUT_SECONDS
        kind = cast(ExportKind, message.kind.removesuffix(".export"))
        if kind not in {"report", "content"}:
            raise self._failure("export_scope_invalid", JobFailureCategory.INVALID_INPUT)
        identifier: UUID | None = None
        try:
            with self.sessions.begin() as session:
                self._lease(session, message, lease)
                configuration = load_job_execution_configuration(session, job_id=message.job_id)
                if (
                    configuration is None
                    or configuration.kind != message.kind
                    or configuration.owner_id != message.owner_id
                    or configuration.operation_id != message.operation_id
                    or configuration.observation.configuration_ref != message.configuration_ref
                    or configuration.observation.configuration_version
                    != message.configuration_version
                ):
                    raise self._failure("export_scope_invalid", JobFailureCategory.INVALID_INPUT)
                identifier = UUID(str(configuration.scope.get("export_id")))
                if (
                    message.configuration_ref != f"private-export:{identifier.hex}"
                    or message.configuration_version != 1
                    or configuration.scope.get("export_kind") != kind
                ):
                    raise self._failure("export_scope_invalid", JobFailureCategory.INVALID_INPUT)
                service = PrivateExportService(session, self.storage, clock=self.clock)
                record = service._record(message.owner_id, identifier, kind, lock=True)
                if record.job_id != message.job_id or record.operation_id != message.operation_id:
                    raise self._failure("export_scope_invalid", JobFailureCategory.INVALID_INPUT)
                document = document_for_record(session, record, self.clock())
                if record.status == "succeeded":
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                if self.storage is None:
                    raise self._failure(
                        "export_storage_unavailable", JobFailureCategory.CONFIGURATION_UNAVAILABLE
                    )
                name, format = object_name(record), cast(ExportFormat, record.format)
                raw_observations = document.manifest.get("observation_ids", [])
                if not isinstance(raw_observations, list):
                    raise self._failure("export_scope_invalid", JobFailureCategory.INVALID_INPUT)
                observations = tuple(UUID(str(item)) for item in raw_observations)
                # Register before object PUT: a crash or cancellation cannot orphan provider data.
                for start in range(0, len(observations), 1000):
                    attach_export_cleanup_targets_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        observation_ids=observations[start : start + 1000],
                        object_name=name,
                        now=self.clock(),
                    )
                # Existing Provenance has a 256-reference bound; every batch has its own result key.
                # This preserves all actual original inputs instead of sampling them to fit a limit.
                for start in range(0, len(observations), 256):
                    batch = observations[start : start + 256]
                    resources = load_readable_resources_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        resource_type="content_observation",
                        resource_ids=set(batch),
                        now=self.clock(),
                    )
                    if set(resources) != set(batch):
                        raise ResourceUnavailableError("an export input is unavailable")
                    refs = tuple(
                        ProvenanceResourceRef(
                            resource_record_id=resources[item].id,
                            snapshot_ref=f"content-observation:{item.hex}",
                        )
                        for item in batch
                    )
                    ProvenanceService(session, clock=self.clock).create_in_transaction(
                        owner_id=message.owner_id,
                        command=ProvenanceManifestInput(
                            job_id=message.job_id,
                            result_kind=f"private_export_inputs_{start // 256}",
                            method_key="private-file-export",
                            method_version=record.renderer_version,
                            method_parameters={
                                "export_id": str(record.id),
                                "input_digest": record.input_hash.hex(),
                                "format": record.format,
                            },
                            subjects=refs[:1],
                            references=refs[1:]
                            or (
                                ProvenanceResourceRef(
                                    resource_record_id=refs[0].resource_record_id,
                                    snapshot_ref=f"export-input:{record.id.hex}:{batch[0].hex}",
                                ),
                            ),
                        ),
                    )
                record.status, record.failure_code, record.updated_at = (
                    "running",
                    None,
                    self.clock(),
                )
            if cancelled():
                return None
            artifact = self.renderer(document, format, deadline=deadline)
            if not 1 <= len(artifact.body) <= EXPORT_MAX_BYTES:
                raise ExportRenderError("export_size_exceeded")
            if time.monotonic() >= deadline:
                raise ExportRenderError("export_timeout")
            if cancelled():
                return None
            with self.sessions.begin() as session:
                self._lease(session, message, lease)
                record = PrivateExportService(session, self.storage, clock=self.clock)._record(
                    message.owner_id, identifier, kind, lock=True
                )
                document_for_record(session, record, self.clock())
                # Hold lease and source permission locks while performing this bounded private PUT.
                assert self.storage is not None
                self.storage.check_bucket()
                self.storage.put(name, artifact.body, artifact.mime_type)
                self._lease(session, message, lease)
                document_for_record(session, record, self.clock())
                if time.monotonic() >= deadline:
                    raise ExportRenderError("export_timeout")
                record.status, record.failure_code = "succeeded", None
                record.object_name, record.object_sha256 = name, artifact.sha256
                record.object_size, record.mime_type, record.updated_at = (
                    len(artifact.body),
                    artifact.mime_type,
                    self.clock(),
                )
            return JobCompletion(status=JobStatus.SUCCEEDED)
        except (
            ApplicationError,
            ResourceUnavailableError,
            ExportRenderError,
            JobExecutionFailure,
        ) as error:
            code = (
                error.code
                if isinstance(error, (ApplicationError, ExportRenderError))
                else error.error_code
                if isinstance(error, JobExecutionFailure)
                else "export_input_unavailable"
            )
            if identifier is not None:
                with self.sessions.begin() as session:
                    self._lease(session, message, lease)
                    record = PrivateExportService(session, self.storage, clock=self.clock)._record(
                        message.owner_id, identifier, kind, lock=True
                    )
                    if record.status != "succeeded":
                        record.status = (
                            "blocked"
                            if code
                            in {
                                "editorial_export_not_authorized",
                                "editorial_material_unavailable",
                                "export_input_unavailable",
                                "export_version_conflict",
                            }
                            else "failed"
                        )
                        record.failure_code, record.updated_at = code, self.clock()
            raise self._failure(code) from error
        except JobExecutionError:
            # A previous executor cannot convert a lost fence into a new business failure/write.
            raise
        except Exception as error:
            # External exception text and original material never enter job details.
            if identifier is not None:
                with self.sessions.begin() as session:
                    self._lease(session, message, lease)
                    record = PrivateExportService(session, self.storage, clock=self.clock)._record(
                        message.owner_id, identifier, kind, lock=True
                    )
                    if record.status != "succeeded":
                        record.status, record.failure_code, record.updated_at = (
                            "failed",
                            "export_artifact_failed",
                            self.clock(),
                        )
            raise self._failure("export_artifact_failed") from error
