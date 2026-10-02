from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.integration.test_content_records import _command, _comment_command, _seed_comment_context
from tests.integration.test_event_reading import _seed_reading
from tests.integration.test_event_reading import event_read_client as event_read_client

from content.schemas import ContentRecordSummaryView
from content.services import ContentService
from events.models import Event, EventMember
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService


def _other_content(client: TestClient, owner: UUID) -> ContentRecordSummaryView:
    with client.app.state.session_factory() as session:
        connection = session.execute(text("SELECT id FROM source_connections")).scalar_one()
        policy = session.execute(text("SELECT id FROM source_access_policies")).scalar_one()
        retention = session.execute(text("SELECT id FROM evidence_retention_policies")).scalar_one()
        job = session.execute(text("SELECT id FROM jobs LIMIT 1")).scalar_one()
        return ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                operation_id=uuid4(),
                external_id=str(uuid4()),
                observed_at=datetime.now(UTC) - timedelta(minutes=1),
                extra_fields={
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "另外一份证据",
                    "body": "可读的独立正文",
                },
            ),
        )


def _attach_member(
    client: TestClient,
    *,
    owner: UUID,
    topic: UUID,
    event_id: UUID,
    content: ContentRecordSummaryView,
    revision: int = 1,
) -> UUID:
    assert content.latest_observation.content_version is not None
    identity = uuid4()
    with client.app.state.session_factory() as session, session.begin():
        session.add(
            EventMember(
                id=identity,
                owner_id=owner,
                topic_id=topic,
                event_id=event_id,
                content_id=content.id,
                content_version_id=content.latest_observation.content_version.id,
                source_key=content.source_key,
                representative_comment_id=None,
                added_revision=revision,
                removed_revision=None,
                assignment_origin="manual",
                created_at=datetime.now(UTC),
            )
        )
    return identity


def test_partial_member_evidence_redacts_derived_text_and_search(
    event_read_client: TestClient,
) -> None:
    owner, topic, event_id, fixed, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    _attach_member(event_read_client, owner=owner, topic=topic, event_id=event_id, content=other)
    with event_read_client.app.state.session_factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=fixed.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    detail = event_read_client.get(f"/api/events/{event_id}").json()
    assert detail["evidence_state"] == "partial"
    assert detail["member_count"] == 2 and detail["readable_member_count"] == 1
    assert detail["title"] is None and detail["summary"] is None
    assert detail["derived_text_available"] is False
    page = event_read_client.get(f"/api/events/{event_id}/members").json()
    unavailable = next(member for member in page["items"] if member["content_id"] == str(fixed.id))
    assert unavailable["content"] is None and unavailable["availability"] == "unavailable"
    assert event_read_client.get("/api/events", params={"query": "固定正文"}).json()["items"] == []
    assert (
        len(event_read_client.get("/api/events", params={"query": "独立正文"}).json()["items"]) == 1
    )


def test_member_pagination_is_bound_to_revision_and_supports_history(
    event_read_client: TestClient,
) -> None:
    owner, topic, event_id, fixed, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    other_member = _attach_member(
        event_read_client, owner=owner, topic=topic, event_id=event_id, content=other
    )
    first = event_read_client.get(f"/api/events/{event_id}/members", params={"limit": 1}).json()
    cursor = first["next_cursor"]
    assert cursor is not None
    second = event_read_client.get(
        f"/api/events/{event_id}/members", params={"cursor": cursor}
    ).json()
    assert {member["content_id"] for member in first["items"] + second["items"]} == {
        str(fixed.id),
        str(other.id),
    }
    with event_read_client.app.state.session_factory() as session, session.begin():
        event = session.get(Event, event_id)
        member = session.get(EventMember, other_member)
        assert event is not None and member is not None
        event.revision = 2
        event.updated_at = datetime.now(UTC)
        member.removed_revision = 2
    assert (
        event_read_client.get(
            f"/api/events/{event_id}/members", params={"cursor": cursor}
        ).status_code
        == 422
    )
    historic = event_read_client.get(
        f"/api/events/{event_id}/members", params={"cursor": cursor, "revision": 1}
    )
    assert historic.status_code == 200, historic.json()
    assert historic.json()["current_revision"] == 2 and historic.json()["revision"] == 1
    assert (
        event_read_client.get(f"/api/events/{event_id}/members", params={"revision": 3}).status_code
        == 422
    )
    with event_read_client.app.state.session_factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=other.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    current = event_read_client.get(f"/api/events/{event_id}").json()
    assert current["evidence_state"] == "complete"
    assert current["derived_text_available"] is False and current["summary"] is None


