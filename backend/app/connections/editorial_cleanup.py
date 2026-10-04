"""Remove withdrawn editorial payload copies inside the content cleanup transaction."""

from uuid import UUID

from sqlalchemy import ColumnElement, delete, or_, select
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceRun


def purge_editorial_material_receipts_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    observation_ids: tuple[UUID, ...] = (),
) -> None:
    if (
        not session.in_transaction()
        or len(content_version_ids) > 1000
        or len(observation_ids) > 1000
    ):
        raise ValueError("editorial cleanup requires a bounded caller transaction")
    if not content_version_ids and not observation_ids:
        return
    selected = or_(
        EditorialSourceMaterialReceipt.content_version_id.in_(content_version_ids),
        EditorialSourceMaterialReceipt.observation_id.in_(observation_ids),
    )
    receipts = session.scalars(
        select(EditorialSourceMaterialReceipt)
        .where(
            EditorialSourceMaterialReceipt.owner_id == owner_id,
            selected,
        )
        .with_for_update()
    ).all()
    affected: dict[UUID, set[str]] = {}
    for receipt in receipts:
        affected.setdefault(receipt.run_id, set()).add(receipt.identity_key)
    # A receipt can move to a later run. The original checkpoint still owns the
    # withdrawn input, so inspect its exact references independently of receipts.
    run_matches: list[ColumnElement[bool]] = (
        [EditorialSourceRun.id.in_(affected)] if affected else []
    )
    for observation_id in observation_ids:
        run_matches.extend(
            (
                EditorialSourceRun.prepared_page.contains(
                    {"_body_phase": {"targets": [{"feed_observation_id": str(observation_id)}]}}
                ),
                EditorialSourceRun.prepared_page.contains(
                    {"_body_phase": {"completed_observation_ids": [str(observation_id)]}}
                ),
            )
        )
    for version_id in content_version_ids:
        run_matches.append(
            EditorialSourceRun.prepared_page.contains(
                {"_body_phase": {"targets": [{"expected_content_version_id": str(version_id)}]}}
            )
        )
    if run_matches:
        runs = session.scalars(
            select(EditorialSourceRun)
            .where(
                EditorialSourceRun.owner_id == owner_id,
                EditorialSourceRun.prepared_page.is_not(None),
                or_(*run_matches),
            )
            .with_for_update()
        )
        for run in runs:
            assert run.prepared_page is not None
            page = dict(run.prepared_page)
            if "_body_phase" in page:
                # A durable body boundary must not resume or repeat a request
                # after one of its frozen inputs is physically withdrawn.
                run.prepared_page = None
                run.status = "failed"
                run.failure_code = "editorial_material_unavailable"
                continue
            materials = page.get("materials")
            if isinstance(materials, list):
                page["materials"] = [
                    material
                    for material in materials
                    if isinstance(material, dict)
                    and material.get("identity_key") not in affected[run.id]
                ]
            run.prepared_page = page
    session.execute(
        delete(EditorialSourceMaterialReceipt).where(
            EditorialSourceMaterialReceipt.owner_id == owner_id,
            selected,
        )
    )
