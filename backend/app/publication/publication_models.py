"""Publication-owned mappings, registered only in the shared schema window."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class PublicationSourcePolicy(Base):
    __tablename__ = "publication_source_policies"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="publication_source_policies_revision_check"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationPolicyVersion(Base):
    __tablename__ = "publication_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "source_key"],
            ["publication_source_policies.owner_id", "publication_source_policies.source_key"],
            name="publication_policy_versions_policy_fk",
        ),
        UniqueConstraint(
            "owner_id", "operation_id", name="publication_policy_versions_operation_key"
        ),
        CheckConstraint("revision >= 1", name="publication_policy_versions_revision_check"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column()
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationRecord(Base):
    __tablename__ = "publication_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            name="publication_records_content_version_fk",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_key"],
            ["publication_source_policies.owner_id", "publication_source_policies.source_key"],
            name="publication_records_source_policy_fk",
        ),
        CheckConstraint("revision >= 1", name="publication_records_revision_check"),
        CheckConstraint(
            "visibility IN ('public','summary-only','withdrawn')",
            name="publication_records_visibility_check",
        ),
        Index("publication_records_timeline_idx", "owner_id", "timeline_at", "content_id"),
        Index("publication_records_source_idx", "owner_id", "source_key", "content_id"),
        Index("publication_records_selected_idx", "owner_id", "selected", "visible_after"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_version_id: Mapped[UUID] = mapped_column()
    source_key: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(20))
    eligible: Mapped[bool] = mapped_column(Boolean)
    selected: Mapped[bool] = mapped_column(Boolean)
    visible_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sort_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column("projection", JSONB)
    override: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationRevision(Base):
    __tablename__ = "publication_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id"],
            ["publication_records.owner_id", "publication_records.content_id"],
            name="publication_revisions_publication_fk",
        ),
        UniqueConstraint("owner_id", "operation_id", name="publication_revisions_operation_key"),
        CheckConstraint("revision >= 1", name="publication_revisions_revision_check"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID | None] = mapped_column()
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column("projection", JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationSyncState(Base):
    __tablename__ = "publication_sync_states"
    __table_args__ = (
        CheckConstraint("sequence >= 0", name="publication_sync_states_sequence_check"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    epoch: Mapped[UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationSelectedChange(Base):
    __tablename__ = "publication_selected_changes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id"],
            ["publication_records.owner_id", "publication_records.content_id"],
            name="publication_selected_changes_publication_fk",
        ),
        CheckConstraint("sequence >= 1", name="publication_selected_changes_sequence_check"),
        CheckConstraint(
            "operation IN ('upsert','remove')", name="publication_selected_changes_operation_check"
        ),
        Index(
            "publication_selected_changes_visible_idx",
            "owner_id",
            "epoch",
            "visible_at",
            "sequence",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    epoch: Mapped[UUID] = mapped_column(primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[UUID] = mapped_column()
    publication_revision: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(10))
    visible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationRepublishRun(Base):
    __tablename__ = "publication_republish_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="publication_republish_runs_owner_id_key"),
        UniqueConstraint(
            "owner_id", "operation_id", name="publication_republish_runs_operation_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_key"],
            ["publication_source_policies.owner_id", "publication_source_policies.source_key"],
            name="publication_republish_runs_policy_fk",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="publication_republish_runs_job_fk",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="publication_republish_runs_status_check",
        ),
        CheckConstraint("processed_count >= 0", name="publication_republish_runs_count_check"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column()
    source_key: Mapped[str] = mapped_column(String(64))
    policy_revision: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[UUID] = mapped_column()
    operation_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))
    after_content_id: Mapped[UUID | None] = mapped_column()
    processed_count: Mapped[int] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
