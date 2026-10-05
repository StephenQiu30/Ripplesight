"""Anonymous HTTP protocols share real PG projections and the real Redis window."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import text
from tests.conftest import authenticate_test_client
from tests.integration.test_publication import NOW, _manual_posts
from tests.integration.test_publication import editorial_client as _editorial_client

from publication.distribution_limits import PublicDistributionLimiter
from publication.publication_models import PublicationRecord
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    import publication.application as application
    import publication.mcp as mcp

    generator = _editorial_client.__wrapped__(request, monkeypatch)
    client = next(generator)

    class ReadingClock(datetime):
        @classmethod
        def now(cls, tz=None):
            at = NOW + timedelta(minutes=1)
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)

    monkeypatch.setattr(application, "datetime", ReadingClock)
    monkeypatch.setattr(mcp, "datetime", ReadingClock)
    assert client.app.state.identity_redis.ping() is True
    try:
        yield client
    finally:
        publisher = client.app.state.settings.public_publication_owner_id
        if publisher:
            client.app.state.identity_redis.delete(
                PublicDistributionLimiter.key(publisher, "unknown")
            )
        generator.close()


def _publish(client: TestClient, count: int = 1):
    owner, posts = _manual_posts(client, count)
    with client.app.state.session_factory.begin() as session:
        for post in posts:
            PublicationService(session).publish_in_transaction(
                owner_id=owner,
                content_id=post.id,
                now=NOW + timedelta(minutes=1),
                released_at=NOW - timedelta(hours=1),
            )
    client.app.state.settings.public_publication_owner_id = owner
    return owner, posts


def _call(client: TestClient, name: str, arguments: dict):
    response = client.post(
        "/public/mcp",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def _counts(client: TestClient):
    with client.app.state.session_factory() as session:
        return tuple(
            session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("jobs", "ai_calls", "outbox_messages", "publication_revisions")
        )


def _correct(client, owner, content_id, **fields):
    from analysis.editorial_schemas import EditorialOverrideInput
    from analysis.editorial_services import EditorialService

    with client.app.state.session_factory() as session:
        row = session.get(PublicationRecord, (owner, content_id))
        run_id, manual_version = UUID(row.data["editorial_run_id"]), row.data["manual_version"]
        EditorialService(
            session,
            clock=lambda: NOW + timedelta(minutes=1),
            indexing_enabled=client.app.state.settings.publication_indexing_enabled,
        ).override(
            owner_id=owner,
            run_id=run_id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=manual_version,
                reason="公开出口一致回归",
                **fields,
            ),
        )


def test_categories_agree_for_page_api_rss_mcp_markdown_and_scope_bound_sync(editorial_client):
    client = editorial_client
    categories = ["ai-models", "ai-products", "industry", "paper", "tip", "opinion", None, "tip"]
    owner, posts = _publish(client, len(categories))  # Shared fixture seeds dated=True, now=NOW.
    for post, category in zip(posts, categories, strict=True):
        _correct(
            client,
            owner,
            post.id,
            **({"category": category} if category else {"clear_fields": ["category"]}),
        )
    assert len(client.get("/public/api/items").json()["items"]) == len(categories)
    client.app.state.settings.public_publication_categories = ("tip", "tip")
    expected = {str(posts[i].id) for i, category in enumerate(categories) if category == "tip"}
    before = _counts(client)
    page = client.get("/public/api/items").json()
    assert {item["id"] for item in page["items"]} == expected
    timeline = client.get("/api/publication/timeline").json()
    assert {card["item"]["id"] for card in timeline["cards"]} == expected
    assert _call(client, "hotkey_get_latest", {})["structuredContent"] == page
    assert {
        item["id"]
        for item in _call(client, "hotkey_search", {"q": "人工摘要"})["structuredContent"]["items"]
    } == expected
    assert client.get("/public/api/items", params={"category": "opinion"}).json()["items"] == []
    for path in ("/public/feed.xml", "/public/feed/full.xml", "/public/feed/all.xml"):
        response = client.get(path)
        assert response.status_code == 200
        titles = {
            item.findtext("title")
            for item in ElementTree.fromstring(response.text).findall("./channel/item")
        }
        assert titles == {"条目4", "条目7"}
    assert not ElementTree.fromstring(client.get("/public/feed/category/opinion.xml").text).findall(
        "./channel/item"
    )
    markdown = client.get("/public/selected.md")
    assert all(
        (f"条目{i}" in markdown.text) == (str(post.id) in expected) for i, post in enumerate(posts)
    )
    for path in (
        f"/public/api/items/{posts[5].id}",
        f"/public/items/{posts[5].id}.md",
        f"/og/items/{posts[5].id}.png",
    ):
        assert client.get(path).status_code == 404
    snapshot = client.get("/api/publication/selected/snapshot", params={"limit": 1}).json()
    assert snapshot["next_cursor"] and snapshot["items"][0]["id"] in expected
    list_page = client.get("/public/api/items", params={"limit": 1}).json()
    search_page = client.get("/public/api/items", params={"q": "人工摘要", "limit": 1}).json()
    for options in ({"limit": 1}, {"q": "人工摘要", "limit": 1}):
        assert client.get("/public/api/items", params=options).json()["next_cursor"]
    changes = client.get(
        "/api/publication/selected/changes", params={"epoch": snapshot["epoch"], "since": 0}
    ).json()
    assert changes["changes"] and all(
        change["item"] is None or change["item"]["id"] in expected for change in changes["changes"]
    )
    client.app.state.settings.public_publication_categories = ("tip",)
    assert (
        client.get(
            "/api/publication/selected/snapshot", params={"cursor": snapshot["next_cursor"]}
        ).status_code
        == 200
    )
    client.app.state.settings.public_publication_categories = ("opinion",)
    for path, params in (
        ("/public/api/items", {"limit": 1, "cursor": list_page["next_cursor"]}),
        ("/public/api/items", {"q": "人工摘要", "limit": 1, "cursor": search_page["next_cursor"]}),
        ("/api/publication/selected/snapshot", {"cursor": snapshot["next_cursor"]}),
    ):
        response = client.get(path, params=params)
        assert (
            response.status_code == 422 and response.json()["code"] == "invalid_publication_cursor"
        )
    stale = client.get(
        "/api/publication/selected/changes",
        params={"epoch": snapshot["epoch"], "since": changes["sequence"]},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "publication_epoch_conflict"
    rebuilt = client.get("/api/publication/selected/snapshot").json()
    assert rebuilt["epoch"] != snapshot["epoch"]
    assert [item["id"] for item in rebuilt["items"]] == [str(posts[5].id)]
    assert _counts(client) == before


def test_correction_and_withdrawal_invalidate_all_outlets_and_old_etags_without_get_writes(
    editorial_client,
):
    client = editorial_client
    owner, posts = _publish(client)
    identity = posts[0].id
    sessions = client.app.state.session_factory
    client.app.state.settings.publication_indexing_enabled = True
    with sessions.begin() as session:
        service = PublicationService(session, indexing_enabled=True)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW + timedelta(minutes=1),
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                site_fulltext=True,
                indexable=True,
                license_name="受控索引许可",
                reason="跨出口验证",
            ),
        )
        service.publish_in_transaction(
            owner_id=owner, content_id=identity, now=NOW + timedelta(minutes=1)
        )
    detail_paths = [
        f"/public/api/items/{identity}",
        f"/public/items/{identity}.md",
        f"/og/items/{identity}.png",
        f"/og/posters/{identity}.png",
    ]
    collection_paths = [
        "/public/api/items",
        "/public/feed.xml",
        "/public/feed/full.xml",
        "/public/selected.md",
    ]
    paths = detail_paths + collection_paths
    original = {path: client.get(path) for path in paths}
    assert all(
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
        for response in original.values()
    )
    assert str(identity) in client.get("/sitemaps/items-0.xml").text
    for path, response in original.items():
        assert (
            client.get(path, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
        )
    _correct(client, owner, identity, title_zh="更正标题", summary_zh="更正摘要")
    before = _counts(client)
    corrected = {}
    for path, old in original.items():
        corrected[path] = response = client.get(
            path, headers={"If-None-Match": old.headers["etag"]}
        )
        assert response.status_code == 200 and response.headers["etag"] != old.headers["etag"]
        assert response.headers["cache-control"] == "no-store"
        if not path.endswith(".png"):
            assert "更正标题" in response.text and "条目0 人工摘要" not in response.text
    assert (
        _call(client, "hotkey_get_latest", {})["structuredContent"]["items"][0]["title"]
        == "更正标题"
    )
    assert (
        _call(client, "hotkey_search", {"q": "条目0 人工摘要"})["structuredContent"]["items"] == []
    )
    assert client.get("/api/publication/timeline").json()["cards"][0]["item"]["title"] == "更正标题"
    assert _counts(client) == before
    with sessions.begin() as session:
        row = session.get(PublicationRecord, (owner, identity))
        PublicationService(session, indexing_enabled=True).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=identity,
            now=NOW + timedelta(minutes=1),
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=row.revision,
                visibility="withdrawn",
                reason="撤回跨出口回归",
            ),
        )
    before = _counts(client)
    for path in detail_paths:
        assert (
            client.get(path, headers={"If-None-Match": corrected[path].headers["etag"]}).status_code
            == 404
        )
    for path in collection_paths:
        response = client.get(path, headers={"If-None-Match": corrected[path].headers["etag"]})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert "更正标题" not in response.text
    assert client.get("/api/publication/timeline").json()["cards"] == []
    assert str(identity) not in client.get("/sitemaps/items-0.xml").text
    assert _call(client, "hotkey_get_latest", {})["structuredContent"]["items"] == []
    assert _call(client, "hotkey_search", {"q": "更正"})["structuredContent"]["items"] == []
    assert _counts(client) == before


def test_fixed_publisher_is_anonymous_and_cookie_cannot_select_another_owner(editorial_client):
    owner, posts = _publish(editorial_client)
    before = _counts(editorial_client)
    editorial_client.cookies.clear()
    anonymous = editorial_client.get("/public/api/items").json()
    assert [item["id"] for item in anonymous["items"]] == [str(posts[0].id)]
    assert editorial_client.get("/feed.xml").status_code == 401
    assert editorial_client.get(f"/items/{posts[0].id}.md").status_code == 401
    assert editorial_client.post("/mcp", json={}).status_code == 401
    other = authenticate_test_client(editorial_client)
    assert other != owner
    assert editorial_client.get("/public/api/items").json()["items"] == anonymous["items"]
    assert editorial_client.get("/api/publication/items").json()["items"] == anonymous["items"]
    assert (
        len(
            ElementTree.fromstring(editorial_client.get("/feed.xml").text).findall("./channel/item")
        )
        == 0
    )
    editorial_client.app.state.settings.public_publication_owner_id = None
    for path in (
        "/public/api/items",
        "/public/feed.xml",
        "/public/selected.md",
        "/public/agent.md",
    ):
        response = editorial_client.get(path)
        assert response.status_code == 404 and response.json()["code"] == "resource_not_found"
    assert editorial_client.post("/public/mcp", json={}).status_code == 404
    editorial_client.app.state.settings.public_publication_owner_id = owner
    assert _counts(editorial_client) == before


def test_same_versions_bounded_pagination_rss50_and_no_site_body_search_leak(editorial_client):
    _, posts = _publish(editorial_client, 53)
    editorial_client.cookies.clear()
    before = _counts(editorial_client)
    page = editorial_client.get("/public/api/items", params={"limit": 40}).json()
    assert len(page["items"]) == 40 and page["next_cursor"]
    mcp = _call(editorial_client, "hotkey_get_latest", {"limit": 40})["structuredContent"]
    assert mcp == page
    tail = editorial_client.get(
        "/public/api/items", params={"limit": 40, "cursor": page["next_cursor"]}
    ).json()
    mcp_tail = _call(
        editorial_client, "hotkey_get_latest", {"limit": 40, "cursor": page["next_cursor"]}
    )["structuredContent"]
    assert mcp_tail == tail and len(tail["items"]) == 13
    assert len({item["id"] for item in page["items"] + tail["items"]}) == 53
    rss = editorial_client.get("/public/feed/full.xml")
    assert rss.status_code == 200 and rss.headers["content-type"].startswith("application/rss+xml")
    root = ElementTree.fromstring(rss.text)
    assert len(root.findall("./channel/item")) == 50
    assert "原始正文" not in rss.text and "/public/feed/full.xml" in rss.text
    detail = editorial_client.get(f"/public/api/items/{posts[0].id}").json()
    assert detail["body"] is None and detail["site_fulltext"] and not detail["syndicate_fulltext"]
    markdown = editorial_client.get(f"/public/items/{posts[0].id}.md")
    assert markdown.status_code == 200 and markdown.headers["content-type"].startswith(
        "text/markdown"
    )
    assert "原始正文" not in markdown.text and "人工摘要" in markdown.text
    assert editorial_client.get("/public/api/items", params={"q": "原始正文"}).json()["items"] == []
    assert (
        _call(editorial_client, "hotkey_search", {"q": "原始正文"})["structuredContent"]["items"]
        == []
    )
    searched = editorial_client.get(
        "/public/api/items", params={"q": "人工摘要", "limit": 40}
    ).json()
    assert (
        searched
        == _call(
            editorial_client,
            "hotkey_search",
            {"q": "人工摘要", "limit": 40, "selected": True, "window": "24h"},
        )["structuredContent"]
    )
    assert editorial_client.get("/public/api/items", params={"limit": 101}).status_code == 422
    assert (
        editorial_client.get("/public/api/items", params={"cursor": "x" * 4097}).status_code == 422
    )
    assert _counts(editorial_client) == before


def test_granted_body_and_revocation_rechecked_before_old_etag_304(editorial_client):
    owner, posts = _publish(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW + timedelta(minutes=1),
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                site_fulltext=True,
                syndicate_fulltext=True,
                license_name="受控再分发许可",
                reason="正文许可测试",
            ),
        )
        service.publish_in_transaction(
            owner_id=owner,
            content_id=posts[0].id,
            now=NOW + timedelta(minutes=1),
            released_at=NOW - timedelta(hours=1),
        )
    editorial_client.cookies.clear()
    path = f"/public/api/items/{posts[0].id}"
    detail = editorial_client.get(path)
    assert detail.status_code == 200 and detail.json()["body"]["original"] == "条目0 原始正文"
    assert (
        editorial_client.get(path, headers={"If-None-Match": detail.headers["etag"]}).status_code
        == 304
    )
    md = editorial_client.get(f"/public/items/{posts[0].id}.md")
    rss = editorial_client.get("/public/feed/full.xml")
    assert "原始正文" in md.text and "原始正文" in rss.text
    before = _counts(editorial_client)
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW + timedelta(minutes=1),
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=2,
                participation_mode="isolated",
                license_name="撤回受控许可",
                reason="撤回所有公开许可",
            ),
        )
    assert (
        editorial_client.get(path, headers={"If-None-Match": detail.headers["etag"]}).status_code
        == 404
    )
    assert (
        editorial_client.get(
            f"/public/items/{posts[0].id}.md", headers={"If-None-Match": md.headers["etag"]}
        ).status_code
        == 404
    )
    changed = editorial_client.get(
        "/public/feed/full.xml", headers={"If-None-Match": rss.headers["etag"]}
    )
    assert (
        changed.status_code == 200
        and len(ElementTree.fromstring(changed.text).findall("./channel/item")) == 0
    )
    assert editorial_client.get("/public/api/items").json()["items"] == []
    assert (
        _call(editorial_client, "hotkey_search", {"q": "条目"})["structuredContent"]["items"] == []
    )
    assert _counts(editorial_client) == before


def test_real_redis_one_window_all_protocols_ignores_spoofed_forwarded_peer(
    editorial_client, monkeypatch
):
    owner, _ = _publish(editorial_client)
    editorial_client.cookies.clear()
    redis = editorial_client.app.state.identity_redis
    key = PublicDistributionLimiter.key(owner, "unknown")
    redis.delete(key)
    assert editorial_client.get("/public/feed.xml").status_code == 200
    assert editorial_client.get("/public/selected.md").status_code == 200
    assert _call(editorial_client, "hotkey_get_latest", {})["structuredContent"]["items"]
    assert int(redis.get(key)) == 3
    redis.set(key, "120", ex=60)
    for path in ("/public/api/items", "/public/feed.xml", "/public/selected.md"):
        response = editorial_client.get(
            path, headers={"X-Forwarded-For": str(uuid4()), "X-Real-IP": "127.0.0.2"}
        )
        assert response.status_code == 429 and response.json()["code"] == "publication_rate_limited"
        assert 1 <= int(response.headers["retry-after"]) <= 60
    blocked_mcp = editorial_client.post("/public/mcp", json={})
    assert (
        blocked_mcp.status_code == 429 and blocked_mcp.json()["code"] == "publication_rate_limited"
    )
    assert int(redis.get(key)) == 124 and 0 < redis.ttl(key) <= 60
    redis.delete(key)
    before = _counts(editorial_client)

    def unavailable(*args, **kwargs):
        raise RedisError("controlled Redis failure")

    monkeypatch.setattr(redis, "eval", unavailable)
    response = editorial_client.get("/public/api/items")
    assert (
        response.status_code == 503
        and response.json()["code"] == "publication_distribution_unavailable"
    )
    assert _counts(editorial_client) == before


def test_story_json_and_mcp_revalidate_all_fixed_members_even_before_304(editorial_client):
    from tests.integration.test_event_reading import _fixed_member_fields

    from events.fact_models import EventFact, EventFactAssignment, EventFactMember
    from events.models import Event, EventMember

    owner, posts = _publish(editorial_client, 2)
    sessions = editorial_client.app.state.session_factory
    event, fact = uuid4(), uuid4()
    at = NOW + timedelta(minutes=1)
    with sessions.begin() as session:
        topic = session.scalar(
            text("SELECT id FROM monitor_topics WHERE owner_id=:owner"), {"owner": owner}
        )
        session.add(
            Event(
                id=event,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="受控事件",
                summary="两个固定成员的公开事实",
                first_seen_at=NOW,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            EventFact(
                id=fact,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="受控事实",
                summary="两个固定成员的公开事实",
                status="confirmed",
                merged_into_id=None,
                frame=None,
                first_seen_at=NOW,
                first_seen_basis="discovered",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            EventFactAssignment(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=event,
                fact_id=fact,
                root_fact_id=None,
                relation="root",
                added_revision=1,
                removed_revision=None,
                created_at=NOW,
            )
        )
        for index, post in enumerate(posts):
            member = uuid4()
            version = post.latest_observation.content_version.id
            session.add(
                EventMember(
                    id=member,
                    owner_id=owner,
                    topic_id=topic,
                    event_id=event,
                    content_id=post.id,
                    content_version_id=version,
                    **_fixed_member_fields(session, owner, post),
                    source_key="x",
                    representative_comment_id=None,
                    added_revision=1,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=NOW,
                )
            )
            session.flush()
            session.add(
                EventFactMember(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    fact_id=fact,
                    event_id=event,
                    event_member_id=member,
                    content_id=post.id,
                    content_version_id=version,
                    role="primary" if index == 0 else "report",
                    assignment_origin="model",
                    added_revision=1,
                    removed_revision=None,
                    created_at=NOW,
                )
            )
        session.flush()
        for post in posts:
            PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=at
            )
    editorial_client.cookies.clear()
    path = f"/public/api/stories/{event}"
    story = editorial_client.get(path)
    assert story.status_code == 200, story.text
    assert len(story.json()["reports"]) == 2
    assert (
        _call(editorial_client, "hotkey_get_story", {"id": str(event)})["structuredContent"]
        == story.json()
    )
    hot = editorial_client.get("/public/api/hot").json()
    assert _call(editorial_client, "hotkey_get_hot_topics", {})["structuredContent"] == hot
    assert (
        editorial_client.get(path, headers={"If-None-Match": story.headers["etag"]}).status_code
        == 304
    )
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[1].id,
            now=at,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=2,
                visibility="withdrawn",
                reason="撤回一个固定输入",
            ),
        )
    before = _counts(editorial_client)
    assert editorial_client.get(f"/public/api/items/{posts[0].id}").status_code == 200
    assert (
        editorial_client.get(path, headers={"If-None-Match": story.headers["etag"]}).status_code
        == 404
    )
    assert _call(editorial_client, "hotkey_get_story", {"id": str(event)})["isError"] is True
    assert _counts(editorial_client) == before


def test_daily_json_markdown_rss_and_mcp_share_same_all_licensed_revision(
    editorial_client, monkeypatch
):
    import tests.integration.test_report_editions as fixtures

    import publication.application as application
    import publication.mcp as mcp

    monkeypatch.setattr(fixtures, "NOW", NOW)
    owner, edition, message, lease = fixtures._admit(editorial_client)
    fixtures._executor(editorial_client, edition).execute(message, lease)
    at = edition.window_end + timedelta(hours=2)

    class EditionClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)

    monkeypatch.setattr(application, "datetime", EditionClock)
    monkeypatch.setattr(mcp, "datetime", EditionClock)
    editorial_client.app.state.settings.public_publication_owner_id = owner
    editorial_client.cookies.clear()
    path = f"/public/api/reports/daily/{edition.key}"
    response = editorial_client.get(path)
    assert response.status_code == 200, response.text
    before = _counts(editorial_client)
    result = _call(editorial_client, "hotkey_get_daily", {"date": edition.key})
    assert not result["isError"] and result["structuredContent"] == response.json()
    markdown = editorial_client.get(f"/public/reports/daily/{edition.key}.md")
    assert markdown.status_code == 200 and response.json()["body_markdown"] in markdown.text
    rss = editorial_client.get("/public/feed/daily.xml")
    assert (
        rss.status_code == 200
        and len(ElementTree.fromstring(rss.text).findall("./channel/item")) == 1
    )
    assert (
        editorial_client.get(path, headers={"If-None-Match": response.headers["etag"]}).status_code
        == 304
    )
    assert _counts(editorial_client) == before
    with editorial_client.app.state.session_factory.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=at,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="isolated",
                license_name="撤回固定来源",
                reason="刊期逐次复验",
            ),
        )
    assert (
        editorial_client.get(path, headers={"If-None-Match": response.headers["etag"]}).status_code
        == 404
    )
    assert (
        editorial_client.get(
            f"/public/reports/daily/{edition.key}.md",
            headers={"If-None-Match": markdown.headers["etag"]},
        ).status_code
        == 404
    )
    assert _call(editorial_client, "hotkey_get_daily", {"date": edition.key})["isError"] is True
    changed = editorial_client.get(
        "/public/feed/daily.xml", headers={"If-None-Match": rss.headers["etag"]}
    )
    assert (
        changed.status_code == 200
        and len(ElementTree.fromstring(changed.text).findall("./channel/item")) == 0
    )
    assert _counts(editorial_client) == before
