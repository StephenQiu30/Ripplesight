from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict

from core.schemas import OutputModel

PublicPlatformQueryMode = Literal[
    "author_feed", "keyword_feed", "tag_feed", "hotlist", "comments_feed", "unknown"
]


class PublicPlatformCapability(StrEnum):
    KEYWORD_SEARCH = "keyword_search"
    AUTHOR_POSTS = "author_posts"
    INCREMENTAL = "incremental"
    TEXT = "text"
    ENGAGEMENT_COUNTS = "engagement_counts"
    COMMENTS = "comments"
    REPLIES = "replies"
    HOTLIST = "hotlist"
    HISTORY = "history"


class PublicPlatformCapabilityView(OutputModel):
    model_config = ConfigDict(frozen=True)

    capability: PublicPlatformCapability
    display_name: str
    documented_support: Literal["route_code", "unknown", "excluded"]
    execution_admitted: Literal[False] = False
    trial_verified: Literal[False] = False
    product_available: Literal[False] = False


class PublicPlatformEntryView(OutputModel):
    """Source research only: this DTO cannot grant an execution permission."""

    model_config = ConfigDict(frozen=True)

    entry_key: str
    display_name: str
    status: Literal["candidate", "blocked", "excluded", "missing"]
    query_mode: PublicPlatformQueryMode
    object_scope: str
    time_range: str
    sort_order: str
    pagination: str
    limitations: tuple[str, ...]
    admission_requirements: tuple[str, ...]
    block_reason: str
    supplier_fee_cap_micros: Literal[0] = 0
    fee_status: Literal["unverified", "disallowed"] = "unverified"
    execution_admitted: Literal[False] = False
    trial_verified: Literal[False] = False
    product_available: Literal[False] = False
    last_persisted_success_at: datetime | None = None
    route_template: str | None
    evidence_urls: tuple[str, ...]
    capabilities: tuple[PublicPlatformCapabilityView, ...]


class PublicPlatformCatalogView(OutputModel):
    model_config = ConfigDict(frozen=True)

    platform_key: Literal["x", "instagram", "facebook", "threads", "douyin", "bilibili", "weibo"]
    display_name: str
    scope_description: str
    inspected_component: Literal["rsshub"] = "rsshub"
    inspected_revision: str
    inspected_at: date
    entries: tuple[PublicPlatformEntryView, ...]
