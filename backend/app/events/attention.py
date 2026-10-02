from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from events.heat_schemas import (
    AttentionEvidence,
    AttentionRosterView,
    AttentionSource,
    AttentionTrend,
    EventAttentionView,
)


def _display_heat(raw: float) -> float:
    return math.floor(raw * 100 + 0.5) / 10


def _behind(source: AttentionSource, at: datetime, historical: bool) -> bool:
    if not source.scheduled:
        return False
    if source.last_successful_fetch_at is None:
        return True
    deadline = at if historical else at - timedelta(seconds=max(3 * source.interval_seconds, 5400))
    return source.last_successful_fetch_at < deadline


def _raw(evidence: Sequence[AttentionEvidence], at: datetime) -> float:
    return sum(float(0.5 ** ((at - row.source_time).total_seconds() / 86400)) for row in evidence)


def _roster(row: AttentionEvidence) -> AttentionRosterView:
    return AttentionRosterView(
        participant_key=row.source.participant_key,
        source_id=row.source.id,
        source_name=row.source.name,
        mode=row.source.mode,
        tier=row.source.tier,
        first_party=row.source.first_party,
        source_time=row.source_time,
        content_id=row.content_id,
        content_version_id=row.content_version_id,
        title=row.title,
        canonical_url=row.canonical_url,
        fact_id=row.fact_id,
    )


def compute_attention(
    evidence: Sequence[AttentionEvidence],
    *,
    at: datetime,
    historical: bool = False,
    first_report_at: datetime | None = None,
) -> EventAttentionView:
    if at.utcoffset() is None or any(row.source_time.utcoffset() is None for row in evidence):
        raise ValueError("attention windows require timezone-aware timestamps")
    previous_at = at - timedelta(hours=6)
    previous_start = at - timedelta(hours=54)
    groups: dict[str, list[AttentionEvidence]] = defaultdict(list)
    for row in evidence:
        if row.source.mode != "isolated" and previous_start < row.source_time <= at:
            groups[row.source.participant_key].append(row)
    current: dict[str, AttentionEvidence] = {}
    previous: dict[str, AttentionEvidence] = {}
    editorial: set[str] = set()
    comparable: set[str] = set()
    incomplete = False
    new_participants = 0
    roster_rows = []
    tier_rank = {"T1": 0, "T1_5": 1, "T2": 2, None: 3}
    for key, rows in groups.items():
        current_rows = [row for row in rows if at - timedelta(hours=48) < row.source_time <= at]
        previous_rows = [row for row in rows if previous_start < row.source_time <= previous_at]
        if current_rows:
            current[key] = max(current_rows, key=lambda row: (row.source_time, str(row.id)))
            editorials = [row for row in current_rows if row.source.mode == "editorial"]
            if editorials:
                editorial.add(key)
            if min(row.source_time for row in current_rows) > previous_at:
                new_participants += 1
            roster_rows.append(
                min(
                    editorials or current_rows,
                    key=lambda row: (
                        tier_rank[row.source.tier],
                        -row.source_time.timestamp(),
                        str(row.id),
                    ),
                )
            )
            incomplete |= any(_behind(row.source, at, historical) for row in current_rows)
        if previous_rows:
            previous[key] = max(previous_rows, key=lambda row: (row.source_time, str(row.id)))
        if all(
            not _behind(row.source, at, historical) and row.source.created_at <= previous_start
            for row in rows
        ):
            comparable.add(key)
    comparable_current = [row for key, row in current.items() if key in comparable]
    comparable_previous = [row for key, row in previous.items() if key in comparable]
    heat = _display_heat(_raw(list(current.values()), at))
    previous_heat = _display_heat(_raw(list(previous.values()), previous_at))
    cohort_heat = _display_heat(_raw(comparable_current, at))
    cohort_previous = _display_heat(_raw(comparable_previous, previous_at))
    trend: AttentionTrend = "unknown"
    trend_pct = None
    if previous_heat <= 0:
        trend = "new"
    elif cohort_previous > 0:
        fraction = (cohort_heat - cohort_previous) / cohort_previous
        trend_pct = math.floor(fraction * 1000 + 0.5) / 10
        trend = "up" if fraction > 0.1 else "down" if fraction < -0.1 else "flat"
    badges = []
    surge = new_participants >= 3 and new_participants * 2 >= len(current)
    if surge:
        badges.append("surge")
    elif trend_pct is not None and trend_pct > 15:
        badges.append("rising")
    if first_report_at is not None and previous_at < first_report_at <= at:
        badges.append("new")
    roster_rows.sort(
        key=lambda row: (
            row.source.mode != "editorial",
            tier_rank[row.source.tier],
            -row.source_time.timestamp(),
            str(row.id),
        )
    )
    roster = [_roster(row) for row in roster_rows]
    representative_row = (
        min(
            roster_rows,
            key=lambda row: (
                not row.source.first_party,
                row.source.mode != "editorial",
                tier_rank[row.source.tier],
                -row.source_time.timestamp(),
                str(row.id),
            ),
        )
        if roster_rows
        else None
    )
    names = list(
        dict.fromkeys(row.source.name for row in roster_rows if row.source.mode == "editorial")
    )[:8]
    return EventAttentionView(
        window_end=at,
        heat=heat,
        eligible=len(current) >= 2 and bool(editorial),
        participant_count=len(current),
        editorial_participant_count=len(editorial),
        signal_participant_count=len(current) - len(editorial),
        comparable_participant_count=len(set(current) & comparable),
        uncomparable_participant_count=len(set(current) - comparable),
        previous_heat=previous_heat,
        comparable_heat=cohort_heat,
        comparable_previous_heat=cohort_previous,
        trend=trend,
        trend_pct=trend_pct,
        complete=not incomplete,
        badges=badges,
        source_names=names,
        roster=roster,
        representative=_roster(representative_row) if representative_row else None,
    )
