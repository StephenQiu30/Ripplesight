from datetime import UTC, datetime
from uuid import uuid4
from xml.etree import ElementTree

from publication.exports import (
    item_jsonld,
    item_markdown,
    render_rss,
    render_sitemap,
    render_sitemap_index,
    render_sitemap_paths,
)
from publication.schemas import PublicBodyView, PublicItemDetailView, PublicSourceView


def detail() -> PublicItemDetailView:
    return PublicItemDetailView(
        id=uuid4(),
        revision=1,
        title="A <script> & B",
        original_title=None,
        summary="摘要 <img src=x> & 内容",
        source=PublicSourceView(key="x", name="来源 & 甲", kind="x_search", first_party=True),
        original_url="https://example.com/a?x=1&y=2",
        reading_url="/items/fixed",
        published_at=None,
        discovered_at=datetime(2026, 10, 1, tzinfo=UTC),
        timeline_at=datetime(2026, 10, 1, tzinfo=UTC),
        category="ai-models",
        tags=[],
        score=90,
        selected=True,
        reason=None,
        event_id=None,
        fact_id=None,
        indexable=True,
        reading_mode="full",
        body=PublicBodyView(original="<script>untrusted</script>\n正文"),
        site_fulltext=True,
        syndicate_fulltext=False,
        markdown_available=True,
        license_name="来源许可",
        license_url=None,
    )


def test_full_rss_needs_separate_redistribution_permission_and_escapes_source_markup() -> None:
    item = detail()
    xml = render_rss(
        [item],
        origin="https://hotkey.example",
        self_path="/feed/full.xml",
        title="HotKey",
        now=datetime(2026, 10, 2, tzinfo=UTC),
        include_content=True,
    )
    tree = ElementTree.fromstring(xml)
    assert tree.find(".//pubDate").text == "Thu, 01 Oct 2026 00:00:00 +0000"
    assert tree.find(".//{http://purl.org/rss/1.0/modules/content/}encoded") is None
    xml = render_rss(
        [item.model_copy(update={"syndicate_fulltext": True})],
        origin="https://hotkey.example",
        self_path="/feed/full.xml",
        title="HotKey",
        now=datetime(2026, 10, 2, tzinfo=UTC),
        include_content=True,
    )
    content = (
        ElementTree.fromstring(xml)
        .find(".//{http://purl.org/rss/1.0/modules/content/}encoded")
        .text
    )
    assert "&lt;script&gt;" in content and "<script>" not in content
    assert str(item.id) in xml and "example.com/a?x=1&amp;amp;y=2" in xml


def test_markdown_and_seo_drop_restricted_outputs_and_escape_script_delimiters() -> None:
    item = detail()
    text = item_markdown(item, origin="https://hotkey.example", redistribute=True)
    assert text and "来源许可" in text and "untrusted" not in text
    assert "untrusted" in item_markdown(item, origin="https://hotkey.example")
    assert item_jsonld(item, origin="https://hotkey.example") and "<script>" not in item_jsonld(
        item, origin="https://hotkey.example"
    )
    restricted = item.model_copy(update={"markdown_available": False, "indexable": False})
    assert item_markdown(restricted, origin="https://hotkey.example") is None
    assert item_jsonld(restricted, origin="https://hotkey.example") is None
    assert "/items/fixed" not in render_sitemap([restricted], origin="https://hotkey.example")


def test_sitemap_index_contains_all_approved_collections_and_bounded_local_paths() -> None:
    xml = render_sitemap_index(2, origin="https://hotkey.example", stories=1, reports=1, topics=1)
    root = ElementTree.fromstring(xml)
    assert [node.text for node in root.findall("{*}sitemap/{*}loc")] == [
        "https://hotkey.example/sitemaps/items-0.xml",
        "https://hotkey.example/sitemaps/items-1.xml",
        "https://hotkey.example/sitemaps/stories-0.xml",
        "https://hotkey.example/sitemaps/reports-0.xml",
        "https://hotkey.example/sitemaps/topics-0.xml",
    ]
    paths = render_sitemap_paths(
        ["/reports/daily/2026-10-01", "/discover/topics/openai"],
        origin="https://hotkey.example",
    )
    assert len(ElementTree.fromstring(paths)) == 2
    import pytest

    with pytest.raises(ValueError):
        render_sitemap_index(50_000, origin="https://hotkey.example", stories=1)
    with pytest.raises(ValueError):
        render_sitemap_paths(["//external.example/private"], origin="https://hotkey.example")


def test_rss_continuous_stream_reaches_licensed_selected_matches_after_2000_nonmatches(
    monkeypatch,
) -> None:
    from contextlib import contextmanager

    from publication.application import PublicationApplicationService
    from publication.listing import PublicationListingMember
    from tests.unit.test_publication_groups import member

    now = datetime(2026, 10, 2, tzinfo=UTC)
    sample = member(at=now)
    final = detail()
    seen = []

    def stream(*_args, **kwargs):
        assert kwargs["order"] == "timeline" and kwargs["ends_at"] == now
        for index in range(2502):
            seen.append(index)
            projection = sample.projection.model_copy(
                update={
                    "selected": index >= 2500,
                    "category": "paper" if index < 2500 else "ai-models",
                }
            )
            yield PublicationListingMember(projection, ())

    class Reader:
        def detail_in_transaction(self, **kwargs):
            assert kwargs["redistribute"] is True
            return final

    @contextmanager
    def read(_self):
        yield Reader()

    monkeypatch.setattr("publication.listing.iter_current_publications_in_transaction", stream)
    monkeypatch.setattr(PublicationApplicationService, "_read", read)
    output = PublicationApplicationService(None, origin="https://hotkey.example").feed(
        owner_id=uuid4(), kind="selected", category="ai-models", now=now
    )
    assert len(ElementTree.fromstring(output).findall(".//item")) == 2
    assert len(seen) == 2502
    assert "untrusted" not in output
