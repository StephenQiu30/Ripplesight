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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EventAttentionSource(Base):
    __tablename__ = "event_attention_sources"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="event_attention_sources_scope_id_key"),
        UniqueConstraint(
            "owner_id",
            "source_key",
            "selector_kind",
            "selector_ref",
            name="event_attention_sources_selector_key",
        ),
        CheckConstraint(
            "source_key ~ '^[a-z][a-z0-9_-]{0,63}$'", name="event_attention_sources_source_check"
        ),
        CheckConstraint(
            "selector_kind IN ('source','author','native_scope','canonical_host')",
            name="event_attention_sources_selector_check",
        ),
        CheckConstraint(
            "btrim(selector_ref) <> '' AND btrim(name) <> ''",
            name="event_attention_sources_identity_check",
        ),
        CheckConstraint(
            "mode IN ('editorial','signal','isolated')", name="event_attention_sources_mode_check"
        ),
        CheckConstraint(
            "revision >= 1 AND interval_seconds >= 300",
            name="event_attention_sources_revision_check",
        ),
        CheckConstraint(
            "tier IS NULL OR tier IN ('T1','T1_5','T2')", name="event_attention_sources_tier_check"
        ),
        CheckConstraint("updated_at >= created_at", name="event_attention_sources_updated_check"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    source_key: Mapped[str] = mapped_column(String(64))
    selector_kind: Mapped[str] = mapped_column(String(24))
    selector_ref: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int]
    mode: Mapped[str] = mapped_column(String(16))
    group_key: Mapped[str | None] = mapped_column(String(128))
    owner_entity_key: Mapped[str | None] = mapped_column(String(128))
    first_party: Mapped[bool]
    tier: Mapped[str | None] = mapped_column(String(8))
    scheduled: Mapped[bool]
    enabled: Mapped[bool]
    interval_seconds: Mapped[int]
    last_successful_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventAttentionSignal(Base):
    __tablename__ = "event_attention_signals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_attention_signals_event_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_id"],
            ["event_attention_sources.owner_id", "event_attention_sources.id"],
            ondelete="CASCADE",
            name="event_attention_signals_source_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "fact_id"],
            ["event_facts.owner_id", "event_facts.topic_id", "event_facts.id"],
            name="event_attention_signals_fact_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="RESTRICT",
            name="event_attention_signals_content_fkey",
        ),
        UniqueConstraint(
            "owner_id",
            "topic_id",
            "event_id",
            "content_id",
            "content_version_id",
            name="event_attention_signals_input_key",
        ),
        CheckConstraint(
            "kind IN ('editorial','discussion','native')", name="event_attention_signals_kind_check"
        ),
        CheckConstraint(
            "time_basis IN ('published','discovered')", name="event_attention_signals_time_check"
        ),
        CheckConstraint(
            "status IN ('active','withdrawn')", name="event_attention_signals_status_check"
        ),
        Index("event_attention_signals_window_idx", "owner_id", "event_id", "source_time"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    event_id: Mapped[UUID]
    fact_id: Mapped[UUID | None]
    source_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_basis: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventAttentionSnapshot(Base):
    __tablename__ = "event_attention_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_attention_snapshots_event_fkey",
        ),
        UniqueConstraint(
            "owner_id",
            "event_id",
            "event_revision",
            "window_end",
            "formula_version",
            "input_fingerprint",
            name="event_attention_snapshots_input_key",
        ),
        CheckConstraint(
            "event_revision >= 1 AND octet_length(input_fingerprint) = 32",
            name="event_attention_snapshots_revision_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_manifest) = 'object' AND jsonb_typeof(result) = 'object'",
            name="event_attention_snapshots_json_check",
        ),
        Index(
            "event_attention_snapshots_latest_idx",
            "owner_id",
            "event_id",
            "window_end",
            "computed_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    event_id: Mapped[UUID]
    event_revision: Mapped[int]
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    formula_version: Mapped[str] = mapped_column(String(128))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    input_manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    complete: Mapped[bool]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
