# ruff: noqa: F811
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.integration.test_event_reading import _seed_reading, event_read_client  # noqa: F401
from tests.integration.test_event_reading_boundaries import _attach_member, _other_content

from core.errors import ApplicationError
from events.corrections import EventCorrectionService
from events.fact_models import (
    EventDerivedContent,
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingOverride,
    EventRevisionOperation,
)
from events.fact_schemas import EventCorrectionInput
from events.facts import load_publication_groupings_in_transaction
from events.models import Event, EventMember
from events.reads import EventReadService
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService


def test_split_keeps_historical_fixed_member_and_invalidates_old_text(
    event_read_client: TestClient,
) -> None:
    owner, _, source, fixed, _ = _seed_reading(event_read_client)
    command = EventCorrectionInput(
        operation_id=uuid4(),
        kind="split",
        reason="独立事实",
        content_ids=[fixed.id],
        expected_revisions={source: 1},
    )
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        result = EventCorrectionService(session).correct(
            owner_id=owner, actor_id=owner, command=command
        )
    assert result.target_event_id is not None and result.target_event_id != source
    with factory() as session:
        reading = EventReadService(session).get_event(owner_id=owner, event_id=source)
        assert reading.id == result.target_event_id
        assert reading.redirected_from_event_id == source
        assert reading.title is None and not reading.derived_text_available
        historical = EventReadService(session).list_members(
            owner_id=owner,
            event_id=source,
            revision=1,
            cursor=None,
            limit=20,
        )
        assert historical.items[0].content_version_id == fixed.latest_observation.content_version.id
        assert historical.items[0].content.observation.content_version.body == "固定正文"
        assert session.get(EventDerivedContent, (owner, result.target_event_id)).status == "stale"


def test_correction_replay_and_revision_conflict_have_no_duplicate_history(
    event_read_client: TestClient,
) -> None:
    owner, _, source, fixed, _ = _seed_reading(event_read_client)
    command = EventCorrectionInput(
        operation_id=uuid4(),
        kind="detach",
        reason="不属于事件",
        content_ids=[fixed.id],
        expected_revisions={source: 1},
    )
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        first = EventCorrectionService(session).correct(
            owner_id=owner, actor_id=owner, command=command
        )
        replay = EventCorrectionService(session).correct(
            owner_id=owner, actor_id=owner, command=command
        )
        assert replay.replayed and first.event_revisions == replay.event_revisions
        session.rollback()
        assert len(session.scalars(select(EventRevisionOperation)).all()) == 1
        override = session.get(
            EventGroupingOverride,
            (owner, next(iter(session.scalars(select(Event.topic_id)))), fixed.id),
        )
        assert override.mode == "standalone"
        session.rollback()
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            EventCorrectionService(session).correct(
                owner_id=owner,
                actor_id=owner,
                command=command.model_copy(update={"reason": "不同请求"}),
            )
        with pytest.raises(ApplicationError, match="event_revision_conflict"):
            EventCorrectionService(session).correct(
                owner_id=owner,
                actor_id=owner,
                command=command.model_copy(update={"operation_id": uuid4()}),
            )


def test_wrong_owner_and_unreadable_content_cannot_mutate_event(
    event_read_client: TestClient,
) -> None:
    owner, _, source, fixed, _ = _seed_reading(event_read_client)
    command = EventCorrectionInput(
        operation_id=uuid4(),
        kind="detach",
        reason="错误归组",
        content_ids=[fixed.id],
        expected_revisions={source: 1},
    )
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        with pytest.raises(ApplicationError, match="resource_not_found"):
            EventCorrectionService(session).correct(
                owner_id=uuid4(), actor_id=owner, command=command
            )
        session.rollback()
        assert session.get(Event, source).revision == 1
        assert len(session.scalars(select(EventMember)).all()) == 1


def test_merge_preserves_source_addresses_and_manual_override(
    event_read_client: TestClient,
) -> None:
    owner, topic, source, fixed, _ = _seed_reading(event_read_client)
    target = uuid4()
    factory = event_read_client.app.state.session_factory
    with factory() as session, session.begin():
        session.add(
            Event(
                id=target,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="目标事件",
                summary="目标摘要",
                first_seen_at=datetime.now(UTC),
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    with factory() as session:
        result = EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="merge",
                reason="同一故事",
                expected_revisions={source: 1, target: 1},
                target_event_id=target,
            ),
        )
        assert result.event_revisions == {source: 2, target: 2}
        session.rollback()
        assert session.get(Event, source).merged_into_id == target
        assert session.get(EventGroupingOverride, (owner, topic, fixed.id)).mode == "manual"
        session.rollback()
        assert EventReadService(session).get_event(owner_id=owner, event_id=source).id == target


