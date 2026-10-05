"""Stable MIT industry topics; counts are computed from current permitted fixed publications."""

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from publication.listing import PublicationListingMember, iter_current_publications_in_transaction
from publication.reading import public_item
from publication.schemas import Category
from publication.topic_schemas import (
    PublicRelatedTopicView,
    PublicTopicDirectoryView,
    PublicTopicPageView,
    PublicTopicSummaryView,
)

TOPIC_PAGE_SIZE = 20


class IndustryTopic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
    slug: str
    name: str
    group: Literal["company", "field", "genre"]
    entity_id: str | None = Field(default=None, alias="entityId")
    tags: tuple[str, ...]
    definition: str
    related: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def industry_topics() -> tuple[IndustryTopic, ...]:
    raw = json.loads(Path(__file__).with_name("topics.json").read_text())
    return tuple(IndustryTopic.model_validate(topic) for topic in raw["topics"])


def topic_match_tags(topic: IndustryTopic) -> tuple[str, ...]:
    return (f"entity:{topic.entity_id}",) if topic.entity_id else topic.tags


def topic_match_tags_for_slug(slug: str) -> tuple[str, ...] | None:
    topic = next((topic for topic in industry_topics() if topic.slug == slug), None)
    return topic_match_tags(topic) if topic else None


def topic_indexable(*, total: int, recent: int) -> bool:
    return total >= 50 or (total >= 20 and recent > 0)


def topic_summaries(
    members: Iterable[PublicationListingMember],
    *,
    now: datetime,
    indexing_enabled: bool = False,
) -> PublicTopicDirectoryView:
    definitions = industry_topics()
    counts = {topic.slug: [0, 0] for topic in definitions}
    latest: dict[str, datetime] = {}
    permitted_index = {topic.slug: True for topic in definitions}
    tags_to_slugs: dict[str, set[str]] = {}
    for topic in definitions:
        for tag in topic_match_tags(topic):
            tags_to_slugs.setdefault(tag, set()).add(topic.slug)
    recent_from = now - timedelta(days=30)
    refresh: datetime | None = None
    for row in members:
        p = row.projection
        if not p.selected or not p.visible_after:
            continue
        if p.visible_after > now:
            refresh = min(refresh or p.visible_after, p.visible_after)
            continue
        matched = set().union(*(tags_to_slugs.get(tag, set()) for tag in row.subject_tags))
        for slug in matched:
            permitted_index[slug] = permitted_index[slug] and p.indexable
            counts[slug][0] += 1
            counts[slug][1] += int(p.timeline_at > recent_from)
            latest[slug] = max(latest.get(slug, p.timeline_at), p.timeline_at)
        if p.timeline_at > recent_from:
            deadline = p.timeline_at + timedelta(days=30)
            refresh = min(refresh or deadline, deadline)
    return PublicTopicDirectoryView(
        topics=[
            PublicTopicSummaryView(
                slug=topic.slug,
                name=topic.name,
                group=topic.group,
                definition=topic.definition,
                total=counts[topic.slug][0],
                recent=counts[topic.slug][1],
                indexable=indexing_enabled
                and permitted_index[topic.slug]
                and topic_indexable(total=counts[topic.slug][0], recent=counts[topic.slug][1]),
                latest_at=latest.get(topic.slug),
            )
            for topic in definitions
        ],
        refresh_at=refresh,
    )


def topic_directory_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    indexing_enabled: bool = False,
    public_categories: tuple[Category, ...] = (),
) -> PublicTopicDirectoryView:
    members = iter_current_publications_in_transaction(
        session,
        owner_id=owner_id,
        now=now,
        indexing_enabled=indexing_enabled,
        public_categories=public_categories,
    )
    return topic_summaries(members, now=now, indexing_enabled=indexing_enabled)


def topic_page_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    slug: str,
    page: int,
    now: datetime,
    indexing_enabled: bool = False,
    public_categories: tuple[Category, ...] = (),
) -> PublicTopicPageView:
    topic = next((topic for topic in industry_topics() if topic.slug == slug), None)
    if topic is None or page < 1:
        raise ApplicationError("resource_not_found")
    matches = set(topic_match_tags(topic))
    page_items = []
    total, recent, latest, refresh = 0, 0, None, None
    permitted_index = True
    recent_from = now - timedelta(days=30)
    offset = (page - 1) * TOPIC_PAGE_SIZE
    for row in iter_current_publications_in_transaction(
        session,
        owner_id=owner_id,
        now=now,
        order="timeline",
        indexing_enabled=indexing_enabled,
        public_categories=public_categories,
    ):
        p = row.projection
        if not p.selected or not p.visible_after or not matches.intersection(row.subject_tags):
            continue
        if p.visible_after > now:
            refresh = min(refresh or p.visible_after, p.visible_after)
            continue
        if offset <= total < offset + TOPIC_PAGE_SIZE:
            page_items.append(public_item(p, icon_url=row.icon_url))
        total += 1
        permitted_index = permitted_index and p.indexable
        recent += int(p.timeline_at > recent_from)
        latest = max(latest or p.timeline_at, p.timeline_at)
        if p.timeline_at > recent_from:
            deadline = p.timeline_at + timedelta(days=30)
            refresh = min(refresh or deadline, deadline)
    summary = PublicTopicSummaryView(
        slug=topic.slug,
        name=topic.name,
        group=topic.group,
        definition=topic.definition,
        total=total,
        recent=recent,
        indexable=indexing_enabled
        and permitted_index
        and topic_indexable(total=total, recent=recent),
        latest_at=latest,
    )
    pages = max(1, (total + TOPIC_PAGE_SIZE - 1) // TOPIC_PAGE_SIZE)
    if page > pages:
        raise ApplicationError("resource_not_found")
    known = {topic.slug: topic for topic in industry_topics()}
    return PublicTopicPageView(
        topic=summary,
        related=[
            PublicRelatedTopicView(slug=slug, name=known[slug].name)
            for slug in topic.related
            if slug in known
        ],
        items=page_items,
        page=page,
        page_count=pages,
        refresh_at=refresh,
    )
