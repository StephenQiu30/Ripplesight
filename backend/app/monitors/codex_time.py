"""AIHOT monitor/time.ts semantic port; see THIRD_PARTY_NOTICES.md for MIT notice."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from monitors.codex_schemas import Estimate, ExpectedLanding, Schedule, StatedTime, StatedWords

PACIFIC = ZoneInfo("America/Los_Angeles")
BEIJING = ZoneInfo("Asia/Shanghai")
HOUR = timedelta(hours=1)


def aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    return value.astimezone(UTC)


def pacific_to_utc(day: str, clock: str) -> datetime:
    parsed = date.fromisoformat(day)
    if clock == "24:00":
        parsed += timedelta(days=1)
        clock = "00:00"
    if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock) is None:
        raise ValueError("invalid Pacific clock time")
    hour, minute = map(int, clock.split(":"))
    wall = datetime(parsed.year, parsed.month, parsed.day, hour, minute)
    # Upstream tries PST before PDT: use fold=1 for a repeated fall-back clock.
    for fold in (1, 0):
        result = wall.replace(tzinfo=PACIFIC, fold=fold).astimezone(UTC)
        if result.astimezone(PACIFIC).replace(tzinfo=None) == wall:
            return result
    raise ValueError("nonexistent Pacific daylight-saving time")


def beijing_range(start: datetime, end: datetime) -> str:
    a, b = aware(start).astimezone(BEIJING), aware(end).astimezone(BEIJING)
    left = f"{a.month}月{a.day}日 {a:%H:%M}"
    if a == b:
        return left
    return f"{left}-{b:%H:%M}" if a.date() == b.date() else f"{left}-{b.month}月{b.day}日 {b:%H:%M}"


def resolve_stated_time(words: StatedWords, posted_at: datetime) -> StatedTime | None:
    post = aware(posted_at).astimezone(PACIFIC)
    day = (post.date() + timedelta(days=words.day_offset or 0)).isoformat()
    if words.relative_hours is not None and words.relative_hours > 0:
        at = (aware(posted_at) + timedelta(hours=words.relative_hours)).astimezone(PACIFIC)
        return StatedTime(
            precision="approximate" if words.precision == "approximate" else "deadline",
            date=at.date().isoformat(),
            clock=at.strftime("%H:%M"),
        )
    if words.period:
        if words.period == "end_of_day":
            return StatedTime(precision="deadline", date=day, clock="24:00")
        start, end = {
            "afternoon": ("12:00", "18:00"),
            "evening": ("17:00", "21:00"),
            "tonight": ("18:00", "23:59"),
        }[words.period]
        if day == post.date().isoformat():
            start = max(post.strftime("%H:%M"), start)
        return StatedTime(precision="window", date=day, clock=start, clock_through=end)
    if words.clock:
        precision = words.precision if words.precision in {"deadline", "approximate"} else "exact"
        return StatedTime(
            precision="window" if words.clock_through else precision,
            date=day,
            clock=words.clock,
            clock_through=words.clock_through,
        )
    if words.precision == "date" and words.day_offset is not None:
        return StatedTime(precision="date", date=day, clock=None)
    return None


def schedule_from(stated: StatedTime) -> Schedule:
    if stated.precision == "date":
        start = pacific_to_utc(stated.date, "00:00")
        end = pacific_to_utc(stated.date, "24:00")
    else:
        start = pacific_to_utc(stated.date, stated.clock or "18:00")
        if stated.precision in {"deadline", "approximate"}:
            end = start
        elif stated.clock_through:
            day = date.fromisoformat(stated.date)
            if stated.clock_through < (stated.clock or "18:00"):
                day += timedelta(days=1)
            end = pacific_to_utc(day.isoformat(), stated.clock_through)
        else:
            end = start + HOUR
    if end < start:
        raise ValueError("stated period has already ended; needs review")
    suffix = " 前" if stated.precision == "deadline" else ""
    prefix = "北京时间约 " if stated.precision == "approximate" else "北京时间预计 "
    return Schedule(
        precision="window" if stated.precision == "exact" else stated.precision,
        starts_at=start,
        ends_at=end,
        label=f"{prefix}{beijing_range(start, end)}{suffix}",
    )


def manual_schedule(schedule: Schedule) -> Schedule:
    """Operator times are instants; the Beijing label is program-derived."""
    start, end = aware(schedule.starts_at), aware(schedule.ends_at)
    if schedule.precision in {"deadline", "approximate"}:
        end = start
    prefix = "北京时间约 " if schedule.precision == "approximate" else "北京时间预计 "
    suffix = " 前" if schedule.precision == "deadline" else ""
    return Schedule(
        precision="window" if schedule.precision == "exact" else schedule.precision,
        starts_at=start,
        ends_at=end,
        label=f"{prefix}{beijing_range(start, end)}{suffix}",
    )


def _estimate(start: datetime, end: datetime, basis: str, reason: str) -> Estimate:
    return Estimate.model_validate(
        {
            "starts_at": start,
            "ends_at": end,
            "basis": basis,
            "label": f"北京时间 {beijing_range(start, end)}",
            "reason": reason,
        }
    )


def estimate_for(
    schedule: Schedule | None, announced_at: datetime, model: ExpectedLanding | None = None
) -> Estimate:
    announced_at = aware(announced_at)
    if model:
        try:

            def parse(value: str) -> datetime:
                m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", value.strip())
                if m is None:
                    raise ValueError("invalid model window")
                return pacific_to_utc(m[1], m[2])

            start, end = parse(model.earliest_pacific), parse(model.latest_pacific)
            sane = announced_at <= start < end and end - start <= 36 * HOUR
            consistent = schedule is None or (
                end >= schedule.starts_at
                and start <= schedule.ends_at + 12 * HOUR
                and (schedule.precision == "deadline" or start >= schedule.starts_at)
            )
            if sane and consistent:
                return _estimate(start, end, "model", f"模型推算:{model.note}")
        except ValueError:
            pass
    if schedule and schedule.precision == "date":
        day = schedule.starts_at.astimezone(PACIFIC).date().isoformat()
        return _estimate(
            pacific_to_utc(day, "16:30"),
            pacific_to_utc(day, "21:30"),
            "source_day",
            "原帖只给日期,按历史太平洋时间傍晚时段估计。",
        )
    if schedule and schedule.precision == "deadline":
        start = min(max(announced_at, schedule.ends_at - 24 * HOUR), schedule.ends_at)
        return _estimate(
            start, schedule.ends_at + HOUR, "source", "按原帖截止时间换算,并预留延迟。"
        )
    if schedule:
        start = (
            max(announced_at, schedule.starts_at - HOUR / 2)
            if schedule.precision == "approximate"
            else schedule.starts_at
        )
        return _estimate(
            start, schedule.ends_at + 2 * HOUR, "source", "按原帖时间换算,并预留一两个小时。"
        )
    post = announced_at.astimezone(PACIFIC)
    usual_day = post.date() + (
        timedelta(days=1) if post.strftime("%H:%M") > "21:30" else timedelta()
    )
    return _estimate(
        max(announced_at, pacific_to_utc(usual_day.isoformat(), "16:30")),
        pacific_to_utc(usual_day.isoformat(), "21:30"),
        "history",
        "原帖未给时间,按历史重置时段推算。",
    )
