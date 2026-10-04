"""Stored source inputs and completed editorial evidence, with no model prerequisite."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialRun, EditorialSource
from analysis.editorial_schemas import (
    EditorialMaterial,
    EditorialPublicationIdPage,
    EditorialPublicationInputView,
    EditorialRunView,
    EditorialSourceView,
)
from analysis.editorial_services import EditorialService
from content.editorial_reading import (
    editorial_discovery_in_transaction,
    frozen_editorial_content_in_transaction,
    load_latest_editorial_content_in_transaction,
    scan_editorial_content_ids_in_transaction,
)
from content.observation_inputs import freeze_observation_inputs_in_transaction
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
                observation_id=UUID(quote["observation_id"])
                if quote.get("observation_id")
                else None,
            )
            if quote is not None
            else None
        )
        result[run.content_id] = EditorialPublicationInputView(
            observation_id=UUID(run.input_manifest["main"]["observation_id"])
            if run.input_manifest.get("main")
            else None,
            input_observation_ids=tuple(
                UUID(i)
                for field in ("main", "quote")
                for i in run.input_manifest.get(field, {}).get("input_observation_ids", [])
            ),
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
    originals = load_latest_editorial_content_in_transaction(
        session,
        owner_id=owner_id,
        content_ids=tuple(identity for identity in content_ids if identity not in result),
        now=now,
    )
    sources = {
        source.source_key: source
        for source in session.scalars(
            select(EditorialSource).where(
                EditorialSource.owner_id == owner_id,
                EditorialSource.source_key.in_({item.source_key for item in originals.values()}),
            )
        )
    }
    for identity, item in originals.items():
        source = sources.get(item.source_key)
        version = item.observation.content_version
        discovery = editorial_discovery_in_transaction(
            session, owner_id=owner_id, content_id=identity
        )
        if source is None or version is None or discovery is None:
            continue
        profile = EditorialSourceView.model_validate(
            {"source_key": source.source_key, "revision": source.revision, **source.configuration}
        )
        body_complete = version.text_scope.value == "full"
        material = EditorialMaterial(
            content_id=identity,
            content_version_id=version.id,
            source_key=item.source_key,
            source_name=profile.name,
            source_kind=profile.source_kind,
            tier=profile.tier,
            title=version.title or "",
            body=version.body or "",
            excerpt=(version.body or "") if version.text_scope.value == "summary" else "",
            body_complete=body_complete,
            url=item.observation.canonical_url or item.observation.final_url or "",
            author=item.observation.author_external_id,
            published_at=item.observation.published_at,
            discovered_at=discovery.first_received_at,
            first_party=profile.first_party,
            source_tags=profile.tags,
        )
        result[identity] = EditorialPublicationInputView(
            observation_id=item.observation.id,
            input_observation_ids=freeze_observation_inputs_in_transaction(
                session, owner_id=owner_id, observation_ids=(item.observation.id,), now=now
            ),
            run=None,
            source=profile,
            material=material,
            timeline_at=discovery.timeline_at,
            first_received_at=discovery.first_received_at,
            backfill=discovery.backfill,
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
    ids = tuple(
        sorted(
            set(session.scalars(query))
            | set(
                scan_editorial_content_ids_in_transaction(
                    session,
                    owner_id=owner_id,
                    source_key=source_key,
                    after=after,
                    limit=limit + 1,
                )
            )
        )
    )
    return EditorialPublicationIdPage(
        content_ids=ids[:limit], next_after=ids[limit - 1] if len(ids) > limit else None
    )


def load_frozen_editorial_publication_input_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    observation_id: UUID,
    now: datetime,
) -> EditorialPublicationInputView | None:
    """Exact selected original and its fixed current input closure; an alias cannot rescue it."""
    reference = EventContentReadReference(
        content_id, content_version_id, observation_id=observation_id
    )
    item = frozen_editorial_content_in_transaction(
        session, owner_id=owner_id, reference=reference, now=now
    )
    if item is None or item.observation.content_version is None:
        return None
    source = session.get(EditorialSource, (owner_id, item.source_key))
    if source is None:
        return None
    try:
        closure = freeze_observation_inputs_in_transaction(
            session, owner_id=owner_id, observation_ids=(observation_id,), now=now
        )
    except ApplicationError:
        return None
    current = load_editorial_publication_inputs_in_transaction(
        session, owner_id=owner_id, content_ids=(content_id,), now=now
    ).get(content_id)
    if (
        current is not None
        and current.observation_id == observation_id
        and current.material.content_version_id == content_version_id
    ):
        return current
    profile = EditorialSourceView.model_validate(
        {"source_key": source.source_key, "revision": source.revision, **source.configuration}
    )
    version = item.observation.content_version
    discovery = editorial_discovery_in_transaction(
        session, owner_id=owner_id, content_id=content_id
    )
    if discovery is None:
        return None
    return EditorialPublicationInputView(
        observation_id=observation_id,
        input_observation_ids=closure,
        run=None,
        source=profile,
        material=EditorialMaterial(
            content_id=content_id,
            content_version_id=content_version_id,
            source_key=item.source_key,
            source_name=profile.name,
            source_kind=profile.source_kind,
            tier=profile.tier,
            title=version.title or "",
            body=version.body or "",
            excerpt=(version.body or "") if version.text_scope.value == "summary" else "",
            body_complete=version.text_scope.value == "full",
            url=item.observation.canonical_url or item.observation.final_url or "",
            author=item.observation.author_external_id,
            published_at=item.observation.published_at,
            discovered_at=discovery.first_received_at,
            first_party=profile.first_party,
            source_tags=profile.tags,
        ),
        timeline_at=discovery.timeline_at,
        first_received_at=discovery.first_received_at,
        backfill=discovery.backfill,
    )
