from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AnalysisPromptActivation(Base):
    __tablename__ = "analysis_prompt_activations"
    __table_args__ = (
        CheckConstraint("prompt_version <> ''", name="analysis_prompt_activations_version_check"),
    )

    prompt_version: Mapped[str] = mapped_column(String(128), primary_key=True)
    activated_at: Mapped[datetime]


class AnalysisPromptRuntimeSession(Base):
    __tablename__ = "analysis_prompt_runtime_sessions"
    __table_args__ = (
        CheckConstraint(
            "prompt_version <> ''", name="analysis_prompt_runtime_sessions_version_check"
        ),
        CheckConstraint(
            "last_seen_at >= started_at", name="analysis_prompt_runtime_sessions_last_seen_check"
        ),
        CheckConstraint(
            "stopped_at IS NULL OR stopped_at >= last_seen_at",
            name="analysis_prompt_runtime_sessions_stopped_check",
        ),
        Index(
            "analysis_prompt_runtime_sessions_version_started_idx", "prompt_version", "started_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(128))
    ai_enabled: Mapped[bool] = mapped_column(Boolean)
    started_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    stopped_at: Mapped[datetime | None]


class ContentAnnotation(Base):
    __tablename__ = "content_annotations"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="content_annotations_owner_id_key"),
        UniqueConstraint(
            "owner_id",
            "content_version_id",
            "topic_id",
            "topic_rule_version",
            "prompt_version",
            "input_signature",
            name="content_annotations_owner_version_topic_rule_prompt_key",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="CASCADE",
            name="content_annotations_owner_content_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="content_annotations_owner_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["topic_id", "topic_rule_version"],
            ["monitor_topic_versions.topic_id", "monitor_topic_versions.version"],
            ondelete="CASCADE",
            name="content_annotations_topic_rule_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="content_annotations_owner_ai_call_fkey",
        ),
        CheckConstraint("topic_rule_version >= 1", name="content_annotations_rule_version_check"),
        CheckConstraint("prompt_version <> ''", name="content_annotations_prompt_version_check"),
        CheckConstraint(
            "(input_manifest IS NULL AND input_signature = 'legacy') OR "
            "(input_manifest IS NOT NULL AND jsonb_typeof(input_manifest) = 'object' "
            "AND octet_length(input_manifest::text) <= 262144 "
            "AND input_signature ~ '^[0-9a-f]{64}$')",
            name="content_annotations_input_manifest_check",
        ),
        CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative')",
            name="content_annotations_sentiment_check",
        ),
        CheckConstraint(
            "jsonb_typeof(viewpoints) = 'array' AND jsonb_array_length(viewpoints) <= 5",
            name="content_annotations_viewpoints_check",
        ),
        CheckConstraint(
            "jsonb_typeof(diagnostic_history) = 'array'",
            name="content_annotations_diagnostic_history_check",
        ),
        CheckConstraint(
            "status IN ('annotated', 'unanalyzed')",
            name="content_annotations_status_check",
        ),
        CheckConstraint(
            "(status = 'annotated' AND result_state = 'valid' "
            "AND relevant IS NOT NULL AND relevance_reason IS NOT NULL "
            "AND btrim(relevance_reason) <> '' AND summary IS NOT NULL "
            "AND btrim(summary) <> '' AND ai_call_id IS NOT NULL AND error_code IS NULL "
            "AND ((relevant AND sentiment IS NOT NULL) OR (NOT relevant AND sentiment IS NULL))) "
            "OR (status = 'unanalyzed' AND result_state IN ('pending', 'failed', 'invalid') "
            "AND relevant IS NULL AND relevance_reason IS NULL AND sentiment IS NULL "
            "AND summary IS NULL AND viewpoints = '[]'::jsonb "
            "AND ((result_state = 'pending' AND ai_call_id IS NULL AND error_code IS NULL) "
            "OR (result_state IN ('failed', 'invalid') AND ai_call_id IS NOT NULL "
            "AND error_code IS NOT NULL AND btrim(error_code) <> '')))",
            name="content_annotations_output_status_check",
        ),
        CheckConstraint(
            "created_at <= updated_at",
            name="content_annotations_updated_at_check",
        ),
        CheckConstraint(
            "(result_state = 'valid') = (first_valid_at IS NOT NULL)",
            name="content_annotations_first_valid_at_check",
        ),
        Index(
            "content_annotations_topic_created_idx",
            "owner_id",
            "topic_id",
            "created_at",
        ),
        Index(
            "content_annotations_content_idx",
            "owner_id",
            "content_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    topic_rule_version: Mapped[int]
    prompt_version: Mapped[str] = mapped_column(String(128))
    input_manifest: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    input_signature: Mapped[str] = mapped_column(String(64), server_default=text("'legacy'"))
    relevant: Mapped[bool | None] = mapped_column(Boolean)
    relevance_reason: Mapped[str | None] = mapped_column(String(500))
    sentiment: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(String(60))
    viewpoints: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    ai_call_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16))
    result_state: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    diagnostic_history: Mapped[list[dict[str, str | None]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    first_valid_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
