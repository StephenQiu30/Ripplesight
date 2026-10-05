from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from sources.adapters.editorial_http import EditorialHttpClient, EditorialSourceError
from sources.adapters.editorial_jina import EditorialJinaReader
from sources.adapters.editorial_json import parse_json_list
from sources.adapters.editorial_mp import (
    DajialaEditorialClient,
    EditorialMpCollector,
    MpArticle,
    MpHistory,
    MpPost,
)
from sources.adapters.editorial_parsing import get_path, parse_loose_date, render_template
from sources.adapters.editorial_rss import parse_feed
from sources.adapters.editorial_web import parse_web_list
from sources.adapters.editorial_x import (
    EditorialXCollector,
    OfficialEditorialXClient,
    shard_eligible,
)
from sources.adapters.x_context import OfficialXContextReader
from sources.contracts import SourcePost
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_schemas import (
    EditorialAuthorization,
    EditorialCursor,
    EditorialProfileView,
    EditorialSourceConfiguration,
    SearchBacklog,
)


def config(kind: str, **kwargs: object) -> EditorialSourceConfiguration:
    return EditorialSourceConfiguration.model_validate(
        {"kind": kind, "allowed_hosts": ["example.com"], **kwargs}
    )


def test_strict_configuration_refuses_unknown_fields_and_credentials() -> None:
    with pytest.raises(ValidationError):
        config("rss", feed_url="https://example.com/rss", title_selector="h1")
    with pytest.raises(ValidationError):
        config("json_list", url="https://example.com/api", headers={"Authorization": "secret"})


def test_json_path_template_and_source_offset_are_host_independent() -> None:
    assert get_path({"items": [{"id": "a/b", "title": "A B"}]}, "items.0.id") == "a/b"
    assert (
        render_template("https://example.com/{id}?q={title}", {"id": "a/b", "title": "A B"})
        == "https://example.com/a/b?q=A%20B"
    )
    assert render_template("https://example.com/{missing}", {}) is None
    assert parse_loose_date("2026年9月26日 10:00", "+08:00") == datetime(2026, 9, 26, 2, tzinfo=UTC)
    assert parse_loose_date("2026-09-26") == datetime(2026, 9, 26, tzinfo=UTC)


def test_rss_teaser_atom_xml_base_and_script_sanitization() -> None:
    c = config("rss", feed_url="https://example.com/feed")
    page = parse_feed(
        (
            '<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://examp'
            'le.com/base/"><entry><id>id1</id><title>Actual update</title><lin'
            'k href="post"/><content type="html">&lt;p&gt;Read the full story&'
            "lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;</content><updated>"
            "2026-09-26T10:00:00Z</updated></entry></feed>"
        ),
        "https://example.com/feed",
        c,
    )
    assert page[0].url == "https://example.com/base/post"
    assert page[0].body_status == "pending" and page[0].body_text is None
    assert "alert" not in (page[0].excerpt or "")


def test_rss_short_content_without_summary_is_kept_for_site_reading() -> None:
    page = parse_feed(
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>short</id>'
        '<title>Update</title><link href="https://example.com/post"/>'
        '<content type="html">&lt;p&gt;First paragraph.&lt;/p&gt;'
        "&lt;p&gt;Second paragraph.&lt;/p&gt;</content></entry></feed>",
        "https://example.com/feed",
        config("rss", feed_url="https://example.com/feed"),
    )
    assert page[0].excerpt == "First paragraph.\nSecond paragraph."
    assert page[0].body_status == "pending"


def test_web_html_dates_markdown_navigation_and_docusaurus_sections() -> None:
    html = (
        '<article><a href="/post">Specific model update</a><time datetime='
        '"2026-09-26 10:00"></time></article>'
    )
    c = config(
        "web_list",
        url="https://example.com/news",
        item_selector="article",
        published_at_selector="time",
    )
    rows = parse_web_list(html, "https://example.com/news", c)
    assert rows[0].published_at == datetime(2026, 9, 26, 2, tzinfo=UTC)
    md = config(
        "web_list", url="https://example.com/news", parse_mode="markdown", links_start_line=True
    )
    rows = parse_web_list(
        (
            "[All news](https://example.com/news)\n## [Actual new model](https:"
            "//example.com/post)\nA paragraph [Another link](https://example.co"
            "m/no)"
        ),
        "https://example.com/news",
        md,
    )
    assert [row.url for row in rows] == ["https://example.com/post"]
    section = config(
        "web_list",
        url="https://example.com/log",
        parse_mode="docusaurus_changelog",
        preserve_url_fragment=True,
    )
    rows = parse_web_list(
        (
            '<article><h2 id="day">2026-09-26</h2><h3 id="update">New model</h'
            "3><p>Concrete changelog body</p></article>"
        ),
        "https://example.com/log",
        section,
    )
    assert len(rows) == 1 and rows[0].url.endswith("#update") and rows[0].body_status == "ok"


