"""Pure public contracts for fixed event heat records and their permission whitelist."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from events.heat_schemas import ATTENTION_FORMULA_VERSION

HistoryReason = Literal[
    "missing",
    "incomplete",
    "recomputed",
    "provenance_unknown",
    "invalid",
    "not_public",
    "capacity",
    "source_changed",
    "zero_baseline",
]
HistoryState = Literal["available", "insufficient_data", "unavailable"]


class PublicHeatPoint(BaseModel):
    """One hourly calculation, with a null value whenever its basis is unusable."""

    window_end: datetime
    computed_at: datetime | None = None
    value: float | None = None
    participant_count: int | None = None
    segment_key: str | None = None
    reason: HistoryReason | None = None


class PublicHeatTrend(BaseModel):
    """Six-hour comparison only when all seven hourly records remain comparable."""

    state: HistoryState
    reason: HistoryReason | None = None
    direction: Literal["up", "down", "flat"] | None = None
    percent: float | None = None


class PublicHeatHistory(BaseModel):
    """Current-revision, delayed calculation records, not platform native metrics."""

    state: HistoryState
    reason: HistoryReason | None = None
    formula_version: str = ATTENTION_FORMULA_VERSION
    event_revision: int
    snapshot_at: datetime
    points: list[PublicHeatPoint]
    trend: PublicHeatTrend
    scope: Literal["current_public_reports"] = "current_public_reports"
    time_basis: Literal["delayed_hourly_calculation"] = "delayed_hourly_calculation"


@dataclass(frozen=True, slots=True)
class PublicHeatReference:
    """Exact already-public report identity supplied by the permission owner."""

    content_id: UUID
    version_id: UUID
    observation_id: UUID
