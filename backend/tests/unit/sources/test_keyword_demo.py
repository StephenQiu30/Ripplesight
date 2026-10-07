import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from sources.adapters.bilibili_chrome import CollectionStoppedError, collect
from sources.keyword_demo import DemoState, tick

NOW = datetime(2026, 10, 7, 4, tzinfo=UTC)


def identity(tmp_path: Path) -> Path:
    path = tmp_path / "identity.env"
    path.write_text("COOKIE_SOURCE_TOKEN=testing-only\n")
    path.chmod(0o600)
    return path


def transport_handler(request: httpx.Request, *, fail_comments: bool = False) -> httpx.Response:
    if request.url.host == "127.0.0.1":
        raw = b".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tsecret-test-value\n"
        return httpx.Response(
            200,
            json={
                "cookies": base64.b64encode(raw).decode(),
                "digest": "a" * 64,  # opaque account HMAC, not a checksum of the payload
            },
        )
    assert request.url.host == "api.bilibili.com"
    assert "secret-test-value" in request.headers["cookie"]
    if request.url.path.endswith("nav"):
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": True}})
    if request.url.path.endswith("search/type"):
        rows = [
            {
                "aid": 1,
                "mid": 2,
                "title": "<em>DeepSeek</em> <script>bad()</script>",
                "description": "新版本",
                "pubdate": int((NOW - timedelta(hours=1)).timestamp()),
            },
            {
                "aid": 2,
                "mid": 2,
                "title": "unrelated",
                "pubdate": int((NOW - timedelta(hours=1)).timestamp()),
            },
            {"aid": 3, "mid": 2, "title": "DeepSeek boundary", "pubdate": int(NOW.timestamp())},
        ]
        return httpx.Response(200, json={"code": 0, "data": {"result": rows}})
    if fail_comments:
        return httpx.Response(200, json={"code": -352})
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "replies": [
                    {
                        "rpid": 5,
                        "mid": 9,
                        "root": 0,
                        "parent": 0,
                        "ctime": int(NOW.timestamp()),
                        "content": {"message": "<script>alert(1)</script>"},
                        "like": 1,
                    }
                ]
            },
        },
    )


def test_real_contract_filter_window_parent_and_no_cookie_artifact(tmp_path: Path) -> None:
    env = identity(tmp_path)
    charges = []
    posts, comments, count = collect(
        identity_env=env,
        keyword="DeepSeek",
        starts_at=NOW - timedelta(hours=72),
        ends_at=NOW,
        charge=lambda: charges.append(1),
        transport=httpx.MockTransport(transport_handler),
    )
    assert count == 3 and [p.external_id for p in posts] == ["1"]
    assert len(charges) == 3
    assert comments[0].parent_relation_status == "root"
    assert "secret-test-value" not in json.dumps([p.model_dump(mode="json") for p in posts])


def test_risk_response_stops_without_retry(tmp_path: Path) -> None:
    count = []

    def handler(request: httpx.Request) -> httpx.Response:
        count.append(str(request.url.path))
        return transport_handler(request, fail_comments=True)

    with pytest.raises(CollectionStoppedError, match="source_access_or_rate_limited"):
        collect(
            identity_env=identity(tmp_path),
            keyword="DeepSeek",
            starts_at=NOW - timedelta(hours=72),
            ends_at=NOW,
            charge=lambda: None,
            transport=httpx.MockTransport(handler),
        )
    assert len(count) == 4  # local bridge plus three source requests, no fallback


def test_schedule_persistence_dedup_and_html_escape(tmp_path: Path) -> None:
    env = identity(tmp_path)
    directory = tmp_path / "demo"

    def collector(**kwargs: Any) -> Any:
        return collect(**kwargs, transport=httpx.MockTransport(transport_handler))

    first = tick(directory, env, clock=lambda: NOW, collector=collector)
    assert len(first.posts) == 1 and first.runs[-1].new_comments == 1
    second = tick(directory, env, clock=lambda: NOW + timedelta(minutes=59), collector=collector)
    assert len(second.runs) == 1
    third = tick(directory, env, clock=lambda: NOW + timedelta(hours=1), collector=collector)
    assert len(third.runs) == 2 and third.runs[-1].new_posts == 1
    assert third.runs[-1].new_comments == 0
    assert len(third.posts) == 2  # one previous post plus the newly eligible boundary post
    text = (directory / "index.html").read_text()
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert (
        "__ITEMS__" not in text
        and "secret-test-value" not in (directory / "state.json").read_text()
    )


