"""HTTP-independent public and worker contracts for the model leaderboard."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from core.schemas import OutputModel

BoardKey = Literal["overall", "coding", "reasoning", "knowledge", "professional"]


class LeaderboardSourceHealthView(OutputModel):
    source_key: str
    enabled: bool
    checked_at: datetime | None
    last_successful_poll_at: datetime | None
    anchor_at: datetime | None
    failing: bool
    stale: bool


class FxQuoteView(OutputModel):
    as_of: date
    rate: float = Field(gt=0)
    source_name: str
    source_url: str | None


class RunView(OutputModel):
    id: UUID
    methodology_version: str
    generated_at: datetime
    calculated_at: datetime | None
    fingerprint: str
    fx: FxQuoteView | None


class BrandView(OutputModel):
    src: str | None
    monogram: str
    raster: bool = False


class ModelRefView(OutputModel):
    slug: str
    name: str
    provider: str | None
    released_at: date | None
    brand: BrandView


class AccessView(OutputModel):
    domestic: bool
    weights_url: str | None


class PriceView(OutputModel):
    currency: str
    input_price: float | None
    output_price: float | None
    cached_input_price: float | None
    cny_input_price: float | None
    cny_output_price: float | None
    cny_cached_input_price: float | None
    verified_on: date
    source_url: str
    unit: Literal["per_million_tokens"] = "per_million_tokens"


class StabilityView(OutputModel):
    from_rank: int
    to_rank: int
    fixed_from: int
    fixed_to: int
    scenarios: int
    sensitive: bool
    incomplete: int
    ordinal_rank: int
    unavailable: int


class RankingEntryView(OutputModel):
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=100)
    model: ModelRefView
    source_count: int = Field(ge=0)
    operator_count: int = Field(ge=0)
    coverage: float = Field(ge=0)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    stability: StabilityView | None
    price: PriceView | None
    access: AccessView


class BoardMetaView(OutputModel):
    key: BoardKey
    name: str
    description: str
    how_to_read: str
    source_count: int
    operator_count: int
    model_count: int
    solver_optimal: bool
    connected_components: int
    score_definition: str
    display_method: str
    max_optimization_gap: float
    observed_weighted_agreement: float


class BoardTabView(OutputModel):
    key: BoardKey
    name: str
    href: str


class PendingModelView(OutputModel):
    model: ModelRefView
    sources: int


class BoardView(OutputModel):
    run: RunView
    board: BoardMetaView
    tabs: list[BoardTabView]
    entries: list[RankingEntryView]
    filter_entries: list[RankingEntryView]
    pending: list[PendingModelView]


class CategoryRankView(OutputModel):
    key: BoardKey
    name: str
    rank: int | None
    score: float | None
    source_count: int
    on_board: bool


class EvidenceItemView(OutputModel):
    unit: str
    source_key: str
    source_name: str
    official_url: str | None
    protocol: str
    snapshot_id: UUID
    raw_score: float
    display: str
    source_rank: int | None
    source_model_name: str
    configuration_key: str
    configuration_label: str
    selection_reason: str
    upstream_at: datetime | None
    verified_at: datetime | None
    measured_at: datetime | None
    carried_forward: bool
    components: dict[str, Any]


class EvidenceGroupView(OutputModel):
    key: str
    name: str
    items: list[EvidenceItemView]


class MissingEvidenceView(OutputModel):
    key: str
    name: str
    reason: str | None = None


class ComparisonRowView(OutputModel):
    source_key: str
    source_name: str
    official_url: str | None
    mine: str
    theirs: str
    weight: float


class ComparisonView(OutputModel):
    model: ModelRefView
    rank: int
    net: float
    shared_weight: float
    shared_count: int
    has_page: bool
    rows: list[ComparisonRowView]


class ModelDetailView(OutputModel):
    run: RunView
    historical: bool
    model: ModelRefView
    context_window_tokens: int | None
    weights_url: str | None
    price: PriceView | None
    overall: CategoryRankView
    overall_stability: StabilityView | None
    categories: list[CategoryRankView]
    metric_count: int
    evidence: list[EvidenceGroupView]
    excluded: list[MissingEvidenceView]
    unmeasured: list[MissingEvidenceView]
    comparisons: list[ComparisonView]


class SourceSummaryView(OutputModel):
    key: str
    status: str
    name: str
    operator: str
    description: str
    brand: BrandView
    weight: float
    family_key: str | None
    category_key: str | None
    collected: bool


class SourceGroupView(OutputModel):
    key: str
    name: str
    blurb: str
    sources: list[SourceSummaryView]


class SourcesView(OutputModel):
    run: RunView | None
    groups: list[SourceGroupView]


class SourceRowView(OutputModel):
    source_rank: int | None
    source_model_name: str
    model_slug: str | None
    provider: str | None
    display: str
    configuration_label: str
    excluded: str | None


class SourceDetailView(OutputModel):
    run: RunView | None
    source: SourceSummaryView
    full_name: str
    area: str | None
    official_url: str | None
    what: str
    usage: str
    limits: str
    license: str
    attribution: str | None
    upstream_at: datetime | None
    synced_at: datetime | None
    collected: bool
    system_rows: bool
    rows: list[SourceRowView]
    rows_note: str | None


class BudgetView(OutputModel):
    key: str
    name: str
    weight: float
    sources: list[str]


class RulesView(OutputModel):
    run: RunView | None
    methodology_version: str
    score_definition: str
    display_method: str
    tie_policy: str
    budgets: list[BudgetView]
    anchors: list[str]
    configuration_policy: str
    carry_forward_days: int
    release_window_months: int
    overall_minimum_models: int = 10
    overall_minimum_anchors: int = 8
    category_minimum_models: int = 5
    category_minimum_anchors: int = 4


class RoundResultView(OutputModel):
    status: Literal["published", "refreshed", "unchanged", "failed"]
    run_id: UUID
    fingerprint: str
    boards: list[dict[str, Any]]
    reason: str | None = None


class SnapshotResultView(OutputModel):
    snapshot_id: UUID
    changed: bool
    rows: int
    selected: int
    new_models: int
