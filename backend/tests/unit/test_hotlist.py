from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest

from content.hotlist import _post_payload, _rank_identity, match_hotlist_topics, rank_change
from core.config import Settings
from main import create_app
from monitors.services import ActiveHotlistTopic, normalize_monitor_rules
from reports.services import ReportService
from sources.adapters.rsshub_hotlist import HOTLIST_ROUTES, RsshubHotlistAdapter
from sources.contracts import HotlistEntry, SourceCapability, SourcePageState, SourceStopReason
from worker.scheduler import hotlist_operation_id

FEED = b"""<rss version="2.0"><channel><title>Hot</title>
<item><title>First</title><link>https://example.com/first</link><description>One</description></item>
<item><title>Second</title><link>https://example.com/second</link>
<pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_rsshub_hotlist_preserves_rank_and_missing_publication_time() -> None:
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=FEED)),
    )
    page = adapter.fetch_hotlist()
    assert page.capability is SourceCapability.HOTLIST
    assert [(item.rank, item.title) for item in page.items] == [(1, "First"), (2, "Second")]
    assert page.items[0].published_at is None
    assert page.items[1].published_at == datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert page.request_count == 1


@pytest.mark.parametrize("count", [100, 101])
def test_rsshub_hotlist_retains_first_100_feed_positions(count: int) -> None:
    entries = "".join(
        f"<item><title>Rank {rank}</title><link>https://example.com/{rank}</link></item>"
        for rank in range(1, count + 1)
    )
    feed = f'<rss version="2.0"><channel><title>Hot</title>{entries}</channel></rss>'
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=feed)),
    )
    page = adapter.fetch_hotlist()
    assert page.state is SourcePageState.COMPLETE
    assert len(page.items) == 100
    assert page.items[0].title == "Rank 1"
    assert (page.items[-1].rank, page.items[-1].title) == (100, "Rank 100")


@pytest.mark.parametrize(
    ("source_key", "feed_url"),
    [
        ("hotlist_weibo", "http://127.0.0.1:1200/baidu/top"),
        ("hotlist_weibo", "http://127.0.0.1:1200/weibo/search/hot?mode=other"),
        ("hotlist_other", "http://127.0.0.1:1200/weibo/search/hot"),
    ],
)
def test_rsshub_hotlist_requires_source_fixed_route(source_key: str, feed_url: str) -> None:
    with pytest.raises(ValueError, match="fixed route"):
        RsshubHotlistAdapter(
            source_key=source_key,
            feed_url=feed_url,
            allowed_hosts=frozenset({"127.0.0.1"}),
            before_request=lambda _: True,
        )


@pytest.mark.parametrize("source_key,route", tuple(HOTLIST_ROUTES.items()))
def test_rsshub_hotlist_accepts_each_fixed_route(source_key: str, route: str) -> None:
    adapter = RsshubHotlistAdapter(
        source_key=source_key,
        feed_url=f"http://127.0.0.1:1200{route}",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=FEED)),
    )
    assert adapter.fetch_hotlist().state is SourcePageState.COMPLETE


def test_rsshub_hotlist_rejects_private_result_link() -> None:
    feed = (
        '<rss version="2.0"><channel><title>Hot</title><item><title>AI</title>'
        "<link>http://localhost/internal</link></item></channel></rss>"
    )
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=feed)),
    )
    page = adapter.fetch_hotlist()
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR


def test_rsshub_hotlist_rejects_redirect_outside_local_allowlist() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/feed"})

    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(respond),
    )
    page = adapter.fetch_hotlist()
    assert page.stop_reason.value == "access_denied"
    assert len(requested) == 1


def test_empty_hotlist_is_a_real_zero_after_one_request() -> None:
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"<rss><channel></channel></rss>")
        ),
    )
    page = adapter.fetch_hotlist()
    assert page.state is SourcePageState.EMPTY
    assert page.stop_reason is SourceStopReason.SOURCE_EMPTY
    assert page.items == ()
    assert page.request_count == 1


def test_malformed_feed_with_parseable_entry_is_not_a_successful_snapshot() -> None:
    malformed = (
        b'<rss version="2.0"><channel><title>Hot</title><item><title>A</title>'
        b"<link>https://example.com/a</link></item><broken></channel></rss>"
    )
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=malformed)),
    )
    page = adapter.fetch_hotlist()
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.PROTOCOL_ERROR
    assert page.items == ()
    assert page.request_count == 1


def test_upstream_http_failure_is_not_an_empty_feed() -> None:
    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=lambda _: True,
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    page = adapter.fetch_hotlist()
    assert page.state is SourcePageState.STOPPED
    assert page.stop_reason is SourceStopReason.UPSTREAM_ERROR
    assert page.items == ()
    assert page.request_count == 1


def test_hotlist_content_uses_observation_time_even_with_feed_pubdate() -> None:
    entry = HotlistEntry(
        rank=1,
        title="First",
        url="https://example.com/first",
        published_at=datetime(2026, 9, 25, 8, tzinfo=UTC),
    )
    assert _post_payload(entry, "hotlist_weibo")["published_at"] is None


def test_hotlist_title_without_summary_is_not_marked_as_full_article() -> None:
    entry = HotlistEntry(rank=1, title="Only a ranking title", url="https://example.com/one")
    payload = _post_payload(entry, "hotlist_weibo")
    assert payload["title"] == entry.title
    assert "body" not in payload
    assert payload["text_scope"] == "truncated"
    assert payload["truncation_reason"] == "source_limit"


def test_rank_change_covers_new_up_down_and_same() -> None:
    assert rank_change(1, None) == "new"
    assert rank_change(1, 2) == "up"
    assert rank_change(3, 2) == "down"
    assert rank_change(2, 2) == "same"


def test_historical_rank_comparison_uses_canonical_url_but_preserves_semantic_query() -> None:
    assert _rank_identity("https://EXAMPLE.com/a?article=7&utm_source=rss#top") == (
        _rank_identity("https://example.com/a?article=7")
    )
    assert _rank_identity("https://example.com/a?article=8") != _rank_identity(
        "https://example.com/a?article=7"
    )
    # Snapshots saved before result-link validation remain readable.
    assert _rank_identity("http://localhost/legacy") == "http://localhost/legacy"


def test_hotlist_operation_id_is_stable_within_bucket() -> None:
    owner_id = uuid4()
    now = datetime(2026, 9, 26, 8, 2, tzinfo=UTC)
    assert hotlist_operation_id(owner_id, "hotlist_weibo", now, 1800, 1) == hotlist_operation_id(
        owner_id, "hotlist_weibo", now + timedelta(minutes=20), 1800, 1
    )
    assert hotlist_operation_id(owner_id, "hotlist_weibo", now, 1800, 1) != hotlist_operation_id(
        owner_id, "hotlist_weibo", now + timedelta(minutes=30), 1800, 1
    )
    assert hotlist_operation_id(owner_id, "hotlist_weibo", now, 1800, 1) != hotlist_operation_id(
        owner_id, "hotlist_weibo", now, 1800, 2
    )


def test_hotlist_matches_each_active_topic_using_title_and_summary() -> None:
    owner_id = uuid4()
    entry = HotlistEntry(
        rank=1,
        title="新款手机发布",
        url="https://example.com/1",
        summary="人工智能功能升级",
        published_at=None,
    )
    topics = (
        ActiveHotlistTopic(
            owner_id=owner_id,
            topic_id=uuid4(),
            name="手机 AI",
            rules=normalize_monitor_rules(
                match_any=("手机",),
                match_all=("人工智能",),
                exclude=(),
            ),
        ),
        ActiveHotlistTopic(
            owner_id=owner_id,
            topic_id=uuid4(),
            name="排除发布",
            rules=normalize_monitor_rules(
                match_any=("手机",),
                match_all=(),
                exclude=("发布",),
            ),
        ),
    )
    assert match_hotlist_topics(entry, topics) == ("手机 AI",)


def test_daily_report_selects_hotlist_discoveries_by_topic_id() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value = []
    owner_id = uuid4()
    topic_id = uuid4()
    start = datetime(2026, 9, 25, tzinfo=UTC)
    assert (
        ReportService(session)._load_posts(
            owner_id=owner_id,
            topic_id=topic_id,
            window_start=start,
            window_end=start + timedelta(days=1),
            cutoff_at=start + timedelta(days=2),
        )
        == ()
    )
    statement = session.execute.call_args.args[0]
    parameters = session.execute.call_args.args[1]
    assert "discovery_job.kind = 'source.hotlist'" in statement.text
    assert "entry.matched_topic_ids ? :topic_id_text" in statement.text
    assert parameters["topic_id_text"] == str(topic_id)


def test_hotlist_api_openapi_declares_auth_and_result_models() -> None:
    app = create_app(
        Settings(environment="test", database_url="postgresql+psycopg://test:test@localhost/test")
    )
    paths = app.openapi()["paths"]
    sources = paths["/api/hotlists/sources"]["get"]
    latest = paths["/api/hotlists/{source_key}"]["get"]
    assert sources["operationId"] == "listHotlistSources"
    assert latest["operationId"] == "getHotlistSnapshot"
    assert sources["security"] == [{"SessionCookie": []}]
    assert latest["security"] == [{"SessionCookie": []}]
    assert {"200", "401", "422", "500"} <= set(sources["responses"])
    assert {"200", "401", "404", "422", "500"} <= set(latest["responses"])
