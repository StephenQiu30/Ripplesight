from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.conftest import authenticate_test_client
from tests.integration.test_content_records import _command, _seed_context, _user_scope

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from content.schemas import ContentRecordSummaryView
from content.services import ContentService
from core.config import Settings
from core.errors import ApplicationError
from main import create_app


@pytest.fixture
def search_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for content search PostgreSQL tests")
    with TestClient(
        create_app(Settings(environment="test", log_level="WARNING", database_url=database_url))
    ) as client:
        authenticate_test_client(client)
        yield client


def _seed_posts(
    client: TestClient,
    texts: list[tuple[str | None, str | None]],
    *,
    now: datetime | None = None,
) -> tuple[UUID, UUID, list[ContentRecordSummaryView]]:
    owner = _user_scope(client)
    connection, policy, retention, first_job, second_job = _seed_context(client, owner, now=now)
    received_at = now
    now = (now or datetime.now(UTC)) - timedelta(minutes=3)
    topic = uuid4()
    factory = client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) "
                "VALUES (:id, :owner, '搜索主题', 'active', 'ready', 1, :now, :now)"
            ),
            {"id": topic, "owner": owner, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:id, 1, :owner, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
            ),
            {"id": topic, "owner": owner, "now": now},
        )
        session.execute(
            text("UPDATE jobs SET configuration_ref=:ref WHERE id IN (:first, :second)"),
            {"ref": f"topic:{topic}", "first": first_job, "second": second_job},
        )
    posts = []
    with factory() as session:
        service = ContentService(
            session, clock=(lambda: received_at) if received_at is not None else None
        )
        for index, (title, body) in enumerate(texts):
            posts.append(
                service.persist_post(
                    owner_id=owner,
                    command=_command(
                        owner_id=owner,
                        connection_id=connection,
                        policy_id=policy,
                        retention_id=retention,
                        job_id=first_job if index % 2 == 0 else second_job,
                        operation_id=uuid4(),
                        observed_at=now + timedelta(seconds=index),
                        external_id=f"search-{index}",
                        extra_fields={
                            "text_scope": "full",
                            "text_origin": "source",
                            "title": title,
                            "body": body,
                            "published_at": None,
                        },
                    ),
                )
            )
    return owner, topic, posts


def _ids(client: TestClient, **params: str | int) -> set[str]:
    response = client.get("/api/contents", params=params)
    assert response.status_code == 200, response.json()
    return {item["id"] for item in response.json()["items"]}


def _write_facts(client: TestClient) -> list[tuple[object, ...]]:
    tables = (
        "jobs",
        "outbox_messages",
        "ai_calls",
        "content_observations",
        "resource_budget_windows",
        "resource_budget_reservations",
    )
    with client.app.state.session_factory() as session:
        return [
            tuple(session.execute(text(f"SELECT row_to_json(t) FROM {table} t ORDER BY id")))
            for table in tables
        ]


def test_search_matches_all_terms_across_fields_and_keeps_metacharacters_literal(
    search_client: TestClient,
) -> None:
    _, _, posts = _seed_posts(
        search_client,
        [
            ("AI Agent 发布", "新的模型证据"),
            ("AI Agent 发布", "只有新闻"),
            ("其他发布", "模型证据"),
            ("100% field_name C:\\models", "literal"),
            ("1000 fieldXname C:models", "literal"),
            (None, "Agent 与 模型"),
        ],
    )
    before = _write_facts(search_client)
    assert _ids(search_client, q="AGENT 模型") == {str(posts[0].id), str(posts[5].id)}
    assert _ids(search_client, q="100% field_name C:\\models") == {str(posts[3].id)}
    assert _ids(search_client, q="Agent 未出现") == set()
    assert _ids(search_client, q="' OR 1=1") == set()
    assert _ids(search_client, q=" \t ") == {str(post.id) for post in posts}
    with search_client.app.state.session_factory() as session:
        assert ContentService(session).list_contents(
            owner_id=uuid4(), cursor=None, limit=20, q="agent"
        ) == ([], None)
    assert _write_facts(search_client) == before


