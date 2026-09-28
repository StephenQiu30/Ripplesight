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
from sources.contracts import SearchRequest, SourcePageState, SourcePost, SourceStopReason
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


def test_hackernews_preserves_story_identity_and_unknown_fields() -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "hits": [
                        {"objectID": "000123", "title": "Story", "url": "https://example.com"}
                    ],
                    "nbPages": 1,
                },
            )
        ),
    )

    page = adapter.fetch_page(SearchRequest(source_key="hackernews", query="Story", page_size=20))

    assert page.state is SourcePageState.COMPLETE
    post = page.items[0]
    assert isinstance(post, SourcePost)
    assert post.external_id == "000123"
    assert post.canonical_url == "https://news.ycombinator.com/item?id=000123"
    assert post.text is None
    assert post.published_at is None
    assert post.author_name is None
    assert post.like_count is None and post.comment_count is None


def test_hackernews_two_pages_keep_window_and_distinct_same_title_ids() -> None:
    ends_at = datetime(2026, 9, 27, tzinfo=UTC)
    starts_at = ends_at - timedelta(days=1)
    requested_pages: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/search_by_date"
        assert request.url.params["query"] == "DeepSeek"
        assert request.url.params["hitsPerPage"] == "2"
        assert request.url.params["numericFilters"] == (
            f"created_at_i>={int(starts_at.timestamp())},created_at_i<{int(ends_at.timestamp())}"
        )
        page = request.url.params["page"]
        requested_pages.append(page)
        if page == "0":
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "objectID": "000201",
                            "title": "DeepSeek story",
                            "created_at_i": int(starts_at.timestamp()),
                        },
                        {"objectID": "000202", "title": "DeepSeek story"},
                    ],
                    "nbPages": 2,
                },
            )
        assert page == "1"
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "000203",
                        "title": "DeepSeek story",
                        "created_at_i": int((ends_at - timedelta(seconds=1)).timestamp()),
                    }
                ],
                "nbPages": 2,
            },
        )

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(respond),
    )
    first = adapter.fetch_page(
        SearchRequest(
            source_key="hackernews",
            query="DeepSeek",
            page_size=2,
            starts_at=starts_at,
            ends_at=ends_at,
        )
    )
    second = adapter.fetch_page(
        SearchRequest(
            source_key="hackernews",
            query="DeepSeek",
            page_size=2,
            page_token=first.next_page_token,
            starts_at=starts_at,
            ends_at=ends_at,
        )
    )

    assert (first.state, first.next_page_token) == (SourcePageState.MORE, "1")
    assert (second.state, second.next_page_token) == (SourcePageState.COMPLETE, None)
    assert requested_pages == ["0", "1"]
    assert [post.external_id for post in (*first.items, *second.items)] == [
        "000201",
        "000202",
        "000203",
    ]
    assert first.items[0].published_at == starts_at
    assert first.items[1].published_at is None
    assert second.items[0].published_at == ends_at - timedelta(seconds=1)


def test_hackernews_missing_page_count_does_not_confirm_end_of_results() -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"hits": [{"objectID": "123", "title": "Story"}]}
            )
        ),
    )

    page = adapter.fetch_page(SearchRequest(source_key="hackernews", query="Story", page_size=20))

    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR


def test_hackernews_page_cap_keeps_unknown_tail_partial() -> None:
    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"hits": [{"objectID": "123", "title": "Story"}], "nbPages": 51},
            )
        ),
    )

    page = adapter.fetch_page(
        SearchRequest(source_key="hackernews", query="Story", page_size=1, page_token="49")
    )

    assert page.state is SourcePageState.PARTIAL
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR
    assert page.next_page_token is None
    assert len(page.items) == 1


def test_hackernews_rejects_redirect_outside_preset_hosts() -> None:
    requested: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://example.com/collect"})

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: True,
        allowed_hosts=frozenset({"hn.algolia.com"}),
        transport=httpx.MockTransport(redirect),
    )

    page = adapter.fetch_page(SearchRequest(source_key="hackernews", query="Story", page_size=20))

    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.ACCESS_DENIED
    assert page.request_count == 1
    assert requested == ["hn.algolia.com"]


def test_hackernews_budget_denial_sends_no_request() -> None:
    requested: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"hits": [], "nbPages": 0})

    adapter = HackerNewsAdapter(
        before_request=lambda _attempt: False,
        transport=httpx.MockTransport(record),
    )

    page = adapter.fetch_page(SearchRequest(source_key="hackernews", query="Story", page_size=20))

    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.BUDGET_EXHAUSTED
    assert page.request_count == 0
    assert requested == []


def test_rss_factory_uses_connection_feed_template() -> None:
    adapter = _factory(
        "google_news",
        feed_url_template="https://news.google.com/rss/search?q={query}",
        allowed_hosts=("news.google.com",),
    )

    assert isinstance(adapter, RssSourceAdapter)
    assert adapter.source_key == "google_news"
    assert adapter._template == "https://news.google.com/rss/search?q={query}"


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


