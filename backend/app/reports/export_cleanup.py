"""Invalidate private artifacts when an actual original input is physically removed."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from reports.export_models import ContentExportRequest, ReportExport


def purge_export_input_references_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    observation_ids: tuple[UUID, ...],
) -> None:
    if not session.in_transaction():
        raise RuntimeError("export cleanup requires caller transaction")
    versions = {str(item) for item in content_version_ids}
    observations = {str(item) for item in observation_ids}
    for model in (ReportExport, ContentExportRequest):
        for raw in session.scalars(
            select(model).where(model.owner_id == owner_id).with_for_update()
        ):
            row = cast(ReportExport | ContentExportRequest, raw)
            raw_versions = row.input_manifest.get("content_version_ids", [])
            raw_observations = row.input_manifest.get("observation_ids", [])
            if (isinstance(raw_versions, list) and versions.intersection(raw_versions)) or (
                isinstance(raw_observations, list) and observations.intersection(raw_observations)
            ):
                row.status, row.failure_code = "blocked", "export_input_deleted"
                row.object_name = row.object_sha256 = row.object_size = row.mime_type = None
                # The original Evidence cleanup target still owns physical MinIO removal.
                # Fixed identity/version/hash metadata stays available for the original Job trace.
