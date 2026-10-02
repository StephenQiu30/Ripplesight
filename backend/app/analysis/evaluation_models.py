from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SelectBenchRun(Base):
    __tablename__ = "analysis_selectbench_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="analysis_selectbench_runs_scope_key"),
        UniqueConstraint(
            "owner_id", "operation_id", name="analysis_selectbench_runs_operation_key"
        ),
        CheckConstraint(
            "octet_length(input_fingerprint)=32 AND octet_length(gold_fingerprint)=32 "
            "AND sample_size BETWEEN 1 AND 5000 AND jsonb_typeof(models)='array' AND "
            "jsonb_typeof(summary)='object'",
            name="analysis_selectbench_runs_input_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    gold_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    label: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    split: Mapped[str | None] = mapped_column(String(64))
    seed: Mapped[int | None]
    sample_size: Mapped[int]
    models: Mapped[list[str]] = mapped_column(JSONB)
    summary: Mapped[dict[str, object]] = mapped_column(JSONB)
    imported_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SelectBenchResult(Base):
    __tablename__ = "analysis_selectbench_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["analysis_selectbench_runs.owner_id", "analysis_selectbench_runs.id"],
            ondelete="CASCADE",
            name="analysis_selectbench_results_run_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="analysis_selectbench_results_call_fkey",
        ),
        UniqueConstraint(
            "owner_id", "run_id", "model", "case_id", name="analysis_selectbench_results_case_key"
        ),
        CheckConstraint(
            "gold IN ('select','reject','either') AND (decision IS NULL OR decision IN "
            "('select','reject')) AND (score IS NULL OR score BETWEEN 0 AND 100)",
            name="analysis_selectbench_results_decision_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    run_id: Mapped[UUID]
    model: Mapped[str] = mapped_column(String(200))
    case_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500))
    stratum: Mapped[str | None] = mapped_column(String(128))
    gold: Mapped[str] = mapped_column(String(8))
    decision: Mapped[str | None] = mapped_column(String(8))
    score: Mapped[float | None]
    relevance: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String(2000))
    error_code: Mapped[str | None] = mapped_column(String(64))
    ai_call_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
