"""Immutable inputs and outputs of the versioned leaderboard calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Direction = Literal["HIGHER", "LOWER"]
Matrix = list[list[float]]


@dataclass(frozen=True, slots=True)
class Policy:
    sources: int
    families: int
    operators: int
    categories: int
    direct_anchors: int


@dataclass(frozen=True, slots=True)
class ScoringSource:
    key: str
    unit: str
    weight: float
    family: str
    operator: str
    budget: str
    category: str | None
    scoring: bool
    interval_sd: float | None
    direction: Direction


@dataclass(frozen=True, slots=True)
class SignalRow:
    score: float
    model_slug: str
    configuration: str
    lower_bound: float | None = None
    upper_bound: float | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    key: str
    rows: tuple[SignalRow, ...]


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    family: str
    weight: float
    operator: str
    protocol: str
    direction: Direction
    interval_sd: float | None


@dataclass(frozen=True, slots=True)
class QualificationScenario:
    units: tuple[str, ...]
    models: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoardInput:
    board: str
    names: dict[str, str]
    models: tuple[str, ...]
    policy: Policy
    anchors: tuple[str, ...]
    signals: tuple[Signal, ...]
    registry: dict[str, RegistryEntry]
    qualification_scenarios: dict[str, QualificationScenario]


@dataclass(frozen=True, slots=True)
class Snapshot:
    id: str
    source_key: str
    fetched_at: datetime
    published_at: datetime | None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScoreRow:
    snapshot_id: str
    metric_key: str
    slug: str
    name: str
    released_at: datetime | None
    raw_score: float | None
    lower_bound: float | None
    upper_bound: float | None
    configuration_key: str
    selected_for_product: bool
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceMeta:
    unit: str
    operator: str
    protocol: str
    snapshot_id: str
    verified_at: str | None
    evaluated_at: str | None
    published_at: str | None
    configuration: str
    carried_forward: bool
    configuration_policy: str


@dataclass(frozen=True, slots=True)
class SourceUse:
    key: str
    weight: float
    family_key: str
    category_key: str | None
    used_in_overall: bool
    used_in_category: bool
    evidence_budget_key: str


@dataclass(frozen=True, slots=True)
class CategoryAvailability:
    key: str
    status: Literal["READY", "INSUFFICIENT"]
    model_count: int
    metric_count: int
    source_count: int
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunInputs:
    at: datetime
    snapshot_ids: tuple[str, ...]
    boards: tuple[BoardInput, ...]
    evidence: dict[str, EvidenceMeta]
    sources: tuple[SourceUse, ...]
    categories: tuple[CategoryAvailability, ...]


@dataclass(frozen=True, slots=True)
class KemenyResult:
    order: tuple[int, ...]
    cost: float
    lower_bound: float
    optimal: bool


@dataclass(frozen=True, slots=True)
class Stability:
    from_rank: int
    to_rank: int
    fixed_from: int
    fixed_to: int
    scenarios: int
    sensitive: bool
    incomplete: int
    ordinal_rank: int
    unavailable: int


@dataclass(frozen=True, slots=True)
class BoardEntry:
    name: str
    rank: int
    slug: str
    score: float
    coverage: float
    stability: Stability
    source_count: int
    operator_count: int


@dataclass(frozen=True, slots=True)
class SolverSummary:
    optimal: bool
    lower_bound: float
    absolute_gap: float
    reversal_cost: float


@dataclass(frozen=True, slots=True)
class DisplayGap:
    gap: float
    lower: str
    higher: str


@dataclass(frozen=True, slots=True)
class DisplaySummary:
    gaps: tuple[DisplayGap, ...]
    method: str
    max_optimization_gap: float


@dataclass(frozen=True, slots=True)
class Comparison:
    net: float
    slug: str
    shared: float
    direct_count: int


@dataclass(frozen=True, slots=True)
class BoardOutput:
    board: str
    solver: SolverSummary
    display: DisplaySummary
    entries: tuple[BoardEntry, ...]
    comparisons: dict[str, tuple[Comparison, ...]]
    model_count: int
    source_count: int
    active_budget: float
    score_definition: str
    connected_components: int
    publishable_connectivity: bool
    observed_weighted_agreement: float


@dataclass(frozen=True, slots=True)
class NetMatrix:
    models: tuple[str, ...]
    index: dict[str, int]
    support: Matrix
    shared_weight: Matrix
    direct_count: list[list[int]]
