"""Immutable representation supplement owned by the existing content version."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ContentRenderedMaterial(Base):
    __tablename__ = "content_rendered_materials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="CASCADE",
            name="content_rendered_materials_version_fkey",
        ),
        CheckConstraint(
            "body_format IN ('text','html','markdown')",
            name="content_rendered_materials_format_check",
        ),
        CheckConstraint(
            "char_length(body) <= 500000", name="content_rendered_materials_body_check"
        ),
        CheckConstraint(
            "jsonb_typeof(media) = 'array' AND jsonb_array_length(media) <= 64 "
            "AND octet_length(media::text) <= 65536",
            name="content_rendered_materials_media_check",
        ),
        CheckConstraint(
            "octet_length(representation_hash) = 32 AND octet_length(input_hash) = 32",
            name="content_rendered_materials_hash_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_version_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_id: Mapped[UUID]
    body_format: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    media: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    representation_hash: Mapped[bytes] = mapped_column(LargeBinary)
    input_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
