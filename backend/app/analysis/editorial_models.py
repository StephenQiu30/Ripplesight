from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EditorialSource(Base):
    __tablename__ = "editorial_sources"
    __table_args__ = (CheckConstraint("revision >= 1", name="editorial_sources_revision_check"),)
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int]
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scan_cursor: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialSourceVersion(Base):
    __tablename__ = "editorial_source_versions"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "operation_id", name="editorial_source_versions_operation_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_key"],
            ["editorial_sources.owner_id", "editorial_sources.source_key"],
            ondelete="CASCADE",
            name="editorial_source_versions_source_fkey",
        ),
        CheckConstraint(
            "revision >= 1 AND octet_length(input_fingerprint) = 32",
            name="editorial_source_versions_input_check",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration) = 'object'",
            name="editorial_source_versions_configuration_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialRun(Base):
    __tablename__ = "editorial_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="editorial_runs_owner_id_key"),
        UniqueConstraint("owner_id", "operation_id", name="editorial_runs_operation_key"),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="CASCADE",
            name="editorial_runs_content_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_key", "source_revision"],
            [
                "editorial_source_versions.owner_id",
                "editorial_source_versions.source_key",
                "editorial_source_versions.revision",
            ],
            name="editorial_runs_source_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"], ["jobs.owner_id", "jobs.id"], name="editorial_runs_job_fkey"
        ),
        CheckConstraint(
            "status IN ('queued','running','complete','blocked','failed','unknown','stale')",
            name="editorial_runs_status_check",
        ),
        CheckConstraint(
            "stages IN ('selection','all') AND manual_version >= 0",
            name="editorial_runs_options_check",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32 AND length(prompt_version) > 0",
            name="editorial_runs_input_check",
        ),
        CheckConstraint(
            "result IS NULL OR jsonb_typeof(result) = 'object'", name="editorial_runs_result_check"
        ),
        Index("editorial_runs_owner_content_created_idx", "owner_id", "content_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    source_key: Mapped[str] = mapped_column(String(64))
    source_revision: Mapped[int]
    job_id: Mapped[UUID | None]
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    stages: Mapped[str] = mapped_column(String(16))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    manual_version: Mapped[int]
    execution_token: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialStage(Base):
    __tablename__ = "editorial_stages"
    __table_args__ = (
        UniqueConstraint("owner_id", "run_id", "stage_key", name="editorial_stages_run_key"),
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["editorial_runs.owner_id", "editorial_runs.id"],
            ondelete="CASCADE",
            name="editorial_stages_run_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="editorial_stages_ai_call_fkey",
        ),
        CheckConstraint(
            "status IN ('running','succeeded','failed','unknown')",
            name="editorial_stages_status_check",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32", name="editorial_stages_input_check"
        ),
        CheckConstraint(
            "output IS NULL OR jsonb_typeof(output) = 'object'",
            name="editorial_stages_output_check",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR output IS NOT NULL", name="editorial_stages_success_check"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    run_id: Mapped[UUID]
    stage_key: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    status: Mapped[str] = mapped_column(String(16))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    ai_call_id: Mapped[UUID | None]
    failure_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EditorialOverride(Base):
    __tablename__ = "editorial_overrides"
    __table_args__ = (
        UniqueConstraint("owner_id", "operation_id", name="editorial_overrides_operation_key"),
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["editorial_runs.owner_id", "editorial_runs.id"],
            name="editorial_overrides_run_fkey",
        ),
        CheckConstraint(
            "revision >= 1 AND octet_length(input_fingerprint) = 32",
            name="editorial_overrides_input_check",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 1000", name="editorial_overrides_reason_check"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    run_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    revision: Mapped[int]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialContentState(Base):
    __tablename__ = "editorial_content_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id"],
            ["content_records.owner_id", "content_records.id"],
            ondelete="CASCADE",
            name="editorial_content_states_content_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "current_run_id"],
            ["editorial_runs.owner_id", "editorial_runs.id"],
            name="editorial_content_states_current_run_fkey",
        ),
        CheckConstraint("manual_version >= 0", name="editorial_content_states_manual_check"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_id: Mapped[UUID] = mapped_column(primary_key=True)
    current_run_id: Mapped[UUID]
    manual_version: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
