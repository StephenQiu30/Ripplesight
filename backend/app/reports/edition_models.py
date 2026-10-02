from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ReportEdition(Base):
    __tablename__ = "report_editions"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="report_editions_owner_id_key"),
        UniqueConstraint("owner_id", "operation_id", name="report_editions_operation_key"),
        UniqueConstraint(
            "owner_id", "kind", "period_key", "revision", name="report_editions_revision_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"], ["jobs.owner_id", "jobs.id"], name="report_editions_job_fkey"
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="report_editions_ai_call_fkey",
        ),
        CheckConstraint(
            "kind IN ('daily','weekly','monthly') AND revision >= 1",
            name="report_editions_kind_revision_check",
        ),
        CheckConstraint(
            "status IN ('queued','running','complete','failed','unknown','stale')",
            name="report_editions_status_check",
        ),
        CheckConstraint(
            "generator IN ('template','model','manual')", name="report_editions_generator_check"
        ),
        CheckConstraint(
            "window_start < window_end AND cutoff_at >= window_end",
            name="report_editions_window_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_snapshot) = 'array'", name="report_editions_snapshot_check"
        ),
        CheckConstraint(
            "content IS NULL OR jsonb_typeof(content) = 'object'",
            name="report_editions_content_check",
        ),
        CheckConstraint(
            "status <> 'complete' OR (content IS NOT NULL AND body_markdown IS NOT NULL "
            "AND length(body_markdown) > 0)",
            name="report_editions_complete_check",
        ),
        CheckConstraint("length(input_fingerprint) = 64", name="report_editions_fingerprint_check"),
        Index("report_editions_owner_period_idx", "owner_id", "kind", "period_key", "revision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    period_key: Mapped[str] = mapped_column(String(10))
    revision: Mapped[int]
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[UUID | None]
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    repeats_suppressed: Mapped[int]
    daily_editions_covered: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    generator: Mapped[str] = mapped_column(String(16))
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    body_markdown: Mapped[str | None] = mapped_column(Text)
    ai_call_id: Mapped[UUID | None]
    failure_code: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportEditionSchedule(Base):
    __tablename__ = "report_edition_schedules"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('daily','weekly','monthly')", name="report_edition_schedules_kind_check"
        ),
        CheckConstraint(
            "length(first_period_key) BETWEEN 7 AND 10", name="report_edition_schedules_key_check"
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    first_period_key: Mapped[str] = mapped_column(String(10))
    scan_after_key: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
