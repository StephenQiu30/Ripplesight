from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .models import EvidenceLink, HotspotEvent, RawContentItem, SourceType

SOURCE_TYPE_WEIGHTS: dict[SourceType, float] = {
    SourceType.NEWS: 1.4,
    SourceType.RSS: 1.2,
    SourceType.GITHUB: 1.1,
    SourceType.HACKER_NEWS: 1.0,
    SourceType.PRODUCT_HUNT: 1.0,
    SourceType.HUGGING_FACE: 1.1,
    SourceType.GOOGLE_TRENDS: 0.9,
    SourceType.X: 0.8,
}

_NON_WORD_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    return _NON_WORD_PATTERN.sub("-", value.casefold()).strip("-")


def derive_event_key(title: str) -> str:
    key = normalize_text(title)
    return key or "untitled-event"


def score_hotspot_event(event: HotspotEvent) -> float:
    unique_types = set(event.source_types)
    base = sum(SOURCE_TYPE_WEIGHTS.get(source_type, 1.0) for source_type in unique_types)
    evidence_bonus = min(len(event.evidence_links) * 0.15, 0.75)
    score = base + evidence_bonus

    if unique_types == {SourceType.X}:
        return round(min(score * 0.35, 0.9), 3)

    return round(score, 3)


def rank_hotspot_events(events: Iterable[HotspotEvent]) -> list[HotspotEvent]:
    return sorted(
        events,
        key=lambda event: (event.score, event.source_count, event.last_seen_at.timestamp()),
        reverse=True,
    )


def cluster_raw_content(items: Iterable[RawContentItem]) -> list[HotspotEvent]:
    grouped_items: dict[str, list[RawContentItem]] = defaultdict(list)
    for item in items:
        grouped_items[derive_event_key(item.title)].append(item)

    events: list[HotspotEvent] = []
    for event_key, grouped in grouped_items.items():
        ordered = sorted(grouped, key=lambda item: item.published_at)
        primary_item = max(ordered, key=lambda item: (len(item.title), item.published_at.timestamp()))
        evidence_links = _build_evidence_links(ordered)
        source_types = tuple(sorted({item.source_type for item in ordered}, key=lambda item: item.value))
        event = HotspotEvent(
            id=event_key,
            event_key=event_key,
            event_title=primary_item.title,
            summary_zh=None,
            topic_tags=(),
            score=0.0,
            status="active",
            first_seen_at=ordered[0].published_at,
            last_seen_at=ordered[-1].published_at,
            source_count=len({item.source_config_id for item in ordered}),
            evidence_links=evidence_links,
            source_types=source_types,
        )
        events.append(_with_score(event))

    return rank_hotspot_events(events)


def _build_evidence_links(items: Iterable[RawContentItem]) -> tuple[EvidenceLink, ...]:
    seen_urls: set[str] = set()
    links: list[EvidenceLink] = []
    for item in items:
        if item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        links.append(
            EvidenceLink(
                source_config_id=item.source_config_id,
                source_name=item.source_name,
                source_type=item.source_type,
                url=item.url,
                title=item.title,
                external_id=item.external_id,
            )
        )
    return tuple(links)


def _with_score(event: HotspotEvent) -> HotspotEvent:
    return HotspotEvent(
        id=event.id,
        event_key=event.event_key,
        event_title=event.event_title,
        summary_zh=event.summary_zh,
        topic_tags=event.topic_tags,
        score=score_hotspot_event(event),
        status=event.status,
        first_seen_at=event.first_seen_at,
        last_seen_at=event.last_seen_at,
        source_count=event.source_count,
        evidence_links=event.evidence_links,
        source_types=event.source_types,
    )
