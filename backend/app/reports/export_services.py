"""Accept fixed private exports through original Jobs, and recheck ALL inputs on download."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from content.export_reading import (
    ContentExportItem,
    FrozenContentExportInput,
    freeze_export_content_in_transaction,
    require_export_observations_in_transaction,
    restore_export_content_in_transaction,
)
from core.errors import ApplicationError
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobStatus
from jobs.services import JobService, load_job_cancellation_state_in_transaction
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from reports.export_models import ContentExportRequest, ReportExport
from reports.export_schemas import (
    EXPORT_MAX_BYTES,
    EXPORT_MAX_ITEMS,
    EXPORT_RENDERER_VERSION,
    EXPORT_SCHEMA_VERSION,
    ContentExportInput,
    ExportDocument,
    ExportFormat,
    ExportKind,
    ExportStatus,
    ExportView,
    ReportExportInput,
)
from reports.models import Report
from reports.notification_reading import load_notification_report_in_transaction
from reports.schemas import ReportInputManifest

type ExportRecord = ReportExport | ContentExportRequest


class ExportStorage(Protocol):
    def check_bucket(self) -> None: ...
    def put(self, name: str, body: bytes, mime_type: str) -> None: ...
    def get(self, name: str, *, max_bytes: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ExportDownload:
    body: bytes
    mime_type: str
    filename: str
    sha256: str


def json_value(value: object) -> object:
    return json.loads(
        json.dumps(
            value,
            default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
        )
    )


def digest(value: object) -> bytes:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).digest()


def _content(
    session: Session,
    owner_id: UUID,
    versions: tuple[UUID, ...],
    now: datetime,
    *,
    frozen_inputs: tuple[FrozenContentExportInput, ...] | None = None,
    observation_ids: tuple[UUID, ...] | None = None,
) -> tuple[ContentExportItem, ...]:
    if len(versions) > EXPORT_MAX_ITEMS or len(set(versions)) != len(versions):
        raise ApplicationError("invalid_export_input")
    if frozen_inputs is not None and tuple(item.version_id for item in frozen_inputs) != versions:
        raise ApplicationError("export_input_unavailable")
    result: dict[UUID, ContentExportItem] = {}
    size = 0
    for start in range(0, len(versions), 32):
        if frozen_inputs is not None:
            batch = restore_export_content_in_transaction(
                session, owner_id=owner_id, frozen_inputs=frozen_inputs[start : start + 32], now=now
            )
        else:
            batch = freeze_export_content_in_transaction(
                session,
                owner_id=owner_id,
                content_version_ids=versions[start : start + 32],
                now=now,
                observation_ids=observation_ids,
            )
        for item in batch:
            size += len(json.dumps(json_value(asdict(item)), ensure_ascii=False).encode())
            if size > EXPORT_MAX_BYTES:
                raise ApplicationError("invalid_export_input")
            result[item.version_id] = item
    return tuple(result[item] for item in versions)


def _rows(items: tuple[ContentExportItem, ...]) -> tuple[dict[str, object], ...]:
    return tuple(cast(dict[str, object], json_value(asdict(item))) for item in items)


def _content_inputs(items: tuple[ContentExportItem, ...]) -> list[dict[str, object]]:
    try:
        return [
            FrozenContentExportInput(
                version_id=item.version_id,
                observation_id=item.observation_id,
                input_observation_ids=item.input_observation_ids,
                discovered_at=item.discovered_at,
            ).model_dump(mode="json")
            for item in items
        ]
    except ValidationError:
        raise ApplicationError("invalid_export_input") from None


def _frozen_inputs(manifest: dict[str, object]) -> tuple[FrozenContentExportInput, ...]:
    raw = manifest.get("content_inputs")
    if not isinstance(raw, list) or len(raw) > EXPORT_MAX_ITEMS:
        raise ApplicationError("export_input_unavailable")
    try:
        return tuple(FrozenContentExportInput.model_validate(item) for item in raw)
    except (ValidationError, ValueError):
        raise ApplicationError("export_input_unavailable") from None


def freeze_content_document(
    session: Session,
    *,
    owner_id: UUID,
    versions: tuple[UUID, ...],
    now: datetime,
    frozen_inputs: tuple[FrozenContentExportInput, ...] | None = None,
) -> ExportDocument:
    items = _content(session, owner_id, versions, now, frozen_inputs=frozen_inputs)
    manifest: dict[str, object] = {
        "content_version_ids": [str(item) for item in versions],
        "content_inputs": _content_inputs(items),
        "observation_ids": sorted(
            {str(value) for item in items for value in item.input_observation_ids}
        ),
        "schema_version": EXPORT_SCHEMA_VERSION,
        "renderer_version": EXPORT_RENDERER_VERSION,
    }
    sections = ["# 私人内容导出\n", f"固定内容版本数: {len(items)}\n"]
    for item in items:
        sections.append(
            f"## {item.title or '未提供标题'}\n\n版本: {item.version_id}\n"
            f"\n来源: {item.source_key}\n\n正文范围: {item.text_scope}\n"
            f"\n发布时间: {item.published_at.isoformat() if item.published_at else '未知'}\n"
            f"\n发现时间: {item.discovered_at.isoformat()}\n"
            f"\n引用: {item.canonical_url or '未提供'}\n\n{item.body or ''}\n"
        )
    return ExportDocument(
        kind="content",
        title="私人内容导出",
        manifest=manifest,
        markdown="\n".join(sections),
        rows=_rows(items),
    )


def freeze_report_document(
    session: Session,
    *,
    owner_id: UUID,
    report_id: UUID,
    version: int,
    now: datetime,
    frozen_inputs: tuple[FrozenContentExportInput, ...] | None = None,
) -> ExportDocument:
    readable = load_notification_report_in_transaction(
        session, owner_id=owner_id, report_id=report_id, version=version, now=now
    )
    if readable is None:
        raise ApplicationError("export_input_unavailable")
    reports: list[Report] = []
    pending = [(report_id, version)]
    seen: set[UUID] = set()
    versions: set[UUID] = set()
    original_observations: set[UUID] = set()
    while pending:
        identifier, number = pending.pop(0)
        if identifier in seen:
            continue
        seen.add(identifier)
        record = session.scalar(
            select(Report)
            .where(
                Report.owner_id == owner_id,
                Report.id == identifier,
                Report.version == number,
                Report.status == "final",
            )
            .with_for_update()
        )
        if record is None or len(seen) > 32:
            raise ApplicationError("export_input_unavailable")
        reports.append(record)
        inputs = ReportInputManifest.model_validate(record.input_manifest)
        versions.update(inputs.content_version_ids + inputs.comment_content_version_ids)
        original_observations.update(inputs.observation_ids)
        pending.extend((item.report_id, item.version) for item in inputs.daily_reports)
    original_ids = tuple(sorted(original_observations, key=str))
    items = _content(
        session,
        owner_id,
        tuple(sorted(versions, key=str)),
        now,
        frozen_inputs=frozen_inputs,
        observation_ids=original_ids,
    )
    for start in range(0, len(original_ids), 500):
        require_export_observations_in_transaction(
            session,
            owner_id=owner_id,
            observation_ids=original_ids[start : start + 500],
            now=now,
        )
    root = reports[0]
    manifest: dict[str, object] = {
        "report_id": str(root.id),
        "report_version": root.version,
        "window_start": root.window_start.isoformat(),
        "window_end": root.window_end.isoformat(),
        "cutoff_at": root.cutoff_at.isoformat(),
        "content_version_ids": [str(item.version_id) for item in items],
        "content_inputs": _content_inputs(items),
        "observation_ids": sorted(
            {str(value) for item in items for value in item.input_observation_ids}
            | {str(value) for value in original_observations}
        ),
        "reports": [
            {
                "report_id": str(item.id),
                "version": item.version,
                "input_manifest": item.input_manifest,
                "data_sha256": digest(item.data).hex(),
                "body_sha256": hashlib.sha256(item.body_markdown.encode()).hexdigest(),
            }
            for item in reports
        ],
        "schema_version": EXPORT_SCHEMA_VERSION,
        "renderer_version": EXPORT_RENDERER_VERSION,
    }
    rows = tuple(
        {
            **row,
            "report_id": str(root.id),
            "report_version": root.version,
            "window_start": root.window_start.isoformat(),
            "window_end": root.window_end.isoformat(),
            "cutoff_at": root.cutoff_at.isoformat(),
        }
        for row in _rows(items)
    )
    metadata = (
        f"\n\n---\n固定报告: {root.id} / v{root.version}\n"
        f"\n窗口: {root.window_start.isoformat()} 至 {root.window_end.isoformat()}\n"
        f"\n截止: {root.cutoff_at.isoformat()}\n"
    )
    return ExportDocument(
        kind="report",
        title=readable.title,
        manifest=manifest,
        markdown=root.body_markdown + metadata,
        rows=rows,
        report_data=root.data,
    )


def document_for_record(session: Session, record: ExportRecord, now: datetime) -> ExportDocument:
    if (
        record.renderer_version != EXPORT_RENDERER_VERSION
        or record.schema_version != EXPORT_SCHEMA_VERSION
    ):
        raise ApplicationError("export_version_conflict")
    if isinstance(record, ReportExport):
        document = freeze_report_document(
            session,
            owner_id=record.owner_id,
            report_id=record.report_id,
            version=record.report_version,
            now=now,
            frozen_inputs=_frozen_inputs(record.input_manifest),
        )
    else:
        raw = record.input_manifest.get("content_version_ids")
        if not isinstance(raw, list):
            raise ApplicationError("export_input_unavailable")
        document = freeze_content_document(
            session,
            owner_id=record.owner_id,
            versions=tuple(UUID(str(item)) for item in raw),
            now=now,
            frozen_inputs=_frozen_inputs(record.input_manifest),
        )
    if (
        digest(document.model_dump(mode="json")) != record.input_hash
        or document.manifest != record.input_manifest
    ):
        raise ApplicationError("export_version_conflict")
    return document


def object_name(record: ExportRecord) -> str:
    extension = "md" if record.format == "markdown" else record.format
    return f"media/exports/{record.owner_id.hex}/{record.id.hex}.{extension}"


class PrivateExportService:
    def __init__(
        self,
        session: Session,
        storage: ExportStorage | None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session, self.storage = session, storage
        self.clock = clock or (lambda: datetime.now(UTC))

    def _record(
        self, owner_id: UUID, id: UUID, kind: ExportKind, *, lock: bool = False
    ) -> ExportRecord:
        model = ReportExport if kind == "report" else ContentExportRequest
        query = select(model).where(model.owner_id == owner_id, model.id == id)
        record = self.session.scalar(query.with_for_update() if lock else query)
        if record is None:
            raise ApplicationError("resource_not_found")
        return cast(ExportRecord, record)

    def _view(self, record: ExportRecord) -> ExportView:
        status = record.status
        failure = record.failure_code
        job = load_job_cancellation_state_in_transaction(
            self.session, owner_id=record.owner_id, job_id=record.job_id
        )
        if status in {"failed", "blocked"} and job is not None and job.status is JobStatus.QUEUED:
            status, failure = "pending", None
        if status != "succeeded" and job is not None and job.status is JobStatus.CANCELLED:
            status, failure = "cancelled", "export_cancelled"
        elif (
            status in {"pending", "running"} and job is not None and job.status is JobStatus.FAILED
        ):
            status, failure = "failed", "export_job_failed"
        versions = record.input_manifest.get("content_version_ids", [])
        return ExportView(
            id=record.id,
            kind="report" if isinstance(record, ReportExport) else "content",
            job_id=record.job_id,
            format=cast(ExportFormat, record.format),
            renderer_version=record.renderer_version,
            schema_version=record.schema_version,
            status=cast(ExportStatus, status),
            content_count=len(versions) if isinstance(versions, list) else 0,
            input_sha256=record.input_hash.hex(),
            artifact_sha256=record.object_sha256.hex() if record.object_sha256 else None,
            artifact_size=record.object_size,
            failure_code=failure,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _accept(
        self,
        owner_id: UUID,
        command: ReportExportInput | ContentExportInput,
        report_id: UUID | None,
    ) -> ExportView:
        if self.storage is None:
            raise ApplicationError("export_storage_unavailable")
        kind: ExportKind = "report" if isinstance(command, ReportExportInput) else "content"
        model = ReportExport if kind == "report" else ContentExportRequest
        request = command.model_dump(mode="json", exclude={"operation_id"})
        if report_id is not None:
            request["report_id"] = str(report_id)
        request_hash = digest(request)
        now = self.clock()
        self.session.rollback()
        with self.session.begin():
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"private-export:{owner_id}"},
            )
            accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action=f"private-export.{kind}.accept",
                target_ref=f"private-export:{kind}",
                reason="本人请求固定版本私有文件导出",
                payload=request,
                actor="user",
                now=now,
            )
            completed = load_completed_audit_in_transaction(
                self.session, owner_id=owner_id, operation_id=command.operation_id
            )
            if completed is not None:
                completed_record = self._record(owner_id, UUID(str(completed["export_id"])), kind)
                document_for_record(self.session, completed_record, now)
                return self._view(completed_record)
            previous = cast(
                ExportRecord | None,
                self.session.scalar(
                    select(model).where(
                        model.owner_id == owner_id, model.operation_id == command.operation_id
                    )
                ),
            )
            if previous is not None:
                if previous.request_hash != request_hash:
                    raise ApplicationError("idempotency_conflict")
                document_for_record(self.session, previous, now)
                return self._view(previous)
            existing: ExportRecord | None
            if isinstance(command, ReportExportInput):
                assert report_id is not None
                document = freeze_report_document(
                    self.session,
                    owner_id=owner_id,
                    report_id=report_id,
                    version=command.report_version,
                    now=now,
                )
                existing = self.session.scalar(
                    select(ReportExport).where(
                        ReportExport.owner_id == owner_id,
                        ReportExport.report_id == report_id,
                        ReportExport.report_version == command.report_version,
                        ReportExport.format == command.format,
                        ReportExport.renderer_version == EXPORT_RENDERER_VERSION,
                        ReportExport.status != "cancelled",
                    )
                )
            else:
                document = freeze_content_document(
                    self.session, owner_id=owner_id, versions=command.content_version_ids, now=now
                )
                existing = self.session.scalar(
                    select(ContentExportRequest).where(
                        ContentExportRequest.owner_id == owner_id,
                        ContentExportRequest.input_hash == digest(document.model_dump(mode="json")),
                        ContentExportRequest.format == command.format,
                        ContentExportRequest.renderer_version == EXPORT_RENDERER_VERSION,
                        ContentExportRequest.schema_version == EXPORT_SCHEMA_VERSION,
                        ContentExportRequest.status != "cancelled",
                    )
                )
            if existing is not None:
                existing_job = load_job_cancellation_state_in_transaction(
                    self.session, owner_id=owner_id, job_id=existing.job_id
                )
                if (
                    existing.status != "succeeded"
                    and existing_job is not None
                    and existing_job.status is JobStatus.CANCELLED
                ):
                    # Only a new explicit operation may begin another attempt. The old
                    # operation, immutable input receipt and terminal Job stay attached.
                    existing.status = "cancelled"
                    existing.failure_code = "export_cancelled"
                    existing.updated_at = now
                    self.session.flush()
                    existing = None
            if existing is not None:
                document_for_record(self.session, existing, now)
                complete_audit_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    operation_id=command.operation_id,
                    after_state={"export_id": str(existing.id), "kind": kind},
                    now=now,
                )
                return self._view(existing)
            identifier = uuid4()
            job = JobService(self.session, clock=lambda: now).accept_in_transaction(
                owner_id=owner_id,
                command=JobAcceptanceInput(
                    operation_id=command.operation_id,
                    kind=f"{kind}.export",
                    observation=JobObservationContext(
                        configuration_ref=f"private-export:{identifier.hex}",
                        configuration_version=1,
                    ),
                    scope={
                        "export_id": str(identifier),
                        "export_kind": kind,
                        "renderer_version": EXPORT_RENDERER_VERSION,
                        "schema_version": EXPORT_SCHEMA_VERSION,
                    },
                ),
            )
            values = dict(
                id=identifier,
                owner_id=owner_id,
                operation_id=command.operation_id,
                job_id=job.id,
                format=command.format,
                renderer_version=EXPORT_RENDERER_VERSION,
                schema_version=EXPORT_SCHEMA_VERSION,
                input_manifest=document.manifest,
                input_hash=digest(document.model_dump(mode="json")),
                request_hash=request_hash,
                status="pending",
                object_name=None,
                object_sha256=None,
                object_size=None,
                mime_type=None,
                failure_code=None,
                created_at=now,
                updated_at=now,
            )
            record: ExportRecord
            if isinstance(command, ReportExportInput):
                record = ReportExport(
                    **values, report_id=report_id, report_version=command.report_version
                )
            else:
                record = ContentExportRequest(**values)
            self.session.add(record)
            self.session.flush()
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state={"export_id": str(record.id), "kind": kind},
                now=now,
            )
            return self._view(record)

    def accept_report(
        self, *, owner_id: UUID, report_id: UUID, command: ReportExportInput
    ) -> ExportView:
        return self._accept(owner_id, command, report_id)

    def accept_content(self, *, owner_id: UUID, command: ContentExportInput) -> ExportView:
        return self._accept(owner_id, command, None)

    def get(self, *, owner_id: UUID, export_id: UUID, kind: ExportKind) -> ExportView:
        self.session.rollback()
        with self.session.begin():
            return self._view(self._record(owner_id, export_id, kind))

    def download(self, *, owner_id: UUID, export_id: UUID, kind: ExportKind) -> ExportDownload:
        if self.storage is None:
            raise ApplicationError("export_storage_unavailable")
        self.session.rollback()
        with self.session.begin():
            record = self._record(owner_id, export_id, kind, lock=True)
            document_for_record(self.session, record, self.clock())
            if (
                record.status != "succeeded"
                or record.object_name != object_name(record)
                or record.mime_type is None
                or record.object_sha256 is None
            ):
                raise ApplicationError("export_not_ready")
            try:
                body = self.storage.get(record.object_name, max_bytes=EXPORT_MAX_BYTES)
            except Exception as error:
                raise ApplicationError("export_storage_unavailable") from error
            if (
                len(body) != record.object_size
                or hashlib.sha256(body).digest() != record.object_sha256
            ):
                raise ApplicationError("export_storage_unavailable")
            # Permissions and source expiry may have changed during the bounded storage read.
            document_for_record(self.session, record, self.clock())
            return ExportDownload(
                body,
                record.mime_type,
                f"{kind}-{record.id.hex}.{record.object_name.rsplit('.', 1)[-1]}",
                record.object_sha256.hex(),
            )
