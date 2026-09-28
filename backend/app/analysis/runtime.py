from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PromptRuntimeWindow:
    """One scheduler run's confirmed static configuration interval [start, end)."""

    run_id: UUID
    prompt_version: str
    ai_enabled: bool
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class PromptRuntimeOrigin:
    status: Literal["candidate", "not_required", "unknown"]
    started_at: datetime | None = None
    reason: str | None = None
    runtime_ids: tuple[UUID, ...] = ()


def project_prompt_runtime_origin(
    *,
    prompt_version: str,
    eligible_spans: Sequence[tuple[datetime, datetime]],
    runtime_windows: Sequence[PromptRuntimeWindow],
) -> PromptRuntimeOrigin:
    """Find the first fully evidenced enabled instant across eligible spans."""
    if not prompt_version:
        raise ValueError("prompt version is required")
    for starts_at, ends_at in eligible_spans:
        if starts_at.tzinfo is None or ends_at.tzinfo is None or starts_at > ends_at:
            raise ValueError("eligible spans need ordered aware times")
    for window in runtime_windows:
        if (
            window.starts_at.tzinfo is None
            or window.ends_at.tzinfo is None
            or window.starts_at > window.ends_at
        ):
            raise ValueError("runtime windows need ordered aware times")

    evidence_ids: list[UUID] = []
    for starts_at, ends_at in sorted(eligible_spans):
        if starts_at == ends_at:
            continue
        boundaries = {starts_at, ends_at}
        for window in runtime_windows:
            if window.starts_at < ends_at and starts_at < window.ends_at:
                boundaries.add(max(starts_at, window.starts_at))
                boundaries.add(min(ends_at, window.ends_at))
        ordered = sorted(boundaries)
        for segment_start, segment_end in pairwise(ordered):
            covering = sorted(
                (
                    window
                    for window in runtime_windows
                    if window.starts_at <= segment_start and segment_end <= window.ends_at
                ),
                key=lambda window: (window.starts_at, str(window.run_id)),
            )
            for window in covering:
                if window.run_id not in evidence_ids:
                    evidence_ids.append(window.run_id)
            if not covering:
                return PromptRuntimeOrigin(
                    "unknown", reason="prompt_runtime_history_gap", runtime_ids=tuple(evidence_ids)
                )
            configurations = {(window.prompt_version, window.ai_enabled) for window in covering}
            if len(configurations) != 1:
                return PromptRuntimeOrigin(
                    "unknown", reason="prompt_runtime_conflict", runtime_ids=tuple(evidence_ids)
                )
            if (prompt_version, True) in configurations:
                return PromptRuntimeOrigin(
                    "candidate", started_at=segment_start, runtime_ids=tuple(evidence_ids)
                )
    return PromptRuntimeOrigin("not_required", runtime_ids=tuple(evidence_ids))
