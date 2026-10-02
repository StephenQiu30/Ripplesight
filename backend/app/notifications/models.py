from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class NotificationTarget(Base):
    __tablename__ = "notification_targets"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="notification_targets_owner_name_key"),
        UniqueConstraint("owner_id", "id", name="notification_targets_owner_id_key"),
        CheckConstraint(
            "channel IN ('feishu', 'email')", name="notification_targets_channel_check"
        ),
        CheckConstraint(
            "jsonb_typeof(recipients) = 'array'", name="notification_targets_recipients_check"
        ),
        CheckConstraint(
            "secret_env IS NULL OR secret_env ~ '^HOTKEY_[A-Z][A-Z0-9_]*$'",
            name="notification_targets_secret_env_check",
        ),
        CheckConstraint("updated_at >= created_at", name="notification_targets_updated_at_check"),
        CheckConstraint("revision >= 1", name="notification_targets_revision_check"),
        CheckConstraint(
            "jsonb_typeof(subscriptions)='array' AND jsonb_array_length(subscriptions)<=4 AND "
            'subscriptions <@ \'["report","edition","selected","codex_reset"]\'::jsonb',
            name="notification_targets_subscriptions_check",
        ),
        CheckConstraint(
            "enabled_at IS NULL OR enabled_at >= created_at",
            name="notification_targets_enabled_at_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(80))
    channel: Mapped[str] = mapped_column(String(16))
    recipients: Mapped[list[Any]] = mapped_column(JSONB)
    secret_env: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscriptions: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "target_id"],
            ["notification_targets.owner_id", "notification_targets.id"],
            ondelete="CASCADE",
            name="notification_deliveries_owner_target_fkey",
        ),
        UniqueConstraint(
            "report_id",
            "report_version",
            "target_id",
            name="notification_deliveries_report_version_target_key",
        ),
        UniqueConstraint(
            "owner_id",
            "target_id",
            "subject_kind",
            "dedupe_key",
            name="notification_deliveries_subject_target_key",
        ),
        CheckConstraint(
            "subject_kind IN ('report','edition','selected','codex_reset') AND "
            "((subject_kind='report' AND report_id IS NOT NULL AND subject_id IS NULL) OR "
            "(subject_kind<>'report' AND report_id IS NULL AND subject_id IS NOT NULL))",
            name="notification_deliveries_subject_check",
        ),
        CheckConstraint(
            "revision>=1 AND target_revision>=1 AND "
            "(input_fingerprint IS NULL OR octet_length(input_fingerprint)=32) AND "
            "(subject_kind='report' OR (input_fingerprint IS NOT NULL AND dedupe_key IS NOT NULL)) "
            "AND (dedupe_key IS NULL OR length(dedupe_key) BETWEEN 1 AND 256) AND "
            "jsonb_typeof(frozen_payload)='object' AND jsonb_typeof(provider_receipt)='object'",
            name="notification_deliveries_snapshot_check",
        ),
        CheckConstraint("report_version >= 1", name="notification_deliveries_version_check"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'succeeded', 'failed', 'unknown')",
            name="notification_deliveries_status_check",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 0 AND 3", name="notification_deliveries_attempt_check"
        ),
        CheckConstraint(
            "updated_at >= created_at", name="notification_deliveries_updated_at_check"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column()
    report_id: Mapped[UUID | None] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    report_version: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[UUID]
    subject_kind: Mapped[str] = mapped_column(String(16), server_default=text("'report'"))
    subject_id: Mapped[UUID | None]
    dedupe_key: Mapped[str | None] = mapped_column(String(256))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    target_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    input_fingerprint: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    frozen_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    provider_receipt: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
