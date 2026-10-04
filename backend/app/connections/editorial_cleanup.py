"""Remove withdrawn editorial payload copies inside the content cleanup transaction."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceRun


def purge_editorial_material_receipts_in_transaction(
    session: Session, *, owner_id: UUID, content_version_ids: tuple[UUID, ...]
) -> None:
    if not session.in_transaction() or len(content_version_ids) > 1000:
        raise ValueError("editorial cleanup requires a bounded caller transaction")
    if not content_version_ids:
        return
    receipts = session.scalars(
        select(EditorialSourceMaterialReceipt)
        .where(
            EditorialSourceMaterialReceipt.owner_id == owner_id,
            EditorialSourceMaterialReceipt.content_version_id.in_(content_version_ids),
        )
        .with_for_update()
    ).all()
    affected: dict[UUID, set[str]] = {}
    for receipt in receipts:
        affected.setdefault(receipt.run_id, set()).add(receipt.identity_key)
    if affected:
        runs = session.scalars(
            select(EditorialSourceRun)
            .where(
                EditorialSourceRun.owner_id == owner_id,
                EditorialSourceRun.id.in_(affected),
            )
            .with_for_update()
        )
        for run in runs:
            if run.prepared_page is None:
                continue
            page = dict(run.prepared_page)
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
            EditorialSourceMaterialReceipt.content_version_id.in_(content_version_ids),
        )
    )
