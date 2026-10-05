"""Calendar history and adjacent editions use the report domain's current fixed DTOs."""

from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from itertools import islice
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from publication.edition_schemas import (
    EditionKind,
    PublicDailyCalendarView,
    PublicEditionCatalogueView,
    PublicEditionIndexView,
    PublicEditionNavigationView,
)
from publication.publication_models import PublicationRecord
from publication.reading import PublicationReadingService
from publication.schemas import Category
from reports.edition_reading import (
    iter_current_editions_in_transaction,
    load_current_edition_in_transaction,
)
from reports.edition_schemas import EditionDetailView


def _index(
    session: Session,
    view: EditionDetailView,
    *,
    owner_id: UUID,
    now: datetime,
    indexing_enabled: bool,
    public_categories: tuple[Category, ...] = (),
) -> PublicEditionIndexView | None:
    if not view.valid or not view.content:
        raise ValueError("only current validated editions may enter the public calendar")
    reader = PublicationReadingService(
        session, indexing_enabled=indexing_enabled, public_categories=public_categories
    )
    references = {entry.content_id: entry for entry in view.content.entries}
    rows = list(
        session.scalars(
            select(PublicationRecord).where(
                PublicationRecord.owner_id == owner_id,
                PublicationRecord.content_id.in_(references),
            )
        )
    )
    live = reader._live(owner_id=owner_id, rows=rows, now=now)
    if public_categories and (
        len(live) != len(references)
        or any(
            projection.content_version_id != references[identity].content_version_id
            for identity, (projection, _) in live.items()
        )
    ):
        return None
    return PublicEditionIndexView(
        kind=view.kind,
        key=view.key,
        title=view.content.title,
        revision=view.revision,
        created_at=view.created_at,
        reading_url=f"/reports/{view.kind}/{view.key}",
        indexable=indexing_enabled
        and bool(references)
        and len(live) == len(references)
        and all(
            projection.indexable
            and projection.content_version_id == references[identity].content_version_id
            for identity, (projection, _) in live.items()
        ),
    )


def _indexes(
    session: Session,
    views: Iterable[EditionDetailView],
    *,
    owner_id: UUID,
    now: datetime,
    indexing_enabled: bool,
    public_categories: tuple[Category, ...],
) -> Iterator[PublicEditionIndexView]:
    for view in views:
        index = _index(
            session,
            view,
            owner_id=owner_id,
            now=now,
            indexing_enabled=indexing_enabled,
            public_categories=public_categories,
        )
        if index is not None:
            yield index


def catalogue_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    kind: EditionKind,
    now: datetime,
    before_key: str | None = None,
    limit: int = 20,
    indexing_enabled: bool = False,
    public_categories: tuple[Category, ...] = (),
) -> PublicEditionCatalogueView:
    if not 1 <= limit <= 50:
        raise ValueError("public catalogue limit is 1..50")
    entries = list(
        islice(
            _indexes(
                session,
                iter_current_editions_in_transaction(
                    session, owner_id=owner_id, kind=kind, now=now, before_key=before_key
                ),
                owner_id=owner_id,
                now=now,
                indexing_enabled=indexing_enabled,
                public_categories=public_categories,
            ),
            limit + 1,
        )
    )
    return PublicEditionCatalogueView(
        kind=kind,
        entries=entries[:limit],
        next_before_key=entries[limit - 1].key if len(entries) > limit else None,
    )


def navigation_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    kind: EditionKind,
    key: str,
    now: datetime,
    indexing_enabled: bool = False,
    public_categories: tuple[Category, ...] = (),
) -> PublicEditionNavigationView:
    current = load_current_edition_in_transaction(
        session, owner_id=owner_id, kind=kind, key=key, now=now
    )
    previous = next(
        _indexes(
            session,
            iter_current_editions_in_transaction(
                session, owner_id=owner_id, kind=kind, now=now, before_key=key
            ),
            owner_id=owner_id,
            now=now,
            indexing_enabled=indexing_enabled,
            public_categories=public_categories,
        ),
        None,
    )
    next_view = next(
        _indexes(
            session,
            iter_current_editions_in_transaction(
                session, owner_id=owner_id, kind=kind, now=now, after_key=key, ascending=True
            ),
            owner_id=owner_id,
            now=now,
            indexing_enabled=indexing_enabled,
            public_categories=public_categories,
        ),
        None,
    )
    return PublicEditionNavigationView(
        current=_index(
            session,
            current,
            owner_id=owner_id,
            now=now,
            indexing_enabled=indexing_enabled,
            public_categories=public_categories,
        )
        if current
        else None,
        previous=previous,
        next=next_view,
    )


def daily_calendar_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    month: str,
    now: datetime,
    indexing_enabled: bool = False,
    public_categories: tuple[Category, ...] = (),
) -> PublicDailyCalendarView:
    if len(month) != 7 or month[4] != "-":
        raise ValueError("calendar month must be YYYY-MM")
    start = date.fromisoformat(month + "-01")
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    entries = iter_current_editions_in_transaction(
        session,
        owner_id=owner_id,
        kind="daily",
        now=now,
        before_key=end.isoformat(),
        after_key=(start - timedelta(days=1)).isoformat(),
        ascending=True,
    )
    return PublicDailyCalendarView(
        month=month,
        entries=list(
            _indexes(
                session,
                entries,
                owner_id=owner_id,
                now=now,
                indexing_enabled=indexing_enabled,
                public_categories=public_categories,
            )
        ),
    )
