"""Content-owned ingestion DTOs for admitted editorial sources."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from sources.contracts import SourceCapability
from sources.editorial_schemas import EditorialContract, EditorialMaterial


class EditorialContentInput(EditorialContract):
    profile_id: UUID
    source_key: str = Field(pattern=r"^ed_[a-z_]+_[a-f0-9]{32}$", max_length=64)
    configuration_version: int = Field(ge=1)
    policy_version: int = Field(ge=1)
    connection_id: UUID
    connection_version: int = Field(ge=1)
    job_id: UUID
    operation_id: UUID
    capability: SourceCapability
    observed_at: datetime
    first_import: bool = False
    grouped_job: bool = False
    material: EditorialMaterial


class EditorialContentResult(EditorialContract):
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID
