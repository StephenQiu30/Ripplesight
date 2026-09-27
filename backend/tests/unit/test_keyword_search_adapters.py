from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from connections.schemas import SourceConnectionConfig
from content.discovery_execution import (
    UnsupportedSearchSourceError,
    build_search_adapter_factory,
)
from core.config import Settings
from sources.adapters.hackernews import HackerNewsAdapter
from sources.adapters.rss import RssSourceAdapter
from sources.adapters.web_search import WebSearchAdapter
from sources.contracts import (
    SearchRequest,
    SourcePageState,
    SourcePost,
    SourceSort,
    SourceStopReason,
)
from worker.app import _registered_job_handlers


def _factory(source_key: str, **config: object):
    return build_search_adapter_factory(
        source_key,
        SourceConnectionConfig.model_validate(config),
    )(
        lambda _attempt: True,
        lambda: False,
        4,
        30.0,
    )


def test_hackernews_factory_uses_connection_allowed_hosts() -> None:
    adapter = _factory(
        "hackernews",
        base_url="https://hn.algolia.com/api/v1",
        allowed_hosts=("hn.algolia.com",),
    )

    assert isinstance(adapter, HackerNewsAdapter)
    assert adapter.source_key == "hackernews"
    assert adapter._api == "https://hn.algolia.com/api/v1"
    assert adapter._allowed_hosts == frozenset({"hn.algolia.com"})


def _hn_search_request(*, page_size: int = 2, page_token: str | None = None) -> SearchRequest:
    return SearchRequest(
        source_key="hackernews",
        query="AI",
        sort=SourceSort.LATEST,
        page_size=page_size,
        page_token=page_token,
        starts_at=datetime(2026, 9, 25, tzinfo=UTC),
        ends_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def test_hn_search_keeps_opaque_object_ids_and_nullable_story_fields() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "page": 0,
                "hitsPerPage": 2,
                "nbPages": 1,
                "nbHits": 2,
                "exhaustiveNbHits": True,
                "hits": [
                    {
                        "objectID": "000123",
                        "title": "Same title",
                        "story_text": "<p>First <b>body</b></p>",
                        "url": "https://example.com/a",
                        "author": "alice",
                        "created_at_i": 1790323200,
                        "points": 0,
                        "num_comments": 7,
                    },
                    {
                        "objectID": "story:a/b",
                        "title": "Same title",
                        "url": "https://example.com/b",
                        "author": None,
                        "created_at_i": None,
                        "points": None,
                        "num_comments": "unknown",
                    },
                ],
            },
        )

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True, transport=httpx.MockTransport(handler)
    )
    page = adapter.fetch_page(_hn_search_request())

    assert page.state is SourcePageState.COMPLETE
    assert page.request_count == 1
    assert [item.external_id for item in page.items] == ["000123", "story:a/b"]
    first, second = page.items
    assert isinstance(first, SourcePost) and isinstance(second, SourcePost)
    assert first.canonical_url == "https://news.ycombinator.com/item?id=000123"
    assert first.text == "First body"
    assert first.author_external_id == first.author_name == "alice"
    assert first.published_at == datetime.fromtimestamp(1790323200, UTC)
    assert first.like_count == 0 and first.comment_count == 7
    assert second.canonical_url == "https://news.ycombinator.com/item?id=story%3Aa%2Fb"
    assert second.text is None and second.published_at is None
    assert second.like_count is None and second.comment_count is None
    assert seen[0].url.path == "/api/v1/search_by_date"
    assert seen[0].url.params["tags"] == "story"
    assert page.terminal_evidence is not None
    assert page.terminal_evidence.terminal_verified is True
    assert page.terminal_evidence.query_bounded is True
    assert page.terminal_evidence.sort_applied is True
    assert page.terminal_evidence.sort_key is SourceSort.LATEST


def test_hn_search_uses_two_pages_and_proves_only_the_true_tail() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "page": page,
                "hitsPerPage": 1,
                "nbPages": 2,
                "nbHits": 2,
                "exhaustiveNbHits": True,
                "hits": [{"objectID": f"{page + 100}", "title": f"Story {page}"}],
            },
        )

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True, transport=httpx.MockTransport(handler)
    )
    first = adapter.fetch_page(_hn_search_request(page_size=1))
    second = adapter.fetch_page(_hn_search_request(page_size=1, page_token=first.next_page_token))

    assert first.state is SourcePageState.MORE and first.next_page_token == "1"
    assert first.terminal_evidence is None
    assert second.state is SourcePageState.COMPLETE and second.next_page_token is None
    assert second.terminal_evidence is not None
    assert second.terminal_evidence.terminal_verified is True
    assert [request.url.params["page"] for request in seen] == ["0", "1"]


