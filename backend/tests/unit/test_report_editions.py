from datetime import UTC, datetime
from math import log2
from uuid import UUID

import pytest

from publication.schemas import ReportPublicationCandidate
from reports.edition_compose import compose_edition, edition_prompt, grounded, render_edition
from reports.edition_rules import (
    DailyIssue,
    EditionKind,
    EditionSelection,
    EditionStory,
    compile_daily,
    compile_period,
    daily_memory,
    due_period_key,
    period_window,
    selection_from_snapshot,
)


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


def candidate(number: int, **changes: object) -> ReportPublicationCandidate:
    values = dict(
        content_id=UUID(int=number),
        content_version_id=UUID(int=10000 + number),
        editorial_run_id=UUID(int=20000 + number),
        manual_version=0,
        source_profile_revision=1,
        policy_revision=1,
        publication_revision=1,
        title_zh=f"公开新模型 {number}",
        summary_zh="来源证据摘要。",
        source_key=f"source-{number}",
        source_name="受控来源",
        source_kind="rss",
        first_party=False,
        url=f"https://example.com/{number}",
        category="ai-models",
        tags=["模型"],
        score=80,
        timeline_at=datetime(2026, 10, 1, tzinfo=UTC),
        backfill=False,
    )
    return ReportPublicationCandidate.model_validate({**values, **changes})


def issue(key: str, selection: EditionSelection) -> DailyIssue:
    return DailyIssue(
        key,
        selection,
        tuple(s.primary.content_id for s in selection.main),
        tuple(s.primary.content_id for s in selection.main[1:4]),
    )


def test_daily_most_reported_fact_authority_and_attached_developments() -> None:
    event, fact, next_fact = UUID(int=900), UUID(int=901), UUID(int=902)
    press = candidate(1, fact_id=fact, event_id=event, score=100)
    official = candidate(2, fact_id=fact, event_id=event, first_party=True, score=60)
    update = candidate(3, fact_id=next_fact, event_id=event, score=95)
    selection = compile_daily((press, official, update), covered=set())
    assert len(selection.main) == 1
    story = selection.main[0]
    assert story.primary == official and story.related == (update.content_id,)
    assert story.score == 100
    assert len(selection.entries) == 3
    restored = selection_from_snapshot(selection.snapshot())
    assert restored == selection
    content = compose_edition("daily", "2026-10-01", restored)
    body = render_edition(content, restored)
    assert f"  - {update.title_zh}" in body
    assert content.sections[0].content_ids == [official.content_id]


def test_daily_fact_ties_use_first_occurrence_then_explicit_authority() -> None:
    event = UUID(int=900)
    first = candidate(1, event_id=event, fact_id=UUID(int=901))
    newer = candidate(
        2, event_id=event, fact_id=UUID(int=902), timeline_at=datetime(2026, 10, 1, 1, tzinfo=UTC)
    )
    duplicate = candidate(3, event_id=event, fact_id=first.fact_id)
    selection = compile_daily(
        (newer, duplicate, first),
        covered=set(),
        authorities={first.content_id: (3, False), duplicate.content_id: (1, True)},
        participants={first.content_id: "same", duplicate.content_id: "same"},
    )
    assert selection.main[0].primary == duplicate
    assert selection.main[0].related == (newer.content_id,)


def test_seven_issue_memory_covers_flashes_and_attachments_across_calendar_gaps() -> None:
    issues = tuple(
        issue(f"2026-09-{day:02}", compile_daily((candidate(day),), covered=set()))
        for day in range(1, 9)
    )
    covered, events = daily_memory(issues, "2026-10-01")
    assert "a:" + str(UUID(int=1)) not in covered
    assert "a:" + str(UUID(int=2)) in covered
    assert len(events) == 7
    selection = EditionSelection(
        flashes=(
            EditionStory(
                candidate(20),
                (candidate(20), candidate(21)),
                (UUID(int=21),),
                frozenset({"s"}),
                80,
                80,
            ),
        )
    )
    covered, _ = daily_memory((issue("2026-09-28", selection),), "2026-10-01")
    assert {"a:" + str(UUID(int=n)) for n in (20, 21)} <= covered
    assert not compile_daily((candidate(20), candidate(21)), covered=covered).entries


