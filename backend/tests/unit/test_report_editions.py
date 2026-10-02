from datetime import UTC, datetime
from uuid import uuid4

import pytest

from publication.schemas import ReportPublicationCandidate
from reports.edition_rules import compile_entries, due_period_key, period_window


def test_periods_use_complete_beijing_days_iso_weeks_and_leap_months() -> None:
    assert period_window("monthly", "2024-02") == (
        datetime(2024, 1, 31, 16, tzinfo=UTC),
        datetime(2024, 2, 29, 16, tzinfo=UTC),
    )
    assert period_window("weekly", "2025-W01") == (
        datetime(2024, 12, 29, 16, tzinfo=UTC),
        datetime(2025, 1, 5, 16, tzinfo=UTC),
    )
    assert period_window("daily", "2026-10-01") == (
        datetime(2026, 9, 30, 16, tzinfo=UTC),
        datetime(2026, 10, 1, 16, tzinfo=UTC),
    )
    for kind, key in [("weekly", "2025-W53"), ("monthly", "2026-13"), ("daily", "2026-02-30")]:
        with pytest.raises(ValueError):
            period_window(kind, key)


def test_due_time_is_nine_am_and_does_not_compose_unfinished_calendar_period() -> None:
    before = datetime(2026, 6, 1, 0, 59, tzinfo=UTC)  # Monday, 08:59 Beijing.
    after = datetime(2026, 6, 1, 1, tzinfo=UTC)
    assert due_period_key("daily", before) == "2026-05-30"
    assert due_period_key("daily", after) == "2026-05-31"
    assert due_period_key("weekly", before) == "2026-W21"
    assert due_period_key("weekly", after) == "2026-W22"
    assert due_period_key("monthly", before) == "2026-04"
    assert due_period_key("monthly", after) == "2026-05"


def candidate(*, fact_id=None, first_party=False, score=80, backfill=False):
    return ReportPublicationCandidate(
        content_id=uuid4(),
        content_version_id=uuid4(),
        editorial_run_id=uuid4(),
        manual_version=0,
        source_profile_revision=1,
        policy_revision=1,
        publication_revision=1,
        fact_id=fact_id,
        title_zh="公开新模型",
        summary_zh="来源证据摘要",
        source_key="controlled",
        source_name="受控来源",
        source_kind="rss",
        first_party=first_party,
        url="https://example.com/new",
        category="ai-models",
        tags=["模型"],
        score=score,
        timeline_at=datetime(2026, 10, 1, tzinfo=UTC),
        backfill=backfill,
    )


def test_report_chooses_first_party_per_fact_suppresses_repeat_and_excludes_backfill() -> None:
    fact = uuid4()
    secondary = candidate(fact_id=fact, score=100)
    principal = candidate(fact_id=fact, first_party=True, score=60)
    historical = candidate(backfill=True)
    unknown = candidate(backfill=None)
    entries = compile_entries("daily", (secondary, principal, historical, unknown), covered=set())
    assert {item.content_id for item in entries} == {principal.content_id, unknown.content_id}
    assert compile_entries("daily", (secondary, principal), covered={f"f:{fact}"}) == ()


def test_daily_caps_each_section_and_flashes_while_periods_keep_top_forty_or_sixty() -> None:
    entries = tuple(candidate() for _ in range(80))
    assert len(compile_entries("daily", entries, covered=set())) == 20
    assert len(compile_entries("weekly", entries, covered=set())) == 40
    assert len(compile_entries("monthly", entries, covered=set())) == 60
