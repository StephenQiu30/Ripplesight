"""Live, fixed editorial grouping eligibility; publication visibility is a separate gate."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialRun
from analysis.editorial_reading import load_editorial_publication_inputs_in_transaction
from analysis.editorial_services import _fingerprint
from analysis.event_schemas import EditorialEventInput, EditorialEventInputPage
from content.report_reading import report_inputs_readable_in_transaction


def list_editorial_event_inputs_in_transaction(
    session: Session,
    *,
    since: datetime,
    now: datetime,
    version_ids: tuple[UUID, ...] | None = None,
    after: tuple[UUID, UUID] | None = None,
    limit: int = 1000,
) -> EditorialEventInputPage:
    """Bound raw keyset consumption; expired/withdrawn items never produce evidence."""
    if (
        not session.in_transaction()
        or since.utcoffset() is None
        or now.utcoffset() is None
        or since > now
        or not 1 <= limit <= 2000
        or (version_ids is not None and len(version_ids) > 4000)
    ):
        raise ValueError("editorial events require bounded aware caller transaction")
    if version_ids == ():
        return EditorialEventInputPage((), None)
    query = (
        select(EditorialContentState.owner_id, EditorialContentState.content_id)
        .join(EditorialRun, EditorialRun.id == EditorialContentState.current_run_id)
        .where(
            EditorialRun.owner_id == EditorialContentState.owner_id,
            EditorialRun.status == "complete",
            EditorialRun.stages == "all",
            EditorialRun.manual_version == EditorialContentState.manual_version,
        )
        .order_by(EditorialContentState.owner_id, EditorialContentState.content_id)
        .limit(limit + 1)
    )
    if version_ids is not None:
        query = query.where(EditorialRun.content_version_id.in_(version_ids))
    if after is not None:
        query = query.where(
            tuple_(EditorialContentState.owner_id, EditorialContentState.content_id) > after
        )
    rows = session.execute(query).all()
    page = rows[:limit]
    owners: dict[UUID, list[UUID]] = {}
    for owner_id, content_id in page:
        owners.setdefault(owner_id, []).append(content_id)
    result = []
    for owner_id, ids in owners.items():
        # The content helper validates every frozen input and quoted Evidence permission.
        for offset in range(0, len(ids), 1000):
            inputs = load_editorial_publication_inputs_in_transaction(
                session, owner_id=owner_id, content_ids=tuple(ids[offset : offset + 1000]), now=now
            )
            for item in inputs.values():
                run, material = item.run, item.material
                if run is None:
                    continue
                row = session.get(EditorialRun, run.id)
                if (
                    row is None
                    or row.stages != "all"
                    or run.result is None
                    or run.result.relevance != "pass"
                    or item.backfill is True
                    or item.timeline_at < since
                    or item.timeline_at > now
                    or _fingerprint(material.model_dump(mode="json")) != row.input_fingerprint
                ):
                    continue
                quotes = row.input_manifest.get("quote")
                fixed = (
                    run.content_version_id,
                    *((UUID(quotes["content_version_id"]),) if quotes else ()),
                )
                if not report_inputs_readable_in_transaction(
                    session,
                    owner_id=owner_id,
                    content_version_ids=fixed,
                    observation_ids=item.input_observation_ids,
                    now=now,
                ):
                    continue
                result_view = run.result
                # Composite material stays in analysis for later mention/edition handling.
                if result_view.structure is not None and result_view.structure.scope == "composite":
                    continue
                writing = result_view.writing
                title = writing.title_zh.strip() if writing else ""
                if not title:
                    title = material.title.strip()
                if not title:
                    continue
                # A human writing override invalidates the old model frame, as upstream does.
                frame = (
                    result_view.structure.fact.model_dump(
                        mode="json", by_alias=True, exclude={"title"}
                    )
                    if not result_view.manual
                    and result_view.structure is not None
                    and result_view.structure.fact is not None
                    else None
                )
                result.append(
                    EditorialEventInput(
                        observation_id=item.observation_id,
                        input_observation_ids=item.input_observation_ids,
                        owner_id=owner_id,
                        content_id=run.content_id,
                        content_version_id=run.content_version_id,
                        source_key=run.source_key,
                        title=title,
                        summary=writing.summary_zh if writing else None,
                        raw_title=material.title,
                        raw_body=material.body,
                        first_seen_at=item.timeline_at,
                        first_seen_basis="published" if material.published_at else "discovered",
                        selected=result_view.selected,
                        fact_frame=frame,
                        provenance_fingerprint=_fingerprint(
                            {
                                "run_id": run.id,
                                "manual_version": run.manual_version,
                                "source_revision": run.source_revision,
                                "input_fingerprint": row.input_fingerprint.hex(),
                                "result": result_view.model_dump(mode="json"),
                            }
                        ).hex(),
                    )
                )
    result.sort(key=lambda item: (item.owner_id, item.content_id))
    next_after = (page[-1].owner_id, page[-1].content_id) if len(rows) > limit else None
    return EditorialEventInputPage(tuple(result), next_after)


def load_frozen_editorial_event_input_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    content_version_id: UUID,
    observation_id: UUID,
    provenance_fingerprint: str,
    now: datetime,
) -> EditorialEventInput | None:
    page = list_editorial_event_inputs_in_transaction(
        session,
        since=datetime.min.replace(tzinfo=now.tzinfo),
        now=now,
        version_ids=(content_version_id,),
    )
    return next(
        (
            item
            for item in page.items
            if item.owner_id == owner_id
            and item.content_id == content_id
            and item.content_version_id == content_version_id
            and item.observation_id == observation_id
            and item.provenance_fingerprint == provenance_fingerprint
        ),
        None,
    )
