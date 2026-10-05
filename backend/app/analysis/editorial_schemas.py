"""Strict editorial business contracts; topic relevance remains separate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from content.schemas import EventContentReadReference
from core.schemas import InputModel, OutputModel

Tier = Literal["T1", "T1_5", "T2", "EXCLUDE_MP", "UNGRADED"]
SourceKind = Literal["rss", "web_list", "json_list", "x_search", "mp_account", "external", "other"]
PrefilterLabel = Literal["PASS", "BLOCK", "UNKNOWN"]
Category = Literal["ai-models", "ai-products", "industry", "paper", "tip", "opinion"]
ItemType = Literal[
    "model_release",
    "product_launch",
    "tool_or_prompt",
    "research_paper",
    "industry_event",
    "opinion_analysis",
    "tutorial_explainer",
]


class EditorialSourceInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    tier: Tier
    source_kind: SourceKind
    name: str = Field(min_length=1, max_length=200)
    first_party: bool = False
    owner_entity_id: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = False

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, value: list[str]) -> list[str]:
        if any(not tag or len(tag) > 80 for tag in value):
            raise ValueError("invalid source tag")
        return list(dict.fromkeys(value))


class EditorialSourceView(OutputModel):
    source_key: str
    revision: int
    tier: Tier
    source_kind: SourceKind
    name: str
    first_party: bool
    owner_entity_id: str | None
    tags: list[str]
    enabled: bool


class EditorialMaterial(InputModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content_id: UUID
    content_version_id: UUID
    source_key: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=200)
    source_kind: SourceKind
    tier: Tier
    title: str = Field(max_length=10000)
    body: str = Field(default="", max_length=1_000_000)
    excerpt: str = Field(default="", max_length=100000)
    body_complete: bool = False
    body_pending: bool = False
    url: str = Field(default="", max_length=2048)
    author: str | None = Field(default=None, max_length=300)
    published_at: datetime | None = None
    discovered_at: datetime
    first_party: bool = False
    owner_entity_id: str | None = Field(default=None, max_length=80)
    source_tags: list[str] = Field(default_factory=list, max_length=20)
    quoted_text: str = Field(default="", max_length=100000)
    quoted_author: str = Field(default="", max_length=300)
    image_count: int = Field(default=0, ge=0, le=100)
    video_count: int = Field(default=0, ge=0, le=100)

    @field_validator("published_at", "discovered_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("editorial time must be timezone-aware")
        return value


class PrefilterOutput(InputModel):
    label: PrefilterLabel
    reason: str = Field(max_length=200)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> str:
        return str(value).strip().upper()


class ScoreOutput(InputModel):
    attention_score: int = Field(alias="attentionScore", ge=0, le=100, strict=True)


class FactOutput(InputModel):
    title: str = Field(max_length=80)
    subject: str | None = Field(default=None, max_length=80)
    action: str | None = Field(default=None, max_length=80)
    object: str | None = Field(default=None, max_length=160)
    occurred_at: str | None = Field(
        alias="occurredAt", default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    evidence: str | None = Field(default=None, max_length=600)
    conditions: list[FactCondition] = Field(default_factory=list, max_length=4)


class FactCondition(InputModel):
    quote: str = Field(min_length=1, max_length=400, strict=True)


class StructureDiscard(OutputModel):
    field: str
    reason: Literal[
        "invalid_type",
        "too_long",
        "empty",
        "ellipsis",
        "cross_paragraph",
        "not_in_original",
        "not_in_model_input",
        "too_many",
        "composite",
        "no_original",
        "invalid_scope",
    ]


class StructureOutput(InputModel):
    category: Category | None
    tags: list[str] = Field(max_length=12)
    subjects: list[str] = Field(max_length=6)
    fact: FactOutput | None
    scope: Literal["single", "composite", "unknown"] = "unknown"
    discards: list[StructureDiscard] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def composite_has_no_fact(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and value.get("scope") == "composite"
            and value.get("fact") is not None
        ):
            return {
                **value,
                "fact": None,
                "discards": [
                    *value.get("discards", []),
                    StructureDiscard(field="fact", reason="composite"),
                ],
            }
        return value


class UnderstandOutput(InputModel):
    item_type: ItemType = Field(alias="itemType")
    author_role: Literal["principal", "observer", "relayer"] = Field(alias="authorRole")
    tags: list[str] = Field(max_length=12)
    editorial_judgment: str = Field(alias="editorialJudgment", max_length=400)
    title_zh: str = Field(alias="titleZh", min_length=1, max_length=200)
    summary_zh: str = Field(alias="summaryZh", min_length=1, max_length=4000)


class SummarizeOutput(InputModel):
    title_zh: str = Field(alias="titleZh", max_length=200)
    summary_zh: str = Field(alias="summaryZh", max_length=4000)
    body_zh: str = Field(alias="bodyZh", default="", max_length=8000)


class TranslationOutput(InputModel):
    t: list[str] = Field(max_length=500)

    @field_validator("t")
    @classmethod
    def bounded_segments(cls, value: list[str]) -> list[str]:
        if sum(len(part) for part in value) > 100000:
            raise ValueError("translation output too long")
        return value


class SelectionDecision(OutputModel):
    complete: bool
    threshold: int | None
    score: int | None
    selected: bool
    understand: bool


class EditorialEntityGuardView(OutputModel):
    outcome: Literal["pass", "fallback"]
    unsupported_title_entity_ids: list[str]
    unsupported_summary_entity_ids: list[str]


class EditorialCopy(OutputModel):
    title_zh: str
    summary_zh: str
    identity_guard: EditorialEntityGuardView


class EditorialWritingView(EditorialCopy):
    kind: Literal["understand", "summarize", "verbatim", "none", "manual"]
    reason_zh: str | None = None
    item_type: ItemType | None = None
    author_role: Literal["principal", "observer", "relayer"] | None = None
    tags: list[str] | None = None


class EditorialResultView(OutputModel):
    prefilter: PrefilterOutput | None = None
    scores: list[int] = Field(default_factory=list)
    threshold: int | None = None
    score: int | None = None
    selected: bool = False
    relevance: Literal["pass", "block", "unknown"]
    writing: EditorialWritingView | None = None
    structure: StructureOutput | None = None
    body_complete: bool = False
    manual: bool = False
    tags_override: list[str] | None = None
    silent: bool = False
    manual_overrides: dict[str, str | bool | list[str]] = Field(default_factory=dict)


class EditorialRunInput(InputModel):
    operation_id: UUID
    content_version_id: UUID
    expected_manual_version: int = Field(default=0, ge=0)
    stages: Literal["selection", "all"] = "all"


class EditorialRunView(OutputModel):
    id: UUID
    job_id: UUID | None
    content_id: UUID
    content_version_id: UUID
    source_key: str
    source_revision: int
    prompt_version: str
    manual_version: int
    status: Literal["queued", "running", "complete", "blocked", "failed", "unknown", "stale"]
    result: EditorialResultView | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc_output(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EditorialPublicationInputView(OutputModel):
    observation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = ()
    run: EditorialRunView | None
    source: EditorialSourceView
    material: EditorialMaterial
    timeline_at: datetime
    first_received_at: datetime
    backfill: bool | None
    quote_reference: EventContentReadReference | None = None


class EditorialPublicationIdPage(OutputModel):
    content_ids: tuple[UUID, ...]
    next_after: UUID | None


class EditorialOverrideInput(InputModel):
    operation_id: UUID
    expected_manual_version: int = Field(ge=0)
    action: Literal["replace", "clear"] = "replace"
    clear_fields: list[
        Literal["selected", "title_zh", "summary_zh", "category", "reason_zh", "tags", "silent"]
    ] = Field(default_factory=list, max_length=7)
    selected: bool | None = None
    title_zh: str | None = Field(default=None, min_length=1, max_length=200)
    summary_zh: str | None = Field(default=None, min_length=1, max_length=4000)
    category: Category | None = None
    reason_zh: str | None = Field(default=None, max_length=400)
    tags: list[str] | None = Field(default=None, max_length=20)
    silent: bool | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        changes = {
            name
            for name in (
                "selected",
                "title_zh",
                "summary_zh",
                "category",
                "reason_zh",
                "tags",
                "silent",
            )
            if getattr(self, name) is not None
        }
        if self.action == "clear" and (changes or self.clear_fields):
            raise ValueError("clearing all overrides cannot also replace fields")
        if self.action == "replace" and not changes and not self.clear_fields:
            raise ValueError("manual correction needs a changed or cleared field")
        if changes.intersection(self.clear_fields):
            raise ValueError("a manual field cannot be cleared and replaced together")
        if any(
            value is not None and not value.strip() for value in (self.title_zh, self.summary_zh)
        ):
            raise ValueError("manual publication copy cannot be empty")
        if self.tags is not None and any(not tag.strip() or len(tag) > 80 for tag in self.tags):
            raise ValueError("manual tags must contain 1 to 80 characters")
        return self
