from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.schemas import InputModel, OutputModel


class ReportEmailSubscriptionInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    enabled: bool


class ReportEmailSubscriptionView(OutputModel):
    email: str | None
    enabled: bool
    revision: int
    target_name: str
    delivery_available: bool
    email_matches_target: bool


type NotificationSubjectKind = Literal["report", "edition", "selected", "codex_reset"]


class NotificationChannel(StrEnum):
    FEISHU = "feishu"
    EMAIL = "email"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80)
    channel: NotificationChannel
    recipients: tuple[str, ...] = Field(default=(), max_length=20)
    secret_env: str | None = Field(default=None, max_length=128)
    enabled: bool = False
    subscriptions: tuple[NotificationSubjectKind, ...] = Field(default=("report",), max_length=4)

    @field_validator("secret_env")
    @classmethod
    def validate_secret_env(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"HOTKEY_[A-Z][A-Z0-9_]*", value) is None:
            raise ValueError("secret_env must name a HOTKEY_ environment variable")
        return value

    @model_validator(mode="after")
    def require_target(self) -> Self:
        if not self.name.strip() or len(set(self.subscriptions)) != len(self.subscriptions):
            raise ValueError("invalid target identity or subscriptions")
        if self.channel is NotificationChannel.FEISHU and self.recipients:
            raise ValueError("webhook has no email recipients")
        if self.channel is NotificationChannel.EMAIL and (
            not self.recipients
            or any(
                re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", address) is None
                or len(address) > 200
                for address in self.recipients
            )
        ):
            raise ValueError("email recipients must be explicit valid addresses")
        return self


class TargetView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    channel: NotificationChannel
    recipients: tuple[str, ...]
    secret_env: str | None
    enabled: bool
    revision: int = Field(ge=1)
    enabled_at: datetime | None
    subscriptions: tuple[NotificationSubjectKind, ...]
    created_at: datetime


class TargetSaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    target_id: UUID | None = None
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)
    target: TargetInput

    @model_validator(mode="after")
    def require_version(self) -> Self:
        if not self.reason.strip() or (self.target_id is None) != (self.expected_revision == 0):
            raise ValueError("target identity, version and reason are required")
        return self


class NotificationDeliveryView(BaseModel):
    id: UUID
    revision: int
    target_id: UUID
    target_revision: int
    subject_kind: NotificationSubjectKind
    subject_id: UUID
    subject_revision: int
    status: DeliveryStatus
    attempt_count: int
    last_error_code: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    provider_receipt: dict[str, object]


class DeliveryResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    outcome: Literal["delivered", "not_delivered"]

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resolution evidence is required")
        return value


class NotificationSubjectMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: NotificationSubjectKind
    subject_id: UUID
    revision: int = Field(ge=1)
    dedupe_key: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=400)
    text: str = Field(max_length=200000)
    reading_url: str = Field(min_length=1, max_length=2048)
    expires_at: datetime | None = None
    locator: dict[str, object] = Field(default_factory=dict)

    @field_validator("occurred_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("notification material time must be aware")
        return value