def test_json_embedded_and_conditions_never_execute_javascript() -> None:
    c = config(
        "json_list",
        url="https://example.com/api",
        mode="html_window_var",
        window_var="DATA",
        items_path="items",
        title_paths=["title"],
        url_template="https://example.com/post/{id}",
        require_boolean={"path": "published", "equals": True},
        published_at_path="date",
        published_at_unit="yyyymmdd",
    )
    rows = parse_json_list(
        (
            'window.DATA = {"items":[{"id":1,"title":"Model","published":true,'
            '"date":"20260926"},{"id":2,"title":"No","published":false}]};'
        ),
        c,
    )
    assert len(rows) == 1 and rows[0].published_at == datetime(2026, 9, 26, tzinfo=UTC)
    with pytest.raises(ValueError):
        parse_json_list('window.DATA = {"items":(function(){return []})()};', c)


NOW = datetime(2026, 10, 2, 2, tzinfo=UTC)


def profile(c):
    return EditorialProfileView(
        id=uuid4(),
        source_key="ed_rss_" + uuid4().hex,
        name="Controlled",
        enabled=True,
        revision=1,
        configuration_version=1,
        configuration=c,
        participation_mode="editorial",
        tier="T1",
        first_party=True,
        connection_id=None,
        connection_version=None,
        policy_version=1,
        interval_minutes=30,
        health="unknown",
        failure_count=0,
        last_fetch_at=None,
        last_ok_at=None,
        next_fetch_at=None,
        has_backlog=False,
    )


def admitted_http(handler, *, hosts=("example.com",), max_requests=25):
    settled = []
    client = EditorialHttpClient(
        allowed_hosts=frozenset(hosts),
        authorization=EditorialAuthorization(
            connection_enabled=True,
            owner_authorized=True,
            budget_confirmed=True,
            credentials_ready=True,
        ),
        before_request=lambda n: True,
        settle_request=lambda n, outcome: settled.append((n, outcome)),
        transport=httpx.MockTransport(handler),
        max_requests=max_requests,
    )
    return client, settled


def test_http_default_denies_no_requests_and_unknown_settles_once():
    calls = []
    client = EditorialHttpClient(
        allowed_hosts=frozenset({"example.com"}),
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200)),
    )
    with pytest.raises(EditorialSourceError, match="source_authorization_required"):
        client.request("https://example.com/")
    assert not calls
    client.close()

    def timeout(request):
        raise httpx.ReadTimeout("Controlled lost answer", request=request)

    client, settled = admitted_http(timeout)
    with pytest.raises(EditorialSourceError) as error:
        client.request("https://example.com/")
    assert error.value.unknown and settled == [(1, "unknown")]
    client.close()


def test_http_redirect_budget_origin_header_isolation_and_runtime_key_redaction():
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(302, headers={"location": "https://other.example/post"})
            if len(calls) == 1
            else httpx.Response(200, text="Done")
        )

    client, settled = admitted_http(handler, hosts=("example.com", "other.example"))
    client.request("https://example.com/", headers={"authorization": "Bearer controlled"})
    assert "authorization" not in calls[1].headers and len(settled) == 2
    client.close()
    client, settled = admitted_http(lambda request: httpx.Response(200, text="Done"))
    answer = client.request(
        "https://example.com/detail", credential_query={"key": SecretStr("controlled-key")}
    )
    assert "controlled-key" not in answer.url
    client.close()


def test_rss_etag_304_redirect_and_changed_configuration_never_false_empty():
    feed = (
        '<rss version="2.0"><channel><title>News</title><item><title>New m'
        "odel</title><link>https://example.com/post</link></item></channel"
        "></rss>"
    )
    calls = []

    def handler(request):
        calls.append(request)
        if request.headers.get("if-none-match"):
            return httpx.Response(304)
        return httpx.Response(200, text=feed, headers={"etag": "version-one"})

    http, _ = admitted_http(handler)
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    p = profile(config("rss", feed_url="https://example.com/feed", allowed_hosts=("example.com",)))
    first = registry.collect(p, EditorialCursor(), {})
    assert first.status == "complete" and len(first.materials) == 1
    second = registry.collect(p, first.cursor, {})
    assert second.status == "unchanged" and len(calls) == 2
    p = p.model_copy(
        update={"configuration": p.configuration.model_copy(update={"summary_is_body": True})}
    )
    third = registry.collect(p, second.cursor, {})
    assert third.status == "complete" and "if-none-match" not in calls[2].headers
    registry.close()


