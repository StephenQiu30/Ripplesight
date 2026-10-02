from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ContentTranslationRun(Base):
    __tablename__ = "content_translation_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="content_translation_runs_owner_key"),
        UniqueConstraint("owner_id", "operation_id", name="content_translation_runs_operation_key"),
        UniqueConstraint(
            "owner_id",
            "content_id",
            "content_version_id",
            "policy_revision",
            "revision",
            name="content_translation_runs_revision_key",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            name="content_translation_runs_content_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="content_translation_runs_job_fkey",
        ),
        CheckConstraint(
            "status IN ('queued','running','complete','partial','unknown','failed','stale')",
            name="content_translation_runs_status_check",
        ),
        CheckConstraint(
            "source_format IN ('text','html','markdown') "
            "AND revision >= 1 AND policy_revision >= 1",
            name="content_translation_runs_version_check",
        ),
        CheckConstraint(
            "length(input_fingerprint)=64 AND length(request_fingerprint)=64 "
            "AND jsonb_typeof(reference)='object'",
            name="content_translation_runs_input_check",
        ),
        CheckConstraint(
            "translated_segments >= 0 AND translated_segments <= total_segments",
            name="content_translation_runs_counts_check",
        ),
        CheckConstraint(
            "status NOT IN ('complete','partial') OR body_html IS NOT NULL",
            name="content_translation_runs_result_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    policy_revision: Mapped[int]
    revision: Mapped[int]
    job_id: Mapped[UUID]
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    reference: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_format: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    body_html: Mapped[str | None] = mapped_column(Text)
    translated_segments: Mapped[int]
    total_segments: Mapped[int]
    complete: Mapped[bool]
    failure_code: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContentTranslationBatch(Base):
    __tablename__ = "content_translation_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["content_translation_runs.owner_id", "content_translation_runs.id"],
            name="content_translation_batches_run_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="content_translation_batches_call_fkey",
        ),
        CheckConstraint(
            "status IN ('running','succeeded','unknown','failed') AND ordinal >= 0",
            name="content_translation_batches_status_check",
        ),
        CheckConstraint(
            "answers IS NULL OR jsonb_typeof(answers)='array'",
            name="content_translation_batches_answers_check",
        ),
    )
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(16))
    ai_call_id: Mapped[UUID | None]
    answers: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
