from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jobs.schemas import BudgetPolicyInput, BudgetWindowUsageView, JobContinuousFailureIssueView


class ScreenshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mime: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data_base64: str = Field(min_length=1, max_length=11184812)


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    content: str = Field(min_length=2, max_length=5000)
    email: str | None = Field(default=None, max_length=200)
    page_url: str | None = Field(default=None, max_length=500)
    screenshot: ScreenshotInput | None = None

    @field_validator("content", "email", "page_url")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        import re

        if len(self.content) < 2:
            raise ValueError("feedback needs at least two characters")
        if self.email and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email) is None:
            raise ValueError("invalid feedback email")
        if self.page_url:
            url = urlsplit(self.page_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
            ):
                raise ValueError("feedback URL must be public HTTP without credentials")
        return self


class FeedbackSubmissionView(BaseModel):
    id: UUID
    operation_id: UUID
    status: str
    replayed: bool = False


class FeedbackView(BaseModel):
    id: UUID
    revision: int
    content: str | None
    email: str | None
    page_url: str | None
    status: Literal["new", "reviewing", "resolved", "rejected", "deleted"]
    note: str | None
    source_ref: str
    banned: bool
    attachment_id: UUID | None
    attachment_mime: str | None
    created_at: datetime
    updated_at: datetime
    forwarded_at: datetime | None
    forward_error: str | None


class FeedbackUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    status: Literal["new", "reviewing", "resolved", "rejected", "deleted"]
    note: str | None = Field(default=None, max_length=2000)
    banned: bool | None = None

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason cannot be blank")
        return value.strip()


class OperatorAuditView(BaseModel):
    id: UUID
    operation_id: UUID
    action: str
    target_ref: str
    actor: str
    reason: str
    status: str
    before_state: dict[str, object]
    after_state: dict[str, object]
    job_id: UUID | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class DictionaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    expected_version: int = Field(ge=0)
    kind: Literal["glossary", "entities", "categories"]
    content: dict[str, list[str]] = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_bounded_words(self) -> Self:
        if not self.reason.strip():
            raise ValueError("reason cannot be blank")
        for key, aliases in self.content.items():
            if (
                not key.strip()
                or len(key) > 100
                or len(aliases) > 20
                or len(set(aliases)) != len(aliases)
            ):
                raise ValueError("dictionary entry is invalid")
            if any(not alias.strip() or len(alias) > 200 for alias in aliases):
                raise ValueError("dictionary aliases are invalid")
        return self


class DictionaryView(BaseModel):
    id: UUID
    kind: Literal["glossary", "entities", "categories"]
    version: int
    content: dict[str, list[str]]
    created_at: datetime


class BudgetUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    expected_policy_version: int = Field(ge=0)
    policy: BudgetPolicyInput


class ProcessHeartbeatView(BaseModel):
    role: str
    instance_id: str
    pid: int
    state: Literal["alive", "stopping", "error", "stale"]
    last_seen_at: datetime
    started_at: datetime
    age_seconds: int
    detail: dict[str, object]


class OperationsHealthView(BaseModel):
    generated_at: datetime
    heartbeats: list[ProcessHeartbeatView]
    failure_issues: list[JobContinuousFailureIssueView]
    budgets: list[BudgetWindowUsageView]
    feedback_new_count: int
    feedback_reviewing_count: int
    maintenance_enabled: bool
    feedback_forward_enabled: bool
    backup_configured: bool


class FeedbackUpdateView(BaseModel):
    id: UUID
    revision: int
    status: str
    replayed: bool = False


class MaintenanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    action: Literal[
        "lifecycle_sweep",
        "recover",
        "alerts",
        "digest",
        "source_health",
        "feedback_forward",
        "backup",
        "verify_backup",
        "retention",
        "watchdog",
    ]
    reason: str = Field(min_length=1, max_length=2000)
    backup_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if not self.reason.strip() or (self.action == "verify_backup") != (
            self.backup_id is not None
        ):
            raise ValueError("restore verification requires a backup identity and a reason")
        return self


class MaintenanceAcceptedView(BaseModel):
    job_id: UUID
    audit_id: UUID
    replayed: bool = False


class MaintenanceFindingView(BaseModel):
    key: str
    severity: Literal["now", "today", "digest"]
    title: str
    detail: str


class MaintenanceScheduleView(BaseModel):
    action: str
    interval_seconds: int
    enabled: bool
    latest_audit: OperatorAuditView | None


class MaintenanceStateView(BaseModel):
    schedules: list[MaintenanceScheduleView]
    findings: list[MaintenanceFindingView]
    backups: list[OperatorAuditView]


class AuditResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    outcome: Literal["delivered", "not_delivered"]

    @field_validator("reason")
    @classmethod
    def require_review(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operator confirmation needs a reason")
        return value.strip()
