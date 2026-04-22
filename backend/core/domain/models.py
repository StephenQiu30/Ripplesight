from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    NEWS = "news"
    X = "x"
    RSS = "rss"
    GITHUB = "github"
    HACKER_NEWS = "hacker_news"
    PRODUCT_HUNT = "product_hunt"
    HUGGING_FACE = "hugging_face"
    GOOGLE_TRENDS = "google_trends"


class AccessMethod(StrEnum):
    API = "api"
    RSS = "rss"
    WEBHOOK = "webhook"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class SourceConfig:
    id: str
    name: str
    source_type: SourceType
    access_method: AccessMethod
    language: str
    region: str
    weight: float
    poll_interval_minutes: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class KeywordRule:
    id: str
    keyword: str
    category: str
    query_template: str
    priority: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MonitoredAccount:
    id: str
    platform: str
    handle: str
    display_name: str
    account_type: str
    weight: float
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class RawContentItem:
    id: str
    source_config_id: str
    source_name: str
    source_type: SourceType
    external_id: str
    title: str
    content_excerpt: str
    url: str
    author: str
    published_at: datetime
    language: str
    raw_payload: dict[str, Any]
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    source_config_id: str
    source_name: str
    source_type: SourceType
    url: str
    title: str
    external_id: str


@dataclass(frozen=True, slots=True)
class HotspotEvent:
    id: str
    event_key: str
    event_title: str
    summary_zh: str | None
    topic_tags: tuple[str, ...]
    score: float
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    source_count: int
    evidence_links: tuple[EvidenceLink, ...] = field(default_factory=tuple)
    source_types: tuple[SourceType, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DailyDigest:
    id: str
    digest_date: date
    title: str
    highlights: tuple[str, ...]
    event_ids: tuple[str, ...]
    generated_at: datetime
    delivery_status: str


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    id: str
    target_type: str
    target_id: str
    feedback_type: str
    comment: str | None
    created_at: datetime
