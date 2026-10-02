from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type ResetKind = Literal["direct_reset", "reset_credit"]
type ResetAction = Literal["announce", "progress", "confirm", "amend", "withdraw"]
type SchedulePrecision = Literal["exact", "approximate", "deadline", "date", "window"]
type PresentationStatus = Literal[
    "announced", "in_progress", "confirmed", "expired_unconfirmed", "likely_completed", "withdrawn"
]


class CodexContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MonitorConfiguration(CodexContract):
    author: Literal["thsottiaux"] = "thsottiaux"
    source_key: Literal["x"] = "x"
    author_external_id: str | None = Field(default=None, pattern=r"^[0-9]{1,19}$")
    connection_id: UUID | None = None
    connection_version: int | None = Field(default=None, ge=1)
    normal_interval_seconds: Literal[300] = 300
    hot_interval_seconds: Literal[180] = 180
    max_pages: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def paired_connection(self) -> MonitorConfiguration:
        if (self.connection_id is None) != (self.connection_version is None):
            raise ValueError("connection identity and version must be provided together")
        return self


class ScanAuthorization(CodexContract):
    connection_enabled: bool = False
    credentials_confirmed: bool = False
    owner_authorized: bool = False
    budget_confirmed: bool = False

    @property
    def allowed(self) -> bool:
        return all(
            (
                self.connection_enabled,
                self.credentials_confirmed,
                self.owner_authorized,
                self.budget_confirmed,
            )
        )


class MonitorView(CodexContract):
    id: UUID
    enabled: bool
    revision: int
    configuration_version: int
    configuration: MonitorConfiguration


class CodexConfigurationInput(CodexContract):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    enabled: bool = False
    configuration: MonitorConfiguration = Field(default_factory=MonitorConfiguration)