def test_hn_second_page_failure_keeps_first_page_without_terminal_proof() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        seen.append(page)
        if page == "1":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "page": 0,
                "hitsPerPage": 1,
                "nbPages": 2,
                "nbHits": 2,
                "exhaustiveNbHits": True,
                "hits": [{"objectID": "first-story", "title": "AI first story"}],
            },
        )

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True, transport=httpx.MockTransport(handler)
    )
    first = adapter.fetch_page(_hn_search_request(page_size=1))
    second = adapter.fetch_page(_hn_search_request(page_size=1, page_token=first.next_page_token))

    assert first.state is SourcePageState.MORE
    assert first.terminal_evidence is None
    assert len(first.items) == 1
    assert second.state is SourcePageState.STOPPED
    assert second.stop_reason is SourceStopReason.UPSTREAM_ERROR
    assert second.terminal_evidence is None
    assert seen == ["0", "1"]


def test_hn_budget_refusal_sends_no_external_request() -> None:
    sent: list[httpx.Request] = []
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: False,
        transport=httpx.MockTransport(
            lambda request: sent.append(request) or httpx.Response(200, json={"hits": []})
        ),
    )

    page = adapter.fetch_page(_hn_search_request())
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.BUDGET_EXHAUSTED
    assert sent == []


@pytest.mark.parametrize("bad_pages", [True, "2", -1])
def test_hn_search_rejects_malformed_page_metadata(bad_pages: object) -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"hits": [{"objectID": "123", "title": "Story"}], "nbPages": bad_pages},
            )
        ),
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1))
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR


@pytest.mark.parametrize(
    "metadata",
    [
        {"page": 1, "hitsPerPage": 1, "nbPages": 2},
        {"page": 0, "hitsPerPage": 2, "nbPages": 1},
    ],
)
def test_hn_search_rejects_mismatched_page_metadata(metadata: dict[str, object]) -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"hits": [{"objectID": "123", "title": "Story"}], **metadata},
            )
        ),
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1))
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR


@pytest.mark.parametrize(
    "metadata",
    [
        {"nbPages": 1},  # missing total/page-size metadata
        {"page": 0, "hitsPerPage": 1, "nbPages": 1, "nbHits": 2, "exhaustiveNbHits": True},
        {"page": 0, "hitsPerPage": 1, "nbPages": 1, "nbHits": 1, "exhaustiveNbHits": False},
    ],
)
def test_hn_search_keeps_uncertain_terminal_metadata_unverified(
    metadata: dict[str, object],
) -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"hits": [{"objectID": "123", "title": "Story"}], **metadata}
            )
        ),
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1))
    assert page.state is SourcePageState.COMPLETE
    assert page.terminal_evidence is not None
    assert page.terminal_evidence.terminal_verified is False


def test_hn_search_caps_page_count_without_claiming_terminal_proof() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "page": 49,
                "hitsPerPage": 1,
                "nbPages": 51,
                "nbHits": 51,
                "exhaustiveNbHits": True,
                "hits": [{"objectID": "123", "title": "Story"}],
            },
        )

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True, transport=httpx.MockTransport(handler)
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1, page_token="49"))
    assert len(seen) == 1
    assert page.state is SourcePageState.COMPLETE
    assert page.terminal_evidence is not None
    assert page.terminal_evidence.terminal_verified is False


def test_hn_search_does_not_verify_an_out_of_range_page() -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "page": 1,
                    "hitsPerPage": 1,
                    "nbPages": 1,
                    "nbHits": 1,
                    "exhaustiveNbHits": True,
                    "hits": [],
                },
            )
        ),
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1, page_token="1"))
    assert page.state is SourcePageState.EMPTY
    assert page.terminal_evidence is not None
    assert page.terminal_evidence.terminal_verified is False


def test_hn_search_rejects_unrepresentable_timestamp_as_protocol_error() -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "nbPages": 1,
                    "hits": [{"objectID": "123", "created_at_i": 10**100}],
                },
            )
        ),
    )
    page = adapter.fetch_page(_hn_search_request(page_size=1))
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR


