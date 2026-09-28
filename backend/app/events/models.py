from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="events_owner_id_key"),
        UniqueConstraint("owner_id", "topic_id", "id", name="events_owner_topic_id_key"),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="events_owner_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "merged_into_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            name="events_merged_into_fkey",
        ),
        CheckConstraint("revision >= 1", name="events_revision_check"),
        CheckConstraint("btrim(title) <> ''", name="events_title_check"),
        CheckConstraint("btrim(summary) <> ''", name="events_summary_check"),
        CheckConstraint(
            "first_seen_basis IN ('published', 'discovered')", name="events_first_seen_basis_check"
        ),
        CheckConstraint("status IN ('active', 'merged')", name="events_status_check"),
        CheckConstraint("updated_at >= created_at", name="events_updated_at_check"),
        CheckConstraint(
            "(status = 'active' AND merged_into_id IS NULL) OR "
            "(status = 'merged' AND merged_into_id IS NOT NULL AND merged_into_id <> id)",
            name="events_merge_state_check",
        ),
        Index("events_owner_topic_seen_idx", "owner_id", "topic_id", "first_seen_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    revision: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime]
    first_seen_basis: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    merged_into_id: Mapped[UUID | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class EventMember(Base):
    __tablename__ = "event_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_members_event_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="RESTRICT",
            name="event_members_content_version_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "source_key"],
            ["content_records.owner_id", "content_records.id", "content_records.source_key"],
            ondelete="RESTRICT",
            name="event_members_content_source_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "representative_comment_id"],
            ["content_records.owner_id", "content_records.id"],
            ondelete="RESTRICT",
            name="event_members_comment_fkey",
        ),
        UniqueConstraint(
            "owner_id",
            "topic_id",
            "content_id",
            "added_revision",
            name="event_members_revision_key",
        ),
        CheckConstraint("added_revision >= 1", name="event_members_added_revision_check"),
        CheckConstraint(
            "removed_revision IS NULL OR removed_revision > added_revision",
            name="event_members_removed_revision_check",
        ),
        CheckConstraint(
            "assignment_origin IN ('model', 'manual')", name="event_members_origin_check"
        ),
        CheckConstraint(
            "source_key ~ '^[a-z][a-z0-9_-]{0,63}$'", name="event_members_source_key_check"
        ),
        Index(
            "event_members_event_current_idx",
            "owner_id",
            "event_id",
            postgresql_where=text("removed_revision IS NULL"),
        ),
        Index(
            "event_members_one_current_assignment_idx",
            "owner_id",
            "topic_id",
            "content_id",
            unique=True,
            postgresql_where=text("removed_revision IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    event_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    source_key: Mapped[str] = mapped_column(String(64))
    representative_comment_id: Mapped[UUID | None]
    added_revision: Mapped[int]
    removed_revision: Mapped[int | None]
    assignment_origin: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime]


class EventCandidate(Base):
    __tablename__ = "event_candidates"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "topic_id", "input_fingerprint", name="event_candidates_fingerprint_key"
        ),
        UniqueConstraint("owner_id", "id", name="event_candidates_owner_id_key"),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="event_candidates_owner_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="event_candidates_ai_call_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="event_candidates_job_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            name="event_candidates_event_fkey",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32", name="event_candidates_fingerprint_length_check"
        ),
        CheckConstraint(
            "jsonb_typeof(member_version_ids) = 'array' AND "
            "jsonb_array_length(member_version_ids) BETWEEN 2 AND 20",
            name="event_candidates_members_check",
        ),
        CheckConstraint(
            "jsonb_typeof(expected_event_revisions) = 'object'",
            name="event_candidates_revisions_check",
        ),
        CheckConstraint("window_end > window_start", name="event_candidates_window_check"),
        CheckConstraint("prompt_version <> ''", name="event_candidates_prompt_check"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected', 'failed')",
            name="event_candidates_status_check",
        ),
        CheckConstraint("updated_at >= created_at", name="event_candidates_updated_at_check"),
        CheckConstraint(
            "(status = 'pending' AND event_id IS NULL) OR "
            "(status = 'confirmed' AND event_id IS NOT NULL "
            "AND ai_call_id IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'rejected' AND event_id IS NULL "
            "AND ai_call_id IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'failed' AND event_id IS NULL AND error_code IS NOT NULL)",
            name="event_candidates_result_check",
        ),
        Index("event_candidates_pending_idx", "status", "owner_id", "topic_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    member_version_ids: Mapped[list[str]] = mapped_column(JSONB)
    expected_event_revisions: Mapped[dict[str, int]] = mapped_column(JSONB)
    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    prompt_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    ai_call_id: Mapped[UUID | None]
    job_id: Mapped[UUID | None]
    event_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
