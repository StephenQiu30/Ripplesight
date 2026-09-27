from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from monitors.services import evaluate_monitor_rules, normalize_monitor_rules
from sources.adapters.hackernews import HackerNewsAdapter
from sources.adapters.rss import RssSourceAdapter
from sources.adapters.web_search import WebSearchAdapter
from sources.contracts import (
    CommentsRequest,
    SearchRequest,
    SourceComment,
    SourcePageState,
    SourcePost,
    SourceSort,
    SourceStopReason,
)

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>t</title>
<item><title>小米 SU7 &lt;b&gt;交付&lt;/b&gt;</title><link>https://news.example.com/a</link>
<guid>https://news.example.com/a</guid><pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;本周交付 1 万台&lt;/p&gt;</description><author>记者甲</author></item>
<item><title>重复</title><link>https://news.example.com/a</link>
<guid>https://news.example.com/a</guid></item>
<item><title>无日期</title><link>https://news.example.com/b</link></item>
</channel></rss>"""
_GOOGLE_NEWS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
)


def _allow(attempt: int) -> bool:
    return attempt <= 10


def _search(source_key: str, **changes: object) -> SearchRequest:
    values: dict[str, object] = {"source_key": source_key, "query": "小米 SU7", "page_size": 20}
    values.update(changes)
    return SearchRequest.model_validate(values)


def test_rss_search_encodes_query_and_maps_entries() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_RSS.encode())

    adapter = RssSourceAdapter(
        source_key="google_news",
        feed_url_template=_GOOGLE_NEWS_TEMPLATE,
        allowed_hosts=frozenset({"news.google.com"}),
        before_request=_allow,
        transport=httpx.MockTransport(handler),
    )
    page = adapter.fetch_page(_search("google_news"))

    assert seen == [
        "https://news.google.com/rss/search?q=%E5%B0%8F%E7%B1%B3%20SU7"
        "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    ]
    assert page.state is SourcePageState.COMPLETE
    assert page.request_count == 1
    first, second = page.items
    assert isinstance(first, SourcePost)
    assert first.title == "小米 SU7 交付"
    assert first.text == "本周交付 1 万台"
    assert first.author_name == "记者甲"
    assert first.published_at == datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert first.canonical_url == "https://news.example.com/a"
    assert second.external_id == "url:https://news.example.com/b"
    assert second.identity_basis == "url_fallback"
    assert second.published_at is None
    assert adapter.fetch_page(_search("google_news")).request_count == 0


def test_rss_guid_fallback_is_normalized_and_title_is_not_identity() -> None:
    feed = """<rss version="2.0"><channel><title>news</title>
    <item><title>Same</title><guid>native-a</guid><link>https://example.com/a</link></item>
    <item><title>Same</title><guid>native-b</guid><link>https://example.com/b</link></item>
    <item><title>Duplicate</title><guid>native-a</guid><link>https://example.com/c</link></item>
    <item><title>Same</title><link>HTTPS://EXAMPLE.COM:443/c#section</link></item>
    <item><title>Same</title><link>https://example.com/c</link></item>
    </channel></rss>"""
    adapter = RssSourceAdapter(
        source_key="google_news",
        feed_url_template=_GOOGLE_NEWS_TEMPLATE,
        allowed_hosts=frozenset({"news.google.com"}),
        before_request=_allow,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=feed)),
    )
    page = adapter.fetch_page(_search("google_news"))

    assert page.state is SourcePageState.COMPLETE
    assert [(item.external_id, item.identity_basis) for item in page.items] == [
        ("native-a", "guid"),
        ("native-b", "guid"),
        ("url:https://example.com/c", "url_fallback"),
    ]


def test_google_news_requires_fixed_search_feed_and_refuses_redirects() -> None:
    for template, hosts in (
        ("https://news.google.com/rss/search?q={query}", frozenset({"news.google.com"})),
        (_GOOGLE_NEWS_TEMPLATE, frozenset({"news.google.com", "example.com"})),
    ):
        with pytest.raises(ValueError, match="Google News"):
            RssSourceAdapter(
                source_key="google_news",
                feed_url_template=template,
                allowed_hosts=hosts,
                before_request=_allow,
            )

    requested: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "/rss/search?q=other"})

    adapter = RssSourceAdapter(
        source_key="google_news",
        feed_url_template=_GOOGLE_NEWS_TEMPLATE,
        allowed_hosts=frozenset({"news.google.com"}),
        before_request=_allow,
        transport=httpx.MockTransport(redirect),
    )
    page = adapter.fetch_page(_search("google_news"))
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.ACCESS_DENIED
    assert page.request_count == 1
    assert len(requested) == 1


def test_google_news_keeps_nullable_fields_and_html_text() -> None:
    feed = """<rss version="2.0"><channel><title>Google News</title>
    <lastBuildDate>Sat, 26 Sep 2026 10:00:00 GMT</lastBuildDate>
    <item><title>AI &lt;b&gt;发布&lt;/b&gt;</title><guid>native-1</guid>
    <link>https://news.google.com/rss/articles/native-1</link>
    <description>&lt;p&gt;AI &lt;i&gt;摘要&lt;/i&gt;&lt;/p&gt;</description></item>
    <item><title>AI 无摘要</title><guid>native-2</guid>
    <link>https://news.google.com/rss/articles/native-2</link></item>
    </channel></rss>"""
    adapter = RssSourceAdapter(
        source_key="google_news",
        feed_url_template=_GOOGLE_NEWS_TEMPLATE,
        allowed_hosts=frozenset({"news.google.com"}),
        before_request=_allow,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=feed)),
    )
    page = adapter.fetch_page(_search("google_news"))
    assert page.state is SourcePageState.COMPLETE
    assert page.source_feed_updated_at == datetime(2026, 9, 26, 10, tzinfo=UTC)
    assert page.observed_at > page.source_feed_updated_at
    assert [(item.external_id, item.identity_basis) for item in page.items] == [
        ("native-1", "guid"),
        ("native-2", "guid"),
    ]
    assert (page.items[0].title, page.items[0].text) == ("AI 发布", "AI 摘要")
    assert page.items[1].text is None
    assert all(item.author_name is None and item.published_at is None for item in page.items)


def test_rss_legitimate_empty_is_distinct_from_malformed_xml() -> None:
    def fetch(xml: str) -> object:
        adapter = RssSourceAdapter(
            source_key="google_news",
            feed_url_template=_GOOGLE_NEWS_TEMPLATE,
            allowed_hosts=frozenset({"news.google.com"}),
            before_request=_allow,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text=xml)),
        )
        return adapter.fetch_page(_search("google_news"))

    assert (
        fetch("<rss version='2.0'><channel><title>empty</title></channel></rss>").state
        is SourcePageState.EMPTY
    )
    assert (
        fetch("<html><body>upstream error</body></html>").stop_reason
        is SourceStopReason.PROTOCOL_ERROR
    )
    truncated = (
        "<rss version='2.0'><channel><title>partial</title>"
        "<item><title>AI first</title><guid>first</guid></item>"
        "<item><title>AI unfinished"
    )
    assert fetch(truncated).stop_reason is SourceStopReason.PROTOCOL_ERROR


def _36kr_adapter(feed: str, *, status: int = 200) -> RssSourceAdapter:
    return RssSourceAdapter(
        source_key="rss_36kr",
        feed_url_template="http://127.0.0.1:1200/36kr/newsflashes",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=_allow,
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text=feed)),
    )


def test_36kr_feed_keeps_build_time_and_does_not_hide_page_truncation() -> None:
    feed = """<rss version="2.0"><channel><title>36Kr</title>
    <lastBuildDate>Sat, 26 Sep 2026 10:00:00 GMT</lastBuildDate>
    <item><title>AI 发布</title><guid>native-1</guid>
    <link>https://www.36kr.com/newsflashes/1</link>
    <pubDate>Sat, 26 Sep 2026 09:00:00 GMT</pubDate>
    <description>人工智能快讯</description><author>记者甲</author></item>
    <item><title>AI 无时间</title><guid>native-2</guid>
    <link>https://www.36kr.com/newsflashes/2</link></item>
    <item><title>AI 第三条</title><guid>native-3</guid>
    <link>https://www.36kr.com/newsflashes/3</link></item>
    </channel></rss>"""
    page = _36kr_adapter(feed).fetch_page(_search("rss_36kr", query="AI", page_size=2))

    assert page.state is SourcePageState.PARTIAL
    assert page.stop_reason is SourceStopReason.BUDGET_EXHAUSTED
    assert page.request_count == 1
    assert page.source_feed_updated_at == datetime(2026, 9, 26, 10, tzinfo=UTC)
    assert page.observed_at > page.source_feed_updated_at
    first, second = page.items
    assert isinstance(first, SourcePost) and isinstance(second, SourcePost)
    assert (first.external_id, first.identity_basis) == ("native-1", "guid")
    assert first.published_at == datetime(2026, 9, 26, 9, tzinfo=UTC)
    assert first.author_name == "记者甲"
    assert first.text == "人工智能快讯"
    assert first.text_scope == "truncated"
    assert second.published_at is None and second.author_name is None


def test_36kr_rules_match_title_and_summary_once_with_exclusion_priority() -> None:
    feed = """<rss version="2.0"><channel><title>36Kr</title>
    <item><title>daily update</title><guid>daily</guid>
    <link>https://www.36kr.com/newsflashes/daily</link></item>
    <item><title>AI AI 发布</title><guid>ai</guid>
    <link>https://www.36kr.com/newsflashes/ai</link></item>
    <item><title>新技术发布</title><guid>cn</guid>
    <link>https://www.36kr.com/newsflashes/cn</link>
    <description>人工智能产品落地</description></item>
    <item><title>AI 发布招聘</title><guid>excluded</guid>
    <link>https://www.36kr.com/newsflashes/excluded</link></item>
    <item><title>AI 再次出现</title><guid>ai</guid>
    <link>https://www.36kr.com/newsflashes/duplicate</link></item>
    </channel></rss>"""
    page = _36kr_adapter(feed).fetch_page(_search("rss_36kr", query="AI", page_size=20))
    rules = normalize_monitor_rules(
        match_any=["AI", "人工智能"], match_all=["发布"], exclude=["招聘"]
    )
    matches = [
        item.external_id
        for item in page.items
        if evaluate_monitor_rules(
            rules, "\n".join(part for part in (item.title, item.text) if part)
        ).matched
    ]

    assert page.state is SourcePageState.COMPLETE
    assert [item.external_id for item in page.items] == ["daily", "ai", "cn", "excluded"]
    assert matches == ["ai", "cn"]


def test_36kr_empty_feed_is_distinct_from_html_and_upstream_failure() -> None:
    empty = "<rss version='2.0'><channel><title>empty</title></channel></rss>"
    assert _36kr_adapter(empty).fetch_page(_search("rss_36kr")).state is SourcePageState.EMPTY
    assert (
        _36kr_adapter("<html>error</html>").fetch_page(_search("rss_36kr")).stop_reason
        is SourceStopReason.PROTOCOL_ERROR
    )
    assert (
        _36kr_adapter(empty, status=503).fetch_page(_search("rss_36kr")).stop_reason
        is SourceStopReason.UPSTREAM_ERROR
    )


def test_rss_maps_http_failures_and_budget_to_stop_reasons() -> None:
    def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "30"})

    adapter = RssSourceAdapter(
        source_key="rsshub",
        feed_url_template="http://127.0.0.1:1200/zhihu/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=_allow,
        transport=httpx.MockTransport(rate_limited),
    )
    page = adapter.fetch_page(_search("rsshub"))
    assert page.stop_reason is SourceStopReason.RATE_LIMITED
    assert page.retry_at is not None

    denied = RssSourceAdapter(
        source_key="rsshub",
        feed_url_template="http://127.0.0.1:1200/zhihu/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda attempt: False,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"")),
    )
    assert denied.fetch_page(_search("rsshub")).stop_reason is SourceStopReason.BUDGET_EXHAUSTED

    broken = RssSourceAdapter(
        source_key="rsshub",
        feed_url_template="http://127.0.0.1:1200/zhihu/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=_allow,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html")),
    )
    assert broken.fetch_page(_search("rsshub")).stop_reason is SourceStopReason.PROTOCOL_ERROR


def _hn_transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/search_by_date"):
            page = int(request.url.params["page"])
            hits = [
                {
                    "objectID": str(100 + page),
                    "title": f"Story {page}",
                    "url": "https://example.com/s",
                    "author": "pg",
                    "points": 42,
                    "num_comments": 3,
                    "created_at_i": 1790323200,
                }
            ]
            return httpx.Response(200, json={"hits": hits, "nbPages": 2})
        tree = {
            "id": 100,
            "children": [
                {
                    "id": 201,
                    "type": "comment",
                    "author": "a",
                    "text": "<p>First</p>",
                    "created_at_i": 1790323300,
                    "children": [
                        {
                            "id": 202,
                            "type": "comment",
                            "author": "b",
                            "text": "Reply",
                            "created_at_i": 1790323400,
                            "children": [],
                        }
                    ],
                },
                {"id": 203, "type": "comment", "author": None, "text": None, "children": []},
            ],
        }
        return httpx.Response(200, json=tree)

    return httpx.MockTransport(handler)


def test_hackernews_search_pages_and_window_filters() -> None:
    calls: list[httpx.Request] = []
    adapter = HackerNewsAdapter(
        allowed_hosts=frozenset({"hn.algolia.com"}),
        before_request=_allow,
        transport=_hn_transport(calls),
    )
    request = _search(
        "hackernews",
        page_size=1,
        sort=SourceSort.LATEST,
        starts_at=datetime(2026, 9, 25, tzinfo=UTC),
        ends_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    first = adapter.fetch_page(request)
    second = adapter.fetch_page(request.model_copy(update={"page_token": first.next_page_token}))

    assert first.state is SourcePageState.MORE and first.next_page_token == "1"
    assert second.state is SourcePageState.COMPLETE
    assert calls[0].url.params["numericFilters"] == (
        "created_at_i>=1790294400,created_at_i<1790380800"
    )
    post = first.items[0]
    assert isinstance(post, SourcePost)
    assert (post.external_id, post.title, post.like_count, post.comment_count) == (
        "100",
        "Story 0",
        42,
        3,
    )
    assert post.canonical_url == "https://news.ycombinator.com/item?id=100"


def test_hackernews_comments_keep_reply_parents_and_skip_deleted() -> None:
    calls: list[httpx.Request] = []
    adapter = HackerNewsAdapter(
        allowed_hosts=frozenset({"hn.algolia.com"}),
        before_request=_allow,
        transport=_hn_transport(calls),
    )
    request = CommentsRequest(source_key="hackernews", post_external_id="100", page_size=1)
    first = adapter.fetch_page(request)
    second = adapter.fetch_page(request.model_copy(update={"page_token": first.next_page_token}))

    assert len(calls) == 1
    comments = [*first.items, *second.items]
    assert all(isinstance(item, SourceComment) for item in comments)
    assert [
        (c.external_id, c.post_external_id, c.parent_comment_external_id, c.text)
        for c in comments
        if isinstance(c, SourceComment)
    ] == [("201", "100", None, "First"), ("202", "100", "201", "Reply")]
    assert second.state is SourcePageState.COMPLETE


def test_hackernews_deleted_parent_keeps_root_target_and_gap() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 100,
                "children": [
                    {
                        "id": 201,
                        "type": "comment",
                        "parent_id": 100,
                        "text": "Root",
                        "created_at_i": 1790323300,
                        "children": [
                            {
                                "id": 202,
                                "type": "comment",
                                "parent_id": 201,
                                "text": None,
                                "children": [
                                    {
                                        "id": 203,
                                        "type": "comment",
                                        "parent_id": 202,
                                        "text": "Reply",
                                        "created_at_i": 1790323400,
                                        "children": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    adapter = HackerNewsAdapter(before_request=_allow, transport=httpx.MockTransport(respond))
    page = adapter.fetch_page(
        CommentsRequest(source_key="hackernews", post_external_id="100", page_size=10)
    )

    assert page.state is SourcePageState.COMPLETE
    root, reply = page.items
    assert isinstance(root, SourceComment) and isinstance(reply, SourceComment)
    assert (root.root_comment_external_id, root.parent_relation_status) == ("201", "root")
    assert (
        reply.root_comment_external_id,
        reply.parent_comment_external_id,
        reply.reply_target_comment_external_id,
        reply.parent_relation_status,
    ) == ("201", "202", "202", "unavailable")


def test_hackernews_rejects_parent_id_conflicting_with_tree() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 100,
                "children": [
                    {
                        "id": 201,
                        "type": "comment",
                        "parent_id": 999,
                        "text": "Wrong parent",
                        "children": [],
                    }
                ],
            },
        )

    adapter = HackerNewsAdapter(before_request=_allow, transport=httpx.MockTransport(respond))
    page = adapter.fetch_page(
        CommentsRequest(source_key="hackernews", post_external_id="100", page_size=10)
    )

    assert (page.state, page.stop_reason) == (
        SourcePageState.STOPPED,
        SourceStopReason.PROTOCOL_ERROR,
    )


def test_web_search_uses_searxng_json_and_dedupes_urls() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        results = [
            {
                "engine": "duckduckgo news",
                "url": "https://news.qq.com/a",
                "title": "SU7 销量",
                "content": "<b>九月</b>销量",
                "publishedDate": "2026-09-25T06:00:00",
            },
            {"engine": "duckduckgo news", "url": "https://news.qq.com/a", "title": "dup"},
            {"engine": "duckduckgo news", "url": "javascript:alert(1)", "title": "bad"},
            {
                "engine": "duckduckgo news",
                "url": "https://sina.cn/b",
                "title": "SU7 评测",
                "publishedDate": "2026-09-25T07:00:00+08:00",
            },
        ]
        return httpx.Response(200, content=json.dumps({"results": results}).encode())

    adapter = WebSearchAdapter(
        base_url="http://127.0.0.1:8888/",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=_allow,
        transport=httpx.MockTransport(handler),
    )
    page = adapter.fetch_page(_search("web"))

    assert calls[0].url.params["format"] == "json"
    assert calls[0].url.params["engines"] == "duckduckgo news"
    assert "categories" not in calls[0].url.params
    assert page.state is SourcePageState.COMPLETE
    assert page.next_page_token is None
    naive, aware = page.items
    assert isinstance(naive, SourcePost) and isinstance(aware, SourcePost)
    assert naive.published_at == datetime(2026, 9, 25, 6, tzinfo=UTC)
    assert aware.published_at == datetime(2026, 9, 24, 23, tzinfo=UTC)
    assert aware.canonical_url == "https://sina.cn/b"
    assert naive.text == "九月 销量"


def test_redirect_to_host_outside_allowlist_is_denied() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "feeds.example.com":
            pytest.fail("redirect target must be rejected before a request is sent")
        return httpx.Response(302, headers={"location": "https://outside.example/rss"})

    adapter = RssSourceAdapter(
        source_key="rss",
        feed_url_template="https://feeds.example.com/rss",
        allowed_hosts=frozenset({"feeds.example.com"}),
        before_request=_allow,
        max_requests=6,
        transport=httpx.MockTransport(handler),
    )

    page = adapter.fetch_page(_search("rss"))

    assert page.stop_reason is SourceStopReason.ACCESS_DENIED
    assert page.request_count == 1


def test_redirect_to_private_address_is_denied_even_when_allowlisted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "feeds.example.com":
            pytest.fail("private redirect target must be rejected before a request is sent")
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    adapter = RssSourceAdapter(
        source_key="rss",
        feed_url_template="https://feeds.example.com/rss",
        allowed_hosts=frozenset({"feeds.example.com", "169.254.169.254"}),
        before_request=_allow,
        max_requests=6,
        transport=httpx.MockTransport(handler),
    )

    page = adapter.fetch_page(_search("rss"))

    assert page.stop_reason is SourceStopReason.ACCESS_DENIED
    assert page.request_count == 1


def test_allowlisted_redirects_are_followed_for_at_most_five_hops() -> None:
    paths: list[str] = []

    def succeeds_after_redirect(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/rss":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, content=_RSS.encode())

    adapter = RssSourceAdapter(
        source_key="rss",
        feed_url_template="https://feeds.example.com/rss",
        allowed_hosts=frozenset({"feeds.example.com"}),
        before_request=_allow,
        max_requests=6,
        transport=httpx.MockTransport(succeeds_after_redirect),
    )

    page = adapter.fetch_page(_search("rss"))

    assert paths == ["/rss", "/final"]
    assert page.state is SourcePageState.COMPLETE
    assert page.request_count == 2

    redirect_requests = 0

    def never_finishes(request: httpx.Request) -> httpx.Response:
        nonlocal redirect_requests
        redirect_requests += 1
        return httpx.Response(302, headers={"location": f"/redirect/{redirect_requests}"})

    limited = RssSourceAdapter(
        source_key="rss",
        feed_url_template="https://feeds.example.com/rss",
        allowed_hosts=frozenset({"feeds.example.com"}),
        before_request=_allow,
        max_requests=7,
        transport=httpx.MockTransport(never_finishes),
    )

    stopped = limited.fetch_page(_search("rss"))

    assert stopped.stop_reason is SourceStopReason.PROTOCOL_ERROR
    assert stopped.request_count == 6
    assert redirect_requests == 6


def test_configured_endpoint_hosts_must_be_allowlisted() -> None:
    with pytest.raises(ValueError, match="feed_url_template host must be allowlisted"):
        RssSourceAdapter(
            source_key="rss",
            feed_url_template="https://feeds.example.com/rss",
            allowed_hosts=frozenset({"other.example"}),
            before_request=_allow,
        )

    with pytest.raises(ValueError, match="base_url host must be allowlisted"):
        WebSearchAdapter(
            base_url="http://127.0.0.1:8888",
            allowed_hosts=frozenset({"localhost"}),
            before_request=_allow,
        )
