"""HTTP-independent publishing, reading and frozen cross-domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from core.schemas import InputModel, OutputModel
from publication.media_mirror_schemas import MediaRenditionView

SharePage = Literal[
    "site",
    "all",
    "hot",
    "daily",
    "weekly",
    "monthly",
    "topics",
    "leaderboard",
    "codex-reset",
    "about",
    "terms",
    "privacy",
    "changelog",
    "feedback",
    "agent",
    "contact",
]

Visibility = Literal["public", "summary-only", "withdrawn"]
ParticipationMode = Literal["editorial", "hot_signal", "isolated"]
Category = Literal["ai-models", "ai-products", "industry", "paper", "tip", "opinion"]


class SourcePolicyInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    participation_mode: ParticipationMode = "isolated"
    body_format: Literal["text", "html", "markdown"] = "text"
    site_fulltext: bool = False
    syndicate_fulltext: bool = False
    indexable: bool = False
    release_delay_seconds: int = Field(default=180, ge=0, le=3600)
    license_name: str = Field(min_length=1, max_length=1000)
    license_url: str | None = Field(default=None, max_length=2048)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("license_url")
    @classmethod
    def public_license_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("license URL must be a public HTTP(S) link")
        return value

    @model_validator(mode="after")
    def redistribution_needs_site_permission(self) -> SourcePolicyInput:
        if self.syndicate_fulltext and not self.site_fulltext:
            raise ValueError(
                "redistribution permission requires confirmed site fulltext permission"
            )
        return self


class SourcePolicyView(OutputModel):
    source_key: str
    revision: int
    participation_mode: ParticipationMode
    body_format: Literal["text", "html", "markdown"] = "text"
    site_fulltext: bool
    syndicate_fulltext: bool
    indexable: bool
    release_delay_seconds: int
    license_name: str
    license_url: str | None
    updated_at: datetime


class PublicationOverrideInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    visibility: Visibility
    seo_indexed: bool = False
    seo_excluded: bool = False
    reason: str = Field(min_length=1, max_length=1000)


class FrozenPublicationReference(OutputModel):
    content_id: UUID
    content_version_id: UUID
    editorial_run_id: UUID | None
    manual_version: int
    source_profile_revision: int
    policy_revision: int
    publication_revision: int
    event_id: UUID | None = None
    event_revision: int | None = None
    fact_id: UUID | None = None
    root_fact_id: UUID | None = None
    fact_revision: int | None = None
    topic_id: UUID | None = None


class ProjectionView(FrozenPublicationReference):
    analysis_state: Literal["not_analyzed", "complete"] = "complete"
    summary_origin: Literal["source", "model", "none"] = "model"
    source_key: str
    source_name: str
    source_kind: str
    first_party: bool
    visibility: Visibility
    eligible: bool
    selected: bool
    silent: bool = False
    title: str
    original_title: str | None
    summary: str | None
    reason: str | None
    category: Category | None
    tags: list[str]
    score: int | None
    channel: Literal["news", "x"]
    url: str
    published_at: datetime | None
    discovered_at: datetime
    timeline_at: datetime
    sort_at: datetime
    backfill: bool | None
    selected_ready_at: datetime | None
    visible_after: datetime | None
    body_mode: Literal["full", "summary"]
    media_candidate_count: int = Field(default=0, ge=0)
    syndicate: bool
    indexable: bool
    input_fingerprint: str

    @field_validator(
        "published_at",
        "discovered_at",
        "timeline_at",
        "sort_at",
        "selected_ready_at",
        "visible_after",
    )
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("publication timestamps must be timezone-aware")
        return value


class PublicSourceView(OutputModel):
    key: str
    name: str
    kind: str
    first_party: bool
    icon_url: str | None = None


class PublicItemView(OutputModel):
    analysis_state: Literal["not_analyzed", "complete"] = "complete"
    summary_origin: Literal["source", "model", "none"] = "model"
    backfill: bool | None = None
    id: UUID
    revision: int
    title: str
    original_title: str | None
    summary: str | None
    source: PublicSourceView
    original_url: str
    reading_url: str
    published_at: datetime | None
    discovered_at: datetime
    timeline_at: datetime
    category: Category | None
    tags: list[str]
    score: int | None
    selected: bool
    reason: str | None
    event_id: UUID | None
    fact_id: UUID | None
    indexable: bool


class PublicBodyView(OutputModel):
    original: str
    original_format: Literal["text", "html", "markdown"] = "text"
    original_html: str | None = None
    body_sha256: str | None = None
    outline: list[PublicOutlineEntry] = Field(default_factory=list)
    media: list[PublicMediaView] = Field(default_factory=list)
    translated: str | None = None
    translation_complete: bool = False
    translation_state: Literal[
        "not_requested", "queued", "running", "complete", "partial", "unknown", "failed", "stale"
    ] = "not_requested"
    translation_revision: int | None = None


class PublicItemDetailView(PublicItemView):
    reading_mode: Literal["full", "summary-only"]
    body: PublicBodyView | None
    site_fulltext: bool
    syndicate_fulltext: bool
    markdown_available: bool
    license_name: str
    license_url: str | None
    quoted_post: PublicQuotedPostView | None = None
    related_stories: list[PublicRelatedStoryView] = Field(default_factory=list, max_length=6)


class PublicQuotedPostView(OutputModel):
    item: PublicItemView
    author: str | None
    body: PublicBodyView | None


class PublicRelatedStoryView(OutputModel):
    id: UUID
    revision: int
    title: str
    summary: str | None
    reading_url: str
    supporting_reports: int


class PublicSourceStatusView(OutputModel):
    source_key: str
    name: str
    enabled: bool
    health: Literal["unknown", "ok", "degraded", "failing"]
    last_success_at: datetime | None


class PublicItemsPage(OutputModel):
    source_status: list[PublicSourceStatusView] = Field(default_factory=list)
    items: list[PublicItemView]
    next_cursor: str | None
    snapshot_at: datetime


class SelectedSnapshotView(OutputModel):
    epoch: UUID
    sequence: int
    items: list[PublicItemView]
    next_cursor: str | None


class SelectedChangeView(OutputModel):
    sequence: int
    operation: Literal["upsert", "remove"]
    content_id: UUID
    changed_at: datetime
    item: PublicItemView | None


class SelectedChangesPage(OutputModel):
    epoch: UUID
    sequence: int
    changes: list[SelectedChangeView]
    next_cursor: str | None


class PublishResultView(OutputModel):
    content_id: UUID
    changed: bool
    revision: int
    selected: bool
    visibility: Visibility
    ledger: Literal["upsert", "remove"] | None
    reduced: bool


class ReportPublicationCandidate(FrozenPublicationReference):
    title_zh: str
    summary_zh: str
    source_key: str
    source_name: str
    source_kind: str
    first_party: bool
    url: str
    category: Category | None
    tags: list[str]
    score: int | None
    timeline_at: datetime
    backfill: bool | None
    root_title: str | None = None


class PublicationValidationView(OutputModel):
    valid: bool
    invalid_content_ids: list[UUID]
    reason: Literal["valid", "publication_changed_or_unavailable"]


class FullTextGrantView(OutputModel):
    granted: bool
    body_format: Literal["text", "html", "markdown"] = "text"
    body_sha256: str | None = None
    media: list[PublicMediaView] = Field(default_factory=list)
    reference: FrozenPublicationReference | None
    body: str | None
    reason: Literal["granted", "not_selected_public_fulltext", "version_or_permission_changed"]


class PublicAttentionView(OutputModel):
    formula_version: str
    window_end: datetime
    last_source_time: datetime
    heat: float
    eligible: bool
    participant_count: int
    editorial_participant_count: int
    signal_participant_count: int
    comparable_participant_count: int
    uncomparable_participant_count: int
    comparable_heat: float
    comparable_previous_heat: float
    previous_heat: float
    trend: Literal["new", "up", "down", "flat", "unknown"]
    trend_pct: float | None
    complete: bool
    badges: list[Literal["new", "surge", "rising"]]


class PublicStoryView(OutputModel):
    id: UUID
    revision: int
    title: str
    summary: str
    latest_progress: str | None
    phase: Literal["active", "watching", "settled"]
    first_seen_at: datetime
    heat: float | None = None
    attention: PublicAttentionView | None = None
    reports: list[PublicItemView]
    indexable: bool = False
    canonical_url: str | None = None


class PublicStoriesPage(OutputModel):
    stories: list[PublicStoryView]
    ranking_basis: Literal["heat", "recent_without_heat"]
    next_cursor: str | None = None


class RepublishInput(InputModel):
    operation_id: UUID
    expected_policy_revision: int = Field(ge=1)


class RepublishRunView(OutputModel):
    id: UUID
    job_id: UUID
    source_key: str
    policy_revision: int
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    after_content_id: UUID | None
    processed_count: int
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class PublicEditionSectionView(OutputModel):
    label: str
    content_ids: list[UUID]


class PublicEditionThemeView(OutputModel):
    heading: str
    summary: str
    content_ids: list[UUID]


class PublicEditionView(OutputModel):
    id: UUID
    kind: Literal["daily", "weekly", "monthly"]
    key: str
    revision: int
    title: str
    lead: str
    window_start: datetime
    window_end: datetime
    created_at: datetime
    highlights: list[UUID]
    sections: list[PublicEditionSectionView]
    flashes: list[UUID]
    themes: list[PublicEditionThemeView]
    entries: list[PublicItemView]
    metrics: dict[str, int]
    body_markdown: str
    indexable: bool = False
    canonical_url: str | None = None


class PublicOutlineEntry(OutputModel):
    id: str
    title: str
    level: int = Field(ge=2, le=5)


class PublicMediaView(OutputModel):
    key: str
    kind: Literal["image", "video", "audio", "unknown"]
    original_url: str
    alt: str
    reading_url: str | None
    state: Literal[
        "original_link",
        "available",
        "pending",
        "running",
        "unknown",
        "failed",
        "stale",
        "cancelled",
        "unavailable",
    ]
    width: int | None = None
    height: int | None = None
    renditions: list[MediaRenditionView] = Field(default_factory=list)


PublicBodyView.model_rebuild()
FullTextGrantView.model_rebuild()
