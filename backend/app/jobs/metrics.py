"""Recomputable collection timing and hotlist bucket arithmetic."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Literal


@dataclass(frozen=True, slots=True)
class CollectionTimingSample:
    due_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class CollectionTimingResult:
    sample_count: int
    finished_count: int
    timeout_count: int
    median_seconds: float | None
    median_lower_bound_seconds: float | None
    result: Literal["passed", "failed", "indeterminate", "no_samples"]


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("metric timestamps must be UTC")
    return value.astimezone(UTC)


def summarize_collection_timing(
    samples: Sequence[CollectionTimingSample], *, cutoff_at: datetime, target_seconds: int
) -> CollectionTimingResult:
    """Censor unfinished dues at cutoff; only assert pass with an exact median."""
    cutoff = _utc(cutoff_at)
    if target_seconds <= 0:
        raise ValueError("timing target must be positive")
    lower: list[float] = []
    upper: list[float] = []
    finished_count = 0
    for sample in samples:
        due = _utc(sample.due_at)
        if due > cutoff:
            raise ValueError("future due cannot enter the measured denominator")
        finished = _utc(sample.finished_at) if sample.finished_at is not None else None
        if finished is not None and finished < due:
            raise ValueError("job cannot finish before its due instant")
        if finished is not None and finished <= cutoff:
            seconds = (finished - due).total_seconds()
            lower.append(seconds)
            upper.append(seconds)
            finished_count += 1
        else:
            lower.append((cutoff - due).total_seconds())
            upper.append(float("inf"))
    if not samples:
        return CollectionTimingResult(0, 0, 0, None, None, "no_samples")
    lower_median = float(median(lower))
    upper_median = float(median(upper))
    exact = lower_median if lower_median == upper_median else None
    result: Literal["passed", "failed", "indeterminate", "no_samples"]
    if exact is not None:
        result = "passed" if exact <= target_seconds else "failed"
    else:
        result = "failed" if lower_median > target_seconds else "indeterminate"
    return CollectionTimingResult(
        len(samples), finished_count, len(samples) - finished_count, exact, lower_median, result
    )


def expected_hotlist_buckets(
    *, start: datetime, end: datetime, interval_seconds: int
) -> tuple[datetime, ...]:
    """Enumerate half-open UTC epoch-phase due points, even when no row was recorded."""
    beginning, ending = _utc(start), _utc(end)
    if not beginning < ending <= beginning + timedelta(days=31):
        raise ValueError("bucket range must be positive and at most 31 days")
    if not 600 <= interval_seconds <= 86_400:
        raise ValueError("bucket interval is outside source schedule bounds")
    epoch = int(beginning.timestamp()) // interval_seconds * interval_seconds
    if datetime.fromtimestamp(epoch, UTC) < beginning:
        epoch += interval_seconds
    result: list[datetime] = []
    while (due := datetime.fromtimestamp(epoch, UTC)) < ending:
        result.append(due)
        epoch += interval_seconds
    return tuple(result)
