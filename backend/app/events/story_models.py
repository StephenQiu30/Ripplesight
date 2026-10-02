from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EventStoryLink(Base):
    __tablename__ = "event_story_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "first_event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_story_links_first_fkey",
        ),
        ForeignKeyConstraint(
            ["owner_id", "topic_id", "second_event_id"],
            ["events.owner_id", "events.topic_id", "events.id"],
            ondelete="CASCADE",
            name="event_story_links_second_fkey",
        ),
        CheckConstraint("first_event_id < second_event_id", name="event_story_links_order_check"),
        CheckConstraint(
            "first_revision >= 1 AND second_revision >= 1",
            name="event_story_links_revision_check",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence)='array' AND jsonb_array_length(evidence) BETWEEN 2 AND 20",
            name="event_story_links_evidence_check",
        ),
        Index("event_story_links_second_idx", "owner_id", "topic_id", "second_event_id"),
    )
    owner_id: Mapped[UUID] = mapped_column(primary_key=True)
    topic_id: Mapped[UUID]
    first_event_id: Mapped[UUID] = mapped_column(primary_key=True)
    second_event_id: Mapped[UUID] = mapped_column(primary_key=True)
    first_revision: Mapped[int]
    second_revision: Mapped[int]
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