def test_repeats_backfill_and_unknown_counts_are_distinct_from_capacity() -> None:
    fact = UUID(int=900)
    selection = compile_daily(
        (
            candidate(1, fact_id=fact),
            candidate(2, fact_id=fact),
            candidate(3, backfill=True),
            candidate(4, backfill=None),
        ),
        covered={f"f:{fact}"},
    )
    assert selection.repeats_suppressed == 1
    assert [e.content_id for e in selection.entries] == [UUID(int=4)]
    assert compose_edition("daily", "2026-10-01", selection).metrics.backfill_unknown_count == 1


@pytest.mark.parametrize(
    ("party", "category", "sources", "main"),
    [
        (True, "ai-models", 1, True),
        (True, "opinion", 1, False),
        (True, "tip", 1, False),
        (False, "ai-models", 4, True),
        (False, "ai-models", 3, False),
    ],
)
def test_follow_up_thresholds(party: bool, category: str, sources: int, main: bool) -> None:
    event, fact = UUID(int=900), UUID(int=901)
    entries = tuple(
        candidate(n, event_id=event, fact_id=fact, category=category, first_party=party)
        for n in range(1, sources + 1)
    )
    selection = compile_daily(entries, covered=set(), previous_events={f"e:{event}"})
    assert bool(selection.main) is main
    assert bool(selection.flashes) is not main


def test_four_reports_from_one_owner_do_not_meet_follow_up_threshold() -> None:
    event, fact = UUID(int=900), UUID(int=901)
    entries = tuple(candidate(n, event_id=event, fact_id=fact) for n in range(1, 5))
    selection = compile_daily(
        entries,
        covered=set(),
        previous_events={f"e:{event}"},
        participants={e.content_id: "owner:one" for e in entries},
        fact_sources={fact: frozenset({"owner:one"})},
    )
    assert not selection.main and len(selection.flashes) == 1
    content = compose_edition("daily", "2026-10-01", selection)
    assert not content.sections and not content.highlights and "快讯" in content.lead


def test_importance_formula_daily_source_capacity_headline_and_highlights() -> None:
    entries = tuple(
        candidate(n, source_key=f"source-{n // 4}", score=100 - n) for n in range(1, 61)
    )
    selection = compile_daily(entries, covered=set())
    assert len(selection.main) == 12 and len(selection.flashes) == 10
    assert all(
        sum(s.primary.source_key == story.primary.source_key for s in selection.main) <= 2
        for story in selection.main
    )
    assert selection.main[0].importance == 99 + 5 * log2(2)
    assert all(
        a.importance >= b.importance
        for a, b in zip(selection.main, selection.main[1:], strict=False)
    )
    content = compose_edition(
        "daily", "2026-10-01", selection, model_output={"ignored": "daily is always by rule"}
    )
    assert content.title == selection.main[0].primary.title_zh
    assert content.lead == selection.main[0].primary.summary_zh
    assert content.highlights == [s.primary.content_id for s in selection.main[1:4]]
    with pytest.raises(ValueError, match="never call"):
        edition_prompt("daily", "2026-10-01", selection)


def test_importance_counts_exact_daily_participants_official_bonus_and_follow_up_penalty() -> None:
    event = UUID(int=900)
    entry = candidate(1, first_party=True, event_id=event)
    selection = compile_daily(
        (entry,),
        covered=set(),
        previous_events={f"e:{event}"},
        event_participants={event: frozenset({"a", "b", "c"})},
    )
    assert selection.main[0].importance == 80 + 5 * log2(4) + 5 - 6


