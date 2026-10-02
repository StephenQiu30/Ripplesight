"""Beijing calendar and deterministic editorial selection, adapted from AIHOT reports."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from publication.schemas import ReportPublicationCandidate

EditionKind = Literal["daily", "weekly", "monthly"]
BEIJING = ZoneInfo("Asia/Shanghai")
SECTIONS = {
    "ai-models": "模型发布/更新",
    "ai-products": "产品发布/更新",
    "industry": "行业动态",
    "paper": "论文研究",
    "tip": "技巧与观点",
    "opinion": "技巧与观点",
}
SECTION_ORDER = tuple(dict.fromkeys(SECTIONS.values()))


def period_window(kind: EditionKind, key: str) -> tuple[datetime, datetime]:
    if kind == "daily":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key) is None:
            raise ValueError("invalid day key")
        start = date.fromisoformat(key)
        end = start + timedelta(days=1)
    elif kind == "weekly":
        match = re.fullmatch(r"(\d{4})-W(\d{2})", key)
        if match is None:
            raise ValueError("invalid ISO week key")
        start = date.fromisocalendar(int(match[1]), int(match[2]), 1)
        end = start + timedelta(days=7)
    elif kind == "monthly":
        if re.fullmatch(r"\d{4}-\d{2}", key) is None:
            raise ValueError("invalid month key")
        start = date.fromisoformat(key + "-01")
        end = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
    else:
        raise ValueError("invalid edition kind")
    return (
        datetime.combine(start, time.min, tzinfo=BEIJING).astimezone(UTC),
        datetime.combine(end, time.min, tzinfo=BEIJING).astimezone(UTC),
    )


def due_period_key(kind: EditionKind, now: datetime) -> str:
    if now.utcoffset() is None:
        raise ValueError("edition clock must be timezone-aware")
    local = now.astimezone(BEIJING)
    if kind == "daily":
        return (local.date() - timedelta(days=1 if local.hour >= 9 else 2)).isoformat()
    if kind == "weekly":
        monday = local.date() - timedelta(days=local.weekday())
        start = monday - timedelta(days=7 if local.weekday() or local.hour >= 9 else 14)
        year, week, _ = start.isocalendar()
        return f"{year:04d}-W{week:02d}"
    if kind == "monthly":
        back = 1 if local.day > 1 or local.hour >= 9 else 2
        total = local.year * 12 + local.month - 1 - back
        return f"{total // 12:04d}-{total % 12 + 1:02d}"
    raise ValueError("invalid edition kind")


def next_period_key(kind: EditionKind, key: str) -> str:
    _, end = period_window(kind, key)
    local = end.astimezone(BEIJING).date()
    if kind == "daily":
        return local.isoformat()
    if kind == "monthly":
        return f"{local.year:04d}-{local.month:02d}"
    year, week, _ = local.isocalendar()
    return f"{year:04d}-W{week:02d}"


def fact_key(entry: ReportPublicationCandidate) -> str:
    return f"f:{entry.fact_id}" if entry.fact_id else f"a:{entry.content_id}"


def section_of(entry: ReportPublicationCandidate) -> str:
    return SECTIONS.get(entry.category or "industry", SECTIONS["industry"])


def compile_entries(
    kind: EditionKind, candidates: tuple[ReportPublicationCandidate, ...], *, covered: set[str]
) -> tuple[ReportPublicationCandidate, ...]:
    facts: dict[str, ReportPublicationCandidate] = {}
    for entry in candidates:
        if entry.backfill is True:
            continue
        key = fact_key(entry)
        if kind == "daily" and (key in covered or f"a:{entry.content_id}" in covered):
            continue
        prior = facts.get(key)
        order = (
            entry.first_party,
            entry.score if entry.score is not None else -1,
            entry.timeline_at,
            str(entry.content_id),
        )
        if prior is None or order > (
            prior.first_party,
            prior.score if prior.score is not None else -1,
            prior.timeline_at,
            str(prior.content_id),
        ):
            facts[key] = entry
    ordered = sorted(
        facts.values(),
        key=lambda e: (
            -(e.score if e.score is not None else -1),
            -e.timeline_at.timestamp(),
            str(e.content_id),
        ),
    )
    if kind != "daily":
        return tuple(ordered[: 40 if kind == "weekly" else 60])
    counters: dict[str, int] = defaultdict(int)
    selected: list[ReportPublicationCandidate] = []
    flashes: list[ReportPublicationCandidate] = []
    for entry in ordered:
        section = section_of(entry)
        if counters[section] < 8:
            counters[section] += 1
            selected.append(entry)
        elif len(flashes) < 12:
            flashes.append(entry)
    return tuple(selected + flashes)
