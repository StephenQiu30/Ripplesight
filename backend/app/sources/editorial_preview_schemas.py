"""Bounded parser preview; these contracts never accept credentials or raw publication grants."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from jobs.schemas import JobStatusView
from sources.editorial_schemas import (
    EditorialContract,
    EditorialSourceConfiguration,
    EditorialSourceKind,
)


class EditorialSamplePreviewInput(EditorialContract):
    operation_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    configuration: EditorialSourceConfiguration
    sample: str = Field(min_length=1, max_length=1_000_000, exclude=True, repr=False)

    @model_validator(mode="after")
    def bounded_sample(self) -> Self:
        if self.configuration.kind not in {"rss", "web_list", "json_list"}:
            raise ValueError("local sample previews support RSS, web and JSON")
        if not self.reason.strip() or len(self.sample.encode()) > 1_000_000:
            raise ValueError("sample or reason is outside the bound")
        return self


class EditorialRemotePreviewInput(EditorialContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def reason_required(self) -> Self:
        if not self.reason.strip():
            raise ValueError("nonblank preview reason required")
        return self


class EditorialPreviewItem(EditorialContract):
    title: str = Field(max_length=10000)
    url: str = Field(max_length=2048)
    published_at: datetime | None
    excerpt: str = Field(max_length=200)


class EditorialSourcePreviewView(EditorialContract):
    mode: Literal["sample", "remote"]
    status: Literal["complete", "partial", "blocked", "unknown"]
    kind: EditorialSourceKind
    count: int = Field(ge=0, le=1000)
    ms: int = Field(ge=0, le=600000)
    requests: int = Field(ge=0, le=500)
    items: tuple[EditorialPreviewItem, ...] = Field(max_length=20)
    reason: str | None = Field(default=None, max_length=128)


class EditorialPreviewJobView(EditorialContract):
    job: JobStatusView
    preview: EditorialSourcePreviewView | None


class EditorialPreviewReviewInput(EditorialRemotePreviewInput):
    preview_operation_id: UUID


class EditorialPreviewReviewView(EditorialContract):
    job_id: UUID
    profile_id: UUID
    preview_operation_id: UUID
    review_operation_id: UUID
    revision: int = Field(ge=1)
    reviewed: Literal[True] = True
    status: Literal["unknown"] = "unknown"
