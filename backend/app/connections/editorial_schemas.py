"""Operator input for editable source profiles; no runtime credential material."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from jobs.schemas import JobView
from sources.editorial_rsshub import EditorialRsshubReview
from sources.editorial_schemas import (
    EditorialContract,
    EditorialMaterial,
    EditorialSourceConfiguration,
    ParticipationMode,
    non_secret_json,
)


class EditorialSourceOperationalHealth(EditorialContract):
    id: UUID
    source_key: str
    name: str
    kind: str
    enabled: bool
    created_at: datetime
    health: Literal["unknown", "ok", "degraded", "failing"]
    consecutive_failures: int = Field(ge=0)
    last_success_at: datetime | None
    last_error: str | None


class EditorialProfileInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)
    enabled: bool = False
    configuration: EditorialSourceConfiguration
    participation_mode: ParticipationMode = "editorial"
    tier: Literal["T1", "T1_5", "T2", "T3"] = "T2"
    first_party: bool = False
    connection_id: UUID | None = None
    connection_version: int | None = Field(default=None, ge=1)
    policy_version: int = Field(ge=1)
    interval_minutes: int = Field(default=30, ge=1, le=360)

    @model_validator(mode="after")
    def connection_pair(self) -> Self:
        if (self.connection_id is None) != (self.connection_version is None):
            raise ValueError("connection identity and version must be supplied together")
        if self.configuration.kind in {"x_search", "mp_account"} and self.connection_id is None:
            raise ValueError("paid provider sources require a registered connection version")
        return self


class EditorialRunReviewInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    actor: str = Field(min_length=1, max_length=128)
    action: Literal["acknowledge_unknown", "retry_failed"]


class EditorialRsshubApprovalInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    configuration_version: int = Field(ge=1)
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)
    review: EditorialRsshubReview


class EditorialRsshubApprovalView(EditorialContract):
    profile_id: UUID
    revision: int
    configuration_version: int
    configuration_sha256: str
    policy_version: int
    reviewed_at: datetime
    expires_at: datetime
    enabled: bool


class EditorialPollInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class ExternalEditorialInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    configuration_version: int = Field(ge=1)
    materials: tuple[EditorialMaterial | dict[str, JsonValue], ...] = Field(
        min_length=1, max_length=50
    )

    @model_validator(mode="after")
    def bounded_body(self) -> Self:
        for material in self.materials:
            non_secret_json(
                material.model_dump(mode="json")
                if isinstance(material, EditorialMaterial)
                else material
            )
        if len(self.model_dump_json().encode()) > 4 * 1024 * 1024:
            raise ValueError("external ingestion exceeds bounded source payload")
        return self


class ExternalIngressItem(EditorialContract):
    index: int = Field(ge=0, le=49)
    identity_key: str | None = Field(default=None, max_length=512)
    status: Literal["pending", "succeeded", "duplicate", "rejected"]
    change: Literal["created", "revised", "unchanged"] | None = None
    content_id: UUID | None = None
    content_version_id: UUID | None = None
    duplicate_of: int | None = Field(default=None, ge=0, le=49)
    reason: str | None = Field(default=None, max_length=64)


class ExternalIngressReceipt(EditorialContract):
    job: JobView
    profile_id: UUID
    run_id: UUID
    configuration_version: int = Field(ge=1)
    received: int = Field(ge=1, le=50)
    items: tuple[ExternalIngressItem, ...] = Field(min_length=1, max_length=50)


class EditorialGroupBacklogMember(EditorialContract):
    profile_id: UUID
    source_key: str
    name: str
    configuration_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    enabled: bool


class EditorialGroupBacklogView(EditorialContract):
    group_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    query: str = Field(max_length=470)
    state: Literal["pending", "held", "blocked_configuration"]
    members: tuple[EditorialGroupBacklogMember, ...] = Field(min_length=2, max_length=24)


class EditorialGroupBacklogExpected(EditorialContract):
    profile_id: UUID
    configuration_version: int = Field(ge=1)
    revision: int = Field(ge=1)


class EditorialGroupBacklogReviewInput(EditorialContract):
    operation_id: UUID
    group_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=1000)
    actor: str = Field(min_length=1, max_length=128)
    action: Literal["restart_from_saved_watermark"]
    expected_members: tuple[EditorialGroupBacklogExpected, ...] = Field(min_length=2, max_length=24)

    @model_validator(mode="after")
    def distinct_members(self) -> Self:
        if len({m.profile_id for m in self.expected_members}) != len(self.expected_members):
            raise ValueError("backlog review must name distinct original members")
        return self


class EditorialGroupBacklogReviewResult(EditorialContract):
    group_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    members: tuple[EditorialGroupBacklogMember, ...] = Field(min_length=2, max_length=24)
