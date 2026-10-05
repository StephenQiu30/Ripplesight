"""Beijing calendar and deterministic editorial selection, adapted from AIHOT reports."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from math import log2
from typing import Any, Literal
from uuid import UUID
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


# Adapted from AIHOT 9acad0c reports/edition.ts; MIT: THIRD_PARTY_NOTICES.md.
RULE_VERSION = "edition-rules-v2"
COMMENTARY = frozenset({"tip", "opinion"})


def event_key(entry: ReportPublicationCandidate) -> str:
    return f"e:{entry.event_id}" if entry.event_id else fact_key(entry)


@dataclass(frozen=True)
class EditionStory:
    primary: ReportPublicationCandidate
    reports: tuple[ReportPublicationCandidate, ...]
    related: tuple[UUID, ...]
    sources: frozenset[str]
    score: int
    importance: float
    follow_up: bool = False
    section: str = ""
    rule_inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EditionSelection:
    main: tuple[EditionStory, ...] = ()
    flashes: tuple[EditionStory, ...] = ()
    repeats_suppressed: int = 0

    @property
    def entries(self) -> tuple[ReportPublicationCandidate, ...]:
        return tuple(
            {e.content_id: e for s in (*self.main, *self.flashes) for e in s.reports}.values()
        )

    def snapshot(self) -> list[dict[str, Any]]:
        rows = {str(e.content_id): e.model_dump(mode="json") for e in self.entries}
        for role, stories in (("main", self.main), ("flash", self.flashes)):
            for position, story in enumerate(stories):
                rows[str(story.primary.content_id)]["_edition"] = {
                    "rule_version": RULE_VERSION,
                    "role": role,
                    "position": position,
                    "reports": [str(e.content_id) for e in story.reports],
                    "related": [str(id) for id in story.related],
                    "sources": sorted(story.sources),
                    "score": story.score,
                    "importance": story.importance,
                    "follow_up": story.follow_up,
                    "section": story.section or section_of(story.primary),
                    "rule_inputs": story.rule_inputs,
                }
        return list(rows.values())


def selection_from_snapshot(snapshot: list[dict[str, Any]]) -> EditionSelection:
    entries = {
        UUID(row["content_id"]): ReportPublicationCandidate.model_validate(row) for row in snapshot
    }
    groups: dict[str, list[tuple[int, EditionStory]]] = defaultdict(list)
    for row in snapshot:
        meta = row.get("_edition")
        if meta is None:
            continue
        primary = entries[UUID(row["content_id"])]
        groups[meta["role"]].append(
            (
                meta["position"],
                EditionStory(
                    primary=primary,
                    reports=tuple(entries[UUID(id)] for id in meta["reports"]),
                    related=tuple(UUID(id) for id in meta["related"]),
                    sources=frozenset(meta["sources"]),
                    score=meta["score"],
                    importance=meta["importance"],
                    follow_up=meta["follow_up"],
                    section=meta["section"],
                    rule_inputs=meta.get("rule_inputs", {}),
                ),
            )
        )
    if not groups:  # Legacy issues retain their wording; period readers use their actual sections.
        return EditionSelection(
            main=tuple(
                EditionStory(
                    primary=e,
                    reports=(e,),
                    related=(),
                    sources=frozenset({e.source_key}),
                    score=e.score or 0,
                    importance=float(e.score or 0),
                    section=section_of(e),
                )
                for e in entries.values()
            )
        )
    return EditionSelection(
        main=tuple(s for _, s in sorted(groups["main"], key=lambda pair: pair[0])),
        flashes=tuple(s for _, s in sorted(groups["flash"], key=lambda pair: pair[0])),
    )


@dataclass(frozen=True)
class DailyIssue:
    key: str
    selection: EditionSelection
    main_ids: tuple[UUID, ...]
    highlights: tuple[UUID, ...]


def daily_memory(issues: tuple[DailyIssue, ...], key: str) -> tuple[set[str], set[str]]:
    """The last seven *issues*, including attached reports and flashes, even across gaps."""
    covered: set[str] = set()
    events: set[str] = set()
    for issue in sorted((i for i in issues if i.key < key), key=lambda i: i.key, reverse=True)[:7]:
        for entry in issue.selection.entries:
            covered.update((fact_key(entry), f"a:{entry.content_id}"))
            events.add(event_key(entry))
    return covered, events


def compile_daily(
    candidates: tuple[ReportPublicationCandidate, ...],
    *,
    covered: set[str],
    previous_events: set[str] | None = None,
    authorities: dict[UUID, tuple[int, bool]] | None = None,
    participants: dict[UUID, str] | None = None,
    fact_sources: dict[UUID, frozenset[str]] | None = None,
    event_participants: dict[UUID, frozenset[str]] | None = None,
) -> EditionSelection:
    authorities, participants = authorities or {}, participants or {}
    fact_sources, event_participants = fact_sources or {}, event_participants or {}
    previous_events = previous_events or set()
    facts: dict[str, list[ReportPublicationCandidate]] = defaultdict(list)
    suppressed: set[str] = set()
    for entry in candidates:
        if entry.backfill is True:
            continue
        key = fact_key(entry)
        if key in covered or f"a:{entry.content_id}" in covered:
            suppressed.add(key)
        else:
            facts[key].append(entry)

    def authority(entry: ReportPublicationCandidate) -> int:
        return authorities.get(
            entry.content_id, (0 if entry.first_party else 3, entry.first_party)
        )[0]

    def representative(rows: list[ReportPublicationCandidate]) -> ReportPublicationCandidate:
        return min(
            rows, key=lambda e: (authority(e), -(e.score or 0), e.timeline_at, str(e.content_id))
        )

    def sources(rows: list[ReportPublicationCandidate]) -> frozenset[str]:
        return frozenset(
            [participants.get(e.content_id, "source:" + e.source_key) for e in rows]
            + [p for e in rows if e.fact_id for p in fact_sources.get(e.fact_id, ())]
        )

    grouped: dict[str, list[list[ReportPublicationCandidate]]] = defaultdict(list)
    for rows in facts.values():
        grouped[event_key(representative(rows))].append(rows)
    ranked: list[tuple[EditionStory, bool]] = []
    for key, developments in grouped.items():
        developments.sort(
            key=lambda rows: (
                -len(sources(rows)),
                min(e.timeline_at for e in rows),
                fact_key(rows[0]),
            )
        )
        primary = representative(developments[0])
        reports = tuple(e for rows in developments for e in rows)
        coverage = sources(list(reports))
        official = any(authority(e) < 3 for e in reports)
        follow_up = key in previous_events
        score = max(e.score if e.score is not None else 50 for e in reports)
        talking = (
            event_participants.get(primary.event_id, coverage) if primary.event_id else coverage
        )
        importance = (
            score + 5 * log2(1 + len(talking)) + (5 if official else 0) - (6 if follow_up else 0)
        )
        # Commentary cannot earn a full follow-up merely through an official publisher.
        action = any(
            e.category not in COMMENTARY
            and authorities.get(e.content_id, (authority(e), e.first_party))[1]
            for e in reports
        )
        earned = not follow_up or action or any(len(sources(rows)) >= 4 for rows in developments)
        ranked.append(
            (
                EditionStory(
                    primary=primary,
                    reports=reports,
                    related=tuple(representative(rows).content_id for rows in developments[1:]),
                    sources=coverage,
                    score=score,
                    importance=importance,
                    follow_up=follow_up,
                    section=section_of(primary),
                    rule_inputs={
                        "participants": sorted(talking),
                        "official": official,
                        "primary_authority": authority(primary),
                        "party_action": action,
                        "development_sources": {
                            fact_key(rows[0]): sorted(sources(rows)) for rows in developments
                        },
                    },
                ),
                earned,
            )
        )
    ranked.sort(key=lambda pair: (-pair[0].importance, str(pair[0].primary.content_id)))
    main: list[EditionStory] = []
    rest: list[EditionStory] = []
    per_source: dict[str, int] = defaultdict(int)
    for story, earned in ranked:
        source = story.primary.source_key
        if earned and len(main) < 12 and per_source[source] < 2:
            main.append(story)
            per_source[source] += 1
        else:
            rest.append(story)
    return EditionSelection(tuple(main), tuple(rest[:10]), len(suppressed))


def compile_period(kind: EditionKind, issues: tuple[DailyIssue, ...]) -> EditionSelection:
    if kind == "daily":
        raise ValueError("a period must be weekly or monthly")
    carried: dict[str, list[tuple[DailyIssue, EditionStory]]] = defaultdict(list)
    for issue in issues:
        for story in issue.selection.main:
            if story.primary.content_id in issue.main_ids:
                carried[event_key(story.primary)].append((issue, story))
    ranked: list[EditionStory] = []
    for rows in carried.values():
        rows.sort(
            key=lambda row: (-len(row[1].sources), row[0].key, str(row[1].primary.content_id))
        )
        _, primary = rows[0]
        score = max(s.score for _, s in rows)
        lead = any(i.main_ids and i.main_ids[0] == s.primary.content_id for i, s in rows)
        highlight = any(s.primary.content_id in i.highlights for i, s in rows)
        days = len({i.key for i, _ in rows})
        rank = (
            score
            + 5 * log2(1 + max(len(s.sources) for _, s in rows))
            + 6 * lead
            + 3 * highlight
            + 4 * (days - 1)
        )
        reports = tuple({e.content_id: e for _, s in rows for e in s.reports}.values())
        # Keep each distinct progress once, underneath the representative event.
        progress: dict[str, ReportPublicationCandidate] = {
            fact_key(primary.primary): primary.primary
        }
        for _, story in rows:
            for id in (story.primary.content_id, *story.related):
                entry = next(e for e in story.reports if e.content_id == id)
                progress.setdefault(fact_key(entry), entry)
        ranked.append(
            replace(
                primary,
                reports=reports,
                related=tuple(
                    e.content_id
                    for e in progress.values()
                    if e.content_id != primary.primary.content_id
                ),
                sources=frozenset(p for _, s in rows for p in s.sources),
                score=score,
                importance=rank,
                rule_inputs={
                    "lead": bool(lead),
                    "highlight": highlight,
                    "days": days,
                    "max_sources": max(len(s.sources) for _, s in rows),
                },
            )
        )
    ranked.sort(key=lambda s: (-s.importance, str(s.primary.content_id)))
    return EditionSelection(main=tuple(ranked[: 20 if kind == "weekly" else 30]))