def x_response(id="200", *, token=None, note=None, refs=()):
    row = {
        "id": id,
        "text": "Short source body",
        "author_id": "10",
        "created_at": "2026-10-02T01:00:00Z",
        "referenced_posts": list(refs),
    }
    if note:
        row["note_post"] = {"text": note}
    return {
        "data": [row],
        "includes": {
            "users": [{"id": "10", "username": "sourceaccount", "name": "Source Account"}]
        },
        "meta": {"next_token": token} if token else {},
    }


def test_official_x_post_fields_top_long_body_backlog_exact_query_and_no_retweets():
    calls = []

    def handler(request):
        calls.append(request)
        params = request.url.params
        return httpx.Response(
            200,
            json=x_response(
                note="Complete long source body",
                token="cursor-two" if params.get("next_token") is None else None,
            ),
        )

    http, _ = admitted_http(handler, hosts=("api.x.com",))
    client = OfficialEditorialXClient(http, bearer=SecretStr("controlled"))
    c = config("x_search", query="from:sourceaccount -filter:replies", search_type="Top")
    page = EditorialXCollector(client, fresh_pages=1, backlog_pages=1).collect(
        c, EditorialCursor(initialized_at=NOW, last_tweet_id="100"), {}, NOW
    )
    assert page.status == "partial" and page.cursor.x_backlog[0].query == c.query
    assert (
        page.cursor.x_backlog[0].stop_at_id == "100"
        and page.cursor.x_backlog[0].next_token == "cursor-two"
    )
    assert page.materials[0].body_text == "Complete long source body"
    assert calls[0].url.params["post.fields"] and calls[0].url.params["sort_order"] == "relevancy"
    assert calls[0].url.params["query"].endswith("-is:reply")
    http.close()


def test_x_backlog_failure_retains_held_gap_and_replay_unknown_blocks():
    def handler(request):
        if request.url.params.get("next_token"):
            return httpx.Response(400)
        return httpx.Response(200, json=x_response())

    http, _ = admitted_http(handler, hosts=("api.x.com",))
    c = config("x_search", query="from:sourceaccount")
    gap = SearchBacklog(query="old frozen query", next_token="old-token", stop_at_id="90")
    page = EditorialXCollector(
        OfficialEditorialXClient(http, bearer=SecretStr("controlled"))
    ).collect(
        c, EditorialCursor(initialized_at=NOW, last_tweet_id="100", x_backlog=(gap,)), {}, NOW
    )
    assert page.status == "partial" and page.cursor.x_backlog[0].state == "held"
    assert page.cursor.x_backlog[0].next_token == "old-token"
    http.close()


def test_x_shard_24_member_470_character_bounds_mode_and_quiet_account_watermark():
    profiles = tuple(profile(config("x_search", query=f"from:account{i}")) for i in range(30))
    cursors = {p.id: EditorialCursor(last_tweet_id="100", last_ok_at=NOW) for p in profiles}
    shards = shard_eligible(profiles, cursors)
    assert len(shards) == 2 and len(shards[0].members) <= 24
    assert all(len(shard.query) <= 470 and int(shard.since_id) > 100 for shard in shards)
    assert all(shard.interval_minutes == 30 for shard in shards)


def test_official_reply_and_quote_context_two_levels_is_bounded():
    def handler(request):
        id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(
            200, json=x_response(id, refs=({"id": str(int(id) - 1), "type": "replied_to"},))
        )

    http, _ = admitted_http(handler, hosts=("api.x.com",))
    reader = OfficialXContextReader(OfficialEditorialXClient(http, bearer=SecretStr("controlled")))
    post = SourcePost(
        source_key="x",
        author_external_id="10",
        like_count=0,
        comment_count=0,
        repost_count=0,
        external_id="100",
        text="Announcement",
        published_at=NOW,
        parent_external_id="99",
        quote_external_id="89",
    )
    contexts = reader.read_context(post, max_reply_depth=2)
    assert len(contexts) == 4 and contexts[0].id == "99" and contexts[1].relation == "quote"
    assert http.request_count == 4
    http.close()


