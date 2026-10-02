"""Mirror job/material references; file ownership and deletion stay in Evidence/MinIO."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class PublicationMediaRun(Base):
    __tablename__ = "publication_media_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="publication_media_runs_job_fk",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            name="publication_media_runs_content_fk",
        ),
        UniqueConstraint("owner_id", "operation_id", name="publication_media_runs_operation_key"),
        UniqueConstraint(
            "owner_id",
            "content_id",
            "content_version_id",
            "policy_revision",
            name="publication_media_runs_identity_key",
        ),
        CheckConstraint(
            "status IN ('queued','running','complete','partial','unknown',"
            "'failed','stale','cancelled')",
            name="publication_media_runs_status_check",
        ),
        CheckConstraint("policy_revision >= 1", name="publication_media_runs_policy_check"),
        Index("publication_media_runs_job_idx", "owner_id", "job_id"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column()
    job_id: Mapped[UUID] = mapped_column()
    content_id: Mapped[UUID] = mapped_column()
    content_version_id: Mapped[UUID] = mapped_column()
    policy_revision: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(64))
    fixed_reference: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationMediaFile(Base):
    __tablename__ = "publication_media_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["publication_media_runs.owner_id", "publication_media_runs.id"],
            name="publication_media_files_run_fk",
        ),
        UniqueConstraint("owner_id", "run_id", "media_key", name="publication_media_files_key_key"),
        CheckConstraint("kind IN ('image','video')", name="publication_media_files_kind_check"),
        CheckConstraint(
            "status IN ('pending','running','complete','unknown','failed','stale','cancelled')",
            name="publication_media_files_status_check",
        ),
        CheckConstraint(
            "byte_count IS NULL OR byte_count > 0", name="publication_media_files_size_check"
        ),
        Index("publication_media_files_run_idx", "owner_id", "run_id"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column()
    media_key: Mapped[str] = mapped_column(String(24))
    source_url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renditions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