@pytest.mark.parametrize(("kind", "cap"), [("weekly", 20), ("monthly", 30)])
def test_period_caps_merge_events_across_days_and_preserve_sections(
    kind: EditionKind, cap: int
) -> None:
    issues = tuple(
        issue(
            f"2026-09-{day:02}",
            compile_daily(
                tuple(
                    candidate(
                        day * 100 + n,
                        event_id=UUID(int=n),
                        fact_id=UUID(int=day * 1000 + n),
                        category="industry" if n % 2 else "paper",
                    )
                    for n in range(1, 41)
                ),
                covered=set(),
            ),
        )
        for day in range(1, 5)
    )
    # Extra nonoverlapping events fill the period beyond its cap.
    issues += tuple(
        issue(
            f"2026-09-{day:02}",
            compile_daily(
                tuple(
                    candidate(day * 100 + n, event_id=UUID(int=day * 100 + n)) for n in range(1, 13)
                ),
                covered=set(),
            ),
        )
        for day in range(5, 9)
    )
    selected = compile_period(kind, issues)
    assert len(selected.main) == cap
    assert len({s.primary.event_id for s in selected.main}) == cap
    recurring = next(s for s in selected.main if s.primary.event_id == UUID(int=1))
    assert len(recurring.related) == 3
    assert recurring.section == "行业动态"
    assert recurring.importance == 80 + 5 * log2(2) + 6 + 4 * 3
    content = compose_edition(
        kind,
        "2026-W40" if kind == "weekly" else "2026-09",
        selected,
        daily_editions_covered=len(issues),
    )
    assert "日报汇编" in content.lead and not content.themes


def test_period_uses_only_daily_body_and_position_bonuses() -> None:
    selection = compile_daily(tuple(candidate(n) for n in range(1, 24)), covered=set())
    only = issue("2026-09-01", selection)
    result = compile_period("weekly", (only,))
    assert len(result.main) == 12
    assert result.main[0].importance == 80 + 5 + 6
    assert result.main[1].importance == 80 + 5 + 3
    assert not {s.primary.content_id for s in selection.flashes} & {
        s.primary.content_id for s in result.main
    }
    assert not compile_period("monthly", ()).entries


@pytest.mark.parametrize(
    "text",
    [
        "Nova 发布。",
        "nova 更新。",
        "收入 845。",
        "增长 12.3。",
        "增长 40%。",
        "谷歌更新。",
        "微软更新。",
        "千问更新。",
    ],
)
def test_period_unlisted_names_or_numbers_fall_back_per_paragraph(text: str) -> None:
    selection = compile_daily(tuple(candidate(n) for n in range(1, 4)), covered=set())
    content = compose_edition(
        "weekly",
        "2026-W40",
        selection,
        model_output={
            "overview": text,
            "sections": {"模型发布/更新": {"summary": text, "refs": [1, 2, 3]}},
        },
        daily_editions_covered=1,
    )
    assert "日报汇编 3 件事件" in content.lead and not content.themes


def test_grounding_plain_terms_company_aliases_and_exact_number_boundaries() -> None:
    assert grounded("HotKey 的 AI API 和 LLM。", "")
    assert grounded("谷歌公布 845 和 40%。", "Google 公布 845 和 40%。")
    assert not grounded("收益 100。", "收益 1000。")
    assert not grounded("Nova 更新。", "SuperNova 更新。")


def test_period_keeps_grounded_overview_and_drops_only_bad_section_intro() -> None:
    selection = compile_daily(
        tuple(candidate(n, title_zh="Google 发布模型") for n in range(1, 4)), covered=set()
    )
    content = compose_edition(
        "weekly",
        "2026-W40",
        selection,
        model_output={
            "overview": "谷歌发布模型。",
            "sections": {"模型发布/更新": {"summary": "微软发布。", "refs": [1, 2, 3]}},
        },
    )
    assert content.lead == "谷歌发布模型。" and not content.themes
    output = {
        "overview": "谷歌发布模型。",
        "sections": {"模型发布/更新": {"summary": "谷歌发布模型。", "refs": [1, 2, 3]}},
    }
    content = compose_edition("weekly", "2026-W40", selection, model_output=output)
    assert len(content.themes) == 1
    assert render_edition(content, selection).count("## 模型发布/更新") == 1


