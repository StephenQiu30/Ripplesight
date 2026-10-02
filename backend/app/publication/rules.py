"""Publication rules adapted from AIHOT 035f7b7 (MIT; see PROVENANCE.md)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal


def is_pool_eligible(
    mode: str, relevance: str | None, title: str | None, summary: str | None
) -> bool:
    return mode == "editorial" and relevance == "pass" and bool(title and summary)


def is_selectable(eligible: bool, judged_selected: bool | None, tier: str) -> bool:
    return eligible and judged_selected is True and tier != "EXCLUDE_MP"


def has_item_page(visibility: str, source_mode: str) -> bool:
    return visibility != "withdrawn" and source_mode == "editorial"


def body_mode_of(
    site_fulltext: bool, body_complete: bool, has_body: bool
) -> Literal["full", "summary"]:
    return "full" if site_fulltext and body_complete and has_body else "summary"


def may_redistribute(syndicate_fulltext: bool, body_mode: str) -> bool:
    return syndicate_fulltext and body_mode == "full"


def is_indexable(
    visibility: str, has_summary: bool, selected: bool, indexed: bool, excluded: bool, enabled: bool
) -> bool:
    return (
        enabled
        and visibility == "public"
        and has_summary
        and not excluded
        and (selected or indexed)
    )


def display_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tag for tag in tags if not tag.startswith("entity:")))


def release_times(
    selected: bool,
    *,
    now: datetime,
    delay_seconds: int = 180,
    ready_at: datetime | None = None,
    visible_after: datetime | None = None,
    grouped_at: datetime | None = None,
    released_at: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    if now.utcoffset() is None or not 0 <= delay_seconds <= 3600:
        raise ValueError("release requires an aware clock and bounded delay")
    if not selected:
        return ready_at, visible_after
    if ready_at is None:
        if released_at is not None:
            if released_at.utcoffset() is None or released_at > now:
                raise ValueError("historical release must be explicitly proven and in the past")
            return released_at, released_at
        return now, now if grouped_at is not None and grouped_at <= now else now + timedelta(
            seconds=delay_seconds
        )
    if (
        visible_after is not None
        and visible_after > now
        and grouped_at is not None
        and grouped_at <= now
    ):
        earliest = max(ready_at, grouped_at)
        if earliest < visible_after:
            return ready_at, max(earliest, now)
    return ready_at, visible_after
