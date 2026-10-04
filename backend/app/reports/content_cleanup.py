"""Remove fixed report text using deleted content, rather than replacing its inputs."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from notifications.content_cleanup import purge_notification_subjects_in_transaction
from reports.edition_models import ReportEdition
from reports.export_cleanup import purge_export_input_references_in_transaction
from reports.models import Report


def _uses(value: object, identifiers: set[str]) -> bool:
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, dict):
        return any(_uses(item, identifiers) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_uses(item, identifiers) for item in value)
    return False


def purge_report_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    observation_ids: tuple[UUID, ...],
    legacy_content_version_ids: tuple[UUID, ...] = (),
) -> None:
    if not session.in_transaction():
        raise RuntimeError("report cleanup requires caller transaction")
    purge_export_input_references_in_transaction(
        session,
        owner_id=owner_id,
        content_version_ids=content_version_ids,
        observation_ids=observation_ids,
    )
    identifiers = {str(item) for item in (*content_version_ids, *observation_ids)}
    legacy_identifiers = {str(i) for i in legacy_content_version_ids}
    rows = tuple(
        session.scalars(select(Report).where(Report.owner_id == owner_id).with_for_update())
    )
    removed: set[UUID] = set()
    while True:
        added = {
            row.id
            for row in rows
            if row.id not in removed
            and (
                _uses(row.input_manifest, identifiers)
                or (
                    not row.input_manifest.get("observation_ids")
                    and _uses(row.input_manifest, legacy_identifiers)
                )
            )
        }
        if not added:
            break
        removed.update(added)
        identifiers.update(str(item) for item in added)
    session.execute(delete(Report).where(Report.owner_id == owner_id, Report.id.in_(removed)))
    for edition in session.scalars(
        select(ReportEdition).where(ReportEdition.owner_id == owner_id).with_for_update()
    ):
        if _uses(edition.input_snapshot, identifiers):
            purge_notification_subjects_in_transaction(
                session, owner_id=owner_id, subject_ids=(edition.id,)
            )
            edition.status = "stale"
            edition.content = None
            edition.body_markdown = None
            edition.input_snapshot = []
            edition.failure_code = "content_input_deleted"
