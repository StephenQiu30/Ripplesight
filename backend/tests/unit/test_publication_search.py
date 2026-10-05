from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import publication.search as module
from core.errors import ApplicationError
from publication.listing import PublicationListingMember
from publication.schemas import PublicSourceStatusView
from tests.unit.test_publication_groups import member

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _search(monkeypatch, rows, **kwargs):
    monkeypatch.setattr(
        module, "iter_current_publications_in_transaction", lambda *a, **k: iter(rows)
    )
    status = PublicSourceStatusView(
        source_key="hackernews", name="Hacker News", enabled=True, health="ok", last_success_at=NOW
    )
    result = module.search_in_transaction(
        SimpleNamespace(
            session=None,
            public_categories=(),
            source_status_in_transaction=lambda **kwargs: [status],
        ),
        owner_id=uuid4(),
        now=NOW,
        query="needle",
        **kwargs,
    )
    assert result.source_status == [status]
    return result


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


def test_search_cursor_requires_same_normalized_public_categories(monkeypatch):
    from publication.reading import PublicationReadingService

    projections = [
        member(at=NOW).projection.model_copy(update={"title": "needle"}) for _ in range(2)
    ]
    categories_seen = []

    def stream(*args, **kwargs):
        categories_seen.append(kwargs["public_categories"])
        return iter(PublicationListingMember(p, ()) for p in projections)

    monkeypatch.setattr(module, "iter_current_publications_in_transaction", stream)
    reader = PublicationReadingService(None, public_categories=("ai-models", "ai-models"))
    monkeypatch.setattr(reader, "source_status_in_transaction", lambda **_: [])
    options = {"owner_id": uuid4(), "now": NOW, "query": "needle", "limit": 1}
    page = module.search_in_transaction(reader, **options)
    assert page.next_cursor and len(page.items) == 1
    continued = module.search_in_transaction(reader, **options, cursor=page.next_cursor)
    assert continued.items[0].id != page.items[0].id
    assert categories_seen == [("ai-models",), ("ai-models",)]
    reader.public_categories = ("tip",)
    with pytest.raises(ApplicationError, match="invalid_publication_cursor"):
        module.search_in_transaction(reader, **options, cursor=page.next_cursor)
    assert len(categories_seen) == 2
