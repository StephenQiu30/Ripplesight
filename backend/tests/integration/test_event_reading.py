from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_content_records import _command, _demo_scope, _seed_context

from content.event_reading import load_event_member_content_in_transaction
from content.schemas import ContentRecordSummaryView, EventContentReadReference
from content.services import ContentService
from core.config import Settings
from core.errors import ApplicationError
from events.models import Event, EventMember
from events.reads import EventReadService
from main import create_app


@pytest.fixture
def event_read_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for event reading PostgreSQL tests")
    with TestClient(
        create_app(Settings(environment="test", log_level="WARNING", database_url=database_url))
    ) as client:
        yield client


def _seed_reading(
    client: TestClient,
) -> tuple[UUID, UUID, UUID, ContentRecordSummaryView, ContentRecordSummaryView]:
    owner = _demo_scope(client)
    connection, policy, retention, first_job, second_job = _seed_context(client, owner)
    now = datetime.now(UTC) - timedelta(minutes=3)
    factory = client.app.state.session_factory
    with factory() as session:
        service = ContentService(session)
        fixed = service.persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=first_job,
                operation_id=uuid4(),
                observed_at=now,
                like_count=0,
                extra_fields={
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "固定标题",
                    "body": "固定正文",
                },
            ),
        )
        later = service.persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=second_job,
                operation_id=uuid4(),
                observed_at=now + timedelta(minutes=1),
                like_count=99,
                extra_fields={
                    "text_scope": "summary",
                    "text_origin": "source",
                    "title": "新版标题",
                    "body": "新版摘要",
                },
            ),
        )
    topic, event_id = uuid4(), uuid4()
    assert fixed.latest_observation.content_version is not None
    with factory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) "
                "VALUES (:id, :owner, '事件阅读', 'active', 'ready', 1, :now, :now)"
            ),
            {"id": topic, "owner": owner, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:id, 1, :owner, '[\"事件\"]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
            ),
            {"id": topic, "owner": owner, "now": now},
        )
        session.add(
            Event(
                id=event_id,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="已确认事件",
                summary="固定正文的归并摘要",
                first_seen_at=now,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=event_id,
                content_id=fixed.id,
                content_version_id=fixed.latest_observation.content_version.id,
                source_key="x",
                representative_comment_id=None,
                added_revision=1,
                removed_revision=None,
                assignment_origin="model",
                created_at=now,
            )
        )
    return owner, topic, event_id, fixed, later


def test_event_reading_returns_fixed_version_full_body_and_observation(
    event_read_client: TestClient,
) -> None:
    _, topic, event_id, fixed, later = _seed_reading(event_read_client)
    response = event_read_client.get(f"/api/events/{event_id}")
    assert response.status_code == 200, response.json()
    assert response.headers["cache-control"] == "no-store"
    detail = response.json()
    assert detail["evidence_state"] == "complete"
    assert detail["title"] == "已确认事件"
    members = event_read_client.get(f"/api/events/{event_id}/members").json()["items"]
    reading = members[0]["content"]
    assert reading["observation"]["id"] == str(fixed.latest_observation.id)
    assert reading["observation"]["content_version"]["body"] == "固定正文"
    assert reading["observation"]["content_version"]["text_scope"] == "full"
    assert reading["observation"]["metrics"]["like_count"] == 0
    assert reading["observation"]["metrics"]["comment_count"] is None
    assert reading["observation"]["id"] != str(later.latest_observation.id)
    listing = event_read_client.get("/api/events", params={"topic_id": str(topic)})
    assert listing.status_code == 200, listing.json()
    assert [item["id"] for item in listing.json()["items"]] == [str(event_id)]
    with (
        event_read_client.app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="resource_not_found"),
    ):
        EventReadService(session).get_event(owner_id=uuid4(), event_id=event_id)


def test_expired_fixed_version_cannot_fall_back_to_newer_readable_version(
    event_read_client: TestClient,
) -> None:
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    with event_read_client.app.state.session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE evidence_resources SET expires_at=collected_at + interval '1 second' "
                "WHERE owner_id=:owner AND resource_id=:observation"
            ),
            {"owner": owner, "observation": fixed.latest_observation.id},
        )
    response = event_read_client.get(f"/api/events/{event_id}")
    assert response.status_code == 404, response.json()
    assert event_read_client.get("/api/events").json()["items"] == []
    with event_read_client.app.state.session_factory() as session, session.begin():
        assert fixed.latest_observation.content_version is not None
        result = load_event_member_content_in_transaction(
            session,
            owner_id=owner,
            references=(
                EventContentReadReference(
                    content_id=fixed.id,
                    content_version_id=fixed.latest_observation.content_version.id,
                ),
            ),
            now=datetime.now(UTC),
        )
        assert result == {}


def test_bulk_read_rejects_cross_content_or_owner_version_pair(
    event_read_client: TestClient,
) -> None:
    owner, _, _, fixed, _ = _seed_reading(event_read_client)
    assert fixed.latest_observation.content_version is not None
    with event_read_client.app.state.session_factory() as session, session.begin():
        references = (
            EventContentReadReference(
                content_id=uuid4(),
                content_version_id=fixed.latest_observation.content_version.id,
            ),
        )
        assert (
            load_event_member_content_in_transaction(
                session, owner_id=owner, references=references, now=datetime.now(UTC)
            )
            == {}
        )
        assert (
            load_event_member_content_in_transaction(
                session,
                owner_id=uuid4(),
                references=(
                    EventContentReadReference(
                        content_id=fixed.id,
                        content_version_id=fixed.latest_observation.content_version.id,
                    ),
                ),
                now=datetime.now(UTC),
            )
            == {}
        )