def test_hn_search_ceil_seconds_preserves_fractional_utc_window() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"hits": [], "nbPages": 0})

    starts_at = datetime(2026, 9, 25, tzinfo=UTC) + timedelta(microseconds=500_000)
    ends_at = starts_at + timedelta(hours=24)
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True, transport=httpx.MockTransport(handler)
    )
    adapter.fetch_page(
        _hn_search_request().model_copy(update={"starts_at": starts_at, "ends_at": ends_at})
    )
    assert seen[0].url.params["numericFilters"] == (
        f"created_at_i>={int(starts_at.timestamp()) + 1},"
        f"created_at_i<{int(ends_at.timestamp()) + 1}"
    )


@pytest.mark.parametrize(
    "base_url,allowed_hosts",
    [
        ("http://hn.algolia.com/api/v1", frozenset({"hn.algolia.com"})),
        ("https://other.example/api/v1", frozenset({"other.example"})),
        ("https://hn.algolia.com/api/v1/other", frozenset({"hn.algolia.com"})),
        ("https://hn.algolia.com:8443/api/v1", frozenset({"hn.algolia.com"})),
    ],
)
def test_hn_search_requires_fixed_https_endpoint(
    base_url: str, allowed_hosts: frozenset[str]
) -> None:
    with pytest.raises(ValueError, match="Algolia API"):
        HackerNewsAdapter(
            before_request=lambda _attempt: True,
            base_url=base_url,
            allowed_hosts=allowed_hosts,
        )


@pytest.mark.parametrize(
    "redirect_to",
    [
        "https://evil.example/api/v1/search_by_date",
        "http://hn.algolia.com/api/v1/search_by_date",
        "https://hn.algolia.com/api/v1/admin",
        "https://hn.algolia.com/api/v1/search_by_date",
    ],
)
def test_hn_search_rejects_redirect_outside_fixed_endpoints(redirect_to: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"location": redirect_to})

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        allowed_hosts=frozenset({"hn.algolia.com", "evil.example"}),
        transport=httpx.MockTransport(handler),
    )
    page = adapter.fetch_page(_hn_search_request())
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.ACCESS_DENIED
    assert len(seen) == 1


def test_google_news_factory_requires_fixed_feed_template() -> None:
    adapter = _factory(
        "google_news",
        feed_url_template=(
            "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        ),
        allowed_hosts=("news.google.com",),
    )

    assert isinstance(adapter, RssSourceAdapter)
    assert adapter.source_key == "google_news"
    assert adapter._template == (
        "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    )
    with pytest.raises(ValueError, match="Google News"):
        _factory(
            "google_news",
            feed_url_template="https://news.google.com/rss/search?q={query}",
            allowed_hosts=("news.google.com",),
        )


def test_36kr_factory_requires_newsflashes_on_local_rsshub() -> None:
    adapter = _factory(
        "rss_36kr",
        feed_url_template="http://127.0.0.1:1200/36kr/newsflashes",
        allowed_hosts=("127.0.0.1",),
    )
    assert isinstance(adapter, RssSourceAdapter)
    assert adapter._template == "http://127.0.0.1:1200/36kr/newsflashes"

    with pytest.raises(ValueError, match="newsflashes"):
        _factory(
            "rss_36kr",
            feed_url_template="http://127.0.0.1:1200/36kr/hot-list",
            allowed_hosts=("127.0.0.1",),
        )
    with pytest.raises(ValueError, match="local"):
        _factory(
            "rss_36kr",
            feed_url_template="https://36kr.com/feed",
            allowed_hosts=("36kr.com",),
        )


def test_web_search_factory_uses_connection_base_url_and_engines() -> None:
    adapter = _factory(
        "news_search",
        base_url="http://searxng:8080",
        engines=("duckduckgo news", "bing news"),
        allowed_hosts=("searxng",),
    )

    assert isinstance(adapter, WebSearchAdapter)
    assert adapter.source_key == "news_search"
    assert adapter._search_url == "http://searxng:8080/search"
    assert adapter._engines == "duckduckgo news,bing news"


def test_unknown_search_source_is_explicitly_rejected() -> None:
    with pytest.raises(UnsupportedSearchSourceError):
        build_search_adapter_factory(
            "unknown_source",
            SourceConnectionConfig(allowed_hosts=("example.com",)),
        )


def test_worker_registers_keyword_search_handler() -> None:
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")

    handlers = _registered_job_handlers(sessionmaker(), settings)

    assert "keyword.search" in handlers
