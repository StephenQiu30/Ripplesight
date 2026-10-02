"""Versioned editorial source configuration and ingest checkpoints, never provider secrets."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EditorialSourceProfile(Base):
    __tablename__ = "editorial_source_profiles"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="editorial_profiles_owner_id_key"),
        UniqueConstraint("owner_id", "source_key", name="editorial_profiles_source_key"),
        ForeignKeyConstraint(
            ["owner_id", "id", "current_version"],
            [
                "editorial_source_profile_versions.owner_id",
                "editorial_source_profile_versions.profile_id",
                "editorial_source_profile_versions.version",
            ],
            name="editorial_profiles_current_version_fkey",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint(
            "source_key ~ '^ed_[a-z_]+_[a-f0-9]{32}$'", name="editorial_profiles_source_key_check"
        ),
        CheckConstraint(
            "current_version >= 1 AND revision >= 1 AND failure_count >= 0",
            name="editorial_profiles_counters_check",
        ),
        CheckConstraint(
            "health IN ('unknown','ok','degraded','failing')",
            name="editorial_profiles_health_check",
        ),
        CheckConstraint("jsonb_typeof(cursor) = 'object'", name="editorial_profiles_cursor_check"),
        Index("editorial_profiles_due_idx", "enabled", "next_fetch_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    source_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool]
    current_version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    cursor: Mapped[dict[str, object]] = mapped_column(JSONB)
    health: Mapped[str] = mapped_column(String(16))
    failure_count: Mapped[int] = mapped_column(Integer)
    last_failure_code: Mapped[str | None] = mapped_column(String(64))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialSourceVersion(Base):
    __tablename__ = "editorial_source_profile_versions"
    __table_args__ = (
        UniqueConstraint("owner_id", "profile_id", "version", name="editorial_versions_owner_key"),
        UniqueConstraint("owner_id", "operation_id", name="editorial_versions_operation_key"),
        ForeignKeyConstraint(
            ["owner_id", "profile_id"],
            ["editorial_source_profiles.owner_id", "editorial_source_profiles.id"],
            name="editorial_versions_profile_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "connection_id", "connection_version"],
            [
                "source_connection_versions.owner_id",
                "source_connection_versions.connection_id",
                "source_connection_versions.version",
            ],
            name="editorial_versions_connection_fkey",
        ),
        CheckConstraint(
            "kind IN ('rss','web_list','json_list','x_search','mp_account','external')",
            name="editorial_versions_kind_check",
        ),
        CheckConstraint(
            (
                "participation_mode IN ('editorial','hot_signal','isolated') AND t"
                "ier IN ('T1','T1_5','T2','T3')"
            ),
            name="editorial_versions_participation_check",
        ),
        CheckConstraint(
            (
                "octet_length(input_hash) = 32 AND version >= 1 AND policy_version"
                " >= 1 AND connection_version >= 1 AND interval_minutes BETWEEN 1 "
                "AND 360"
            ),
            name="editorial_versions_numbers_check",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration) = 'object'", name="editorial_versions_configuration_check"
        ),
    )
    profile_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_hash: Mapped[bytes] = mapped_column(LargeBinary)
    kind: Mapped[str] = mapped_column(String(16))
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB)
    participation_mode: Mapped[str] = mapped_column(String(16))
    tier: Mapped[str] = mapped_column(String(8))
    first_party: Mapped[bool]
    connection_id: Mapped[UUID]
    connection_version: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[int] = mapped_column(Integer)
    interval_minutes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialSourceRun(Base):
    __tablename__ = "editorial_source_runs"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "profile_id", "operation_id", name="editorial_source_runs_operation_key"
        ),
        UniqueConstraint("owner_id", "id", name="editorial_source_runs_owner_id_key"),
        ForeignKeyConstraint(
            ["owner_id", "profile_id", "configuration_version"],
            [
                "editorial_source_profile_versions.owner_id",
                "editorial_source_profile_versions.profile_id",
                "editorial_source_profile_versions.version",
            ],
            name="editorial_source_runs_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="editorial_source_runs_job_fkey",
        ),
        CheckConstraint(
            (
                "status IN ('running','staged','succeeded','partial','unknown','fa"
                "iled','blocked','cancelled')"
            ),
            name="editorial_source_runs_status_check",
        ),
        CheckConstraint(
            (
                "octet_length(input_hash) = 32 AND configuration_version >= 1 AND "
                "profile_revision >= 1"
            ),
            name="editorial_source_runs_input_check",
        ),
        CheckConstraint(
            "found >= 0 AND created >= 0 AND revised >= 0",
            name="editorial_source_runs_counts_check",
        ),
        CheckConstraint(
            (
                "prepared_page IS NULL OR (jsonb_typeof(prepared_page) = 'object' "
                "AND octet_length(prepared_page::text) <= 8388608)"
            ),
            name="editorial_source_runs_page_check",
        ),
        CheckConstraint(
            "review_audit IS NULL OR jsonb_typeof(review_audit) = 'object'",
            name="editorial_source_runs_review_check",
        ),
        Index("editorial_runs_profile_status_idx", "owner_id", "profile_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    profile_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_hash: Mapped[bytes] = mapped_column(LargeBinary)
    configuration_version: Mapped[int] = mapped_column(Integer)
    profile_revision: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(16))
    prepared_page: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    revised: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    review_audit: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditorialSourceMaterialReceipt(Base):
    __tablename__ = "editorial_source_material_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "profile_id"],
            ["editorial_source_profiles.owner_id", "editorial_source_profiles.id"],
            name="editorial_materials_profile_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            name="editorial_materials_content_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "run_id"],
            ["editorial_source_runs.owner_id", "editorial_source_runs.id"],
            name="editorial_materials_run_fkey",
        ),
        CheckConstraint(
            "octet_length(material_hash) = 32 AND body_retry_count BETWEEN 0 AND 3",
            name="editorial_materials_numbers_check",
        ),
        CheckConstraint(
            "body_status IN ('ok','pending','none')", name="editorial_materials_body_check"
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="editorial_materials_metadata_check"
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    profile_id: Mapped[UUID] = mapped_column(primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    material_hash: Mapped[bytes] = mapped_column(LargeBinary)
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    run_id: Mapped[UUID]
    body_status: Mapped[str] = mapped_column(String(16))
    body_retry_count: Mapped[int] = mapped_column(Integer)
    first_import: Mapped[bool]
    detail_title: Mapped[str | None] = mapped_column(String(2000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_body_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    material_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