class CodexTickInput(CodexContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    lookback_hours: int | None = Field(default=None, ge=1, le=168)


class ContextPost(CodexContract):
    id: str = Field(pattern=r"^[0-9]{1,19}$")
    author: str = Field(min_length=1, max_length=128)
    relation: Literal["reply", "quote"]
    original_text: str = Field(min_length=1, max_length=100_000)
    text_zh: str | None = Field(default=None, max_length=100_000)
    published_at: datetime | None = None
    url: str = Field(
        max_length=2048,
        pattern=r"^https://x\.com/(?:[A-Za-z0-9_]{1,15}|i)/status/[0-9]{1,19}$",
    )

    @field_validator("published_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("context time must be timezone-aware")
        return value


class ResetPostInput(CodexContract):
    external_id: str = Field(pattern=r"^[0-9]{1,19}$")
    author: Literal["thsottiaux"] = "thsottiaux"
    published_at: datetime
    text: str = Field(min_length=1, max_length=100_000)
    url: str = Field(max_length=2048)
    context: tuple[ContextPost, ...] = Field(default=(), max_length=4)
    content_version_id: UUID | None = None
    source_receipt_ref: str | None = Field(default=None, max_length=256)
    origin: Literal["live", "lookback", "import"] = "live"

    @field_validator("published_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("post time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def fixed_source_evidence(self) -> ResetPostInput:
        if self.url != f"https://x.com/thsottiaux/status/{self.external_id}":
            raise ValueError("post URL must match the fixed author and source ID")
        if sum(c.relation == "reply" for c in self.context) > 2:
            raise ValueError("at most two reply levels are allowed")
        if len({(c.id, c.relation) for c in self.context}) != len(self.context):
            raise ValueError("context entries must be unique")
        return self


class StatedWords(CodexContract):
    precision: SchedulePrecision
    relative_hours: float | None = Field(default=None, ge=0, le=240)
    period: Literal["afternoon", "evening", "tonight", "end_of_day"] | None = None
    clock: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    clock_through: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    day_offset: int | None = Field(default=None, ge=-1, le=14)


class StatedTime(CodexContract):
    precision: SchedulePrecision
    date: str
    clock: str | None
    clock_through: str | None = None


class Schedule(CodexContract):
    precision: SchedulePrecision
    starts_at: datetime
    ends_at: datetime
    label: str = Field(max_length=256)

    @model_validator(mode="after")
    def valid_bounds(self) -> Schedule:
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("schedule must be timezone-aware")
        if self.ends_at < self.starts_at:
            raise ValueError("schedule bounds must be forward")
        return self


class Estimate(CodexContract):
    starts_at: datetime
    ends_at: datetime
    basis: Literal["model", "source", "source_day", "history"]
    label: str = Field(max_length=256)
    reason: str = Field(max_length=1000)

    @model_validator(mode="after")
    def valid_bounds(self) -> Estimate:
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("estimate must be timezone-aware")
        if self.ends_at <= self.starts_at:
            raise ValueError("estimate bounds must be forward")
        return self


class ExpectedLanding(CodexContract):
    earliest_pacific: str = Field(max_length=32)
    latest_pacific: str = Field(max_length=32)
    note: str = Field(max_length=500)


class ResetScope(CodexContract):
    audience_source: str | None = Field(default=None, max_length=500)
    plans: tuple[Annotated[str, Field(min_length=1, max_length=80)], ...] | None = Field(
        default=None, max_length=20
    )
    audience_zh: str | None = Field(default=None, max_length=500)
    products_zh: str | None = Field(default=None, max_length=500)


class Proposition(CodexContract):
    kind: ResetKind
    kind_explicit: bool = False
    action: ResetAction
    real: bool
    count: int = Field(default=1, ge=1, le=5)
    relates_to: str | None = Field(default=None, max_length=128)
    excerpt: str = Field(max_length=10_000)
    excerpt_zh: str = Field(default="", max_length=10_000)
    stated_time: StatedWords | None = None
    time_inferred: bool = False
    expected_landing: ExpectedLanding | None = None
    scope: ResetScope = ResetScope()


class ContextTranslation(CodexContract):
    id: str = Field(pattern=r"^[0-9]{1,19}$")
    text_zh: str = Field(max_length=100_000)


class Recognition(CodexContract):
    relevant: bool
    translation_zh: str | None = Field(default=None, max_length=100_000)
    context_zh: tuple[ContextTranslation, ...] = Field(default=(), max_length=4)
    outage: Literal["outage", "recovery"] | None = None
    needs_review: bool
    propositions: tuple[Proposition, ...] = Field(max_length=20)


class RecognitionInput(CodexContract):
    owner_id: UUID
    monitor_id: UUID
    post_id: UUID
    configuration_version: int
    projection_epoch: int
    review_version: int
    input_fingerprint: str
    post: ResetPostInput
    open_events: tuple[ResetEventView, ...]


class NotificationIntent(CodexContract):
    post_id: UUID
    event_id: str
    action: Literal["announce", "confirm", "amend", "withdraw"]
    content_at: datetime
    dedupe_key: str


class AppliedRecognition(CodexContract):
    status: Literal["applied", "held", "stale", "duplicate"]
    event_ids: tuple[str, ...] = ()
    notifications: tuple[NotificationIntent, ...] = ()
    notifications_enqueued: int = Field(default=0, ge=0)


class ResetPostView(CodexContract):
    id: UUID
    external_id: str
    published_at: datetime
    text: str
    translation_zh: str | None
    url: str
    context: tuple[ContextPost, ...]
    processed_at: datetime | None
    needs_review: bool
    reviewed: bool
    review_version: int
    failure_count: int
    failure_code: str | None
    event_ids: tuple[str, ...] = ()


class ResetEventPost(CodexContract):
    post_id: UUID
    external_id: str
    published_at: datetime
    action: ResetAction
    stage: str
    excerpt: str
    excerpt_zh: str
    original_text: str
    translation_zh: str | None
    url: str
    context: tuple[ContextPost, ...]


class ResetEventView(CodexContract):
    id: str
    kind: ResetKind
    status: Literal["announced", "confirmed"]
    revision: int
    created_at: datetime
    updated_at: datetime
    withdrawn: bool = False
    in_progress: bool = False
    kind_explicit: bool = False
    time_inferred: bool = False
    confirmed_at: datetime | None = None
    occurred_on: date | None = None
    confirmation_basis: Literal["source_post", "receipt_review"] | None = None
    schedule: Schedule | None = None
    estimate: Estimate | None = None
    scope: ResetScope = ResetScope()
    reported_at: datetime | None = None
    presentation_status: PresentationStatus = "announced"
    title: str = ""
    posts: tuple[ResetEventPost, ...] = ()


class ResetHealth(CodexContract):
    status: Literal["unknown", "attention", "delayed", "healthy"]
    enabled: bool
    last_attempt_at: datetime | None
    last_collected_at: datetime | None
    last_verified_at: datetime | None
    pending_count: int
    review_count: int
    held_window_count: int


class OutageView(CodexContract):
    post_id: UUID
    published_at: datetime
    original_text: str
    translation_zh: str | None
    recovered_at: datetime | None
    reset_event_id: str | None
    url: str


class CalendarMark(CodexContract):
    date: date
    event_id: str
    kind: ResetKind
    state: Literal["confirmed", "likely", "pending"]
    label: str


class ResetStatistics(CodexContract):
    resets_90: int
    credits_90: int
    median_interval_days: float | None
    last_reset_date: date | None


class ResetSnapshot(CodexContract):
    schema_version: Literal[1] = 1
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    today: date
    checked_at: datetime | None
    history_from: datetime | None
    events: tuple[ResetEventView, ...]
    activities: tuple[ResetPostView, ...]
    monitor: ResetHealth
    outage: OutageView | None
    calendar: tuple[CalendarMark, ...]
    statistics: ResetStatistics
    current: ResetEventView | None
    last_landed: ResetEventView | None
    confirm_minutes: tuple[int, ...]
    version: str


class ReviewInput(CodexContract):
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    actor: str = Field(min_length=1, max_length=128)

    @field_validator("reason", "actor")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("review reason and actor cannot be blank")
        return value.strip()


class EventPatch(CodexContract):
    kind: ResetKind | None = None
    status: Literal["announced", "confirmed"] | None = None
    schedule: Schedule | None = None
    scope: ResetScope | None = None
    confirmed_at: datetime | None = None
    occurred_on: date | None = None
    confirmation_basis: Literal["source_post", "receipt_review"] | None = None
    withdrawn: bool | None = None


class CodexPostReviewInput(CodexContract):
    action: Literal["skip", "reviewed", "retry"]
    review: ReviewInput


class CodexPostRelinkInput(CodexContract):
    from_event_id: str = Field(min_length=1, max_length=128)
    to_event_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_expected_revision: int | None = Field(default=None, ge=1)
    review: ReviewInput

    @model_validator(mode="after")
    def target_version_pair(self) -> Self:
        if (self.to_event_id is None) != (self.target_expected_revision is None):
            raise ValueError("a target event requires its explicit current revision")
        if not self.from_event_id.strip() or (
            self.to_event_id is not None and not self.to_event_id.strip()
        ):
            raise ValueError("event identities cannot be blank")
        return self


class CodexGapReviewInput(CodexContract):
    action: Literal["retry", "acknowledge"]
    review: ReviewInput


class CodexEventReviewInput(CodexContract):
    patch: EventPatch
    review: ReviewInput


class ScanResult(CodexContract):
    status: Literal["collected", "skipped", "blocked", "partial"]
    reason: str | None = None
    stored: int = 0
    pages: int = 0
    backlog: int = 0


class ScanGapView(CodexContract):
    id: UUID
    configuration_version: int
    monitor_revision: int
    query: str
    has_resume_token: bool
    stop_at_id: str | None
    before_id: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    state: Literal["pending", "held", "complete"]
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class ResetVersionView(CodexContract):
    version: str
    checked_at: datetime | None
    today: date


class CodexMonitorDue(CodexContract):
    owner_id: UUID
    monitor_id: UUID
    configuration_version: int
    monitor_revision: int
    due_at: datetime
    interval_seconds: int
    configuration: MonitorConfiguration


class CodexTickResult(CodexContract):
    status: Literal["succeeded", "partial", "blocked", "cancelled", "skipped"]
    reason: str | None = None
    collected: ScanResult | None = None
    processed: int = 0
    failed: int = 0
    notification_intents: tuple[NotificationIntent, ...] = ()
    notifications_enqueued: int = 0
    verified: bool = False


class CodexOperationalHealth(CodexContract):
    configured: bool
    enabled: bool
    monitor_id: UUID | None = None
    stuck_oldest_collected_at: datetime | None = None
    held_unreviewed_count: int = Field(default=0, ge=0)
