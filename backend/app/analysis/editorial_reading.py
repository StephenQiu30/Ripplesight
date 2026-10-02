"""Current completed editorial inputs; source pauses do not withdraw prior publications."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialRun, EditorialSource
from analysis.editorial_schemas import (
    EditorialPublicationIdPage,
    EditorialPublicationInputView,
    EditorialRunView,
    EditorialSourceView,
)
from analysis.editorial_services import EditorialService
from content.editorial_reading import editorial_discovery_in_transaction
from content.schemas import EventContentReadReference
from core.errors import ApplicationError


def load_editorial_publication_inputs_in_transaction(
    session: Session, *, owner_id: UUID, content_ids: tuple[UUID, ...], now: datetime
) -> dict[UUID, EditorialPublicationInputView]:
    if not session.in_transaction() or len(content_ids) > 1000:
        raise ValueError("editorial inputs require a bounded caller transaction")
    if not content_ids:
        return {}
    rows = session.execute(
        select(EditorialRun, EditorialSource)
        .join(EditorialContentState, EditorialContentState.current_run_id == EditorialRun.id)
        .join(
            EditorialSource,
            (EditorialSource.owner_id == EditorialRun.owner_id)
            & (EditorialSource.source_key == EditorialRun.source_key),
        )
        .where(
            EditorialContentState.owner_id == owner_id,
            EditorialContentState.content_id.in_(content_ids),
            EditorialRun.owner_id == owner_id,
            EditorialRun.manual_version == EditorialContentState.manual_version,
            EditorialRun.status == "complete",
        )
    ).all()
    result = {}
    service = EditorialService(session, clock=lambda: now)
    for run, source in rows:
        if run.result is None:
            continue
        try:
            material = service._load_material(run)
        except ApplicationError as error:
            if error.code == "editorial_material_unavailable":
                continue
            raise
        discovery = editorial_discovery_in_transaction(
            session, owner_id=owner_id, content_id=run.content_id
        )
        if discovery is None:
            continue
        quote = run.input_manifest.get("quote")
        quote_reference = (
            EventContentReadReference(
                content_id=UUID(quote["content_id"]),
                content_version_id=UUID(quote["content_version_id"]),
            )
            if quote is not None
            else None
        )
        result[run.content_id] = EditorialPublicationInputView(
            run=EditorialRunView.model_validate(run),
            source=EditorialSourceView.model_validate(
                {
                    "source_key": source.source_key,
                    "revision": source.revision,
                    **source.configuration,
                }
            ),
            material=material,
            timeline_at=discovery.timeline_at,
            first_received_at=discovery.first_received_at,
            backfill=discovery.backfill,
            quote_reference=quote_reference,
        )
    return result


def scan_current_editorial_publication_ids_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    limit: int = 100,
    after: UUID | None = None,
    source_key: str | None = None,
) -> EditorialPublicationIdPage:
    if not session.in_transaction() or not 1 <= limit <= 1000:
        raise ValueError("editorial scan requires a bounded caller transaction")
    query = (
        select(EditorialContentState.content_id)
        .where(EditorialContentState.owner_id == owner_id)
        .order_by(EditorialContentState.content_id)
        .limit(limit + 1)
    )
    if after is not None:
        query = query.where(EditorialContentState.content_id > after)
    if source_key is not None:
        query = query.join(EditorialRun, EditorialContentState.current_run_id == EditorialRun.id)
        query = query.where(
            EditorialRun.owner_id == owner_id, EditorialRun.source_key == source_key
        )
    ids = tuple(session.scalars(query))
    return EditorialPublicationIdPage(
        content_ids=ids[:limit], next_after=ids[limit - 1] if len(ids) > limit else None
    )
