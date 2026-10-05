"""AIHOT timeline/groups adapted to fixed publication DTOs (MIT; see PROVENANCE)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from analysis.editorial_selection import representative_order
from core.errors import ApplicationError
from publication.cursors import decode_cursor, encode_cursor
from publication.group_schemas import (
    PublicDevelopmentsPage,
    PublicDevelopmentView,
    PublicFactReportsPage,
    PublicReadingFilters,
    PublicReadingGroupView,
    PublicTimelineCardView,
    PublicTimelinePage,
)
from publication.listing import PublicationListingMember, iter_current_publications_in_transaction
from publication.projection import fingerprint
from publication.reading import public_item
from publication.schemas import Category


def pick_representative(rows: list[PublicationListingMember]) -> PublicationListingMember:
    if not rows:
        raise ValueError("a representative requires at least one permitted member")
    return min(
        rows,
        key=lambda row: representative_order(
            first_party=row.projection.first_party,
            body_complete=row.projection.body_mode == "full",
            score=row.projection.score,
            at=row.projection.timeline_at,
            identity=row.projection.content_id,
        ),
    )


def matching_member(
    member: PublicationListingMember,
    filters: PublicReadingFilters,
    *,
    now: datetime,
    topic_tags: tuple[str, ...] = (),
    released: bool = True,
) -> bool:
    p = member.projection
    return (
        p.visibility == "public"
        and p.eligible
        and (not released or not p.selected or bool(p.visible_after and p.visible_after <= now))
        and (
            filters.channel == "all"
            or filters.channel == p.channel
            or (filters.channel == "firstParty" and p.first_party)
        )
        and (filters.category is None or filters.category == p.category)
        and (filters.source_key is None or filters.source_key == p.source_key)
        and (filters.tag is None or filters.tag in member.subject_tags)
        and (not topic_tags or bool(set(topic_tags).intersection(member.subject_tags)))
    )


@dataclass(slots=True)
class _FactSummary:
    count: int = 0
    sources: set[str] = field(default_factory=set)
    first_report_at: datetime | None = None
    selected_anchor: datetime | None = None
    representative: PublicationListingMember | None = None

    def add(self, row: PublicationListingMember) -> None:
        p = row.projection
        self.count += 1
        self.sources.add(p.source_key)
        self.first_report_at = min(self.first_report_at or p.timeline_at, p.timeline_at)
        if p.selected:
            self.selected_anchor = min(self.selected_anchor or p.sort_at, p.sort_at)
            self.representative = pick_representative(
                [self.representative, row] if self.representative else [row]
            )

    def development(self, fact_id: UUID) -> PublicDevelopmentView:
        assert self.representative and self.selected_anchor
        p = self.representative.projection
        return PublicDevelopmentView(
            fact_id=fact_id,
            title=p.title,
            anchor_at=self.selected_anchor,
            report_count=self.count,
            representative=public_item(p, icon_url=self.representative.icon_url),
        )


def build_timeline_cards(
    members: Iterable[PublicationListingMember],
    *,
    filters: PublicReadingFilters,
    now: datetime,
    topic_tags: tuple[str, ...] = (),
) -> list[PublicTimelineCardView]:
    # One permitted representative and counters per fact, never archive bodies or member lists.
    groups: dict[str, dict[UUID, _FactSummary]] = {}
    standalone: list[PublicTimelineCardView] = []
    start = now - timedelta(days=1 if filters.window == "24h" else 7)
    for row in members:
        if not matching_member(row, filters, now=now, topic_tags=topic_tags):
            continue
        p = row.projection
        if p.fact_id is None:
            if p.selected and start <= p.sort_at <= now:
                standalone.append(
                    PublicTimelineCardView(
                        key=f"item:{p.content_id}",
                        anchor_at=p.sort_at,
                        item=public_item(p, icon_url=row.icon_url),
                        group=None,
                    )
                )
            continue
        key = f"story:{p.event_id}" if p.event_id else f"fact:{p.fact_id}"
        groups.setdefault(key, {}).setdefault(p.fact_id, _FactSummary()).add(row)
    cards = standalone
    for key, facts in groups.items():
        selected = {
            identity: fact for identity, fact in facts.items() if fact.representative is not None
        }
        if not selected:
            continue
        main = min(facts, key=lambda identity: (facts[identity].first_report_at, str(identity)))
        first = min(
            selected, key=lambda identity: (selected[identity].selected_anchor, str(identity))
        )
        latest = max(
            selected, key=lambda identity: (selected[identity].selected_anchor, str(identity))
        )
        main_rep = selected.get(main, selected[first]).representative
        assert main_rep
        anchor = selected[latest].selected_anchor
        assert anchor is not None
        if not start <= anchor <= now:
            continue
        report_count = sum(fact.count for fact in selected.values())
        group = PublicReadingGroupView(
            fact_id=main,
            event_id=main_rep.projection.event_id,
            additional_source_count=max(0, len(facts[main].sources) - 1),
            report_count=report_count,
            development_count=len(selected),
            latest_development=selected[latest].development(latest) if latest != main else None,
        )
        cards.append(
            PublicTimelineCardView(
                key=key,
                anchor_at=anchor,
                item=public_item(main_rep.projection, icon_url=main_rep.icon_url),
                group=group if report_count > 1 or len(selected) > 1 else None,
            )
        )
    return sorted(cards, key=lambda card: (card.anchor_at, card.key), reverse=True)


def _topic_tags(filters: PublicReadingFilters) -> tuple[str, ...]:
    if filters.topic:
        from publication.topics import topic_match_tags_for_slug

        tags = topic_match_tags_for_slug(filters.topic)
        if tags is None:
            raise ApplicationError("resource_not_found")
        return tags
    return ()


def timeline_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    filters: PublicReadingFilters,
    now: datetime,
    limit: int = 20,
    cursor: str | None = None,
    public_categories: tuple[Category, ...] = (),
) -> PublicTimelinePage:
    if now.utcoffset() is None or not 1 <= limit <= 40:
        raise ApplicationError("invalid_publication_input")
    scope = {
        "owner": owner_id,
        "type": "timeline",
        **filters.model_dump(),
        "public_categories": tuple(sorted(set(public_categories))),
    }
    tags = _topic_tags(filters)
    refresh_at: datetime | None = None

    def stream() -> Iterable[PublicationListingMember]:
        nonlocal refresh_at
        for member in iter_current_publications_in_transaction(
            session, owner_id=owner_id, now=now, public_categories=public_categories
        ):
            p = member.projection
            if (
                matching_member(member, filters, now=now, topic_tags=tags, released=False)
                and p.selected
                and p.visible_after
                and p.visible_after > now
            ):
                refresh_at = min(refresh_at or p.visible_after, p.visible_after)
            yield member

    cards = build_timeline_cards(stream(), filters=filters, now=now, topic_tags=tags)
    day_counts: dict[str, int] = {}
    for card in cards:
        day = card.anchor_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        day_counts[day] = day_counts.get(day, 0) + 1
    if cursor:
        data = decode_cursor(cursor, scope)
        try:
            anchor, key = datetime.fromisoformat(data["anchor"]), str(data["key"])
            if anchor.utcoffset() is None or anchor > now:
                raise ValueError("invalid timeline anchor")
        except (ValueError, KeyError, TypeError) as error:
            raise ApplicationError("invalid_publication_cursor") from error
        cards = [card for card in cards if (card.anchor_at, card.key) < (anchor, key)]
    page = cards[:limit]
    return PublicTimelinePage(
        filters=filters,
        cards=page,
        next_cursor=encode_cursor(scope, {"anchor": page[-1].anchor_at, "key": page[-1].key})
        if len(cards) > limit
        else None,
        refresh_at=refresh_at,
        day_counts=day_counts,
        snapshot_at=now,
    )


def _requested_offset(*, cursor: str | None, scope: dict[str, object]) -> int:
    if cursor is None:
        return 0
    data = decode_cursor(cursor, scope)
    return _expansion_offset(
        cursor=cursor, expected_revision=None, scope=scope, revision=str(data.get("revision", ""))
    )


def _expansion_offset(
    *, cursor: str | None, expected_revision: str | None, scope: dict[str, object], revision: str
) -> int:
    offset = 0
    if cursor:
        data = decode_cursor(cursor, scope)
        try:
            offset = data["offset"]
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise ValueError("invalid group offset")
        except (ValueError, KeyError, TypeError) as error:
            raise ApplicationError("invalid_publication_cursor") from error
        expected_revision = data.get("revision")
    if expected_revision is not None and expected_revision != revision:
        raise ApplicationError("publication_revision_conflict")
    return offset


def fact_reports_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    fact_id: UUID,
    filters: PublicReadingFilters,
    now: datetime,
    limit: int = 20,
    cursor: str | None = None,
    public_categories: tuple[Category, ...] = (),
    revision: str | None = None,
) -> PublicFactReportsPage:
    if not 1 <= limit <= 100:
        raise ApplicationError("invalid_publication_input")
    scope = {
        "owner": owner_id,
        "type": "fact-reports",
        "fact": fact_id,
        **filters.model_dump(),
        "public_categories": tuple(sorted(set(public_categories))),
    }
    offset = _requested_offset(cursor=cursor, scope=scope)
    page: list[PublicationListingMember] = []
    total, digest = 0, sha256()
    tags = _topic_tags(filters)
    for row in iter_current_publications_in_transaction(
        session, owner_id=owner_id, now=now, order="timeline", public_categories=public_categories
    ):
        if row.projection.fact_id != fact_id or not matching_member(
            row, filters, now=now, topic_tags=tags
        ):
            continue
        digest.update(fingerprint(row.projection.model_dump(mode="json")).encode())
        if offset <= total < offset + limit:
            page.append(row)
        total += 1
    if not total:
        raise ApplicationError("resource_not_found")
    current_revision = digest.hexdigest()[:20]
    _expansion_offset(
        cursor=cursor, expected_revision=revision, scope=scope, revision=current_revision
    )
    return PublicFactReportsPage(
        fact_id=fact_id,
        revision=current_revision,
        reports=[public_item(row.projection, icon_url=row.icon_url) for row in page],
        next_cursor=encode_cursor(scope, {"offset": offset + limit, "revision": current_revision})
        if offset + limit < total
        else None,
    )


def developments_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    event_id: UUID,
    filters: PublicReadingFilters,
    now: datetime,
    limit: int = 20,
    cursor: str | None = None,
    public_categories: tuple[Category, ...] = (),
    revision: str | None = None,
) -> PublicDevelopmentsPage:
    if not 1 <= limit <= 100:
        raise ApplicationError("invalid_publication_input")
    by_fact: dict[UUID, _FactSummary] = {}
    digest = sha256()
    tags = _topic_tags(filters)
    for row in iter_current_publications_in_transaction(
        session, owner_id=owner_id, now=now, public_categories=public_categories
    ):
        if (
            row.projection.event_id != event_id
            or not row.projection.fact_id
            or not matching_member(row, filters, now=now, topic_tags=tags)
        ):
            continue
        digest.update(fingerprint(row.projection.model_dump(mode="json")).encode())
        by_fact.setdefault(row.projection.fact_id, _FactSummary()).add(row)
    developments = [
        fact.development(identity) for identity, fact in by_fact.items() if fact.representative
    ]
    if not developments:
        raise ApplicationError("resource_not_found")
    developments.sort(key=lambda item: (item.anchor_at, str(item.fact_id)), reverse=True)
    current_revision = digest.hexdigest()[:20]
    scope = {
        "owner": owner_id,
        "type": "developments",
        "event": event_id,
        **filters.model_dump(),
        "public_categories": tuple(sorted(set(public_categories))),
    }
    offset = _expansion_offset(
        cursor=cursor, expected_revision=revision, scope=scope, revision=current_revision
    )
    return PublicDevelopmentsPage(
        event_id=event_id,
        revision=current_revision,
        developments=developments[offset : offset + limit],
        next_cursor=encode_cursor(scope, {"offset": offset + limit, "revision": current_revision})
        if offset + limit < len(developments)
        else None,
    )
