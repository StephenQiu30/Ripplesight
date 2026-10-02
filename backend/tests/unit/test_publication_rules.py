from datetime import UTC, datetime, timedelta

from publication.rules import (
    body_mode_of,
    display_tags,
    has_item_page,
    is_indexable,
    is_pool_eligible,
    is_selectable,
    may_redistribute,
    release_times,
)


def test_permissions_and_summary_visibility_are_independent_and_fail_closed() -> None:
    assert is_pool_eligible("editorial", "pass", "标题", "摘要")
    assert not is_pool_eligible("hot_signal", "pass", "标题", "摘要")
    assert not is_pool_eligible("editorial", "unknown", "标题", "摘要")
    assert not is_selectable(True, True, "EXCLUDE_MP")
    assert body_mode_of(True, True, True) == "full"
    assert body_mode_of(True, False, True) == "summary"
    assert not may_redistribute(False, "full")
    assert not may_redistribute(True, "summary")
    assert has_item_page("summary-only", "editorial")
    assert not has_item_page("withdrawn", "editorial")
    assert not has_item_page("public", "isolated")
    assert not is_indexable("summary-only", True, True, False, False, True)
    assert not is_indexable("public", True, True, False, False, False)
    assert display_tags(["topic", "entity:openai", "topic"]) == ["topic"]


def test_release_gate_is_stable_and_grouping_can_only_shorten_pending_delay() -> None:
    now = datetime(2026, 10, 2, tzinfo=UTC)
    ready, visible = release_times(True, now=now, delay_seconds=180)
    assert ready == now and visible == now + timedelta(seconds=180)
    assert release_times(
        True,
        now=now + timedelta(seconds=50),
        ready_at=ready,
        visible_after=visible,
        grouped_at=now + timedelta(seconds=20),
    ) == (ready, now + timedelta(seconds=50))
    assert release_times(
        True, now=now + timedelta(hours=1), ready_at=ready, visible_after=visible
    ) == (ready, visible)
    assert release_times(True, now=now, released_at=now - timedelta(days=3)) == (
        now - timedelta(days=3),
        now - timedelta(days=3),
    )


def test_scope_bound_cursor_rejects_other_owner_and_malformed_input() -> None:
    from uuid import uuid4

    import pytest

    from core.errors import ApplicationError
    from publication.cursors import decode_cursor, encode_cursor

    first, second = uuid4(), uuid4()
    cursor = encode_cursor({"owner": first, "type": "items"}, {"after": "literal"})
    assert decode_cursor(cursor, {"owner": first, "type": "items"}) == {"after": "literal"}
    for scope, raw in [
        ({"owner": second, "type": "items"}, cursor),
        ({"owner": first, "type": "search"}, cursor),
        ({}, "not-json"),
    ]:
        with pytest.raises(ApplicationError, match="invalid_publication_cursor"):
            decode_cursor(raw, scope)


def test_search_requires_all_literal_terms_and_counts_title_more_than_body() -> None:
    from publication.search import normalize_terms, search_weight

    assert normalize_terms(" AGENT agent 模型 ") == ("agent", "模型")
    assert search_weight(("agent", "模型"), title="AGENT 模型", summary="", body="") == 12
    assert search_weight(("agent", "模型"), title="AGENT", summary="模型", body="") == 9
    assert search_weight(("agent", "missing"), title="AGENT", summary="模型", body="") == 0
    assert search_weight(("100%",), title="1000", summary="", body="") == 0
