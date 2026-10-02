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


class EventContentEmbedding(Base):
    __tablename__ = "event_content_embeddings"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="event_content_embeddings_scope_key"),
        UniqueConstraint(
            "owner_id",
            "content_version_id",
            "model",
            "requested_dimensions",
            "input_fingerprint",
            name="event_content_embeddings_input_key",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            name="event_content_embeddings_version_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="event_content_embeddings_job_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="event_content_embeddings_call_fkey",
        ),
        CheckConstraint(
            "requested_dimensions BETWEEN 0 AND 3072 AND octet_length(input_fingerprint)=32",
            name="event_content_embeddings_input_check",
        ),
        CheckConstraint(
            "status IN ('pending','running','response_saved','valid','failed','unknown','stale')",
            name="event_content_embeddings_status_check",
        ),
        CheckConstraint(
            "(status IN ('valid','response_saved') AND dimensions BETWEEN 1 AND 3072 "
            "AND vector IS NOT NULL AND jsonb_typeof(vector)='array' "
            "AND jsonb_array_length(vector)=dimensions AND ai_call_id IS NOT NULL) OR "
            "(status NOT IN ('valid','response_saved') AND dimensions IS NULL "
            "AND vector IS NULL)",
            name="event_content_embeddings_vector_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    model: Mapped[str] = mapped_column(String(128))
    requested_dimensions: Mapped[int]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    status: Mapped[str] = mapped_column(String(16))
    dimensions: Mapped[int | None]
    vector: Mapped[list[float] | None] = mapped_column(JSONB(none_as_null=True))
    ai_call_id: Mapped[UUID | None]
    job_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
