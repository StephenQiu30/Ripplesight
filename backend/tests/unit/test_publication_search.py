from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import publication.search as module
from core.errors import ApplicationError
from publication.listing import PublicationListingMember
from tests.unit.test_publication_groups import member

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _search(monkeypatch, rows, **kwargs):
    monkeypatch.setattr(
        module, "iter_current_publications_in_transaction", lambda *a, **k: iter(rows)
    )
    return module.search_in_transaction(
        SimpleNamespace(session=None), owner_id=uuid4(), now=NOW, query="needle", **kwargs
    )


def test_search_scans_beyond_old_raw_limit_and_ignores_html_attributes(monkeypatch):
    base = member(at=NOW).projection
    rows = [
        PublicationListingMember(
            base.model_copy(
                update={"content_id": UUID(int=i + 1), "title": "无关资料", "summary": None}
            ),
            (),
        )
        for i in range(2001)
    ]
    match = PublicationListingMember(
        base.model_copy(update={"title": "无关资料", "summary": None}),
        (),
        "<p>visible needle</p>",
        "html",
    )
    hidden = PublicationListingMember(
        base.model_copy(update={"content_id": uuid4(), "title": "无关资料", "summary": None}),
        (),
        '<img src="https://example.com/needle"><script>needle</script>',
        "html",
    )
    page = _search(monkeypatch, [*rows, hidden, match])
    assert [p.id for p in page.items] == [match.projection.content_id]
    assert page.next_cursor is None
    hidden_markdown = PublicationListingMember(
        hidden.projection, (), "[unrelated](https://example.com/needle)", "markdown"
    )
    visible_markdown = PublicationListingMember(
        match.projection, (), "A **needle** release", "markdown"
    )
    assert [
        item.id for item in _search(monkeypatch, [hidden_markdown, visible_markdown]).items
    ] == [match.projection.content_id]


def test_search_order_and_first_party_filters_do_not_change_permission_scope(monkeypatch):
    older = member(at=NOW - timedelta(hours=1), first_party=True).projection.model_copy(
        update={"title": "needle", "summary": "needle"}
    )
    newer = member(at=NOW, first_party=True).projection.model_copy(
        update={"title": "其他", "summary": "needle"}
    )
    other = member(at=NOW).projection.model_copy(update={"title": "needle", "summary": "needle"})
    rows = [PublicationListingMember(p, ()) for p in (older, newer, other)]
    relevance = _search(monkeypatch, rows, channel="firstParty")
    assert [p.id for p in relevance.items] == [older.content_id, newer.content_id]
    chronological = _search(monkeypatch, rows, channel="firstParty", search_order="time")
    assert [p.id for p in chronological.items] == [newer.content_id, older.content_id]


def test_search_capacity_is_explicit_busy_not_partial_success(monkeypatch):
    base = member(at=NOW).projection.model_copy(update={"title": "needle"})
    rows = [
        PublicationListingMember(base.model_copy(update={"content_id": UUID(int=i + 1)}), ())
        for i in range(2001)
    ]
    with pytest.raises(ApplicationError, match="publication_search_busy"):
        _search(monkeypatch, rows, limit=40)
