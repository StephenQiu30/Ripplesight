from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isclose

import pytest

from leaderboard.method.inputs import build_run_inputs, protocol_of
from leaderboard.method.kemeny import reversal_cost, solve_kemeny
from leaderboard.method.ndtr import ndtr
from leaderboard.method.types import (
    BoardInput,
    Policy,
    RegistryEntry,
    ScoreRow,
    ScoringSource,
    Signal,
    SignalRow,
    Snapshot,
)
from leaderboard.method.v15 import compute_board, net_matrix
from leaderboard.read import filter_entries


def test_weighted_cycle_uses_exact_kemeny_and_retains_solver_bound() -> None:
    matrix = [[0.0, 3.0, -1.0], [-3.0, 0.0, 2.0], [1.0, -2.0, 0.0]]
    result = solve_kemeny(matrix, prefer=(0, 1, 2))
    assert result.order == (0, 1, 2)
    assert result.optimal
    assert result.cost == result.lower_bound == 1.0
    assert reversal_cost(matrix, (2, 0, 1)) == 2.0
    forced = solve_kemeny(matrix, force=((1, 0),))
    assert forced.order.index(1) < forced.order.index(0)
    assert forced.cost == 3.0


def test_equal_evidence_uses_preferred_order_in_second_stage() -> None:
    result = solve_kemeny([[0.0] * 3 for _ in range(3)], prefer=(2, 0, 1))
    assert result.order == (2, 0, 1)
    assert result.optimal and result.cost == 0.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-10.0, 7.61985302416047e-24),
        (-1.0, 0.15865525393145707),
        (0.0, 0.5),
        (1.0, 0.8413447460685429),
        (10.0, 1.0),
    ],
)
def test_cephes_cdf_matches_fixed_reference(value: float, expected: float) -> None:
    assert isclose(ndtr(value), expected, rel_tol=1e-13, abs_tol=1e-30)


def fixed_board() -> BoardInput:
    rows = tuple(
        SignalRow(score=score, model_slug=slug, configuration="default")
        for slug, score in [("a", 3.0), ("b", 2.0), ("c", 1.0)]
    )
    registry = {
        "one": RegistryEntry("f1", 0.4, "op1", "v1", "HIGHER", None),
        "two": RegistryEntry("f2", 0.6, "op2", "v1", "HIGHER", None),
    }
    return BoardInput(
        board="overall",
        names={slug: slug.upper() for slug in ("a", "b", "c")},
        models=("a", "b", "c"),
        policy=Policy(1, 1, 1, 0, 1),
        anchors=("a", "c"),
        signals=(Signal("one", rows), Signal("two", rows)),
        registry=registry,
        qualification_scenarios={},
    )


def test_fixed_v15_ranks_support_scores_and_missing_share_not_renormalized() -> None:
    board = fixed_board()
    result = compute_board(board)
    assert [(e.slug, e.rank, e.score) for e in result.entries] == [
        ("a", 1, 69.0),
        ("b", 2, 50.0),
        ("c", 3, 31.0),
    ]
    assert result.solver.optimal and result.publishable_connectivity
    assert result.active_budget == 1.0
    missing = net_matrix(board, units=("one",))
    assert missing.support[0][1] == missing.shared_weight[0][1] == 0.4
    assert missing.direct_count[0][1] == 1


def test_open_weight_and_domestic_filters_do_not_recompute_rank() -> None:
    result = compute_board(fixed_board())
    filtered = filter_entries(
        result.entries,
        domestic=True,
        open_weights=True,
        domestic_slugs=frozenset({"b", "c"}),
        weight_urls={"c": "https://example.org/c"},
    )
    assert [(e.slug, e.rank, e.score) for e in filtered] == [("c", 3, 31.0)]


def test_protocol_change_and_explicit_exclusion_never_revive_old_score() -> None:
    at = datetime(2026, 10, 2, tzinfo=UTC)
    sources = (
        ScoringSource("one", "unit", 0.3, "f", "op", "coding", "coding", True, None, "HIGHER"),
    )
    snapshots = (
        Snapshot("new", "one", at, None, {"benchmarkVersion": "v2"}),
        Snapshot("old", "one", at - timedelta(days=1), None, {"benchmarkVersion": "v1"}),
    )
    scores = (
        ScoreRow("new", "unit", "a", "A", None, None, None, None, "excluded", False),
        ScoreRow("old", "unit", "a", "A", None, 100.0, None, None, "old", True),
    )
    run = build_run_inputs(
        snapshots,
        scores,
        at=at,
        sources=sources,
        anchors=("a",),
        overall_policy=Policy(1, 1, 1, 0, 0),
    )
    assert run.boards == ()
    assert run.evidence == {}
    assert protocol_of("one", snapshots[0].metadata) != protocol_of("one", snapshots[1].metadata)


def test_same_protocol_missing_model_carries_forward_only_seven_days() -> None:
    at = datetime(2026, 10, 2, tzinfo=UTC)
    sources = (
        ScoringSource("one", "unit", 0.3, "f", "op", "coding", "coding", True, None, "HIGHER"),
    )
    snapshots = (
        Snapshot("new", "one", at, None, {}),
        Snapshot("recent", "one", at - timedelta(days=2), None, {}),
        Snapshot("expired", "one", at - timedelta(days=8), None, {}),
    )
    scores = tuple(
        ScoreRow(sid, "unit", slug, slug, None, value, None, None, "default", True)
        for sid, slug, value in [("new", "a", 3.0), ("recent", "b", 2.0), ("expired", "c", 1.0)]
    )
    run = build_run_inputs(
        snapshots,
        scores,
        at=at,
        sources=sources,
        anchors=("a",),
        overall_policy=Policy(1, 1, 1, 0, 0),
    )
    board = next(b for b in run.boards if b.board == "overall")
    assert board.models == ("a", "b")
    assert run.evidence["unit:b"].carried_forward
    assert not run.evidence["unit:a"].carried_forward
    assert board.registry["unit"].weight == 0.3
