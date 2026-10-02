"""Shared guarded reading groups, timeline and fixed-revision expansion contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from core.schemas import OutputModel
from publication.schemas import Category, PublicItemView


class PublicReadingFilters(OutputModel):
    window: Literal["24h", "7d"] = "24h"
    channel: Literal["all", "news", "x", "firstParty"] = "all"
    category: Category | None = None
    source_key: str | None = None
    tag: str | None = None
    topic: str | None = None


class PublicDevelopmentView(OutputModel):
    fact_id: UUID
    title: str
    anchor_at: datetime
    report_count: int
    representative: PublicItemView


class PublicReadingGroupView(OutputModel):
    fact_id: UUID
    event_id: UUID | None
    additional_source_count: int
    report_count: int
    development_count: int
    latest_development: PublicDevelopmentView | None


class PublicTimelineCardView(OutputModel):
    key: str
    anchor_at: datetime
    item: PublicItemView
    group: PublicReadingGroupView | None


class PublicTimelinePage(OutputModel):
    filters: PublicReadingFilters
    cards: list[PublicTimelineCardView]
    next_cursor: str | None
    refresh_at: datetime | None
    day_counts: dict[str, int] = Field(default_factory=dict)
    snapshot_at: datetime


class PublicFactReportsPage(OutputModel):
    fact_id: UUID
    revision: str
    reports: list[PublicItemView]
    next_cursor: str | None


class PublicDevelopmentsPage(OutputModel):
    event_id: UUID
    revision: str
    developments: list[PublicDevelopmentView]
    next_cursor: str | None
