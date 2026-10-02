"""Caller-transaction, guarded fixed publication DTOs for groups and public topics."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.orm import Session

from publication.publication_models import PublicationRecord
from publication.reading import (
    PublicationReadingService,
    _fixed_body_in_transaction,
    editorial_subject_tags,
)
from publication.schemas import ProjectionView
from publication.services import require_transaction


@dataclass(frozen=True, slots=True)
class PublicationListingMember:
    projection: ProjectionView
    subject_tags: tuple[str, ...]
    permitted_body: str = ""
    body_format: Literal["text", "html", "markdown"] = "text"
    icon_url: str | None = None


def iter_current_publications_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    order: Literal["identity", "timeline"] = "identity",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    source_key: str | None = None,
    include_body: bool = False,
    indexing_enabled: bool = False,
) -> Iterator[PublicationListingMember]:
    require_transaction(session)
    if now.utcoffset() is None:
        raise ValueError("publication listing needs an aware bounded caller transaction")
    query = select(PublicationRecord).where(
        PublicationRecord.owner_id == owner_id,
        PublicationRecord.visibility == "public",
        PublicationRecord.eligible.is_(True),
    )
    query = (
        query.order_by(PublicationRecord.content_id)
        if order == "identity"
        else query.order_by(
            PublicationRecord.timeline_at.desc(), PublicationRecord.content_id.desc()
        )
    )
    if starts_at is not None:
        query = query.where(PublicationRecord.timeline_at >= starts_at)
    if ends_at is not None:
        query = query.where(
            PublicationRecord.timeline_at <= ends_at, PublicationRecord.updated_at <= ends_at
        )
    if source_key is not None:
        query = query.where(PublicationRecord.source_key == source_key)
    reader, after = PublicationReadingService(session, indexing_enabled=indexing_enabled), None
    after_timeline: datetime | None = None
    while True:
        page_query = query
        if after:
            page_query = (
                query.where(PublicationRecord.content_id > after)
                if order == "identity"
                else query.where(
                    tuple_(PublicationRecord.timeline_at, PublicationRecord.content_id)
                    < tuple_(literal(after_timeline), literal(after))
                )
            )
        rows = list(session.scalars(page_query.limit(500)))
        live = reader._live(owner_id=owner_id, rows=rows, now=now)
        for record in rows:
            value = live.get(record.content_id)
            if value is None:
                continue
            projection, snapshot = value
            if projection.visibility != "public" or not projection.eligible:
                continue
            subject_tags = editorial_subject_tags(snapshot)
            body = ""
            body_format: Literal["text", "html", "markdown"] = "text"
            if (
                include_body
                and projection.selected
                and projection.body_mode == "full"
                and projection.visible_after
                and projection.visible_after <= now
            ):
                body, body_format, _, _ = _fixed_body_in_transaction(
                    session, owner_id=owner_id, snapshot=snapshot, now=now
                )
            yield PublicationListingMember(
                projection,
                subject_tags,
                body,
                body_format,
                reader.source_icon_url(projection.source_key),
            )
        if len(rows) < 500:
            return
        after = rows[-1].content_id
        after_timeline = rows[-1].timeline_at


def list_current_publications_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> tuple[PublicationListingMember, ...]:
    return tuple(iter_current_publications_in_transaction(session, owner_id=owner_id, now=now))
