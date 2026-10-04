from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from connections.editorial_services import PreparedEditorialRun
from sources.adapters.editorial_http import EditorialHttpClient, EditorialSourceError
from sources.adapters.editorial_rss import parse_feed
from sources.editorial_factory import ConfiguredEditorialCollectorFactory
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_rsshub import RSSHUB_REVISION, EditorialRsshubAdmission, rsshub_route_blocker
from sources.editorial_schemas import (
    EditorialAuthorization,
    EditorialCursor,
    EditorialProfileView,
    EditorialRunResult,
    EditorialSourceConfiguration,
    RssValidator,
    fingerprint,
)

NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Reviewed feed</title>
<link>https://www.threads.com/@sample</link><description>Finite snapshot</description>
<item><title>One public update</title><link>https://www.threads.com/@sample/post/ABC</link>
<guid isPermaLink="false">feed-guid-is-not-platform-id</guid>
<description>Observed post text</description>
<pubDate>Sun, 04 Oct 2026 02:00:00 GMT</pubDate></item></channel></rss>"""


def rsshub_config(**overrides: object) -> EditorialSourceConfiguration:
    nested: dict[str, object] = {
        "platform": "threads",
        "query_mode": "author_stream",
        "target": "sample",
        "route": "/threads/sample",
        "revision": RSSHUB_REVISION,
        "item_hosts": ["www.threads.com"],
        "downstream_hosts": ["www.threads.com"],
        "text_scope": "post_text",
        "max_downstream_requests": 1,
        "cache_ttl_seconds": 300,
        "review": {
            "purpose_reference": "evidence://purpose",
            "downstream_reference": "trace://egress",
            "cache_reference": "deployment://cache",
            "fee_reference": "evidence://zero-fee",
            "stop_reference": "test://stop",
            "deployment_reference": "deployment://fixed-service",
            "reviewed_at": NOW,
            "expires_at": NOW + timedelta(days=7),
        },
    }
    nested.update(overrides)
    return EditorialSourceConfiguration.model_validate(
        {
            "kind": "rss",
            "allowed_hosts": ["127.0.0.1"],
            "rsshub": nested,
            "feed_url": "http://127.0.0.1:1200" + str(nested["route"]),
        }
    )


def profile(config: EditorialSourceConfiguration) -> EditorialProfileView:
    return EditorialProfileView(
        id=uuid4(),
        source_key="ed_rss_" + uuid4().hex,
        name="Controlled source",
        enabled=True,
        revision=2,
        configuration_version=2,
        configuration=config,
        participation_mode="editorial",
        tier="T2",
        first_party=False,
        connection_id=uuid4(),
        connection_version=2,
        policy_version=1,
        interval_minutes=60,
        health="unknown",
        failure_count=0,
        last_fetch_at=None,
        last_ok_at=None,
        next_fetch_at=None,
        has_backlog=False,
    )


def admission(config: EditorialSourceConfiguration) -> EditorialRsshubAdmission:
    assert config.rsshub
    return EditorialRsshubAdmission(
        configuration_sha256=fingerprint(config.model_dump(mode="json")).hex(),
        revision=config.rsshub.revision,
        reviewed_at=NOW,
        expires_at=NOW + timedelta(days=7),
        max_downstream_requests=config.rsshub.max_downstream_requests,
    )


def client(config, handler, *, proof=True):
    sent, settled, checked = [], [], []

    def request_handler(request):
        sent.append(request)
        return handler(request)

    def gate():
        checked.append(True)
        return admission(config) if proof is True else proof

    http = EditorialHttpClient(
        allowed_hosts=frozenset(config.allowed_hosts),
        authorization=EditorialAuthorization(
            connection_enabled=True,
            owner_authorized=True,
            budget_confirmed=True,
            credentials_ready=True,
        ),
        before_request=lambda attempt: True,
        settle_request=lambda attempt, outcome: settled.append((attempt, outcome)),
        transport=httpx.MockTransport(request_handler),
        rsshub=config.rsshub,
        rsshub_configuration_sha256=fingerprint(config.model_dump(mode="json")).hex(),
        rsshub_admission=gate if proof is not None else None,
        clock=lambda: NOW,
    )
    return http, sent, settled, checked


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:1201/threads/sample",
        "http://localhost:1200/threads/sample",
        "http://127.0.0.2:1200/threads/sample",
        "http://user:secret@127.0.0.1:1200/threads/sample",
        "http://127.0.0.1:1200/threads/other",
        "http://127.0.0.1:1200/threads/sample?limit=30",
    ],
)
def test_local_endpoint_is_exact_and_never_widens_public_guard(url):
    config = rsshub_config()
    with pytest.raises(ValidationError):
        EditorialSourceConfiguration.model_validate({**config.model_dump(), "feed_url": url})
    with pytest.raises(ValidationError):
        EditorialSourceConfiguration(kind="rss", allowed_hosts=("127.0.0.1",), feed_url=url)


@pytest.mark.parametrize(
    "value",
    [
        "/threads/../sample",
        "/threads/%2fsample",
        "/threads/%252fsample",
        "/threads/sample#part",
        "//evil.com/thread",
        "/threads/sample?token=secret",
    ],
)
def test_route_traversal_and_unfrozen_parameters_refused(value):
    with pytest.raises(ValidationError):
        rsshub_config(route=value)


@pytest.mark.parametrize(
    "values",
    [
        {"supplier_fee_cny_micros": 1},
        {"fallback": "paid"},
        {"browser": "enabled"},
        {"query_parameters": {"cookie": "secret"}},
        {"max_local_requests": 2},
    ],
)
def test_fee_fallback_browser_and_credentials_are_rejected_before_http(values):
    with pytest.raises(ValidationError):
        rsshub_config(**values)


def test_candidate_routes_are_not_execution_approval():
    for platform, route, reason in (
        ("douyin", "/douyin/user/123", "rsshub_browser_route_blocked"),
        ("weibo", "/weibo/user/123", "rsshub_fixed_cookie_branch_unverified"),
        ("bilibili", "/bilibili/user/video/123", "rsshub_bilibili_route_unverified"),
        ("x", "/twitter/user/sample", "rsshub_x_secret_and_fee_boundary"),
        ("facebook", "/facebook/sample", "rsshub_facebook_route_unavailable"),
    ):
        config = rsshub_config(platform=platform, route=route)
        assert rsshub_route_blocker(config.rsshub) == reason


def test_threads_default_tags_cannot_be_declared_native_keyword_search():
    assert (
        rsshub_route_blocker(
            rsshub_config(query_mode="tag_feed", target="news", route="/threads/search/news").rsshub
        )
        is None
    )
    assert (
        rsshub_route_blocker(
            rsshub_config(
                query_mode="platform_keyword", target="news", route="/threads/search/news"
            ).rsshub
        )
        == "rsshub_query_contract_mismatch"
    )
    assert (
        rsshub_route_blocker(
            rsshub_config(
                query_mode="platform_keyword",
                target="news",
                route="/threads/search/news/serpType=recent",
            ).rsshub
        )
        is None
    )


def test_instagram_anonymous_declaration_and_review_cannot_certify_shared_cache():
    config = rsshub_config(
        platform="instagram",
        target="sample",
        route="/instagram/2/user/sample",
        item_hosts=["www.instagram.com"],
        downstream_hosts=["www.instagram.com"],
        text_scope="caption",
    )
    assert rsshub_route_blocker(config.rsshub) == "rsshub_anonymous_cache_isolation_unverified"
    http, sent, settled, _checked = client(
        config, lambda request: httpx.Response(200, content=FEED)
    )
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    page = registry.collect(profile(config), EditorialCursor(), {})
    registry.close()
    assert page.status == "blocked"
    assert page.reason == "rsshub_anonymous_cache_isolation_unverified"
    assert not sent and not settled


def test_approved_feed_retains_observed_dates_url_and_unknown_downstream_count():
    config = rsshub_config()
    http, sent, settled, checked = client(config, lambda request: httpx.Response(200, content=FEED))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    page = registry.collect(profile(config), EditorialCursor(), {})
    registry.close()
    assert page.status == "complete" and page.request_count == 1
    assert len(sent) == len(checked) == 1 and settled == [(1, "succeeded")]
    item = page.materials[0]
    assert item.published_at == datetime(2026, 10, 4, 2, tzinfo=UTC)
    assert item.external_id is None and item.metadata["feed_guid"] == "feed-guid-is-not-platform-id"
    assert item.identity_key == "url:https://www.threads.com/@sample/post/ABC"
    assert item.metadata["downstream_request_count"] is None
    assert item.metadata["snapshot_scope"] == "limited_feed"
    assert item.body_status == "pending" and item.excerpt == "Observed post text"


def test_updated_only_is_not_invented_publication_and_long_description_not_full_article():
    config = rsshub_config()
    sample = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title><entry><title>Post</title><link href="https://www.threads.com/@sample/post/ABC"/><updated>2026-10-04T02:00:00Z</updated><summary>'
        + "caption " * 60
        + "</summary></entry></feed>"
    )
    item = parse_feed(sample, config.feed_url, config)[0]
    assert item.published_at is None and item.source_updated_at is not None
    assert item.body_text is None and item.body_status == "pending" and item.excerpt


@pytest.mark.parametrize(
    "body,status,reason",
    [
        (b"<html><title>Login</title>captcha</html>", "blocked", "rsshub_authentication_required"),
        (b"<html><title>Service unavailable</title></html>", "partial", "rsshub_html_response"),
        (
            b'<rss version="2.0"><channel><title>Empty</title></channel></rss>',
            "partial",
            "rsshub_empty_snapshot_unverified",
        ),
        (b"<rss><broken", "partial", "source_protocol_error"),
        (
            FEED.replace(b"www.threads.com/@sample/post/ABC", b"unapproved.example/post/ABC"),
            "blocked",
            "rsshub_item_target_unapproved",
        ),
    ],
)
def test_bad_or_empty_feeds_stop_without_success_cursor_or_detail_fallback(body, status, reason):
    config = rsshub_config()
    original = EditorialCursor(
        initialized_at=NOW - timedelta(days=1), last_ok_at=NOW - timedelta(days=1)
    )
    http, sent, _, _ = client(config, lambda request: httpx.Response(200, content=body))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    page = registry.collect(profile(config), original, {})
    registry.close()
    assert (page.status, page.reason, page.cursor) == (status, reason, original)
    assert len(sent) == 1 and page.materials == ()


@pytest.mark.parametrize(
    "location",
    ["/threads/sample", "https://www.threads.com/@sample", "http://127.0.0.1:8000/admin"],
)
def test_all_local_redirects_stop_after_one_metered_request(location):
    config = rsshub_config()
    http, sent, settled, _ = client(
        config, lambda request: httpx.Response(302, headers={"location": location})
    )
    with pytest.raises(EditorialSourceError, match="rsshub_redirect_forbidden"):
        http.request(config.feed_url)
    http.close()
    assert len(sent) == 1 and settled == [(1, "failed")]


@pytest.mark.parametrize(
    "change",
    [
        {"configuration_sha256": "0" * 64},
        {"revision": "0" * 40},
        {"supplier_fee_cny_micros": 1},
        {"max_downstream_requests": 9},
        {"expires_at": NOW},
    ],
)
def test_changed_review_or_fee_blocks_before_metering_and_network(change):
    config = rsshub_config()
    proof = replace(admission(config), **change)
    http, sent, settled, _ = client(
        config, lambda request: httpx.Response(200, content=FEED), proof=proof
    )
    with pytest.raises(EditorialSourceError, match="rsshub_admission_changed"):
        http.request(config.feed_url)
    http.close()
    assert sent == settled == [] and http.request_count == 0


def test_missing_server_approval_is_denied_before_network():
    config = rsshub_config()
    http, sent, settled, _ = client(
        config, lambda request: httpx.Response(200, content=FEED), proof=None
    )
    with pytest.raises(EditorialSourceError, match="rsshub_route_review_required"):
        http.request(config.feed_url)
    http.close()
    assert sent == settled == []


def test_unexpected_304_has_no_implicit_second_request():
    config = rsshub_config()
    http, sent, _, _ = client(config, lambda request: httpx.Response(304))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    page = registry.collect(profile(config), EditorialCursor(), {})
    registry.close()
    assert page.status == "partial" and page.reason == "rsshub_unexpected_not_modified"
    assert len(sent) == 1 and page.cursor.initialized_at is None


def test_matching_304_is_only_a_feed_cache_observation():
    config = rsshub_config()
    cursor = EditorialCursor(
        initialized_at=NOW - timedelta(days=1),
        rss=RssValidator(
            configuration_hash=fingerprint(config.model_dump(mode="json")).hex(),
            response_url=config.feed_url,
            etag='"snapshot-1"',
        ),
    )
    http, sent, _, _ = client(config, lambda request: httpx.Response(304))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW)
    page = registry.collect(profile(config), cursor, {})
    registry.close()
    assert page.status == "unchanged" and page.request_count == 1
    assert sent[0].headers["if-none-match"] == '"snapshot-1"'


def test_rate_limit_and_oversize_are_bounded_without_retry():
    config = rsshub_config(max_response_bytes=1024)
    for response, code in (
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(200, content=b"a" * 1025), "response_too_large"),
    ):
        http, sent, settled, _ = client(config, lambda request, value=response: value)
        with pytest.raises(EditorialSourceError, match=code):
            http.request(config.feed_url)
        http.close()
        assert len(sent) == 1 and settled == [(1, "failed")]


@pytest.mark.parametrize("kind", ["x_search", "mp_account", "jina"])
def test_zero_supplier_fee_factory_blocks_old_paid_routes_before_http(kind):
    config = EditorialSourceConfiguration.model_validate(
        {"kind": "x_search", "query": "sample"}
        if kind == "x_search"
        else {"kind": "mp_account", "wxid": "sample"}
        if kind == "mp_account"
        else {
            "kind": "web_list",
            "allowed_hosts": ["r.jina.ai", "example.com"],
            "url": "https://r.jina.ai/https://example.com/",
            "item_selector": "a",
        }
    )
    p = profile(config)
    prepared = PreparedEditorialRun(
        EditorialRunResult(run_id=uuid4(), status="running", configuration_version=2),
        p,
        EditorialCursor(),
        {},
        None,
        True,
    )
    sent = []
    factory = ConfiguredEditorialCollectorFactory(
        sessionmaker(),
        owner_id=uuid4(),
        job_id=uuid4(),
        operation_id=uuid4(),
        public_enabled=True,
        transport=httpx.MockTransport(lambda request: sent.append(request)),
        clock=lambda: NOW,
    )
    registry = factory(prepared)
    page = registry.collect(p, prepared.cursor, {})
    registry.close()
    assert page.status == "blocked" and page.reason == "free_only_paid_source"
    assert sent == [] and page.request_count == 0
