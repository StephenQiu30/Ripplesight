"""Literal AND search over currently permitted projections, with bounded work."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Literal
from uuid import UUID

from core.errors import ApplicationError
from publication.cursors import decode_cursor, encode_cursor
from publication.listing import iter_current_publications_in_transaction
from publication.media import body_presentation
from publication.reading import PublicationReadingService, public_item
from publication.schemas import Category, PublicItemsPage

_ACTIVE = threading.BoundedSemaphore(4)
_WAITERS = threading.BoundedSemaphore(8)


class _BodyText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def normalize_terms(query: str) -> tuple[str, ...]:
    if not query.strip() or len(query) > 200:
        raise ApplicationError("invalid_publication_input")
    terms = tuple(dict.fromkeys(query.casefold().split()))
    if len(terms) > 6:
        raise ApplicationError("invalid_publication_input")
    return terms


def search_weight(terms: tuple[str, ...], *, title: str, summary: str, body: str) -> int:
    lowered = (title.casefold(), summary.casefold(), body.casefold())
    total = 0
    for term in terms:
        score = sum(
            weight for field, weight in zip(lowered, (6, 3, 1), strict=True) if term in field
        )
        if not score:
            return 0
        total += score
    return total


@contextmanager
def bounded_search_slot() -> Iterator[None]:
    if not _WAITERS.acquire(blocking=False):
        raise ApplicationError("publication_search_busy")
    acquired = False
    try:
        acquired = _ACTIVE.acquire(timeout=3)
        if not acquired:
            raise ApplicationError("publication_search_busy")
        yield
    finally:
        if acquired:
            _ACTIVE.release()
        _WAITERS.release()


def search_in_transaction(
    reader: PublicationReadingService,
    *,
    owner_id: UUID,
    query: str,
    now: datetime,
    window: str = "7d",
    selected: bool = False,
    limit: int = 50,
    cursor: str | None = None,
    category: Category | None = None,
    channel: str | None = None,
    source_key: str | None = None,
    tag: str | None = None,
    topic: str | None = None,
    search_order: Literal["relevance", "time"] = "relevance",
) -> PublicItemsPage:
    terms = normalize_terms(query)
    if window not in {"24h", "7d"} or not 1 <= limit <= 100:
        raise ApplicationError("invalid_publication_input")
    limit = min(limit, 40)
    scope = {
        "owner": owner_id,
        "query": terms,
        "window": window,
        "selected": selected,
        "type": "search",
        "order": search_order,
        "limit": limit,
        "category": category,
        "channel": channel,
        "source_key": source_key,
        "tag": tag,
        "topic": topic,
    }
    anchor: tuple[int, datetime, str] | None = None
    as_of = now
    if cursor:
        data = decode_cursor(cursor, scope)
        try:
            anchor = (
                int(data["weight"]),
                datetime.fromisoformat(data["sort"]),
                str(UUID(data["id"])),
            )
            as_of = datetime.fromisoformat(data["at"])
            if as_of.utcoffset() is None or anchor[1].utcoffset() is None or as_of > now:
                raise ValueError("invalid cursor")
        except (ValueError, TypeError, KeyError) as error:
            raise ApplicationError("invalid_publication_cursor") from error
    ranked = []
    from publication.topics import topic_match_tags_for_slug

    topic_tags = topic_match_tags_for_slug(topic) if topic else ()
    if topic and topic_tags is None:
        raise ApplicationError("invalid_publication_input")
    with bounded_search_slot():
        for member in iter_current_publications_in_transaction(
            reader.session,
            owner_id=owner_id,
            now=now,
            starts_at=as_of - timedelta(days=1 if window == "24h" else 7),
            ends_at=as_of,
            source_key=source_key,
            include_body=True,
        ):
            projection = member.projection
            if (
                (selected and not projection.selected)
                or (category is not None and projection.category != category)
                or (
                    channel is not None
                    and channel != projection.channel
                    and not (channel == "firstParty" and projection.first_party)
                )
                or (tag is not None and tag not in member.subject_tags)
                or (topic_tags and not set(topic_tags).intersection(member.subject_tags))
                or (
                    projection.selected
                    and (projection.visible_after is None or projection.visible_after > now)
                )
            ):
                continue
            body = member.permitted_body
            if member.body_format in {"html", "markdown"}:
                visible_html, _, _ = body_presentation(body, body_format=member.body_format)
                parser = _BodyText()
                parser.feed(visible_html)
                body = " ".join(parser.parts)
            weight = search_weight(
                terms, title=projection.title, summary=projection.summary or "", body=body
            )
            if weight:
                ranked.append(
                    (
                        weight if search_order == "relevance" else 0,
                        projection.sort_at,
                        str(projection.content_id),
                        public_item(projection, icon_url=member.icon_url),
                    )
                )
                # Explicit 40-per-page/50-page search capacity, never a partial success.
                if len(ranked) > limit * 50:
                    raise ApplicationError("publication_search_busy")
    ranked.sort(key=lambda item: item[:3], reverse=True)
    if anchor:
        ranked = [item for item in ranked if item[:3] < anchor]
    page = ranked[:limit]
    next_cursor = (
        encode_cursor(
            scope, {"weight": page[-1][0], "sort": page[-1][1], "id": page[-1][2], "at": as_of}
        )
        if len(ranked) > limit
        else None
    )
    return PublicItemsPage(
        items=[item[3] for item in page],
        next_cursor=next_cursor,
        snapshot_at=as_of,
        source_status=reader.source_status_in_transaction(owner_id=owner_id),
    )
