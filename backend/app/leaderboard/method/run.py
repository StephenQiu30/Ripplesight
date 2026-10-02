"""Run-level reproducibility and publication gates; failures preserve public state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from leaderboard.method.constants import ANCHORS, METHOD_VERSION
from leaderboard.method.types import BoardInput, BoardOutput
from leaderboard.method.v15 import compute_board
from leaderboard.registry import PUBLIC_BOARDS

TIE_POLICY = "published-order-then-slug/highspy-1.15.1"


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def input_fingerprint(boards: Sequence[BoardInput]) -> str:
    payload = {"method": METHOD_VERSION, "boards": [asdict(board) for board in boards]}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def publication_failure(inputs: Sequence[BoardInput], outputs: Sequence[BoardOutput]) -> str | None:
    by_key = {board.board: board for board in inputs}
    out_by_key = {board.board: board for board in outputs}
    broken: list[str] = []
    for key in PUBLIC_BOARDS:
        board, output = by_key.get(key), out_by_key.get(key)
        models = board.models if board else ()
        anchors = sum(model in ANCHORS for model in models)
        enough = len(models) >= (10 if key == "overall" else 5) and anchors >= (
            8 if key == "overall" else 4
        )
        if (
            output is None
            or not output.solver.optimal
            or not output.publishable_connectivity
            or not enough
        ):
            broken.append(key)
    return "not publishable: " + ", ".join(broken) if broken else None


def published_outputs(
    inputs: Sequence[BoardInput], computed: Sequence[BoardOutput]
) -> tuple[BoardOutput, ...]:
    models_of = {board.board: board.models for board in inputs}
    return tuple(
        output
        for output in computed
        if output.board in PUBLIC_BOARDS
        or (
            len(models_of.get(output.board, ())) >= 5
            and sum(model in ANCHORS for model in models_of.get(output.board, ())) >= 4
        )
    )


@dataclass(frozen=True, slots=True)
class BoardTiming:
    board: str
    models: int
    optimal: bool
    milliseconds: float


@dataclass(frozen=True, slots=True)
class ComputedBoards:
    outputs: tuple[BoardOutput, ...]
    timings: tuple[BoardTiming, ...]
    calculated_at: datetime


def compute_boards(
    boards: Sequence[BoardInput], *, time_limit_seconds: float = 300
) -> ComputedBoards:
    """Worker-only synchronous computation; API requests do not execute the solver."""
    outputs: list[BoardOutput] = []
    timings: list[BoardTiming] = []
    for board in boards:
        started = perf_counter()
        output = compute_board(board, time_limit_seconds=time_limit_seconds)
        outputs.append(output)
        timings.append(
            BoardTiming(
                board.board,
                output.model_count,
                output.solver.optimal,
                (perf_counter() - started) * 1000,
            )
        )
    return ComputedBoards(tuple(outputs), tuple(timings), datetime.now(UTC))


def evidence_fingerprint(summary: dict[str, Any]) -> str:
    consensus = summary.get("consensus", {})
    return canonical_json(
        {
            "fx": summary.get("fx_quote"),
            "sources": summary.get("sources"),
            "categories": summary.get("categories"),
            "evidence": consensus.get("evidence"),
        }
    )
