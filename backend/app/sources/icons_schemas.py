"""Bounded source avatar cache contracts; source MEDIA permission remains independent."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from evidence.schemas import CleanupTargetKind, CleanupTargetSpec
from sources.editorial_schemas import (
    EditorialContract,
    EditorialSourceConfiguration,
    fingerprint,
    public_url,
)


class SourceIconSeed(EditorialContract):
    owner_id: UUID
    profile_id: UUID
    source_key: str = Field(pattern=r"^ed_[a-z_]+_[a-f0-9]{32}$")
    configuration_version: int = Field(ge=1)
    profile_revision: int = Field(ge=1)
    policy_version: int = Field(ge=1)
    connection_id: UUID
    connection_version: int = Field(ge=1)
    configuration: EditorialSourceConfiguration
    article_urls: tuple[str, ...] = Field(default=(), max_length=10)
    avatar_url: str | None = Field(default=None, max_length=2048)
    scheduled_for_at: datetime

    @model_validator(mode="after")
    def bounded_seed(self) -> Self:
        if self.scheduled_for_at.utcoffset() is None:
            raise ValueError("source icon scheduling requires an aware timestamp")
        if self.source_key != f"ed_{self.configuration.kind}_{self.profile_id.hex}":
            raise ValueError("icon cache needs its original source identity")
        for url in (*self.article_urls, *([self.avatar_url] if self.avatar_url else [])):
            public_url(url)
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("source icon Job input exceeds its limit")
        return self

    @property
    def sha256(self) -> str:
        return fingerprint(self.model_dump(mode="json")).hex()


class SourceIconObjectRef(EditorialContract):
    mode: Literal["avatar-48", "avatar-96"]
    object_name: str = Field(max_length=1024)
    evidence_resource_id: UUID
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: Literal["image/webp", "image/jpeg", "image/svg+xml"]
    width: Literal[48, 96]
    height: Literal[48, 96]
    byte_count: int = Field(ge=1, le=15 * 1024 * 1024)

    @model_validator(mode="after")
    def avatar_identity(self) -> Self:
        expected = 48 if self.mode == "avatar-48" else 96
        if self.width != expected or self.height != expected:
            raise ValueError("avatar rendition must retain its declared square dimensions")
        CleanupTargetSpec(kind=CleanupTargetKind.MINIO_OBJECT, reference=self.object_name)
        if not self.object_name.startswith("media/"):
            raise ValueError("icon objects require the original media namespace")
        return self


class SourceIconVariant(EditorialContract):
    mode: Literal["avatar-48", "avatar-96"]
    url: str = Field(max_length=512)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: Literal["image/webp", "image/jpeg", "image/svg+xml"]
    width: Literal[48, 96]
    height: Literal[48, 96]


class SourceIconView(EditorialContract):
    profile_id: UUID
    configuration_version: int = Field(ge=1)
    status: Literal[
        "not_configured", "ready", "missing", "blocked", "unknown", "running", "obsolete"
    ]
    checked_at: datetime | None
    next_retry_at: datetime | None
    failure_code: str | None = Field(default=None, max_length=64)
    variants: tuple[SourceIconVariant, ...] = Field(default=(), max_length=2)


class SourceIconRefreshInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    action: Literal["refresh", "retry_unknown"] = "refresh"
