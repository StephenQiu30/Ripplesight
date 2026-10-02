from datetime import UTC, datetime, timedelta

from events.interaction import compare_interaction_growth, compute_interaction

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def test_unknown_is_not_zero_and_formula_preserves_masks():
    unknown = compute_interaction(
        {"a": {"like_count": None, "comment_count": None, "repost_count": None, "view_count": None}}
    )
    assert unknown.score is None and len(unknown.unknown_masks["a"]) == 4
    zero = compute_interaction(
        {"a": {"like_count": 0, "comment_count": None, "repost_count": None, "view_count": None}}
    )
    assert zero.score is not None and zero.score > 0
    assert zero.components["a"] == 0 and "like_count" not in zero.unknown_masks["a"]


def test_growth_requires_eight_actual_comparable_3h_intervals_and_no_gaps():
    history = [(NOW - timedelta(hours=3 * index), 30 - index) for index in range(1, 10)]
    current = compute_interaction(
        {"a": {"like_count": 100, "comment_count": 0, "repost_count": 0, "view_count": 0}}
    )
    current.score = 35
    result = compare_interaction_growth(current, history, at=NOW)
    assert result.rising_state == "rising" and result.current_increment == 6
    assert result.baseline_increment == 1
    assert compare_interaction_growth(current, history[:8], at=NOW).rising_state == "insufficient"
    gap = [(time - timedelta(hours=2), score) for time, score in history]
    assert compare_interaction_growth(current, gap, at=NOW).rising_state == "insufficient"