def test_partial_split_creates_new_fact_and_current_then_historical_reading_stays_fixed(
    event_read_client: TestClient,
) -> None:
    owner, topic, source, fixed, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    _attach_member(event_read_client, owner=owner, topic=topic, event_id=source, content=other)
    factory = event_read_client.app.state.session_factory
    response = event_read_client.post(
        "/api/events/corrections",
        headers={"X-HotKey-CSRF": event_read_client.cookies["hotkey_csrf"]},
        json={
            "operation_id": str(uuid4()),
            "kind": "split",
            "reason": "拆出不同发生",
            "expected_revisions": {str(source): 1},
            "content_ids": [str(other.id)],
        },
    )
    assert response.status_code == 200, response.json()
    target = response.json()["target_event_id"]
    assert len(response.json()["created_fact_ids"]) == 1
    source_facts = event_read_client.get(f"/api/events/{source}/facts").json()["facts"]
    target_facts = event_read_client.get(f"/api/events/{target}/facts").json()["facts"]
    assert source_facts[0]["id"] != target_facts[0]["id"]
    assert source_facts[0]["members"][0]["content_id"] == str(fixed.id)
    history = event_read_client.get(f"/api/events/{source}/facts", params={"revision": 1}).json()
    assert {member["content_id"] for member in history["facts"][0]["members"]} == {
        str(fixed.id),
        str(other.id),
    }
    with factory() as session:
        audit = session.scalar(select(EventRevisionOperation))
        assert len(audit.after_state["facts"]) == 2
        assert (
            len(
                session.scalars(
                    select(EventFactMember).where(EventFactMember.removed_revision.is_(None))
                ).all()
            )
            == 2
        )


def test_move_and_fact_merge_keep_stable_fact_identity_and_direct_root(
    event_read_client: TestClient,
) -> None:
    owner, topic, source, fixed, _ = _seed_reading(event_read_client)
    other = _other_content(event_read_client, owner)
    target = uuid4()
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        session.add(
            Event(
                id=target,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="目标",
                summary="目标摘要",
                first_seen_at=now,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    _attach_member(event_read_client, owner=owner, topic=topic, event_id=target, content=other)
    with factory() as session:
        result = EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="move",
                reason="事实属于目标故事",
                expected_revisions={source: 1, target: 1},
                content_ids=[fixed.id],
                target_event_id=target,
            ),
        )
        assert result.created_fact_ids == []
        session.rollback()
        current = list(
            session.scalars(
                select(EventFactAssignment).where(
                    EventFactAssignment.event_id == target,
                    EventFactAssignment.removed_revision.is_(None),
                )
            )
        )
        root = next(row for row in current if row.relation == "root")
        assert all(row.root_fact_id == root.fact_id for row in current if row.relation != "root")
        command = EventCorrectionInput(
            operation_id=uuid4(),
            kind="merge_facts",
            reason="实际同一次发生",
            expected_revisions={target: 2},
            fact_ids=[row.fact_id for row in current],
            target_fact_id=root.fact_id,
        )
        result = EventCorrectionService(session).correct(
            owner_id=owner, actor_id=owner, command=command
        )
        session.rollback()
        assert (
            len(
                session.scalars(
                    select(EventFactAssignment).where(
                        EventFactAssignment.event_id == target,
                        EventFactAssignment.removed_revision.is_(None),
                    )
                ).all()
            )
            == 1
        )
        assert (
            session.scalar(select(EventFact).where(EventFact.status == "merged")).merged_into_id
            == root.fact_id
        )


def test_standalone_regroup_requires_explicit_action_and_keeps_pending_on_no_model(
    event_read_client: TestClient,
) -> None:
    owner, topic, source, fixed, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="detach",
                reason="保持独立",
                expected_revisions={source: 1},
                content_ids=[fixed.id],
            ),
        )
        result = EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="regroup",
                reason="重新模型复核",
                expected_revisions={source: 2},
                content_ids=[fixed.id],
            ),
        )
        assert result.event_revisions[source] == 3
        session.rollback()
        assert (
            session.get(EventGroupingOverride, (owner, topic, fixed.id)).mode == "regroup_pending"
        )


def test_unreadable_fixed_version_and_missing_csrf_block_manual_writes(
    event_read_client: TestClient,
) -> None:
    owner, _, source, fixed, _ = _seed_reading(event_read_client)
    command = {
        "operation_id": str(uuid4()),
        "kind": "detach",
        "reason": "排除",
        "expected_revisions": {str(source): 1},
        "content_ids": [str(fixed.id)],
    }
    assert event_read_client.post("/api/events/corrections", json=command).status_code == 403
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=fixed.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    assert (
        event_read_client.post(
            "/api/events/corrections",
            json=command,
            headers={"X-HotKey-CSRF": event_read_client.cookies["hotkey_csrf"]},
        ).status_code
        == 404
    )
    with factory() as session:
        assert session.get(Event, source).revision == 1
        assert session.scalar(select(EventRevisionOperation)) is None


def test_publication_grouping_reads_strict_current_fixed_version_without_mutation(
    event_read_client: TestClient,
) -> None:
    owner, topic, source, fixed, later = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        result = EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="split",
                reason="规范分组",
                expected_revisions={source: 1},
                content_ids=[fixed.id],
            ),
        )
    with factory() as session, session.begin():
        groups = load_publication_groupings_in_transaction(
            session,
            owner_id=owner,
            topic_id=topic,
            content_versions={fixed.id: fixed.latest_observation.content_version.id},
            now=datetime.now(UTC),
        )
        assert groups[fixed.id].event_id == result.target_event_id
        assert groups[fixed.id].role == "primary" and groups[fixed.id].event_revision == 1
        assert not session.new and not session.dirty
        assert not load_publication_groupings_in_transaction(
            session,
            owner_id=owner,
            content_versions={fixed.id: later.latest_observation.content_version.id},
            now=datetime.now(UTC),
        )
        assert not load_publication_groupings_in_transaction(
            session,
            owner_id=uuid4(),
            content_versions={fixed.id: fixed.latest_observation.content_version.id},
            now=datetime.now(UTC),
        )
