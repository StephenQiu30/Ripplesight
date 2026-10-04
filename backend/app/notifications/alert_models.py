"""Notification-owned immutable alert configuration and evaluation ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="alert_rules_owner_id_key"),
        CheckConstraint("revision>=1", name="alert_rules_revision_check"),
        CheckConstraint("updated_at>=created_at", name="alert_rules_time_check"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    last_trigger_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRuleVersion(Base):
    __tablename__ = "alert_rule_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "rule_id"],
            ["alert_rules.owner_id", "alert_rules.id"],
            ondelete="CASCADE",
            name="alert_rule_versions_owner_rule_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="alert_rule_versions_owner_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["topic_id", "topic_rule_version"],
            ["monitor_topic_versions.topic_id", "monitor_topic_versions.version"],
            ondelete="CASCADE",
            name="alert_rule_versions_topic_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "target_id"],
            ["notification_targets.owner_id", "notification_targets.id"],
            ondelete="CASCADE",
            name="alert_rule_versions_owner_target_fkey",
        ),
        UniqueConstraint("owner_id", "operation_id", name="alert_rule_versions_operation_key"),
        UniqueConstraint(
            "owner_id", "rule_id", "version", name="alert_rule_versions_owner_version_key"
        ),
        CheckConstraint(
            "version>=1 AND topic_rule_version>=1 AND target_revision>=1",
            name="alert_rule_versions_revision_check",
        ),
        CheckConstraint(
            "metric IN ('negative_count','heat_increment') AND "
            "((metric='negative_count' AND event_id IS NULL AND threshold>=1 "
            "AND threshold=trunc(threshold::numeric)) OR "
            "(metric='heat_increment' AND event_id IS NOT NULL AND threshold>0)) "
            "AND threshold<=1000000000",
            name="alert_rule_versions_metric_check",
        ),
        CheckConstraint(
            "cooldown_seconds BETWEEN 300 AND 86400 AND octet_length(request_hash)=32",
            name="alert_rule_versions_config_check",
        ),
    )
    rule_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    request_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    name: Mapped[str] = mapped_column(String(80))
    topic_id: Mapped[UUID]
    topic_rule_version: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[UUID | None]
    metric: Mapped[str] = mapped_column(String(32))
    threshold: Mapped[float] = mapped_column(Float)
    cooldown_seconds: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[UUID]
    target_revision: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertEvaluation(Base):
    __tablename__ = "alert_evaluations"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="alert_evaluations_owner_id_key"),
        UniqueConstraint(
            "owner_id", "rule_id", "rule_version", "window_end", name="alert_evaluations_window_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "rule_id", "rule_version"],
            [
                "alert_rule_versions.owner_id",
                "alert_rule_versions.rule_id",
                "alert_rule_versions.version",
            ],
            ondelete="CASCADE",
            name="alert_evaluations_rule_version_fkey",
        ),
        CheckConstraint(
            "status IN ('blocked','unknown','below_threshold','cooldown','triggered','withdrawn')",
            name="alert_evaluations_status_check",
        ),
        CheckConstraint(
            "window_end=window_start+interval '1 hour' "
            "AND mod(date_part('epoch',window_end)::bigint,300)=0",
            name="alert_evaluations_window_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_manifest)='object' AND octet_length(input_hash)=32",
            name="alert_evaluations_input_check",
        ),
        CheckConstraint(
            "cooldown_until IS NULL OR cooldown_until>window_end",
            name="alert_evaluations_cooldown_check",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    rule_id: Mapped[UUID]
    rule_version: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float)
    input_manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
