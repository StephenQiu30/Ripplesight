from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AttentionMode = Literal["editorial", "signal", "isolated"]
AttentionTrend = Literal["new", "up", "down", "flat", "unknown"]
ATTENTION_FORMULA_VERSION = "attention-v1-48h-halflife24h"


@dataclass(frozen=True)
class AttentionSource:
    id: UUID
    name: str
    mode: AttentionMode
    group_key: str | None
    owner_entity_key: str | None
    tier: Literal["T1", "T1_5", "T2"] | None
    first_party: bool
    created_at: datetime
    scheduled: bool
    interval_seconds: int
    last_successful_fetch_at: datetime | None

    @property
    def participant_key(self) -> str:
        if self.group_key:
            return "group:" + self.group_key
        if self.owner_entity_key:
            return "owner:" + self.owner_entity_key
        return "source:" + str(self.id)


@dataclass(frozen=True)
class AttentionEvidence:
    id: UUID
    source: AttentionSource
    content_id: UUID
    content_version_id: UUID
    source_time: datetime
    kind: Literal["editorial", "discussion", "native"]
    title: str | None = None
    canonical_url: str | None = None
    fact_id: UUID | None = None


class AttentionRosterView(BaseModel):
    participant_key: str
    source_id: UUID
    source_name: str
    mode: AttentionMode
    tier: Literal["T1", "T1_5", "T2"] | None
    first_party: bool
    source_time: datetime
    content_id: UUID
    content_version_id: UUID
    title: str | None
    canonical_url: str | None
    fact_id: UUID | None


class EventInteractionView(BaseModel):
    formula_version: str = "interaction-v1-ln"
    score: float | None
    post_count: int
    components: dict[str, float | None]
    unknown_masks: dict[str, list[str]]
    rising_state: Literal["rising", "steady", "insufficient"] = "insufficient"
    current_increment: float | None = None
    baseline_increment: float | None = None


class EventAttentionView(BaseModel):
    formula_version: str = ATTENTION_FORMULA_VERSION
    event_id: UUID | None = None
    event_revision: int | None = None
    window_end: datetime
    heat: float
    eligible: bool
    participant_count: int
    editorial_participant_count: int
    signal_participant_count: int
    comparable_participant_count: int
    uncomparable_participant_count: int
    previous_heat: float
    comparable_heat: float
    comparable_previous_heat: float
    trend: AttentionTrend
    trend_pct: float | None
    complete: bool
    badges: list[Literal["new", "surge", "rising"]]
    source_names: list[str]
    roster: list[AttentionRosterView]
    representative: AttentionRosterView | None
    interaction: EventInteractionView | None = None


class AttentionSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    selector_kind: Literal["source", "author", "native_scope", "canonical_host"]
    selector_ref: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=200)
    mode: AttentionMode
    group_key: str | None = Field(default=None, min_length=1, max_length=128)
    owner_entity_key: str | None = Field(default=None, min_length=1, max_length=128)
    first_party: bool = False
    tier: Literal["T1", "T1_5", "T2"] | None = None
    scheduled: bool = True
    enabled: bool = True
    interval_seconds: int = Field(default=1800, ge=300, le=604800)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("selector_ref", "name", "group_key", "owner_entity_key")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("identity must not be blank")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def canonical_selector(self) -> AttentionSourceInput:
        if self.selector_kind == "source" and self.selector_ref != self.source_key:
            raise ValueError("source selector_ref must equal source_key")
        if self.selector_kind == "canonical_host":
            self.selector_ref = self.selector_ref.casefold().rstrip(".")
            if any(character in self.selector_ref for character in "/:@ "):
                raise ValueError("canonical_host must be a hostname")
        return self


class AttentionSourceView(BaseModel):
    id: UUID
    source_key: str
    selector_kind: str
    selector_ref: str
    name: str
    revision: int
    mode: AttentionMode
    group_key: str | None
    owner_entity_key: str | None
    first_party: bool
    tier: Literal["T1", "T1_5", "T2"] | None
    scheduled: bool
    enabled: bool
    interval_seconds: int
    last_successful_fetch_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EventHotPageView(BaseModel):
    window_end: datetime
    items: list[EventAttentionView]


class EventAttentionHistoryView(BaseModel):
    event_id: UUID
    event_revision: int
    items: list[EventAttentionView]
