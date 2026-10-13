"""Explicit public-board grants and anonymous DTOs, independent of ORM and task scopes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content.hotlist_schemas import BOARD_FIELDS, BOARD_REQUIRED, ENTRY_FIELDS, ENTRY_REQUIRED
from core.schemas import OutputModel
from sources.adapters.web_targets import normalize_public_article_url


class HotlistPublicationGrant(BaseModel):
    """Default absent; collection permission and component licenses cannot enable publication."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    enabled: bool = Field(strict=True)
    source_policy_version: int = Field(strict=True, ge=1)
    board_fields: list[str]
    entry_fields: list[str]
    license_name: str = Field(min_length=1, max_length=200)
    license_url: str = Field(min_length=1, max_length=2048)
    reviewed_at: datetime
    expires_at: datetime
    max_age_seconds: int = Field(strict=True, ge=60, le=86400)

    @field_validator("license_url")
    @classmethod
    def public_license(cls, value: str) -> str:
        """Reject credentials and local/private targets without accessing the URL."""
        return normalize_public_article_url(value)

    @model_validator(mode="after")
    def validate_grant(self) -> HotlistPublicationGrant:
        if (
            self.reviewed_at.utcoffset() is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.reviewed_at
        ):
            raise ValueError("public grant requires an aware nonempty review interval")
        for fields, allowed, required in [
            (self.board_fields, BOARD_FIELDS, BOARD_REQUIRED),
            (self.entry_fields, ENTRY_FIELDS, ENTRY_REQUIRED),
        ]:
            if (
                len(fields) != len(set(fields))
                or not set(fields).issubset(allowed)
                or not required.issubset(fields)
            ):
                raise ValueError(
                    "public grant requires exact allowed fields including mandatory metadata"
                )
        return self


class PublicPlatformEntry(OutputModel):
    """Only fields explicitly allowed by the current board grant."""

    rank: int
    title: str
    url: str
    summary: str | None = None
    heat: str | None = None
    published_at: datetime | None = None
    native_id: str | None = None
    native_rank: int | None = None
    heat_unit: str | None = None
    previous_rank: int | None = None
    rank_delta: int | None = None


class PublicPlatformTrend(OutputModel):
    """One source's guarded snapshot or explicit reason why it cannot currently be read."""

    source_key: str
    source_name: str
    provider: Literal["RSSHub"] = "RSSHub"
    rank_basis: Literal["feed_position"] = "feed_position"
    state: Literal[
        "available",
        "empty",
        "partial",
        "stale",
        "no_snapshot",
        "collecting",
        "failed",
        "not_configured",
        "unavailable",
    ]
    reasons: list[str] = Field(default_factory=list)
    snapshot_id: UUID | None = None
    observed_at: datetime | None = None
    received_at: datetime | None = None
    source_updated_at: datetime | None = None
    due_at: datetime | None = None
    last_success_at: datetime | None = None
    valid_until: datetime | None = None
    source_entry_count: int | None = None
    entry_count: int | None = None
    truncated: bool | None = None
    adapter_version: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    permission_reviewed_at: datetime | None = None
    permission_expires_at: datetime | None = None
    comparison_reason: Literal[
        "comparable", "no_baseline", "gap", "source_changed", "unavailable"
    ] = "no_baseline"
    items: list[PublicPlatformEntry] = Field(default_factory=list)
