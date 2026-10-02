"""Exact weighted incomplete Kemeny ILP with lazy transitivity constraints.

AIHOT kemeny.ts, MIT, ported to the official highspy interface. No network IO.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isclose, isfinite

from leaderboard.method.types import KemenyResult


class KemenyError(RuntimeError):
    """The solver could not produce a usable incumbent; keep the last public run."""


def _validate(matrix: Sequence[Sequence[float]]) -> int:
    n = len(matrix)
    if any(len(row) != n for row in matrix):
        raise ValueError("Kemeny matrix must be square")
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if not isfinite(value):
                raise ValueError("Kemeny matrix must contain finite values")
            if (i == j and value != 0) or not isclose(value, -matrix[j][i], abs_tol=1e-12):
                raise ValueError("Kemeny matrix must be antisymmetric with a zero diagonal")
    return n


def reversal_cost(matrix: Sequence[Sequence[float]], order: Sequence[int]) -> float:
    return sum(max(0.0, -matrix[a][b]) for p, a in enumerate(order) for b in order[p + 1 :])


def solve_kemeny(
    matrix: Sequence[Sequence[float]],
    *,
    force: Sequence[tuple[int, int]] = (),
    prefer: Sequence[int] | None = None,
    time_limit_seconds: float = 300,
) -> KemenyResult:
    """Minimise reversed net support, then pair disagreements with ``prefer``.

    Nonoptimal incumbents carry their lower bound and cannot become public runs.
    A solver failure never falls back to a fabricated average-score ranking.
    """
    import highspy  # Runtime load: registry/read operations do not initialise a solver.

    n = _validate(matrix)
    if prefer is not None and sorted(prefer) != list(range(n)):
        raise ValueError("Preferred order must be a permutation of all matrix indices")
    if not isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("Solver time limit must be positive and finite")
    for a, b in force:
        if a == b or not 0 <= a < n or not 0 <= b < n:
            raise ValueError("Forced pair must contain distinct valid indices")
    if n <= 1:
        return KemenyResult(tuple(range(n)), 0.0, 0.0, True)
    solver = highspy.Highs()  # type: ignore[no-untyped-call]  # Official constructor has no annotation.
    for key, value in {
        "output_flag": False,
        "mip_rel_gap": 0.0,
        "mip_abs_gap": 0.0,
        "random_seed": 0,
        "time_limit": time_limit_seconds,
        "threads": 1,
    }.items():
        if solver.setOptionValue(key, value) == highspy.HighsStatus.kError:
            raise KemenyError(f"HiGHS rejected option {key}")

    def col(i: int, j: int) -> int:
        return i * n - i * (i + 1) // 2 + j - i - 1

    nv = n * (n - 1) // 2
    lower, upper = [0.0] * nv, [1.0] * nv
    for a, b in force:
        if a < b:
            lower[col(a, b)] = 1.0
        else:
            upper[col(b, a)] = 0.0
    costs, constant = [0.0] * nv, 0.0
    for i in range(n):
        for j in range(i + 1, n):
            k = col(i, j)
            costs[k] = -matrix[i][j]
            constant += max(0.0, matrix[i][j])
            solver.addVar(lower[k], upper[k])
            solver.changeColCost(k, costs[k])
            solver.changeColIntegrality(k, highspy.HighsVarType.kInteger)
    added: set[tuple[int, int, int, bool]] = set()

    def transitive() -> tuple[tuple[int, ...], bool]:
        optimal = True
        while True:
            status = solver.run()
            model_status = solver.getModelStatus()
            if status == highspy.HighsStatus.kError:
                raise KemenyError("HiGHS failed to solve the Kemeny model")
            if model_status != highspy.HighsModelStatus.kOptimal:
                optimal = False
            solution = solver.getSolution()
            if not solution.value_valid or len(solution.col_value) != nv:
                raise KemenyError(
                    f"No Kemeny incumbent: {solver.modelStatusToString(model_status)}"
                )
            x = solution.col_value

            def y(i: int, j: int, values: Sequence[float] = x) -> int:
                return int(values[col(i, j)] > 0.5)

            violations = 0
            for i in range(n):
                for j in range(i + 1, n):
                    a = y(i, j)
                    for k in range(j + 1, n):
                        b, c = y(j, k), y(i, k)
                        positive = a + b - c > 1
                        negative = c - a - b > 0
                        if not positive and not negative:
                            continue
                        key = (i, j, k, positive)
                        if key in added:
                            continue
                        added.add(key)
                        violations += 1
                        solver.addRow(
                            -highspy.kHighsInf,
                            1.0 if positive else 0.0,
                            3,
                            [col(i, j), col(j, k), col(i, k)],
                            [1.0, 1.0, -1.0] if positive else [-1.0, -1.0, 1.0],
                        )
            if violations == 0 or not optimal:
                wins = [0] * n
                for i in range(n):
                    for j in range(i + 1, n):
                        wins[i if y(i, j) else j] += 1
                return tuple(sorted(range(n), key=lambda p: -wins[p])), optimal and violations == 0

    try:
        first_order, optimal = transitive()
        lower_bound = float(solver.getInfo().mip_dual_bound) + constant
        best = reversal_cost(matrix, first_order)
        order = first_order
        if prefer is not None and optimal:
            positions = {model: position for position, model in enumerate(prefer)}
            for i in range(n):
                for j in range(i + 1, n):
                    solver.changeColCost(col(i, j), -1.0 if positions[i] < positions[j] else 1.0)
            slack = 1e-9 * max(1.0, constant)
            solver.addRow(-highspy.kHighsInf, best - constant + slack, nv, list(range(nv)), costs)
            second_order, second_optimal = transitive()
            if second_optimal and reversal_cost(matrix, second_order) <= best + slack:
                order = second_order
        return KemenyResult(order, reversal_cost(matrix, order), lower_bound, optimal)
    finally:
        solver.clear()
