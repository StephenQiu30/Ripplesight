from datetime import UTC, datetime, timedelta

import pytest

from monitors.codex_schemas import ExpectedLanding, StatedWords
from monitors.codex_time import (
    estimate_for,
    manual_schedule,
    pacific_to_utc,
    resolve_stated_time,
    schedule_from,
)


def test_pacific_dst_and_end_of_day() -> None:
    assert pacific_to_utc("2026-09-25", "18:00") == datetime(2026, 9, 26, 1, tzinfo=UTC)
    assert pacific_to_utc("2026-12-25", "18:00") == datetime(2026, 12, 26, 2, tzinfo=UTC)
    assert pacific_to_utc("2026-09-25", "24:00") == datetime(2026, 9, 26, 7, tzinfo=UTC)
    with pytest.raises(ValueError):
        pacific_to_utc("2026-03-08", "02:30")


def test_relative_deadline_clock_overnight_and_date() -> None:
    posted = datetime(2026, 9, 26, 1, tzinfo=UTC)
    stated = resolve_stated_time(StatedWords(precision="deadline", relative_hours=1), posted)
    assert stated is not None
    schedule = schedule_from(stated)
    assert schedule.starts_at == posted + timedelta(hours=1)
    assert schedule.starts_at == schedule.ends_at
    estimate = estimate_for(schedule, posted)
    assert estimate.starts_at == posted
    assert estimate.ends_at == posted + timedelta(hours=2)
    overnight = resolve_stated_time(
        StatedWords(precision="window", clock="23:00", clock_through="01:00"), posted
    )
    assert overnight is not None
    assert schedule_from(overnight).ends_at - schedule_from(overnight).starts_at == timedelta(
        hours=2
    )
    day = resolve_stated_time(StatedWords(precision="date", day_offset=1), posted)
    assert day is not None
    assert schedule_from(day).ends_at - schedule_from(day).starts_at == timedelta(days=1)


def test_model_estimates_cannot_predate_source_or_exceed_36_hours() -> None:
    posted = datetime(2026, 9, 26, 1, tzinfo=UTC)
    words = resolve_stated_time(StatedWords(precision="exact", clock="19:00"), posted)
    assert words is not None
    schedule = schedule_from(words)
    bad = ExpectedLanding(
        earliest_pacific="2026-09-25 17:00", latest_pacific="2026-09-25 20:00", note="bad"
    )
    assert estimate_for(schedule, posted, bad).basis == "source"
    good = ExpectedLanding(
        earliest_pacific="2026-09-25 19:00", latest_pacific="2026-09-25 21:00", note="bounded"
    )
    assert estimate_for(schedule, posted, good).basis == "model"


def test_missing_time_stays_an_estimate_and_naive_input_is_rejected() -> None:
    value = estimate_for(None, datetime(2026, 9, 26, 5, tzinfo=UTC))
    assert value.basis == "history"
    assert value.starts_at < value.ends_at
    with pytest.raises(ValueError):
        estimate_for(None, datetime(2026, 9, 26, 5))


def test_pacific_whole_day_tracks_dst_and_manual_labels_are_program_derived() -> None:
    posted = datetime(2026, 3, 8, 15, tzinfo=UTC)
    stated = resolve_stated_time(StatedWords(precision="date", day_offset=0), posted)
    assert stated is not None
    schedule = schedule_from(stated)
    assert schedule.ends_at - schedule.starts_at == timedelta(hours=23)
    manual = manual_schedule(schedule.model_copy(update={"label": "Already completed"}))
    assert "预计" in manual.label and "completed" not in manual.label
