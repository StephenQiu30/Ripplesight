"""Explicit operator approval of a fixed source body-extraction declaration."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from sources.editorial_base import EditorialContract
from sources.editorial_body_review import EditorialBodyReview


class EditorialBodyApprovalInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    configuration_version: int = Field(ge=1)
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)
    review: EditorialBodyReview


class EditorialBodyApprovalView(EditorialContract):
    profile_id: UUID
    revision: int
    configuration_version: int
    configuration_sha256: str
    policy_version: int
    reviewed_at: datetime
    expires_at: datetime
    enabled: bool
