from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_monitor_topics import _csrf_headers
from tests.integration.test_topic_runs import _ready_topic
from tests.integration.test_topic_runs import monitor_topic_client as _topic_client  # noqa: F401

from connections.schemas import SourceEntryPoint
from content.comments import CommentManualRunService
from content.schemas import CommentManualRunInput, PersistContentPostInput
from content.services import ContentService
from core.errors import ApplicationError
from evidence.schemas import AdmittedSourcePayload, DataClass
from sources.contracts import SourceCapability


def _seed_old_hn_post(client: TestClient) -> UUID:
    topic_location = _ready_topic(client, source_keys=("hackernews",))
    search = client.post(
        f"{topic_location}/runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert search.status_code == 202, search.json()
    job_id = UUID(search.json()["sources"][0]["job_ids"][0])
    now = datetime.now(UTC)
    factory = client.app.state.session_factory
    with factory() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
        connection_id, connection_version = session.execute(
            text(
                "SELECT id, current_version FROM source_connections WHERE source_key = 'hackernews'"
            )
        ).one()
        policy_id, policy_version = session.execute(
            text(
                "SELECT id, policy_version FROM source_access_policies "
                "WHERE source_key = 'hackernews' AND capability = 'search'"
            )
        ).one()
        retention_id, retention_version, retention_days = session.execute(
            text(
                "SELECT id, policy_version, effective_days FROM evidence_retention_policies "
                "WHERE source_policy_id = :policy_id AND data_class = 'structured'"
            ),
            {"policy_id": policy_id},
        ).one()
        created = ContentService(session).persist_post(
            owner_id=owner_id,
            command=PersistContentPostInput(
                job_id=job_id,
                source_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=connection_version,
                entry_point=SourceEntryPoint.MANUAL,
                component_name="collector.hackernews",
                component_version="hn-algolia-v1",
                admission=AdmittedSourcePayload(
                    policy_id=policy_id,
                    policy_version=policy_version,
                    owner_id=owner_id,
                    source_key="hackernews",
                    capability=SourceCapability.SEARCH,
                    retention_policy_id=retention_id,
                    retention_policy_version=retention_version,
                    data_class=DataClass.STRUCTURED,
                    collected_at=now,
                    expires_at=now + timedelta(days=retention_days),
                    fields={
                        "object_type": "post",
                        "external_id": "old-hn-story",
                        "canonical_url": "https://news.ycombinator.com/item?id=123456",
                        "author_external_id": "hn-author",
                        "published_at": (now - timedelta(days=3)).isoformat(),
                        "like_count": 100,
                        "comment_count": 42,
                        "repost_count": None,
                        "view_count": None,
                        "play_count": None,
                        "danmaku_count": None,
                        "text_scope": "full",
                        "text_origin": "source",
                        "title": "Brand 召回 old HN story",
                        "body": "Brand 召回 discussion",
                    },
                ),
            ),
        )
    with factory.begin() as session:
        session.execute(
            text("UPDATE content_records SET created_at = :old WHERE id = :id"),
            {"old": now - timedelta(days=3), "id": created.id},
        )
    return created.id


def test_old_hn_post_manual_comments_are_accepted_once(request: pytest.FixtureRequest) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    route = f"/api/contents/{content_id}/comment-runs"
    payload = {"operation_id": str(uuid4())}
    assert monitor_topic_client.get(f"/api/contents/{content_id}").status_code == 200
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'source.comments'")) == 0
    assert monitor_topic_client.post(route, json=payload).status_code == 403
    first = monitor_topic_client.post(
        route, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    replay = monitor_topic_client.post(
        route, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert first.status_code == 202, first.json()
    assert replay.status_code == 200, replay.json()
    assert first.json() == replay.json()
    with monitor_topic_client.app.state.session_factory() as session:
        rows = session.execute(
            text(
                "SELECT scope, configuration_ref, configuration_version "
                "FROM jobs WHERE kind = 'source.comments'"
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].scope["post_external_id"] == "old-hn-story"
        assert rows[0].scope["entry_point"] == "manual"
        assert rows[0].configuration_ref.startswith("topic:")
        assert rows[0].configuration_version == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 2


def test_manual_comments_reject_unknown_content_and_frequency(
    request: pytest.FixtureRequest,
) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    headers = _csrf_headers(monitor_topic_client)
    unknown = monitor_topic_client.post(
        f"/api/contents/{uuid4()}/comment-runs",
        headers=headers,
        json={"operation_id": str(uuid4())},
    )
    assert unknown.status_code == 404
    route = f"/api/contents/{content_id}/comment-runs"
    first = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert first.status_code == 202, first.json()
    limited = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert limited.status_code == 409
    assert limited.json()["code"] == "comments_rate_limited"
    with (
        monitor_topic_client.app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="resource_not_found"),
    ):
        CommentManualRunService(session).run(
            owner_id=uuid4(),
            content_id=content_id,
            command=CommentManualRunInput(operation_id=uuid4()),
        )


def test_manual_comments_require_budget_and_comment_capability(
    request: pytest.FixtureRequest,
) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    route = f"/api/contents/{content_id}/comment-runs"
    headers = _csrf_headers(monitor_topic_client)
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    budget = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert budget.status_code == 409
    assert budget.json()["code"] == "comments_budget_exhausted"
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = true "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET enabled = false "
                "WHERE source_key = 'hackernews' AND capability = 'comments'"
            )
        )
    capability = monitor_topic_client.post(
        route, headers=headers, json={"operation_id": str(uuid4())}
    )
    assert capability.status_code == 409
    assert capability.json()["code"] == "comments_not_ready"
