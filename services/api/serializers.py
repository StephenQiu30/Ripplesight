from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from backend.core.domain import DailyDigest, FeedbackRecord, HotspotEvent, KeywordRule, MonitoredAccount, SourceConfig, SourceType
from backend.core.interface import PageMeta

T = TypeVar("T")


def paginate(items: list[T], page: int, page_size: int) -> tuple[list[T], PageMeta]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], PageMeta(page=page, page_size=page_size, total=total)


def serialize_page_meta(meta: PageMeta) -> dict[str, int]:
    return {"page": meta.page, "page_size": meta.page_size, "total": meta.total}


def serialize_source_config(item: SourceConfig) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "source_type": item.source_type.value,
        "access_method": item.access_method.value,
        "language": item.language,
        "region": item.region,
        "weight": item.weight,
        "poll_interval_minutes": item.poll_interval_minutes,
        "enabled": item.enabled,
    }


def serialize_keyword_rule(item: KeywordRule) -> dict[str, Any]:
    return {
        "id": item.id,
        "keyword": item.keyword,
        "category": item.category,
        "query_template": item.query_template,
        "priority": item.priority,
        "enabled": item.enabled,
    }


def serialize_monitored_account(item: MonitoredAccount) -> dict[str, Any]:
    return {
        "id": item.id,
        "platform": item.platform,
        "handle": item.handle,
        "display_name": item.display_name,
        "account_type": item.account_type,
        "weight": item.weight,
        "enabled": item.enabled,
    }


def serialize_hotspot_event(item: HotspotEvent) -> dict[str, Any]:
    return {
        "id": item.id,
        "event_title": item.event_title,
        "summary_zh": item.summary_zh or _build_summary(item),
        "topic_tags": list(item.topic_tags),
        "score": item.score,
        "status": item.status,
        "first_seen_at": _serialize_datetime(item.first_seen_at),
        "last_seen_at": _serialize_datetime(item.last_seen_at),
        "source_count": item.source_count,
        "evidence_links": [link.url for link in item.evidence_links],
    }


def serialize_daily_digest(item: DailyDigest) -> dict[str, Any]:
    return {
        "id": item.id,
        "digest_date": item.digest_date.isoformat(),
        "title": item.title,
        "highlights": list(item.highlights),
        "event_ids": list(item.event_ids),
        "generated_at": _serialize_datetime(item.generated_at),
        "delivery_status": item.delivery_status,
    }


def serialize_feedback_record(item: FeedbackRecord) -> dict[str, Any]:
    return {
        "id": item.id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "feedback_type": item.feedback_type,
        "comment": item.comment,
        "created_at": _serialize_datetime(item.created_at),
    }


def filter_events(
    events: list[HotspotEvent],
    *,
    source_type: SourceType | None,
    from_date: datetime | None,
    to_date: datetime | None,
    topic: str | None,
) -> list[HotspotEvent]:
    filtered = events
    if source_type is not None:
        filtered = [event for event in filtered if source_type in event.source_types]
    if from_date is not None:
        filtered = [event for event in filtered if event.last_seen_at >= from_date]
    if to_date is not None:
        filtered = [event for event in filtered if event.first_seen_at <= to_date]
    if topic:
        topic_match = topic.casefold()
        filtered = [
            event
            for event in filtered
            if topic_match in event.event_title.casefold()
            or any(topic_match in tag.casefold() for tag in event.topic_tags)
        ]
    return filtered


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _build_summary(item: HotspotEvent) -> str:
    if SourceType.X in item.source_types and len(item.source_types) == 1:
        return f"{item.event_title} 当前主要来自 X 单源信号，仍需更多来源交叉验证。"
    return f"{item.event_title} 已由多源信号汇聚成热点事件，可继续追踪其证据链。"
