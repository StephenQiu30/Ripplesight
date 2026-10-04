"""Typed private, fixed-version export commands and receipts, with no credentials."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

type ExportFormat = Literal["markdown", "pdf", "csv", "json"]
type ExportKind = Literal["report", "content"]
type ExportStatus = Literal["pending", "running", "succeeded", "failed", "blocked", "cancelled"]
EXPORT_RENDERER_VERSION = "private-export-v2-chromium1243-pingfang9ff3ce9439fe"
EXPORT_SCHEMA_VERSION = "private-export-v2"
EXPORT_MAX_BYTES = 5 * 1024 * 1024
EXPORT_MAX_ITEMS = 10_000
EXPORT_TIMEOUT_SECONDS = 120


class ExportContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*")
    @classmethod
    def aware_times(cls, value: object) -> object:
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValueError("export times must be aware")
            return value.astimezone(UTC)
        return value


class ReportExportInput(ExportContract):
    operation_id: UUID
    report_version: int = Field(ge=1)
    format: ExportFormat


class ContentExportInput(ExportContract):
    operation_id: UUID
    content_version_ids: tuple[UUID, ...] = Field(min_length=1, max_length=EXPORT_MAX_ITEMS)
    format: ExportFormat

    @field_validator("content_version_ids")
    @classmethod
    def unique_versions(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("export versions must be unique")
        return value


class ExportView(ExportContract):
    id: UUID
    kind: ExportKind
    job_id: UUID
    format: ExportFormat
    renderer_version: str
    schema_version: str
    status: ExportStatus
    content_count: int = Field(ge=0)
    input_sha256: str
    artifact_sha256: str | None = None
    artifact_size: int | None = None
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class ExportDocument(ExportContract):
    kind: ExportKind
    title: str
    manifest: dict[str, object]
    markdown: str
    rows: tuple[dict[str, object], ...]
    report_data: dict[str, object] | None = None