def test_stopped_state_never_retries_on_future_tick(tmp_path: Path) -> None:
    def failure(**kwargs: Any) -> Any:
        kwargs["charge"]()
        raise CollectionStoppedError("chrome_login_required")

    state = tick(tmp_path / "demo", identity(tmp_path), clock=lambda: NOW, collector=failure)
    assert state.daily_requests == 1
    state = tick(
        tmp_path / "demo",
        tmp_path / "identity.env",
        clock=lambda: NOW + timedelta(days=1),
        collector=failure,
    )
    assert len(state.runs) == 1


def test_quiet_hours_and_budget_are_persisted(tmp_path: Path) -> None:
    def unexpected(**kwargs: Any) -> Any:
        raise AssertionError("no source request expected")

    directory = tmp_path / "demo"
    state = tick(
        directory, identity(tmp_path), clock=lambda: NOW.replace(hour=18), collector=unexpected
    )
    assert not state.runs and state.next_run_at.hour == 0
    state.daily_requests, state.request_day = 60, "2026-10-08"
    (directory / "state.json").write_text(state.model_dump_json())
    state = tick(
        directory,
        tmp_path / "identity.env",
        clock=lambda: NOW + timedelta(days=1),
        collector=unexpected,
    )
    assert not state.runs and state.next_run_at.date().isoformat() == "2026-10-09"


def test_interrupted_run_pauses_without_catching_up(tmp_path: Path) -> None:
    directory = tmp_path / "demo"
    state = tick(
        directory, identity(tmp_path), clock=lambda: NOW, collector=lambda **kwargs: ([], [], 0)
    )
    state.runs[-1].status = "running"
    (directory / "state.json").write_text(state.model_dump_json())
    state = tick(directory, tmp_path / "identity.env", clock=lambda: NOW + timedelta(hours=4))
    assert state.stopped_reason == "process_interrupted"
    assert len(state.runs) == 1
    assert (
        DemoState.model_validate_json((directory / "state.json").read_text()).runs[0].status
        == "interrupted"
    )


def test_pause_resume_and_retention_without_source_requests(tmp_path: Path) -> None:
    directory = tmp_path / "demo"
    env = identity(tmp_path)

    def collector(**kwargs: Any) -> Any:
        return collect(**kwargs, transport=httpx.MockTransport(transport_handler))

    tick(directory, env, clock=lambda: NOW, collector=collector)
    paused = tick(directory, env, clock=lambda: NOW, pause=True, collector=collector)
    assert paused.stopped_reason == "operator_paused"
    resumed = tick(directory, env, clock=lambda: NOW, resume=True, collector=collector)
    assert resumed.stopped_reason is None and len(resumed.runs) == 1
    expired = tick(directory, env, clock=lambda: NOW + timedelta(days=31), pause=True)
    assert not expired.posts and not expired.comments and not expired.last_seen
    assert expired.daily_requests == 3


def test_fractional_window_end_preserves_last_valid_second(tmp_path: Path) -> None:
    end = NOW + timedelta(microseconds=500_000)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("search/type"):
            assert request.url.params["pubtime_end_s"] == str(int(NOW.timestamp()))
        return transport_handler(request)

    posts, _, _ = collect(
        identity_env=identity(tmp_path),
        keyword="DeepSeek",
        starts_at=NOW - timedelta(hours=72),
        ends_at=end,
        charge=lambda: None,
        transport=httpx.MockTransport(handler),
    )
    assert [p.external_id for p in posts] == ["1", "3"]


def test_chrome_adapter_separates_metered_search_and_fresh_comments(tmp_path: Path) -> None:
    from sources.adapters.bilibili_chrome import BilibiliChromeAdapter
    from sources.contracts import CommentsRequest, SearchRequest, SourcePageState

    paths = []
    charges = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return transport_handler(request)

    adapter = BilibiliChromeAdapter(
        identity_env=identity(tmp_path),
        before_request=lambda n: charges.append(n) or True,
        cancelled=lambda: False,
        max_requests=4,
        max_seconds=60,
        transport=httpx.MockTransport(handler),
    )
    page = adapter.fetch_page(
        SearchRequest(
            source_key="bilibili",
            query="DeepSeek",
            page_size=2,
            starts_at=NOW - timedelta(hours=2),
            ends_at=NOW,
        )
    )
    assert page.state is SourcePageState.PARTIAL
    assert [post.external_id for post in page.items] == ["1"]
    assert page.request_count == 2 and "/x/v2/reply" not in paths
    page = adapter.fetch_page(
        CommentsRequest(source_key="bilibili", post_external_id="1", page_size=20)
    )
    assert page.request_count == 2 and len(charges) == 4
    assert paths.count("/x/web-interface/wbi/search/type") == 1
    assert page.items[0].external_id == "5"
    exhausted = adapter.fetch_page(
        CommentsRequest(source_key="bilibili", post_external_id="1", page_size=20)
    )
    assert exhausted.request_count == 0 and len(charges) == 4
