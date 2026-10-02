from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from reports.edition_models import ReportEdition
from reports.edition_rules import EditionKind, period_window
from reports.edition_schemas import EditionDetailView, EditionIndexingChangeView
from reports.edition_services import EditionService


def load_current_edition_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    kind: EditionKind,
    key: str | None = None,
    now: datetime,
) -> EditionDetailView | None:
    """Revalidate a completed edition inside the caller's read transaction."""
    if not session.in_transaction():
        raise RuntimeError("edition reading requires caller transaction")
    if key is not None:
        period_window(kind, key)
    if key is None:
        return next(
            iter_current_editions_in_transaction(session, owner_id=owner_id, kind=kind, now=now),
            None,
        )
    row = session.scalar(
        select(ReportEdition)
        .where(
            ReportEdition.owner_id == owner_id,
            ReportEdition.kind == kind,
            ReportEdition.period_key == key,
        )
        .order_by(ReportEdition.revision.desc())
        .limit(1)
    )
    # A queued/failed/newer revision cannot make an earlier completed draft current again.
    if row is None or row.status != "complete" or row.created_at > now:
        return None
    view = EditionService(session, clock=lambda: now)._view(row)
    return view if view.valid else None


def iter_current_editions_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    kind: EditionKind,
    now: datetime,
    before_key: str | None = None,
    after_key: str | None = None,
    ascending: bool = False,
) -> Iterator[EditionDetailView]:
    """Stream all distinct keys; return only the newest currently licensed revision of each."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("edition history requires an aware caller transaction")
    for key in (before_key, after_key):
        if key is not None:
            period_window(kind, key)
    query = (
        select(ReportEdition.period_key)
        .where(
            ReportEdition.owner_id == owner_id,
            ReportEdition.kind == kind,
            ReportEdition.created_at <= now,
        )
        .distinct()
    )
    if before_key is not None:
        query = query.where(ReportEdition.period_key < before_key)
    if after_key is not None:
        query = query.where(ReportEdition.period_key > after_key)
    query = query.order_by(
        ReportEdition.period_key.asc() if ascending else ReportEdition.period_key.desc()
    )
    cursor = None
    while True:
        page = query
        if cursor is not None:
            page = page.where(
                ReportEdition.period_key > cursor
                if ascending
                else ReportEdition.period_key < cursor
            )
        keys = session.scalars(page.limit(500)).all()
        for key in keys:
            view = load_current_edition_in_transaction(
                session, owner_id=owner_id, kind=kind, key=key, now=now
            )
            if view is not None:
                yield view
        if len(keys) < 500:
            return
        cursor = keys[-1]


def list_current_editions_in_transaction(
    session: Session, *, owner_id: UUID, kind: EditionKind, limit: int = 20, now: datetime
) -> list[EditionDetailView]:
    if not session.in_transaction() or not 1 <= limit <= 50:
        raise ValueError("edition listing requires a bounded caller transaction")
    from itertools import islice

    return list(
        islice(
            iter_current_editions_in_transaction(session, owner_id=owner_id, kind=kind, now=now),
            limit,
        )
    )


def list_edition_indexing_changes_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    after: tuple[datetime, UUID],
    until: datetime,
    limit: int = 500,
) -> list[EditionIndexingChangeView]:
    """Continuous immutable edition identities; the newest revision is revalidated live."""
    if (
        not session.in_transaction()
        or after[0].utcoffset() is None
        or until.utcoffset() is None
        or not 1 <= limit <= 500
    ):
        raise ValueError("edition indexing requires aware dates and a bounded caller transaction")
    rows = session.scalars(
        select(ReportEdition)
        .where(
            ReportEdition.owner_id == owner_id,
            ReportEdition.created_at <= until,
            tuple_(ReportEdition.created_at, ReportEdition.id) > after,
        )
        .order_by(ReportEdition.created_at, ReportEdition.id)
        .limit(limit)
    ).all()
    current: dict[tuple[str, str], EditionDetailView | None] = {}
    result = []
    for row in rows:
        pair = (row.kind, row.period_key)
        if pair not in current:
            current[pair] = load_current_edition_in_transaction(
                session,
                owner_id=owner_id,
                kind=cast(EditionKind, row.kind),
                key=row.period_key,
                now=until,
            )
        result.append(
            EditionIndexingChangeView(
                edition_id=row.id,
                kind=row.kind,
                key=row.period_key,
                changed_at=row.created_at,
                public=current[pair] is not None,
            )
        )
    return result
