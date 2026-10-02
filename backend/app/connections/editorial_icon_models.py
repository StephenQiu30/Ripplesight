"""Rebuildable source avatar cache, versioned by the original source identity."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EditorialSourceIcon(Base):
    __tablename__ = "editorial_source_icons"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "profile_id", "configuration_version"],
            [
                "editorial_source_profile_versions.owner_id",
                "editorial_source_profile_versions.profile_id",
                "editorial_source_profile_versions.version",
            ],
            name="editorial_source_icons_version_fkey",
        ),
        ForeignKeyConstraint(["job_id"], ["jobs.id"], name="editorial_source_icons_job_fkey"),
        CheckConstraint(
            "configuration_version >= 1 AND profile_revision >= 1",
            name="editorial_source_icons_version_check",
        ),
        CheckConstraint("octet_length(input_hash) = 32", name="editorial_source_icons_hash_check"),
        CheckConstraint(
            "status IN ('ready','missing','blocked','unknown','running')",
            name="editorial_source_icons_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(media_refs) = 'array' AND octet_length(media_refs::text) <= 65536",
            name="editorial_source_icons_media_check",
        ),
        CheckConstraint(
            "status <> 'ready' OR (source_url IS NOT NULL AND jsonb_array_length(media_refs) = 2)",
            name="editorial_source_icons_ready_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    profile_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64))
    configuration_version: Mapped[int] = mapped_column(Integer)
    profile_revision: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(Text)
    media_refs: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    operation_id: Mapped[UUID]
    job_id: Mapped[UUID]
    failure_code: Mapped[str | None] = mapped_column(String(64))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
