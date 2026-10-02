from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, field_validator, model_validator

from core.schemas import InputModel, OutputModel
from publication.schemas import ReportPublicationCandidate
from reports.edition_rules import EditionKind, period_window


class EditionRequestInput(InputModel):
    operation_id: UUID
    kind: EditionKind
    key: str = Field(min_length=7, max_length=10)
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def calendar_key(self) -> EditionRequestInput:
        period_window(self.kind, self.key)
        return self


class EditionLeadOutput(InputModel):
    title: str = Field(min_length=1, max_length=120)
    lead_paragraph: str = Field(alias="leadParagraph", min_length=1, max_length=600)
    highlights: list[StrictInt] = Field(max_length=6)


class EditionThemeOutput(InputModel):
    heading: str = Field(min_length=1, max_length=60)
    summary: str = Field(min_length=1, max_length=800)
    refs: list[StrictInt] = Field(min_length=1, max_length=8)


class EditionPeriodOutput(InputModel):
    headline: str = Field(default="", max_length=60)
    overview: str = Field(min_length=1, max_length=1500)
    themes: list[EditionThemeOutput] = Field(min_length=1, max_length=6)


class EditionSectionView(OutputModel):
    label: str
    content_ids: list[UUID]


class EditionThemeView(OutputModel):
    heading: str
    summary: str
    content_ids: list[UUID]


class EditionMetricsView(OutputModel):
    selected_count: int = Field(ge=0)
    facts_count: int = Field(ge=0)
    sources_count: int = Field(ge=0)
    first_party_count: int = Field(ge=0)
    models_released: int = Field(ge=0)
    repeats_suppressed: int = Field(ge=0)
    backfill_unknown_count: int = Field(ge=0)
    daily_editions_covered: int = Field(ge=0)


class EditionContentView(OutputModel):
    title: str
    lead: str
    highlights: list[UUID]
    sections: list[EditionSectionView]
    flashes: list[UUID]
    themes: list[EditionThemeView]
    entries: list[ReportPublicationCandidate]
    metrics: EditionMetricsView


class EditionSummaryView(OutputModel):
    id: UUID
    kind: EditionKind
    key: str
    revision: int
    status: Literal["queued", "running", "complete", "failed", "unknown", "stale"]
    generator: Literal["template", "model", "manual"]
    window_start: datetime
    window_end: datetime
    title: str | None
    valid: bool
    failure_code: str | None
    created_at: datetime

    @field_validator("window_start", "window_end", "created_at")
    @classmethod
    def utc_output(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EditionIndexingChangeView(OutputModel):
    edition_id: UUID
    kind: EditionKind
    key: str
    changed_at: datetime
    public: bool


class EditionDetailView(EditionSummaryView):
    job_id: UUID | None
    content: EditionContentView | None
    body_markdown: str | None
    ai_call_id: UUID | None
    reason: str
    historical_revision: bool


class EditionCorrectionInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    lead: str = Field(min_length=1, max_length=1500)
    highlights: list[UUID] = Field(max_length=6)
    themes: list[EditionThemeInput] = Field(max_length=6)
    reason: str = Field(min_length=1, max_length=1000)


class EditionThemeInput(InputModel):
    heading: str = Field(min_length=1, max_length=60)
    summary: str = Field(min_length=1, max_length=800)
    content_ids: list[UUID] = Field(min_length=1, max_length=8)
