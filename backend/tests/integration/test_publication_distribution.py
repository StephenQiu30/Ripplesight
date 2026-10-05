"""Anonymous HTTP protocols share real PG projections and the real Redis window."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import text
from tests.conftest import authenticate_test_client
from tests.integration.test_publication import NOW, _manual_posts
from tests.integration.test_publication import editorial_client as _editorial_client

from publication.distribution_limits import PublicDistributionLimiter
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