def test_mp_paid_paused_body_sanitized_seven_day_eight_posts_and_unknown_stop():
    class Provider:
        request_count = 0

        def history(self, account, *, window):
            self.request_count += 1
            return MpHistory(
                posts=tuple(
                    MpPost(
                        url=f"https://mp.weixin.qq.com/s/{i}",
                        title=f"News {i}",
                        post_time=int(NOW.timestamp()) - i,
                    )
                    for i in range(10)
                )
            )

        def article(self, url, *, identity):
            self.request_count += 1
            return MpArticle(content="<p>Original source</p><script>secret()</script>")

    provider = Provider()
    c = config("mp_account", ghid="controlled-account")
    assert EditorialMpCollector(provider).collect(c, EditorialCursor(), {}, NOW).status == "blocked"
    assert provider.request_count == 0
    auth = EditorialAuthorization(
        connection_enabled=True,
        owner_authorized=True,
        budget_confirmed=True,
        credentials_ready=True,
    )
    result = EditorialMpCollector(provider, authorization=auth).collect(
        c, EditorialCursor(), {}, NOW
    )
    assert (
        result.status == "complete" and len(result.materials) == 8 and provider.request_count == 9
    )
    assert result.materials[0].body_text == "Original source"
    assert "secret" not in result.materials[0].body_html


def test_mp_and_jina_full_wire_replay_prices_reported_only_after_admission():
    calls = []

    def handler(request):
        calls.append(request)
        if "post_history" in request.url.path:
            return httpx.Response(200, json={"code": 0, "data": [], "cost_money": 0.14})
        if "article_detail" in request.url.path:
            return httpx.Response(
                200, json={"code": 0, "content": "<p>Source</p>", "cost_money": 0.03}
            )
        return httpx.Response(
            200,
            text=(
                "Title: Source\nURL Source: https://example.com/\nMarkdown Content:\n"
                "# Actual source"
            ),
            headers={"x-usage-tokens": "1000"},
        )

    http, _ = admitted_http(handler, hosts=("www.dajiala.com", "r.jina.ai"))
    costs = []
    provider = DajialaEditorialClient(
        http,
        key=SecretStr("controlled-key"),
        before_paid=lambda purpose: True,
        report_cost=lambda purpose, cost: costs.append((purpose, cost)),
    )
    assert provider.history("account", window="fixed:1").posts == ()
    assert provider.article("https://mp.weixin.qq.com/s/a", identity="a").content
    reader = EditorialJinaReader(
        http,
        key=SecretStr("controlled-key"),
        allowed_targets=frozenset({"example.com"}),
        before_paid=lambda purpose: True,
        report_cost=lambda purpose, cost: costs.append((purpose, cost)),
        cny_per_million_tokens=Decimal("0.36"),
    )
    answer = reader.read("https://r.jina.ai/https://example.com/", format="markdown")
    assert answer.text == "# Actual source" and answer.url == "https://example.com/"
    assert costs == [
        ("mp_history", Decimal("0.14")),
        ("mp_article", Decimal("0.03")),
        ("jina_listing", Decimal("0.00036")),
    ]
    assert "key" in calls[1].url.params
    http.close()


def test_official_x_media_type_alt_and_playable_variant_are_source_facts():
    response = x_response()
    response["data"][0]["attachments"] = {"media_keys": ["photo", "video"]}
    response["includes"]["media"] = [
        {
            "media_key": "photo",
            "type": "photo",
            "url": "https://pbs.twimg.com/photo",
            "alt_text": "Original caption",
        },
        {
            "media_key": "video",
            "type": "video",
            "preview_image_url": "https://pbs.twimg.com/preview",
            "variants": [
                {"content_type": "video/mp4", "bit_rate": 10, "url": "https://video.twimg.com/low"},
                {
                    "content_type": "video/mp4",
                    "bit_rate": 20,
                    "url": "https://video.twimg.com/high",
                },
                {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/stream"},
            ],
        },
    ]
    counts = []
    http, _ = admitted_http(
        lambda request: httpx.Response(200, json=response), hosts=("api.x.com",)
    )
    client = OfficialEditorialXClient(
        http, bearer=SecretStr("controlled"), report_posts=counts.append
    )
    answer = client.search("from:sourceaccount")
    assert [(m.kind, m.url, m.alt) for m in answer.materials[0].media_details] == [
        ("image", "https://pbs.twimg.com/photo", "Original caption"),
        ("video", "https://video.twimg.com/high", None),
        ("image", "https://pbs.twimg.com/preview", None),
    ]
    assert counts == [1] and http.request_count == 1
    http.close()


def test_official_x_malformed_billed_body_reports_unknown_instead_of_empty_success():
    counts = []
    http, _ = admitted_http(
        lambda request: httpx.Response(200, json={"data": "malformed"}), hosts=("api.x.com",)
    )
    client = OfficialEditorialXClient(
        http, bearer=SecretStr("controlled"), report_posts=counts.append
    )
    with pytest.raises(EditorialSourceError) as error:
        client.search("from:sourceaccount")
    assert error.value.unknown and counts == [None]
    assert http.request_count == 1
    http.close()