def test_search_uses_selected_readable_version_and_excludes_expired_text(
    search_client: TestClient,
) -> None:
    owner, _, posts = _seed_posts(search_client, [("obsolete", "old"), ("secret", "expired")])
    factory = search_client.app.state.session_factory
    with factory() as session, session.begin():
        context = session.execute(
            text(
                "SELECT (SELECT id FROM source_connections WHERE owner_id=:owner) "
                "AS connection_id, er.source_policy_id AS policy_id, "
                "er.retention_policy_id, ob.job_id FROM content_observations ob "
                "JOIN evidence_resources er ON er.resource_id=ob.id AND er.owner_id=ob.owner_id "
                "WHERE ob.id=:id"
            ),
            {"id": posts[0].latest_observation.id, "owner": owner},
        ).one()
    with factory() as session:
        updated = ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=context.connection_id,
                policy_id=context.policy_id,
                retention_id=context.retention_policy_id,
                job_id=context.job_id,
                operation_id=uuid4(),
                observed_at=datetime.now(UTC) - timedelta(seconds=1),
                external_id="search-0",
                extra_fields={
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "current",
                    "body": "new evidence",
                    "published_at": None,
                },
            ),
        )
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE evidence_resources SET expires_at=collected_at + interval '1 second' "
                "WHERE resource_id=:id"
            ),
            {"id": posts[1].latest_observation.id},
        )
    assert _ids(search_client, q="obsolete") == set()
    assert _ids(search_client, q="current evidence") == {str(updated.id)}
    assert _ids(search_client, q="secret") == set()
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE evidence_resources SET expires_at=collected_at + interval '1 second' "
                "WHERE resource_id=:id"
            ),
            {"id": updated.latest_observation.id},
        )
    assert _ids(search_client, q="current") == set()
    assert _ids(search_client, q="obsolete") == {str(posts[0].id)}
    with factory() as session:
        metrics_only = ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=context.connection_id,
                policy_id=context.policy_id,
                retention_id=context.retention_policy_id,
                job_id=context.job_id,
                operation_id=uuid4(),
                observed_at=datetime.now(UTC),
                external_id="search-0",
                like_count=99,
                extra_fields={"published_at": None},
            ),
        )
    assert metrics_only.latest_observation.content_version is None
    assert _ids(search_client, q="obsolete") == set()
    assert _ids(search_client) == {str(posts[0].id)}


def test_sparse_search_scans_past_unmatched_batches_without_returning_them(
    search_client: TestClient,
) -> None:
    _, _, posts = _seed_posts(
        search_client, [(f"entry-{index:03d}-token", None) for index in range(52)]
    )
    final = max(posts, key=lambda post: post.id)
    version = final.latest_observation.content_version
    assert version is not None
    response = search_client.get("/api/contents", params={"q": version.title, "limit": 1})
    assert response.status_code == 200, response.json()
    assert [item["id"] for item in response.json()["items"]] == [str(final.id)]
    assert response.json()["next_cursor"] is None


def test_search_preserves_filters_cursor_scope_and_current_analysis_state(
    search_client: TestClient,
) -> None:
    owner, topic, posts = _seed_posts(
        search_client, [("Agent", "模型 first"), ("Agent", "模型 second"), ("other", "news")]
    )
    version = posts[0].latest_observation.content_version
    assert version is not None
    now = datetime.now(UTC)
    factory = search_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO content_annotations "
                "(id, owner_id, content_id, content_version_id, topic_id, topic_rule_version, "
                "prompt_version, status, result_state, created_at, updated_at) VALUES "
                "(:id, :owner, :content, :version, :topic, 1, :prompt, 'unanalyzed', "
                "'pending', :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner": owner,
                "content": posts[0].id,
                "version": version.id,
                "topic": topic,
                "prompt": ANALYSIS_PROMPT_VERSION,
                "now": now,
            },
        )
    filters = {"q": "Agent 模型", "topic_id": str(topic), "source_key": "x", "limit": 1}
    first = search_client.get("/api/contents", params=filters)
    assert first.status_code == 200, first.json()
    assert first.json()["next_cursor"] is not None
    cursor = first.json()["next_cursor"]
    second = search_client.get(
        "/api/contents", params={**filters, "q": " 模型  AGENT ", "cursor": cursor}
    )
    assert second.status_code == 200, second.json()
    assert {item["id"] for item in first.json()["items"] + second.json()["items"]} == {
        str(posts[0].id),
        str(posts[1].id),
    }
    assert second.json()["next_cursor"] is None
    wrong_query = search_client.get(
        "/api/contents", params={**filters, "q": "other", "cursor": cursor}
    )
    assert wrong_query.status_code == 422
    assert wrong_query.json()["code"] == "invalid_content_cursor"
    with factory() as session, pytest.raises(ApplicationError, match="invalid_content_cursor"):
        ContentService(session).list_contents(
            owner_id=uuid4(), cursor=cursor, limit=20, q="Agent 模型"
        )
    assert _ids(search_client, q="Agent 模型", topic_id=str(topic), analysis_state="pending") == {
        str(posts[0].id)
    }
    assert _ids(search_client, q="Agent 模型", topic_id=str(topic), analysis_state="missing") == {
        str(posts[1].id)
    }
    assert _ids(search_client, q="Agent 模型", source_key="hackernews") == set()
    assert _ids(
        search_client,
        q="Agent 模型",
        starts_at=(now - timedelta(minutes=5)).isoformat(),
        ends_at=now.isoformat(),
    ) == {str(posts[0].id), str(posts[1].id)}
    assert (
        _ids(
            search_client,
            q="Agent 模型",
            starts_at=(now - timedelta(days=2)).isoformat(),
            ends_at=(now - timedelta(days=1)).isoformat(),
        )
        == set()
    )


@pytest.mark.parametrize("query", ["a" * 201, "a b c d e f g", "ai\x00agent"])
def test_search_api_rejects_excessive_or_unsupported_queries(
    search_client: TestClient, query: str
) -> None:
    response = search_client.get("/api/contents", params={"q": query})
    assert response.status_code == 422, response.json()
    assert response.json()["code"] in {"validation_error", "invalid_content_filter"}