@pytest.mark.parametrize(
    "refs", [[1, 2, 4], [1, 1, 3], [0, 2, 3], [-1, 2, 3], [True, 2, 3], [1.0, 2, 3]]
)
def test_period_citations_are_strict_and_cannot_change_sections(refs: list[object]) -> None:
    selection = compile_daily(tuple(candidate(n) for n in range(1, 4)), covered=set())
    with pytest.raises(ValueError):
        compose_edition(
            "weekly",
            "2026-W40",
            selection,
            model_output={
                "overview": "模型发布。",
                "sections": {"模型发布/更新": {"summary": "模型发布。", "refs": refs}},
            },
        )


def test_period_prompt_only_introduces_sections_with_three_events() -> None:
    selection = compile_daily((candidate(1), candidate(2)), covered=set())
    system, _, _ = edition_prompt("monthly", "2026-10", selection)
    assert "sections 留空" in system
    with pytest.raises(ValueError, match="unlisted section"):
        compose_edition(
            "monthly",
            "2026-10",
            selection,
            model_output={
                "overview": "模型发布。",
                "sections": {"模型发布/更新": {"summary": "模型发布。", "refs": [1, 2, 3]}},
            },
        )


def test_follow_up_four_sources_must_report_one_development_not_two_pairs() -> None:
    event = UUID(int=900)
    entries = tuple(
        candidate(n, event_id=event, fact_id=UUID(int=1000 + n // 3)) for n in range(1, 5)
    )
    selected = compile_daily(entries, covered=set(), previous_events={f"e:{event}"})
    assert len(selected.flashes[0].sources) == 4 and not selected.main


def test_legacy_snapshot_remains_readable_without_new_metadata() -> None:
    entry = candidate(1)
    restored = selection_from_snapshot([entry.model_dump(mode="json")])
    assert restored.entries == (entry,)
    assert restored.main[0].section == "模型发布/更新"


def test_frozen_rule_inputs_reproduce_daily_and_period_ranking() -> None:
    event = UUID(int=900)
    daily = compile_daily(
        (candidate(1, event_id=event, first_party=True),),
        covered=set(),
        event_participants={event: frozenset({"a", "b", "c"})},
    )
    story = selection_from_snapshot(daily.snapshot()).main[0]
    inputs = story.rule_inputs
    assert story.importance == story.score + 5 * log2(1 + len(inputs["participants"])) + 5
    assert inputs["official"] and inputs["party_action"]
    period = compile_period("weekly", (issue("2026-09-01", daily), issue("2026-09-02", daily)))
    story = selection_from_snapshot(period.snapshot()).main[0]
    inputs = story.rule_inputs
    assert story.importance == (
        story.score
        + 5 * log2(1 + inputs["max_sources"])
        + 6 * inputs["lead"]
        + 3 * inputs["highlight"]
        + 4 * (inputs["days"] - 1)
    )


def test_model_text_cannot_hide_invented_figures_after_truncation_or_use_two_sentence_intro() -> (
    None
):
    selection = compile_daily(tuple(candidate(n) for n in range(1, 4)), covered=set())
    content = compose_edition(
        "weekly",
        "2026-W40",
        selection,
        model_output={
            "overview": "模型发布。" * 50 + "收入 999。",
            "sections": {"模型发布/更新": {"summary": "模型发布。模型更新。", "refs": [1, 2, 3]}},
        },
        daily_editions_covered=1,
    )
    assert "日报汇编" in content.lead and not content.themes
