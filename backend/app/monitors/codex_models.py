from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class CodexResetMonitor(Base):
    __tablename__ = "codex_reset_monitors"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="codex_reset_monitors_owner_id_key"),
        UniqueConstraint("owner_id", name="codex_reset_monitors_owner_key"),
        CheckConstraint(
            "revision >= 1 AND configuration_version >= 1 "
            "AND projection_epoch >= 1 AND scan_revision >= 1",
            name="codex_reset_monitors_versions_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    enabled: Mapped[bool]
    revision: Mapped[int]
    configuration_version: Mapped[int]
    projection_epoch: Mapped[int]
    scan_revision: Mapped[int]
    since_id: Mapped[str | None] = mapped_column(String(19))
    hot_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetMonitorVersion(Base):
    __tablename__ = "codex_reset_monitor_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id"],
            ["codex_reset_monitors.owner_id", "codex_reset_monitors.id"],
            ondelete="CASCADE",
            name="codex_reset_monitor_versions_monitor_fkey",
        ),
        CheckConstraint(
            "version >= 1 AND jsonb_typeof(configuration) = 'object'",
            name="codex_reset_monitor_versions_configuration_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    monitor_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetScanGap(Base):
    __tablename__ = "codex_reset_scan_gaps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id", "configuration_version"],
            [
                "codex_reset_monitor_versions.owner_id",
                "codex_reset_monitor_versions.monitor_id",
                "codex_reset_monitor_versions.version",
            ],
            ondelete="CASCADE",
            name="codex_reset_scan_gaps_version_fkey",
        ),
        CheckConstraint(
            "state IN ('pending', 'held', 'complete')", name="codex_reset_scan_gaps_state_check"
        ),
        CheckConstraint(
            "starts_at IS NULL AND ends_at IS NULL OR starts_at < ends_at",
            name="codex_reset_scan_gaps_bounds_check",
        ),
        Index("codex_reset_scan_gaps_monitor_idx", "owner_id", "monitor_id", "state", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    monitor_id: Mapped[UUID]
    configuration_version: Mapped[int]
    query: Mapped[str] = mapped_column(String(512))
    next_token: Mapped[str | None] = mapped_column(String(2048))
    stop_at_id: Mapped[str | None] = mapped_column(String(19))
    before_id: Mapped[str | None] = mapped_column(String(19))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetPost(Base):
    __tablename__ = "codex_reset_posts"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "monitor_id", "id", name="codex_reset_posts_owner_monitor_id_key"
        ),
        UniqueConstraint(
            "owner_id", "monitor_id", "external_id", name="codex_reset_posts_external_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "monitor_id", "configuration_version"],
            [
                "codex_reset_monitor_versions.owner_id",
                "codex_reset_monitor_versions.monitor_id",
                "codex_reset_monitor_versions.version",
            ],
            name="codex_reset_posts_version_fkey",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32 AND review_version >= 1 AND failure_count >= 0",
            name="codex_reset_posts_input_check",
        ),
        CheckConstraint(
            "external_id ~ '^[0-9]{1,19}$' AND jsonb_typeof(source_input) = 'object'",
            name="codex_reset_posts_source_check",
        ),
        Index(
            "codex_reset_posts_pending_idx", "owner_id", "monitor_id", "published_at", "external_id"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    monitor_id: Mapped[UUID]
    configuration_version: Mapped[int]
    external_id: Mapped[str] = mapped_column(String(19))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    translation_zh: Mapped[str | None] = mapped_column(Text)
    context: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    needs_review: Mapped[bool]
    reviewed: Mapped[bool]
    skipped: Mapped[bool]
    review_version: Mapped[int]
    failure_count: Mapped[int]
    failure_code: Mapped[str | None] = mapped_column(String(64))
    outage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    activity: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetRecognition(Base):
    __tablename__ = "codex_reset_recognitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id", "post_id"],
            ["codex_reset_posts.owner_id", "codex_reset_posts.monitor_id", "codex_reset_posts.id"],
            name="codex_reset_recognitions_post_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="codex_reset_recognitions_ai_call_fkey",
        ),
        CheckConstraint(
            "status IN ('applied', 'held', 'stale', 'failed', 'running', 'unknown') "
            "AND octet_length(input_fingerprint) = 32",
            name="codex_reset_recognitions_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(recognition) = 'object' AND jsonb_typeof(held) = 'array' "
            "AND jsonb_typeof(notifications) = 'array'",
            name="codex_reset_recognitions_json_check",
        ),
        Index(
            "codex_reset_recognitions_post_idx", "owner_id", "monitor_id", "post_id", "created_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    monitor_id: Mapped[UUID]
    post_id: Mapped[UUID]
    configuration_version: Mapped[int]
    projection_epoch: Mapped[int]
    review_version: Mapped[int]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    prompt_version: Mapped[str] = mapped_column(String(128))
    ai_call_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16))
    recognition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    held: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    notifications: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetEvent(Base):
    __tablename__ = "codex_reset_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id"],
            ["codex_reset_monitors.owner_id", "codex_reset_monitors.id"],
            name="codex_reset_events_monitor_fkey",
        ),
        CheckConstraint(
            "kind IN ('direct_reset', 'reset_credit') AND status IN ('announced', 'confirmed')",
            name="codex_reset_events_state_check",
        ),
        CheckConstraint(
            "revision >= 1 AND manual_version >= 0", name="codex_reset_events_revision_check"
        ),
        CheckConstraint(
            "confirmation_basis IS NULL OR confirmation_basis IN ('source_post', 'receipt_review')",
            name="codex_reset_events_basis_check",
        ),
        Index("codex_reset_events_timeline_idx", "owner_id", "monitor_id", "created_at"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    monitor_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int]
    manual_version: Mapped[int]
    withdrawn: Mapped[bool]
    in_progress: Mapped[bool]
    kind_explicit: Mapped[bool]
    time_inferred: Mapped[bool]
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    estimate: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_on: Mapped[date | None]
    confirmation_basis: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CodexResetEventPost(Base):
    __tablename__ = "codex_reset_event_posts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id", "event_id"],
            [
                "codex_reset_events.owner_id",
                "codex_reset_events.monitor_id",
                "codex_reset_events.id",
            ],
            name="codex_reset_event_posts_event_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "monitor_id", "post_id"],
            ["codex_reset_posts.owner_id", "codex_reset_posts.monitor_id", "codex_reset_posts.id"],
            name="codex_reset_event_posts_post_fkey",
        ),
        CheckConstraint(
            "action IN ('announce', 'progress', 'confirm', 'amend', 'withdraw')",
            name="codex_reset_event_posts_action_check",
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    monitor_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    post_id: Mapped[UUID] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(32))
    excerpt: Mapped[str] = mapped_column(Text)
    excerpt_zh: Mapped[str] = mapped_column(Text)


class CodexResetReview(Base):
    __tablename__ = "codex_reset_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "monitor_id"],
            ["codex_reset_monitors.owner_id", "codex_reset_monitors.id"],
            name="codex_reset_reviews_monitor_fkey",
        ),
        UniqueConstraint(
            "owner_id", "monitor_id", "operation_id", name="codex_reset_reviews_operation_key"
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32 AND length(reason) BETWEEN 1 AND 1000",
            name="codex_reset_reviews_input_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    monitor_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    entity_kind: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
