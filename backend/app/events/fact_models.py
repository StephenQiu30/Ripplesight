from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
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


class EventFact(Base):
    """Stable occurrence identity within a topic, independent of its current story."""

    __tablename__ = "event_facts"
    __table_args__ = (
        UniqueConstraint("owner_id", "topic_id", "id", name="event_facts_scope_id_key"),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="event_facts_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "merged_into_id"],
            ["event_facts.owner_id", "event_facts.topic_id", "event_facts.id"],
            name="event_facts_merged_into_fkey",
        ),
        CheckConstraint("revision >= 1", name="event_facts_revision_check"),
        CheckConstraint("btrim(title) <> ''", name="event_facts_title_check"),
        CheckConstraint("btrim(summary) <> ''", name="event_facts_summary_check"),
        CheckConstraint(
            "status IN ('confirmed','unreviewed','merged')", name="event_facts_status_check"
        ),
        CheckConstraint(
            "(status = 'merged' AND merged_into_id IS NOT NULL AND merged_into_id <> id) OR "
            "(status <> 'merged' AND merged_into_id IS NULL)",
            name="event_facts_merge_check",
        ),
        CheckConstraint(
            "first_seen_basis IN ('published','discovered')", name="event_facts_time_check"
        ),
        CheckConstraint(
            "frame IS NULL OR jsonb_typeof(frame) = 'object'", name="event_facts_frame_check"
        ),
        CheckConstraint("updated_at >= created_at", name="event_facts_updated_check"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    revision: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    merged_into_id: Mapped[UUID | None]
    frame: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_basis: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventFactAssignment(Base):
    __tablename__ = "event_fact_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_fact_assignments_event_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "fact_id"],
            ["event_facts.owner_id", "event_facts.topic_id", "event_facts.id"],
            ondelete="CASCADE",
            name="event_fact_assignments_fact_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "root_fact_id"],
            ["event_facts.owner_id", "event_facts.topic_id", "event_facts.id"],
            name="event_fact_assignments_root_fkey",
        ),
        UniqueConstraint(
            "owner_id",
            "event_id",
            "fact_id",
            "added_revision",
            name="event_fact_assignments_revision_key",
        ),
        CheckConstraint("added_revision >= 1", name="event_fact_assignments_added_check"),
        CheckConstraint(
            "removed_revision IS NULL OR removed_revision > added_revision",
            name="event_fact_assignments_removed_check",
        ),
        CheckConstraint(
            "relation IN ('root','development','background','roundup','unreviewed')",
            name="event_fact_assignments_relation_check",
        ),
        CheckConstraint(
            "(relation IN ('development','background') AND root_fact_id IS NOT NULL "
            "AND root_fact_id <> fact_id) OR "
            "(relation IN ('root','roundup','unreviewed') AND root_fact_id IS NULL)",
            name="event_fact_assignments_root_check",
        ),
        Index(
            "event_fact_assignments_current_fact_idx",
            "owner_id",
            "topic_id",
            "fact_id",
            unique=True,
            postgresql_where=text("removed_revision IS NULL"),
        ),
        Index(
            "event_fact_assignments_current_root_idx",
            "owner_id",
            "event_id",
            unique=True,
            postgresql_where=text("removed_revision IS NULL AND relation IN ('root','roundup')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    event_id: Mapped[UUID]
    fact_id: Mapped[UUID]
    root_fact_id: Mapped[UUID | None]
    relation: Mapped[str] = mapped_column(String(16))
    added_revision: Mapped[int]
    removed_revision: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventFactMember(Base):
    __tablename__ = "event_fact_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "fact_id"],
            ["event_facts.owner_id", "event_facts.topic_id", "event_facts.id"],
            ondelete="CASCADE",
            name="event_fact_members_fact_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id", "event_member_id"],
            [
                "event_members.owner_id",
                "event_members.topic_id",
                "event_members.event_id",
                "event_members.id",
            ],
            ondelete="CASCADE",
            name="event_fact_members_member_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id", "content_version_id"],
            ["content_versions.owner_id", "content_versions.content_id", "content_versions.id"],
            ondelete="RESTRICT",
            name="event_fact_members_content_fkey",
        ),
        UniqueConstraint(
            "owner_id", "fact_id", "event_member_id", name="event_fact_members_history_key"
        ),
        CheckConstraint(
            "role IN ('primary','report','mention')", name="event_fact_members_role_check"
        ),
        CheckConstraint(
            "assignment_origin IN ('model','manual','legacy')",
            name="event_fact_members_origin_check",
        ),
        CheckConstraint("added_revision >= 1", name="event_fact_members_added_check"),
        CheckConstraint(
            "removed_revision IS NULL OR removed_revision > added_revision",
            name="event_fact_members_removed_check",
        ),
        Index(
            "event_fact_members_current_content_idx",
            "owner_id",
            "topic_id",
            "content_id",
            unique=True,
            postgresql_where=text("removed_revision IS NULL"),
        ),
        Index(
            "event_fact_members_current_primary_idx",
            "owner_id",
            "fact_id",
            unique=True,
            postgresql_where=text("removed_revision IS NULL AND role = 'primary'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    fact_id: Mapped[UUID]
    event_id: Mapped[UUID]
    event_member_id: Mapped[UUID]
    content_id: Mapped[UUID]
    content_version_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(String(16))
    assignment_origin: Mapped[str] = mapped_column(String(16))
    added_revision: Mapped[int]
    removed_revision: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventGroupingOverride(Base):
    __tablename__ = "event_grouping_overrides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="event_grouping_overrides_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "content_id"],
            ["content_records.owner_id", "content_records.id"],
            ondelete="CASCADE",
            name="event_grouping_overrides_content_fkey",
        ),
        CheckConstraint(
            "mode IN ('standalone','manual','regroup_pending')",
            name="event_grouping_overrides_mode_check",
        ),
        CheckConstraint("revision >= 1", name="event_grouping_overrides_revision_check"),
        CheckConstraint("btrim(reason) <> ''", name="event_grouping_overrides_reason_check"),
    )

    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    topic_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_id: Mapped[UUID] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int]
    reason: Mapped[str] = mapped_column(String(2000))
    actor_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRevisionOperation(Base):
    __tablename__ = "event_revision_operations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "operation_id", name="event_revision_operations_operation_key"
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="event_revision_operations_topic_fkey",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32", name="event_revision_operations_hash_check"
        ),
        CheckConstraint(
            "kind IN ('merge','split','move','detach','merge_facts','regroup','create_fact')",
            name="event_revision_operations_kind_check",
        ),
        CheckConstraint("btrim(reason) <> ''", name="event_revision_operations_reason_check"),
        CheckConstraint(
            "jsonb_typeof(before_state) = 'object' AND "
            "jsonb_typeof(after_state) = 'object' AND jsonb_typeof(result) = 'object'",
            name="event_revision_operations_json_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    operation_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(24))
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    actor_id: Mapped[UUID]
    reason: Mapped[str] = mapped_column(String(2000))
    before_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    after_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventDerivedContent(Base):
    __tablename__ = "event_derived_contents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_derived_contents_event_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="event_derived_contents_call_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "job_id"],
            ["jobs.owner_id", "jobs.id"],
            name="event_derived_contents_job_fkey",
        ),
        CheckConstraint("event_revision >= 1", name="event_derived_contents_revision_check"),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32", name="event_derived_contents_hash_check"
        ),
        CheckConstraint(
            "status IN ('pending','valid','failed','stale')",
            name="event_derived_contents_status_check",
        ),
        CheckConstraint(
            "(status = 'valid' AND title IS NOT NULL AND summary IS NOT NULL) OR "
            "(status <> 'valid' AND title IS NULL AND summary IS NULL AND latest_progress IS NULL)",
            name="event_derived_contents_text_check",
        ),
    )

    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    topic_id: Mapped[UUID]
    event_revision: Mapped[int]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    status: Mapped[str] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    latest_progress: Mapped[str | None] = mapped_column(String(2000))
    ai_call_id: Mapped[UUID | None]
    job_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventGroupingAssessment(Base):
    __tablename__ = "event_grouping_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "candidate_id"],
            ["event_candidates.owner_id", "event_candidates.id"],
            ondelete="CASCADE",
            name="event_grouping_assessments_candidate_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id"],
            ["monitor_topics.owner_id", "monitor_topics.id"],
            ondelete="CASCADE",
            name="event_grouping_assessments_topic_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "ai_call_id"],
            ["ai_calls.owner_id", "ai_calls.id"],
            name="event_grouping_assessments_call_fkey",
        ),
        UniqueConstraint(
            "owner_id",
            "candidate_id",
            "input_fingerprint",
            name="event_grouping_assessments_input_key",
        ),
        CheckConstraint(
            "octet_length(input_fingerprint) = 32", name="event_grouping_assessments_hash_check"
        ),
        CheckConstraint(
            "status IN ('pending','valid','degraded','stale','failed')",
            name="event_grouping_assessments_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(input_snapshot) = 'object' AND jsonb_typeof(decisions) = 'array'",
            name="event_grouping_assessments_json_check",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="event_grouping_assessments_confidence_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID]
    topic_id: Mapped[UUID]
    candidate_id: Mapped[UUID]
    input_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    decisions: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float)
    ai_call_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
