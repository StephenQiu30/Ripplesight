from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from itertools import permutations

import pytest

from leaderboard.configuration import (
    cloaked_model,
    configuration_of,
    model_slug,
    peel_effort_suffix,
    scaffolded,
)
from leaderboard.evidence import ParsedRow, select_representatives, stored_configuration_key
from leaderboard.method.constants import SCORING_SOURCES
from leaderboard.method.inputs import release_cutoff
from leaderboard.method.kemeny import reversal_cost, solve_kemeny
from leaderboard.method.run import input_fingerprint, publication_failure
from leaderboard.method.types import SignalRow
from leaderboard.method.v15 import pair_support
from leaderboard.registry import model_brand, registry_source, score_format, source_brand
from tests.unit.test_leaderboard_method import fixed_board


@pytest.mark.parametrize(
    "matrix",
    [
        [
            [0.0, 0.4, -0.8, 0.1],
            [-0.4, 0.0, 0.7, -0.6],
            [0.8, -0.7, 0.0, 0.9],
            [-0.1, 0.6, -0.9, 0.0],
        ],
        [
            [0.0, 1.0, 1.0, -2.0, 0.0],
            [-1.0, 0.0, 3.0, 0.0, -1.0],
            [-1.0, -3.0, 0.0, 1.0, 2.0],
            [2.0, 0.0, -1.0, 0.0, -4.0],
            [0.0, 1.0, -2.0, 4.0, 0.0],
        ],
    ],
)
def test_kemeny_matches_independent_exhaustive_oracle(matrix: list[list[float]]) -> None:
    optimum = min(reversal_cost(matrix, order) for order in permutations(range(len(matrix))))
    result = solve_kemeny(matrix, prefer=tuple(range(len(matrix))))
    assert result.optimal
    assert result.cost == pytest.approx(optimum, abs=1e-10)
    assert result.lower_bound == pytest.approx(optimum, abs=1e-10)


def test_representative_priority_never_selects_largest_score() -> None:
    low = ParsedRow("gpt-5-low", "GPT-5", configuration_of(["low"]), "unit", "Benchmark", 100.0)
    high = replace(
        low,
        source_model_name="gpt-5-high",
        configuration=configuration_of(["high"]),
        raw_score=40.0,
    )
    hybrid = replace(
        high,
        source_model_name="gpt-5-max-fallback",
        configuration=configuration_of(["max", "default fallback"]),
        raw_score=999.0,
    )
    selected = select_representatives((low, high, hybrid), ("model",) * 3, {"model": "gpt-5"})
    assert [row.row.raw_score for row in selected if row.selected] == [40.0]
    assert (
        next(row for row in selected if row.row is hybrid).selection_reason
        == hybrid.configuration.ineligible
    )
    assert stored_configuration_key(high) == "first_party:high@gpt-5-high"


def test_configuration_adaptive_scaffold_and_real_product_max() -> None:
    adaptive = configuration_of(["Adaptive Reasoning, Low Effort"])
    assert adaptive.rank == 452
    assert scaffolded(adaptive, ("codex-harness",), ("Codex Harness",)).rank == 451
    assert peel_effort_suffix("gpt-5-thinking-64k-high-effort") == ("gpt-5", "high-effort")
    assert peel_effort_suffix("qwen-3-max") == ("qwen-3-max", None)
    assert model_slug("GPT-4o") == "gpt-4-o"
    assert cloaked_model("openrouter/horizon-alpha:free")
    assert not cloaked_model("production-alpha")


def test_sources_missing_data_preserve_full_budget_and_registry_status() -> None:
    assert sum(source.weight for source in SCORING_SOURCES) == pytest.approx(1.0)
    assert len(SCORING_SOURCES) == 22
    assert {source.key for source in SCORING_SOURCES if not source.scoring} == {
        "artificial-analysis-multilingual",
        "tau-banking",
    }
    assert registry_source("artificial-analysis").source.license
    assert registry_source("does-not-exist") is None
    assert score_format("livebench-coding", 0.5) == "percent"
    assert score_format("epoch-gpqa", 0.5) == "fraction"


def test_public_brand_uses_deployed_monogram_without_advertising_absent_assets() -> None:
    model = model_brand("claude-test", "anthropic", "Anthropic", "Claude Test")
    source = source_brand(registry_source("artificial-analysis").source)
    assert model.monogram == "A" and model.src is None
    assert source.monogram == "A" and source.src is None and not source.raster


def test_soft_bounds_and_direction_and_ordinal_are_distinct() -> None:
    registry = replace(fixed_board().registry["one"], interval_sd=1.0)
    a = SignalRow(1.0, "a", "default", 0.0, 2.0)
    b = SignalRow(0.0, "b", "default", -1.0, 1.0)
    assert pair_support(a, b, registry) == pytest.approx(0.5204998778130465)
    assert pair_support(a, b, replace(registry, direction="LOWER")) == pytest.approx(
        -0.5204998778130465
    )
    assert pair_support(a, b, registry, ordinal=True) == 1.0


def test_failure_gate_does_not_publish_sparse_or_missing_public_boards() -> None:
    board = fixed_board()
    from leaderboard.method.v15 import compute_board

    reason = publication_failure((board,), (compute_board(board),))
    assert reason == "not publishable: overall, coding, reasoning, knowledge, professional"


def test_run_hash_ignores_evidence_verification_but_tracks_configuration_and_protocol() -> None:
    board = fixed_board()
    fingerprint = input_fingerprint((board,))
    altered = replace(
        board, registry={**board.registry, "one": replace(board.registry["one"], protocol="v2")}
    )
    assert input_fingerprint((altered,)) != fingerprint
    assert input_fingerprint((board,)) == fingerprint


def test_release_window_preserves_js_month_overflow() -> None:
    assert release_cutoff(datetime(2026, 8, 31, tzinfo=UTC)) == datetime(2025, 3, 3, tzinfo=UTC)


@pytest.mark.parametrize("matrix", [[[0.0, 1.0], [1.0, 0.0]], [[float("nan")]], [[0.0, 1.0]]])
def test_invalid_evidence_is_rejected_before_solving(matrix: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        solve_kemeny(matrix)
