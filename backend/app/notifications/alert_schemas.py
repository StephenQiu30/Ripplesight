from datetime import datetime
from math import isfinite
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.schemas import InputModel, OutputModel

AlertMetric = Literal["negative_count", "heat_increment"]


class AlertRuleInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    topic_id: UUID
    topic_rule_version: int = Field(ge=1)
    event_id: UUID | None = None
    metric: AlertMetric
    threshold: float = Field(gt=0, le=1_000_000_000)
    cooldown_seconds: int = Field(ge=300, le=86400)
    target_id: UUID
    target_revision: int = Field(ge=1)
    enabled: bool = False

    @model_validator(mode="after")
    def exact_metric(self) -> Self:
        self.name = self.name.strip()
        if not self.name or not isfinite(self.threshold):
            raise ValueError("alert name and threshold must be finite")
        if self.metric == "negative_count" and (
            self.event_id is not None or not self.threshold.is_integer()
        ):
            raise ValueError("negative count needs an integer threshold without an event")
        if self.metric == "heat_increment" and self.event_id is None:
            raise ValueError("heat increment requires an exact event")
        return self


class AlertRuleView(OutputModel):
    id: UUID
    name: str
    revision: int
    enabled: bool
    topic_id: UUID
    topic_rule_version: int
    event_id: UUID | None
    metric: AlertMetric
    threshold: float
    cooldown_seconds: int
    target_id: UUID
    target_revision: int
    readiness: Literal["ready", "blocked"]
    reason: str | None
    last_trigger_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertTargetView(OutputModel):
    id: UUID
    name: str
    revision: int
    eligible: bool
    reason: str | None


class AlertEvaluationView(OutputModel):
    id: UUID
    rule_id: UUID
    rule_version: int
    window_start: datetime
    window_end: datetime
    status: Literal["blocked", "unknown", "below_threshold", "cooldown", "triggered", "withdrawn"]
    reason: str | None
    value: float | None
    cooldown_until: datetime | None
    created_at: datetime
