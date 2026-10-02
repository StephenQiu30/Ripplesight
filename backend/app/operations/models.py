from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Feedback(Base):
    __tablename__ = "operations_feedback"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="operations_feedback_scope_key"),
        UniqueConstraint("owner_id", "operation_id", name="operations_feedback_operation_key"),
        CheckConstraint(
            "octet_length(source_hash)=32 AND octet_length(input_fingerprint)=32",
            name="operations_feedback_hash_check",
        ),
        CheckConstraint(
            "status IN ('new','reviewing','resolved','rejected','deleted') AND revision>=1",
            name="operations_feedback_state_check",
        ),
        CheckConstraint(
            "(status='deleted' AND content IS NULL AND email IS NULL AND page_url IS "
            "NULL) OR (status<>'deleted' AND btrim(content)<>'' AND content IS NOT NULL)",
            name="operations_feedback_content_check",
        ),
        Index("operations_feedback_inbox_idx", "owner_id", "status", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    source_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    content: Mapped[str | None] = mapped_column(String(5000))
    email: Mapped[str | None] = mapped_column(String(200))
    page_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int]
    note: Mapped[str | None] = mapped_column(String(2000))
    forwarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    forward_error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackCooldown(Base):
    __tablename__ = "operations_feedback_cooldowns"
    __table_args__ = (
        CheckConstraint(
            "octet_length(source_hash)=32", name="operations_feedback_cooldowns_hash_check"
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    banned: Mapped[bool]
    ban_reason: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackAttachment(Base):
    __tablename__ = "operations_feedback_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "feedback_id"],
            ["operations_feedback.owner_id", "operations_feedback.id"],
            ondelete="CASCADE",
            name="operations_feedback_attachments_feedback_fkey",
        ),
        UniqueConstraint(
            "owner_id", "feedback_id", name="operations_feedback_attachments_feedback_key"
        ),
        CheckConstraint(
            "mime IN ('image/png','image/jpeg','image/webp','image/gif') AND "
            "octet_length(data) BETWEEN 1 AND 8388608 AND octet_length(sha256)=32 AND "
            "width BETWEEN 1 AND 20000 AND height BETWEEN 1 AND 20000 AND "
            "width*height<=40000000",
            name="operations_feedback_attachments_format_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    feedback_id: Mapped[UUID]
    mime: Mapped[str] = mapped_column(String(16))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32))
    width: Mapped[int]
    height: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperatorAuditOperation(Base):
    __tablename__ = "operations_audit_operations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "operation_id", name="operations_audit_operations_operation_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="operations_audit_operations_job_fkey",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint)=32 AND status IN "
            "('accepted','succeeded','failed','unknown') AND "
            "jsonb_typeof(before_state)='object' AND jsonb_typeof(after_state)='object'",
            name="operations_audit_operations_state_check",
        ),
        Index("operations_audit_operations_history_idx", "owner_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    action: Mapped[str] = mapped_column(String(64))
    target_ref: Mapped[str] = mapped_column(String(256))
    actor: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16))
    before_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    after_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    job_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessHeartbeat(Base):
    __tablename__ = "operations_process_heartbeats"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "role", "instance_id", name="operations_process_heartbeats_instance_key"
        ),
        CheckConstraint(
            "role IN ('api','worker','scheduler','watchdog') AND state IN "
            "('alive','stopping','error') AND pid>0",
            name="operations_process_heartbeats_state_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(String(16))
    instance_id: Mapped[str] = mapped_column(String(128))
    pid: Mapped[int]
    state: Mapped[str] = mapped_column(String(16))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict[str, object]] = mapped_column(JSONB)


class DictionaryVersion(Base):
    __tablename__ = "operations_dictionary_versions"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "kind", "version", name="operations_dictionary_versions_version_key"
        ),
        UniqueConstraint(
            "owner_id", "operation_id", name="operations_dictionary_versions_operation_key"
        ),
        CheckConstraint(
            "kind IN ('glossary','entities','categories') AND version>=1 AND "
            "jsonb_typeof(content)='object' AND octet_length(input_fingerprint)=32",
            name="operations_dictionary_versions_value_check",
        ),
        Index(
            "operations_dictionary_versions_one_current_idx",
            "owner_id",
            "kind",
            unique=True,
            postgresql_where=text("active"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[int]
    active: Mapped[bool]
    content: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
