"""Caller-transaction publication reads for notification admission and final send checks."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import DateTime, cast, select
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from publication.notification_schemas import (
    SelectedNotificationCandidate,
    SelectedNotificationPage,
    WeeklySelectedSourceCount,
)
from publication.projection import fingerprint
from publication.publication_models import PublicationRecord
from publication.reading import PublicationReadingService, frozen_reference
from publication.schemas import ProjectionView
from publication.services import require_transaction


def notification_dedupe_key(*, content_id: UUID, fact_id: UUID | None) -> str:
    return f"fact:{fact_id}" if fact_id is not None else f"item:{content_id}"


def _candidate(projection: ProjectionView, now: datetime) -> SelectedNotificationCandidate | None:
    if (
        projection.visibility != "public"
        or not projection.eligible
        or not projection.selected
        or not projection.summary
        or not projection.selected_ready_at
        or not projection.visible_after
        or projection.visible_after > now
    ):
        return None
    # Deduplicate confirmed same-fact reports, never all progress inside the parent event.
    dedupe_key = notification_dedupe_key(
        content_id=projection.content_id, fact_id=projection.fact_id
    )
    data = {
        **frozen_reference(projection).model_dump(mode="json"),
        "selected_at": projection.selected_ready_at.isoformat(),
        "title": projection.title,
        "summary": projection.summary,
        "reading_url": f"/items/{projection.content_id}",
        "source_name": projection.source_name,
        "dedupe_key": dedupe_key,
        "silent": projection.silent,
    }
    return SelectedNotificationCandidate.model_validate({**data, "fingerprint": fingerprint(data)})


def list_selected_notification_candidates_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    enabled_at: datetime,
    now: datetime,
    after_content_id: UUID | None = None,
    limit: int = 100,
) -> SelectedNotificationPage:
    require_transaction(session)
    if (
        enabled_at.utcoffset() is None
        or now.utcoffset() is None
        or enabled_at > now
        or not 1 <= limit <= 100
    ):
        raise ApplicationError("invalid_publication_input")
    query = (
        select(PublicationRecord)
        .where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.selected.is_(True),
            PublicationRecord.eligible.is_(True),
            PublicationRecord.visibility == "public",
            PublicationRecord.visible_after <= now,
            cast(PublicationRecord.data["selected_ready_at"].astext, DateTime(timezone=True))
            >= enabled_at,
        )
        .order_by(PublicationRecord.content_id)
    )
    if after_content_id is not None:
        query = query.where(PublicationRecord.content_id > after_content_id)
    rows = list(session.scalars(query.limit(1000)))
    live = PublicationReadingService(session)._live(owner_id=owner_id, rows=rows, now=now)
    candidates = []
    consumed = 0
    for row in rows:
        consumed += 1
        value = live.get(row.content_id)
        candidate = _candidate(value[0], now) if value else None
        if candidate is not None and enabled_at <= candidate.selected_at <= now:
            candidates.append(candidate)
        if len(candidates) == limit:
            break
    more = consumed < len(rows) or len(rows) == 1000
    return SelectedNotificationPage(
        candidates=tuple(candidates),
        next_after_content_id=rows[consumed - 1].content_id if more and consumed else None,
    )


def load_selected_notification_candidate_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    publication_revision: int,
    now: datetime,
) -> SelectedNotificationCandidate | None:
    require_transaction(session)
    if now.utcoffset() is None or publication_revision < 1:
        raise ApplicationError("invalid_publication_input")
    projection = PublicationReadingService(session).projection_in_transaction(
        owner_id=owner_id, content_id=content_id, now=now
    )
    if projection is None or projection.publication_revision != publication_revision:
        return None
    return _candidate(projection, now)


def weekly_selected_source_counts_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> tuple[WeeklySelectedSourceCount, ...]:
    """Count current permitted selections by actual discovery, with bounded raw pages.

    Summary-only selections count, while withdrawn or unreadable fixed evidence
    does not. Counts are not derived from a model's selected flag alone. No body,
    title, model call, poll, transaction switch or mutable projection is emitted.
    """
    require_transaction(session)
    if now.utcoffset() is None:
        raise ValueError("weekly publication counts require an aware caller transaction")
    starts = now - timedelta(days=14)
    boundary = now - timedelta(days=7)
    discovered = cast(PublicationRecord.data["discovered_at"].astext, DateTime(timezone=True))
    query = (
        select(PublicationRecord)
        .where(
            PublicationRecord.owner_id == owner_id,
            PublicationRecord.selected.is_(True),
            PublicationRecord.visibility.in_(("public", "summary-only")),
            discovered >= starts,
            discovered <= now,
        )
        .order_by(PublicationRecord.content_id)
    )
    reader = PublicationReadingService(session)
    after = None
    counts: dict[str, list[int]] = {}
    while True:
        page_query = query.where(PublicationRecord.content_id > after) if after else query
        rows = list(session.scalars(page_query.limit(500)))
        for projection, _ in reader._live(owner_id=owner_id, rows=rows, now=now).values():
            if (
                not projection.selected
                or projection.visibility == "withdrawn"
                or not starts <= projection.discovered_at <= now
            ):
                continue
            counter = counts.setdefault(projection.source_key, [0, 0])
            counter[0 if projection.discovered_at >= boundary else 1] += 1
        if len(rows) < 500:
            break
        after = rows[-1].content_id
    return tuple(
        WeeklySelectedSourceCount(source_key=key, current_count=value[0], previous_count=value[1])
        for key, value in sorted(counts.items())
    )
