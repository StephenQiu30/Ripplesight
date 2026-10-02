"""Public consensus v15: support votes, exact ordering and uncertainty disclosures.

Ported from AIHOT 035f7b7 under MIT. Budgets, anchor scale and stability scenarios
are part of the published method; they must change together with METHOD_VERSION.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from itertools import pairwise
from math import exp, floor, isfinite, sqrt

from leaderboard.method.constants import DISPLAY_METHOD, SCORE_DEFINITION
from leaderboard.method.kemeny import solve_kemeny
from leaderboard.method.ndtr import ndtr
from leaderboard.method.types import (
    BoardEntry,
    BoardInput,
    BoardOutput,
    Comparison,
    DisplayGap,
    DisplaySummary,
    NetMatrix,
    RegistryEntry,
    SignalRow,
    SolverSummary,
    Stability,
)


def pair_support(
    a: SignalRow, b: SignalRow, registry: RegistryEntry, *, ordinal: bool = False
) -> float:
    diff = a.score - b.score
    if registry.direction == "LOWER":
        diff = -diff
    sign = float((diff > 0) - (diff < 0))
    if (
        ordinal
        or registry.interval_sd is None
        or a.lower_bound is None
        or a.upper_bound is None
        or b.lower_bound is None
        or b.upper_bound is None
    ):
        return sign
    if registry.interval_sd <= 0:
        raise ValueError("Published interval standard-error multiplier must be positive")
    sa = (a.upper_bound - a.lower_bound) / (2 * registry.interval_sd)
    sb = (b.upper_bound - b.lower_bound) / (2 * registry.interval_sd)
    se = sqrt(sa * sa + sb * sb)
    return 2 * ndtr(diff / se) - 1 if se > 0 else sign


def net_matrix(
    input_: BoardInput,
    *,
    weight_scale: dict[str, float] | None = None,
    ordinal: bool = False,
    units: Sequence[str] | None = None,
) -> NetMatrix:
    models = input_.models
    if len(set(models)) != len(models):
        raise ValueError("Board model identifiers must be unique")
    index = {model: position for position, model in enumerate(models)}
    n = len(models)
    support = [[0.0] * n for _ in range(n)]
    shared_weight = [[0.0] * n for _ in range(n)]
    direct_count = [[0] * n for _ in range(n)]
    for signal in input_.signals:
        if units is not None and signal.key not in units:
            continue
        registry = input_.registry.get(signal.key)
        if registry is None:
            continue
        weight = registry.weight * (weight_scale or {}).get(signal.key, 1.0)
        if not isfinite(weight) or weight < 0:
            raise ValueError("Evidence weights must be finite and nonnegative")
        if not weight:
            continue
        rows = tuple(row for row in signal.rows if row.model_slug in index)
        if len({row.model_slug for row in rows}) != len(rows):
            raise ValueError("A unit may contain one representative row per model")
        if any(not isfinite(row.score) for row in rows):
            raise ValueError("Evidence scores must be finite")
        for position, a in enumerate(rows):
            for b in rows[position + 1 :]:
                p = weight * pair_support(a, b, registry, ordinal=ordinal)
                ia, ib = index[a.model_slug], index[b.model_slug]
                support[ia][ib] += p
                support[ib][ia] -= p
                shared_weight[ia][ib] += weight
                shared_weight[ib][ia] += weight
                direct_count[ia][ib] += 1
                direct_count[ib][ia] += 1
    return NetMatrix(models, index, support, shared_weight, direct_count)


def connected_components(weights: Sequence[Sequence[float]]) -> int:
    seen: set[int] = set()
    count = 0
    for start in range(len(weights)):
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            vertex = stack.pop()
            for target, weight in enumerate(weights[vertex]):
                if target not in seen and weight > 0:
                    seen.add(target)
                    stack.append(target)
    return count


def _logistic(x: float) -> float:
    if x >= 0:
        return 1 / (1 + exp(-x))
    value = exp(x)
    return value / (1 + value)


def _round_positive(value: float, digits: int) -> float:
    factor = float(10**digits)
    return floor(value * factor + 0.5) / factor


def compute_board(input_: BoardInput, *, time_limit_seconds: float = 300) -> BoardOutput:
    net = net_matrix(input_)
    models, matrix = net.models, net.support
    base = solve_kemeny(
        matrix, prefer=tuple(range(len(models))), time_limit_seconds=time_limit_seconds
    )
    order = base.order
    max_gap = max(0.0, base.cost - base.lower_bound)
    gaps: list[DisplayGap] = []
    for higher, lower in pairwise(order):
        reversed_pair = solve_kemeny(
            matrix, force=((lower, higher),), time_limit_seconds=time_limit_seconds
        )
        max_gap = max(max_gap, max(0.0, reversed_pair.cost - reversed_pair.lower_bound))
        gaps.append(
            DisplayGap(max(0.0, reversed_pair.cost - base.cost), models[lower], models[higher])
        )
    cumulative = [0.0] * len(models)
    for position in range(len(models) - 2, -1, -1):
        cumulative[position] = cumulative[position + 1] + gaps[position].gap
    positions = {models[index]: position for position, index in enumerate(order)}
    anchor_values = tuple(
        cumulative[positions[anchor]] for anchor in input_.anchors if anchor in positions
    )
    base_rank = {slug: position + 1 for slug, position in positions.items()}
    all_units = tuple(signal.key for signal in input_.signals)

    def scenario_ranks(
        candidates: tuple[str, ...],
        *,
        units: Sequence[str] | None = None,
        weight_scale: dict[str, float] | None = None,
        ordinal: bool = False,
    ) -> tuple[dict[str, int], bool]:
        subset = replace(input_, models=tuple(sorted(candidates)))
        scenario = net_matrix(subset, units=units, weight_scale=weight_scale, ordinal=ordinal)
        preferred = tuple(
            sorted(
                range(len(scenario.models)),
                key=lambda index: (base_rank.get(scenario.models[index], 10**9), index),
            )
        )
        result = solve_kemeny(
            scenario.support, prefer=preferred, time_limit_seconds=time_limit_seconds
        )
        return {
            scenario.models[index]: position + 1 for position, index in enumerate(result.order)
        }, result.optimal

    scenarios: list[tuple[dict[str, int], dict[str, int], bool]] = []
    for key, qualification in input_.qualification_scenarios.items():
        kind, _, name = key.partition(":")
        remaining = tuple(
            unit
            for unit in all_units
            if (input_.registry[unit].operator != name if kind == "operator" else unit != name)
        )
        requal, requal_ok = (
            scenario_ranks(qualification.models, units=qualification.units)
            if qualification.models
            else ({}, True)
        )
        fixed, fixed_ok = scenario_ranks(input_.models, units=remaining)
        scenarios.append((requal, fixed, requal_ok and fixed_ok))
    for unit in all_units:
        for factor in (0.8, 1.2):
            ranks, ok = scenario_ranks(input_.models, weight_scale={unit: factor})
            scenarios.append((ranks, ranks, ok))
    ordinal_ranks, ordinal_ok = scenario_ranks(input_.models, ordinal=True)
    scenarios.append((ordinal_ranks, ordinal_ranks, ordinal_ok))

    def units_of(slug: str) -> tuple[str, ...]:
        return tuple(
            signal.key
            for signal in input_.signals
            if signal.key in input_.registry
            and input_.registry[signal.key].weight
            and any(row.model_slug == slug for row in signal.rows)
        )

    entries: list[BoardEntry] = []
    for position, index in enumerate(order):
        slug, rank = models[index], position + 1
        from_rank = to_rank = fixed_from = fixed_to = rank
        unavailable = incomplete = 0
        for requal, fixed, ok in scenarios:
            incomplete += not ok
            if slug not in requal:
                unavailable += 1
            else:
                from_rank, to_rank = min(from_rank, requal[slug]), max(to_rank, requal[slug])
            if slug in fixed:
                fixed_from, fixed_to = min(fixed_from, fixed[slug]), max(fixed_to, fixed[slug])
        units = units_of(slug)
        score = (
            (
                100
                * sum(_logistic(cumulative[position] - anchor) for anchor in anchor_values)
                / len(anchor_values)
            )
            if anchor_values
            else 50.0
        )
        stability = Stability(
            from_rank,
            to_rank,
            fixed_from,
            fixed_to,
            len(scenarios),
            to_rank - from_rank >= 3
            or fixed_to - fixed_from >= 3
            or unavailable > 0
            or incomplete > 0,
            incomplete,
            ordinal_ranks.get(slug, rank),
            unavailable,
        )
        entries.append(
            BoardEntry(
                input_.names.get(slug, slug),
                rank,
                slug,
                _round_positive(score, 1),
                _round_positive(sum(input_.registry[unit].weight for unit in units), 9),
                stability,
                len(units),
                len({input_.registry[unit].operator for unit in units}),
            )
        )
    top = order[:30]
    comparisons = {
        models[index]: tuple(
            Comparison(
                matrix[index][other],
                models[other],
                net.shared_weight[index][other],
                net.direct_count[index][other],
            )
            for other in top
            if other != index
        )
        for index in order
    }
    agree = total = 0.0
    for signal in input_.signals:
        registry = input_.registry.get(signal.key)
        if registry is None or not registry.weight:
            continue
        rows = tuple(row for row in signal.rows if row.model_slug in base_rank)
        for position, a in enumerate(rows):
            for b in rows[position + 1 :]:
                p = pair_support(a, b, registry)
                sign = 1 if base_rank[a.model_slug] < base_rank[b.model_slug] else -1
                agree += registry.weight * (1 + p * sign) / 2
                total += registry.weight
    components = connected_components(net.shared_weight)
    return BoardOutput(
        input_.board,
        SolverSummary(
            base.optimal, base.lower_bound, max(0.0, base.cost - base.lower_bound), base.cost
        ),
        DisplaySummary(tuple(gaps), DISPLAY_METHOD, max_gap),
        tuple(entries),
        comparisons,
        len(models),
        len(input_.signals),
        sum(entry.weight for entry in input_.registry.values()),
        SCORE_DEFINITION,
        components,
        components == 1,
        agree / total if total else 0.0,
    )