def test_web_search_factory_requires_fixed_news_engine_and_local_endpoint() -> None:
    adapter = _factory(
        "news_search",
        base_url="http://127.0.0.1:8888",
        engines=("duckduckgo news",),
        allowed_hosts=("127.0.0.1",),
    )

    assert isinstance(adapter, WebSearchAdapter)
    assert adapter.source_key == "news_search"
    assert adapter._search_url == "http://127.0.0.1:8888/search"
    assert adapter._engines == "duckduckgo news"

    with pytest.raises(ValueError, match="duckduckgo news"):
        _factory(
            "news_search",
            base_url="http://127.0.0.1:8888",
            engines=("duckduckgo news", "bing news"),
            allowed_hosts=("127.0.0.1",),
        )
    with pytest.raises(ValueError, match="local"):
        _factory(
            "news_search",
            base_url="http://searxng:8080",
            engines=("duckduckgo news",),
            allowed_hosts=("searxng",),
        )


def _news_adapter(response: httpx.Response | httpx.MockTransport) -> WebSearchAdapter:
    transport = (
        response
        if isinstance(response, httpx.MockTransport)
        else httpx.MockTransport(lambda _request: response)
    )
    return WebSearchAdapter(
        source_key="news_search",
        base_url="http://127.0.0.1:8888",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _attempt: True,
        transport=transport,
    )


def _news_request(*, page_token: str | None = None) -> SearchRequest:
    return SearchRequest(source_key="news_search", query="AI", page_size=20, page_token=page_token)


def test_searxng_empty_requires_healthy_engine() -> None:
    empty = _news_adapter(
        httpx.Response(200, json={"query": "AI", "results": [], "unresponsive_engines": []})
    )
    healthy = empty.fetch_page(_news_request())
    assert healthy.state is SourcePageState.EMPTY
    assert healthy.request_count == 1

    failed = _news_adapter(
        httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [],
                "unresponsive_engines": [["duckduckgo news", "TimeoutException"]],
            },
        )
    ).fetch_page(_news_request())
    assert failed.state is SourcePageState.STOPPED
    assert failed.stop_reason is SourceStopReason.UPSTREAM_ERROR
    assert failed.source_engine == "duckduckgo news"
    assert failed.source_diagnostic == "engine_timeout"


def test_searxng_partial_results_and_explicit_error_keep_gap() -> None:
    result = {
        "url": "https://example.com/ai?topic=go&utm_source=search#top",
        "title": "AI news",
        "content": "brief",
        "engine": "duckduckgo news",
    }
    page = _news_adapter(
        httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [result],
                "unresponsive_engines": [["duckduckgo news", "TimeoutException"]],
            },
        )
    ).fetch_page(_news_request())
    assert page.state is SourcePageState.PARTIAL
    assert page.stop_reason is SourceStopReason.UPSTREAM_ERROR
    assert page.source_diagnostic == "engine_timeout"
    post = page.items[0]
    assert isinstance(post, SourcePost)
    assert post.identity_basis == "url_fallback"
    assert post.canonical_url == "https://example.com/ai?topic=go"
    assert post.published_at is None
    assert post.text_scope == "truncated"

    error = _news_adapter(
        httpx.Response(200, json={"query": "AI", "results": [], "error": "engine failed"})
    )
    assert error.fetch_page(_news_request()).stop_reason is SourceStopReason.UPSTREAM_ERROR


def test_searxng_invalid_json_or_wrong_engine_is_protocol_failure() -> None:
    invalid = _news_adapter(httpx.Response(200, content=b"<html>failure</html>"))
    assert invalid.fetch_page(_news_request()).stop_reason is SourceStopReason.PROTOCOL_ERROR

    wrong = _news_adapter(
        httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [{"url": "https://example.com/ai", "engine": "bing news"}],
                "unresponsive_engines": [],
            },
        )
    )
    assert wrong.fetch_page(_news_request()).stop_reason is SourceStopReason.PROTOCOL_ERROR


def test_searxng_timeout_and_native_identity_are_explicit() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("search timed out")

    timed_out = _news_adapter(httpx.MockTransport(timeout)).fetch_page(_news_request())
    assert timed_out.state is SourcePageState.STOPPED
    assert timed_out.stop_reason is SourceStopReason.UPSTREAM_ERROR
    assert timed_out.source_diagnostic == "request_timeout"
    assert timed_out.request_count == 1

    native = _news_adapter(
        httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [
                    {
                        "id": "story-42",
                        "url": "https://example.com/ai?topic=go",
                        "engine": "duckduckgo news",
                    }
                ],
                "unresponsive_engines": [],
            },
        )
    ).fetch_page(_news_request())
    post = native.items[0]
    assert isinstance(post, SourcePost)
    assert post.external_id == "native:story-42"
    assert post.identity_basis == "guid"


def test_searxng_repeated_page_is_partial_and_budget_denial_sends_no_request() -> None:
    calls: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(int(request.url.params["pageno"]))
        return httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [{"url": "https://example.com/ai", "engine": "duckduckgo news"}],
                "unresponsive_engines": [],
            },
        )

    adapter = _news_adapter(httpx.MockTransport(respond))
    first = adapter.fetch_page(_news_request())
    second = adapter.fetch_page(_news_request(page_token=first.next_page_token))
    assert first.state is SourcePageState.MORE
    assert second.state is SourcePageState.STOPPED
    assert second.stop_reason is SourceStopReason.CURSOR_LOOP
    assert calls == [1, 2]

    blocked = WebSearchAdapter(
        source_key="news_search",
        base_url="http://127.0.0.1:8888",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _attempt: False,
        transport=httpx.MockTransport(respond),
    ).fetch_page(_news_request())
    assert blocked.stop_reason is SourceStopReason.BUDGET_EXHAUSTED
    assert blocked.request_count == 0
    assert calls == [1, 2]


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
