from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReportKind(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    FINAL = "final"


class ReportGenerator(StrEnum):
    TEMPLATE = "template"
    MODEL = "model"


class ReportPeriod(StrEnum):
    CURRENT = "current"
    PREVIOUS = "previous"


class AnnotationState(StrEnum):
    MISSING = "missing"
    ANNOTATED = "annotated"
    UNANALYZED = "unanalyzed"


class ReportSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SourceCoverageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    MISSING = "missing"


class ReportMetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    repost_count: int | None = Field(default=None, ge=0)
    view_count: int | None = Field(default=None, ge=0)
    play_count: int | None = Field(default=None, ge=0)
    danmaku_count: int | None = Field(default=None, ge=0)

    @property
    def interaction_count(self) -> int | None:
        values = [getattr(self, field) for field in self.interaction_fields]
        return sum(values) if values else None

    @property
    def interaction_fields(self) -> tuple[str, ...]:
        return tuple(
            field
            for field in ("like_count", "comment_count", "repost_count", "danmaku_count")
            if getattr(self, field) is not None
        )


class ReportPostInput(BaseModel):
    """One exact post version and annotation selected at the report cutoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period: ReportPeriod
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID
    annotation_id: UUID | None
    source_key: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=2_000)
    body: str | None = Field(default=None, max_length=100_000)
    url: str | None = Field(default=None, max_length=2_048)
    published_at: datetime | None
    first_observed_at: datetime
    occurred_at: datetime
    annotation_state: AnnotationState
    relevant: bool | None
    sentiment: ReportSentiment | None
    summary: str | None = Field(default=None, max_length=60)
    relevance_reason: str | None = Field(default=None, max_length=500)
    viewpoints: tuple[str, ...] = Field(default=(), max_length=5)
    metrics: ReportMetricInput

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("report source URL must use HTTP or HTTPS")
        return value

    @field_validator("published_at", "first_observed_at", "occurred_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("report input times must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_annotation(self) -> Self:
        if self.annotation_state is AnnotationState.MISSING:
            if self.annotation_id is not None or self.relevant is not None:
                raise ValueError("missing annotations cannot carry annotation output")
        elif self.annotation_id is None:
            raise ValueError("persisted annotation states require an annotation id")
        if self.annotation_state is AnnotationState.ANNOTATED:
            if self.relevant is None or self.summary is None or self.relevance_reason is None:
                raise ValueError("annotated report inputs require complete output")
            if self.relevant and self.sentiment is None:
                raise ValueError("relevant report inputs require sentiment")
            if not self.relevant and self.sentiment is not None:
                raise ValueError("irrelevant report inputs cannot carry sentiment")
        elif any(
            item is not None
            for item in (self.relevant, self.sentiment, self.summary, self.relevance_reason)
        ):
            raise ValueError("unanalyzed report inputs cannot carry annotation output")
        return self


class ReportCommentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    period: ReportPeriod
    post_content_id: UUID
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID
    text: str = Field(min_length=1, max_length=100_000)
    occurred_at: datetime
    metrics: ReportMetricInput
    source_key: str | None = None
    native_id: str | None = None
    url: str | None = None
    root_content_id: UUID | None = None
    parent_content_id: UUID | None = None
    reply_target_content_id: UUID | None = None
    parent_relation_status: str = "unknown"
    collected_at: datetime | None = None
    job_id: UUID | None = None
    connection_version: int | None = None
    entry_point: str | None = None
    sort_key: str | None = None
    first_level_limit: int | None = None
    replies_per_thread_limit: int | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("comment occurrence time must be timezone-aware")
        return value


class ReportSourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: str = Field(min_length=1, max_length=64)
    status: SourceCoverageStatus
    succeeded_jobs: int = Field(ge=0)
    partial_jobs: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    incomplete_jobs: int = Field(ge=0)


class ReportBuildDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    posts: tuple[ReportPostInput, ...]
    comments: tuple[ReportCommentInput, ...]
    source_coverage: tuple[ReportSourceCoverage, ...]
    comment_scopes: tuple[ReportCommentScope, ...] = ()


class ReportInputManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_version_ids: tuple[UUID, ...]
    annotation_ids: tuple[UUID, ...]
    observation_ids: tuple[UUID, ...]
    comment_content_version_ids: tuple[UUID, ...]
    source_coverage: tuple[ReportSourceCoverage, ...]
    discovered_at_count: int = Field(ge=0)
    unanalyzed_count: int = Field(ge=0)
    daily_reports: tuple[ReportDailyReference, ...] = ()
    missing_daily_dates: tuple[date, ...] = ()


class ReportDailyReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: UUID
    version: int = Field(ge=1)
    day: date
    posts: int = Field(ge=0)
    comments: int = Field(ge=0)


class ReportComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current: int = Field(ge=0)
    previous: int = Field(ge=0)
    delta: int


class ReportOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    posts: ReportComparison
    comments: ReportComparison
    platform_distribution: dict[str, int]
    sentiment_distribution: dict[ReportSentiment, int]


class ReportRepresentativeComment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_id: UUID
    content_version_id: UUID
    text: str
    interaction_count: int | None = Field(default=None, ge=0)
    reference: ReportCommentInput | None = None


class ReportContentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str = Field(pattern=r"^c[1-9][0-9]*$")
    content_id: UUID
    content_version_id: UUID
    title: str
    summary: str
    sentiment: ReportSentiment
    source_key: str
    url: str | None
    interaction_count: int | None = Field(default=None, ge=0)
    interaction_fields: tuple[str, ...] = ()
    representative_comments: tuple[ReportRepresentativeComment, ...]


class ReportRiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str
    title: str
    url: str | None
    reason: str
    interaction_count: int | None = Field(default=None, ge=0)


class ReportVoiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str
    excerpt: str
    url: str | None


class ReportCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: tuple[ReportSourceCoverage, ...]
    discovered_at_count: int = Field(ge=0)
    unanalyzed_count: int = Field(ge=0)
    comments: tuple[ReportCommentScope, ...] = ()
    disclaimer: str = "样本观察，不代表全网"  # noqa: RUF001


class ReportCommentScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    post_content_id: UUID
    source_key: str
    status: Literal[
        "unknown", "unsupported", "not_authorized", "not_attempted", "failed", "partial", "observed"
    ]
    stored_comments: int = Field(ge=0)
    unresolved_relations: int = Field(ge=0)
    note: str = "仅本报告时间窗内已存样本；未确认远端完整覆盖。"  # noqa: RUF001


class ReportPendingContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str = Field(pattern=r"^c[1-9][0-9]*$")
    content_id: UUID
    content_version_id: UUID
    title: str
    source_key: str
    url: str | None
    occurred_at: datetime
    time_basis: Literal["published", "discovered"]
    annotation_state: AnnotationState
    metrics: ReportMetricInput
    comments: tuple[ReportCommentInput, ...] = ()


type ReportSection = Literal["overview", "top_content", "risks", "voices"]


class ReportNarrativeSentence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=500)
    citations: tuple[str, ...] = Field(min_length=1, max_length=10)


class DailyReportData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: UUID
    topic_name: str
    window_start: datetime
    window_end: datetime
    cutoff_at: datetime
    kind: ReportKind = ReportKind.DAILY
    overview: ReportOverview
    previous_sample_available: bool = False
    top_contents: tuple[ReportContentItem, ...]
    risks: tuple[ReportRiskItem, ...]
    voices: tuple[ReportVoiceItem, ...]
    coverage: ReportCoverage
    pending_contents: tuple[ReportPendingContent, ...] = ()
    daily_reports: tuple[ReportDailyReference, ...] = ()
    missing_daily_dates: tuple[date, ...] = ()
    daily_totals_match: bool | None = None
    narratives: dict[ReportSection, tuple[ReportNarrativeSentence, ...]] = Field(
        default_factory=dict
    )

    @field_validator("window_start", "window_end", "cutoff_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("report persistence times must be UTC")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if not self.window_start < self.window_end <= self.cutoff_at:
            raise ValueError("report window and cutoff must be ordered")
        return self


class PreparedDailyReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: UUID
    topic_id: UUID
    version: int = Field(ge=1)
    window_start: datetime
    window_end: datetime
    cutoff_at: datetime
    input_manifest: ReportInputManifest
    data: DailyReportData
    body_markdown: str = Field(min_length=1)


class DailyReportJobScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: UUID
    window_start: datetime
    window_end: datetime
    report_id: UUID | None = None

    @field_validator("window_start", "window_end")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("daily report job windows must be UTC")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end - self.window_start != timedelta(days=1):
            raise ValueError("daily report job window must be one day")
        return self

    @classmethod
    def from_job_scope(cls, scope: dict[str, str | int | bool | None]) -> DailyReportJobScope:
        return cls.model_validate(
            {
                "topic_id": scope.get("topic_id"),
                "window_start": scope.get("window_start"),
                "window_end": scope.get("window_end"),
                "report_id": scope.get("report_id"),
            }
        )


class WeeklyReportJobScope(DailyReportJobScope):
    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end - self.window_start != timedelta(days=7):
            raise ValueError("weekly report job window must be seven days")
        # Monday 00:00 Asia/Shanghai is Sunday 16:00 UTC.
        if self.window_start.weekday() != 6 or self.window_start.time().isoformat() != "16:00:00":
            raise ValueError("weekly report window must use the Shanghai ISO week")
        return self


class ReportView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: UUID
    owner_id: UUID
    topic_id: UUID
    kind: ReportKind
    window_start: datetime
    window_end: datetime
    cutoff_at: datetime
    version: int
    status: ReportStatus
    generator: ReportGenerator
    input_manifest: ReportInputManifest
    data: DailyReportData
    body_markdown: str
    created_at: datetime


class ReportSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    topic_id: UUID
    topic_name: str
    kind: ReportKind
    window_start: datetime
    window_end: datetime
    version: int
    generator: ReportGenerator


class ReportCitationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str = Field(pattern=r"^c[1-9][0-9]*$")
    title: str
    url: str | None


class ReportDetailView(ReportSummaryView):
    cutoff_at: datetime
    body_markdown: str
    citations: list[ReportCitationView]