def test_merged_current_read_resolves_canonical_but_historical_members_remain(
    event_read_client: TestClient,
) -> None:
    owner, topic, old_id, fixed, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    canonical_id = uuid4()
    now = datetime.now(UTC)
    with event_read_client.app.state.session_factory() as session, session.begin():
        session.add(
            Event(
                id=canonical_id,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="归并后的事件",
                summary="规范事件的摘要",
                first_seen_at=now,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        old = session.get(Event, old_id)
        member = session.scalar(select(EventMember).where(EventMember.event_id == old_id))
        assert old is not None and member is not None
        old.status, old.merged_into_id, old.revision, old.updated_at = (
            "merged",
            canonical_id,
            2,
            now,
        )
        member.removed_revision = 2
    _attach_member(
        event_read_client, owner=owner, topic=topic, event_id=canonical_id, content=other
    )
    response = event_read_client.get(f"/api/events/{old_id}")
    assert response.status_code == 200, response.json()
    assert response.json()["id"] == str(canonical_id)
    assert response.json()["redirected_from_event_id"] == str(old_id)
    members = event_read_client.get(f"/api/events/{old_id}/members").json()
    assert members["event_id"] == str(canonical_id)
    history = event_read_client.get(f"/api/events/{old_id}/members", params={"revision": 1}).json()
    assert history["event_id"] == str(old_id) and history["items"][0]["content_id"] == str(fixed.id)


def test_representative_comment_must_belong_to_post_and_remain_readable(
    event_read_client: TestClient,
) -> None:
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    with event_read_client.app.state.session_factory() as session:
        connection = session.execute(text("SELECT id FROM source_connections")).scalar_one()
    policy, retention, job = _seed_comment_context(event_read_client, owner, connection)
    with event_read_client.app.state.session_factory() as session:
        comment = ContentService(session).persist_comment(
            owner_id=owner,
            command=_comment_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                external_id="representative",
                post_external_id=fixed.external_id,
            ),
        )
    with event_read_client.app.state.session_factory() as session, session.begin():
        member = session.scalar(select(EventMember).where(EventMember.event_id == event_id))
        assert member is not None
        member.representative_comment_id = comment.id
    reading = event_read_client.get(f"/api/events/{event_id}/members").json()["items"][0]["content"]
    assert reading["representative_comment_state"] == "readable"
    comment_version = reading["representative_comment"]["observation"]["content_version"]
    assert comment_version["body"] == "评论 representative"
    with event_read_client.app.state.session_factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=comment.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    reading = event_read_client.get(f"/api/events/{event_id}/members").json()["items"][0]["content"]
    assert reading["representative_comment_state"] == "unavailable"
    assert reading["representative_comment"] is None
    assert (
        event_read_client.get(f"/api/events/{event_id}").json()["derived_text_available"] is False
    )


def test_event_list_paginates_after_filtering_more_than_one_batch_of_unreadable_events(
    event_read_client: TestClient,
) -> None:
    owner, topic, readable_id, _, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    second_id = uuid4()
    now = datetime.now(UTC)
    with event_read_client.app.state.session_factory() as session, session.begin():
        for identity in [second_id, *(uuid4() for _ in range(101))]:
            session.add(
                Event(
                    id=identity,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="无成员不公开",
                    summary="无证据派生内容",
                    first_seen_at=now,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
    _attach_member(event_read_client, owner=owner, topic=topic, event_id=second_id, content=other)
    first = event_read_client.get("/api/events", params={"limit": 1, "topic_id": str(topic)})
    assert first.status_code == 200, first.json()
    assert first.json()["items"][0]["id"] == str(second_id)
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    second = event_read_client.get(
        "/api/events",
        params={
            "limit": 1,
            "topic_id": str(topic),
            "cursor": cursor,
        },
    )
    assert second.status_code == 200, second.json()
    assert [item["id"] for item in second.json()["items"]] == [str(readable_id)]
    assert second.json()["next_cursor"] is None
    assert (
        event_read_client.get(
            "/api/events",
            params={
                "cursor": cursor,
                "topic_id": str(topic),
                "source_key": "reddit",
            },
        ).status_code
        == 422
    )
    assert event_read_client.get(
        "/api/events",
        params={
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": now.isoformat(),
            "topic_id": str(topic),
            "source_key": "x",
            "query": "固定正文",
        },
    ).json()["items"][0]["id"] == str(readable_id)


def test_representative_comment_from_another_post_is_unavailable(
    event_read_client: TestClient,
) -> None:
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    with event_read_client.app.state.session_factory() as session:
        connection = session.execute(text("SELECT id FROM source_connections")).scalar_one()
    policy, retention, job = _seed_comment_context(event_read_client, owner, connection)
    with event_read_client.app.state.session_factory() as session:
        comment = ContentService(session).persist_comment(
            owner_id=owner,
            command=_comment_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                external_id="other-post-comment",
                post_external_id="unrelated-post",
            ),
        )
    with event_read_client.app.state.session_factory() as session, session.begin():
        member = session.scalar(select(EventMember).where(EventMember.event_id == event_id))
        assert member is not None
        member.representative_comment_id = comment.id
    reading = event_read_client.get(f"/api/events/{event_id}/members").json()["items"][0]["content"]
    assert reading["representative_comment_state"] == "unavailable"
    assert reading["representative_comment"] is None
