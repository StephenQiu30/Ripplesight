# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from tests.integration.test_event_reading import _seed_reading, event_read_client  # noqa: F401
from tests.integration.test_event_reading_boundaries import _attach_member, _other_content

from events.heat import EventHeatService, record_source_fetch_success_in_transaction
from events.heat_models import EventAttentionSignal, EventAttentionSnapshot, EventAttentionSource
from events.heat_schemas import AttentionSourceInput
from events.models import Event, EventMember
from jobs.models import Job
from monitors.models import MonitorTopic, MonitorTopicVersion


def _seed_heat(client):
    owner, topic, event, fixed, _ = _seed_reading(client)
    other = _other_content(client, owner)
    _attach_member(client, owner=owner, topic=topic, event_id=event, content=other)
    with client.app.state.session_factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE content_observations SET author_external_id=:author "
                "WHERE content_id=:content"
            ),
            {"author": "second-author", "content": other.id},
        )
    with client.app.state.session_factory() as session, session.begin():
        session.execute(
            text("UPDATE content_observations SET published_at=:published WHERE owner_id=:owner"),
            {"published": datetime.now(UTC) - timedelta(minutes=3), "owner": owner},
        )
    return owner, event, topic, fixed, other


def _seed_heat_beyond_candidate_page(client, *, count=1000):
    owner, hottest, topic, fixed, other = _seed_heat(client)
    factory = client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        for selector_kind, selector_ref, mode in (
            ("source", "x", "editorial"),
            ("author", "second-author", "signal"),
        ):
            service.upsert_source(
                owner_id=owner,
                command=AttentionSourceInput(
                    source_key="x",
                    selector_kind=selector_kind,
                    selector_ref=selector_ref,
                    name=selector_ref,
                    mode=mode,
                    scheduled=False,
                ),
            )
    # One permitted fixed report can belong to distinct monitor topics. Each newer
    # event is readable but has one participant; the older event has two and is hot.
    topics = [uuid4() for _ in range(count)]
    newer = [uuid4() for _ in topics]
    with factory() as session, session.begin():
        session.execute(
            insert(MonitorTopic),
            [
                dict(
                    id=identity,
                    owner_id=owner,
                    name="Controlled heat candidate",
                    status="active",
                    readiness_status="ready",
                    current_version=1,
                    created_at=now,
                    updated_at=now,
                )
                for identity in topics
            ],
        )
        session.execute(
            insert(MonitorTopicVersion),
            [
                dict(
                    topic_id=identity,
                    version=1,
                    created_by=owner,
                    match_any=["heat"],
                    match_all=[],
                    exclude=[],
                    created_at=now,
                )
                for identity in topics
            ],
        )
        session.execute(
            insert(Event),
            [
                dict(
                    id=identity,
                    owner_id=owner,
                    topic_id=topic_id,
                    revision=1,
                    title="Controlled newer event",
                    summary="One readable independent source",
                    first_seen_at=now,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
                for identity, topic_id in zip(newer, topics, strict=True)
            ],
        )
        session.execute(
            insert(EventMember),
            [
                dict(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic_id,
                    event_id=identity,
                    content_id=fixed.id,
                    content_version_id=fixed.latest_observation.content_version.id,
                    source_key="x",
                    representative_comment_id=None,
                    added_revision=1,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=now,
                )
                for identity, topic_id in zip(newer, topics, strict=True)
            ],
        )
    return owner, hottest, topic, factory, now, other, tuple(zip(newer, topics, strict=True))


def test_hot_read_scans_past_thousand_newer_events_for_actual_highest_heat(event_read_client):
    owner, hottest, topic, factory, now, _, _ = _seed_heat_beyond_candidate_page(event_read_client)
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        highest = service.get_attention(owner_id=owner, event_id=hottest)
        assert highest.eligible and highest.participant_count == 2 and highest.heat > 10
        page = service.list_hot(owner_id=owner, topic_id=None)
        assert [item.event_id for item in page.items] == [hottest]
        assert page.items[0].heat == highest.heat
        assert service.list_hot(owner_id=owner, topic_id=topic).items == page.items
        assert session.scalar(select(Job).where(Job.kind == "events.heat")) is None
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


def test_hourly_heat_scan_continues_after_thousand_already_admitted_events(event_read_client):
    owner, hottest, _, factory, now, _, _ = _seed_heat_beyond_candidate_page(event_read_client)
    with factory() as session, session.begin():
        service = EventHeatService(session)
        assert service.enqueue_due_in_transaction(now=now, enabled=False) == 0
        assert service.enqueue_due_in_transaction(now=now, enabled=True) == 1000
        assert service.enqueue_due_in_transaction(now=now, enabled=True) == 1
        assert service.enqueue_due_in_transaction(now=now, enabled=True) == 0
        jobs = session.scalars(select(Job).where(Job.kind == "events.heat")).all()
        assert len(jobs) == 1001 and len({job.operation_id for job in jobs}) == 1001
        assert any(job.scope["event_id"] == str(hottest) and job.owner_id == owner for job in jobs)
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


def test_hot_read_retains_exact_top_ten_and_canonical_tie_order(event_read_client):
    owner, hottest, _, factory, now, second, candidates = _seed_heat_beyond_candidate_page(
        event_read_client, count=14
    )
    with factory() as session, session.begin():
        session.execute(
            insert(EventMember),
            [
                dict(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    event_id=identity,
                    content_id=second.id,
                    content_version_id=second.latest_observation.content_version.id,
                    source_key="x",
                    representative_comment_id=None,
                    added_revision=1,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=now,
                )
                for identity, topic in candidates
            ],
        )
    with factory() as session:
        actual = EventHeatService(session, clock=lambda: now).list_hot(
            owner_id=owner, topic_id=None
        )
        # Fixed evidence and source times are identical across these distinct topics.
        # Event update order must not replace the documented canonical-ID tie break.
        expected = sorted([hottest, *(identity for identity, _ in candidates)], key=str)[:10]
        assert [item.event_id for item in actual.items] == expected
        assert len(actual.items) == 10 and len({item.heat for item in actual.items}) == 1


def test_heat_persists_exact_versions_without_repeated_collection_time_refresh(event_read_client):
    client = event_read_client
    owner, event, _, fixed, other = _seed_heat(client)
    now = datetime.now(UTC)
    factory = client.app.state.session_factory
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        first = service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="source",
                selector_ref="x",
                name="独立新闻",
                mode="editorial",
                scheduled=False,
            ),
        )
        second = service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="author",
                selector_ref="second-author",
                name="社区讨论",
                mode="signal",
                scheduled=False,
            ),
        )
    with factory() as session, session.begin():
        EventHeatService(session).refresh_in_transaction(owner_id=owner, event_id=event, at=now)
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        result = service.get_attention(owner_id=owner, event_id=event)
        assert result.eligible and result.participant_count == 2
        assert result.editorial_participant_count == 1
        signals = session.scalars(select(EventAttentionSignal)).all()
        assert {row.content_version_id for row in signals} == {
            fixed.latest_observation.content_version.id,
            other.latest_observation.content_version.id,
        }
        times = {row.id: row.source_time for row in signals}
        assert session.scalar(select(EventAttentionSnapshot)) is not None
        assert {first.id, second.id} == {row.source_id for row in signals}
    with factory() as session, session.begin():
        EventHeatService(session).refresh_in_transaction(
            owner_id=owner, event_id=event, at=now + timedelta(hours=1)
        )
        assert {
            row.id: row.source_time for row in session.scalars(select(EventAttentionSignal))
        } == times
    assert first.id != second.id


def test_source_clock_only_records_exact_successful_scope_and_never_moves_back(event_read_client):
    owner, _, _, _, _ = _seed_reading(event_read_client)
    now = datetime.now(UTC)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        wildcard = service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="source",
                selector_ref="x",
                name="整个来源",
                mode="editorial",
            ),
        )
        author = service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="author",
                selector_ref="writer",
                name="指定作者",
                mode="editorial",
            ),
        )
    with factory() as session, session.begin():
        record_source_fetch_success_in_transaction(
            session,
            owner_id=owner,
            source_key="x",
            selector_kind="author",
            selector_ref="writer",
            completed_at=now,
        )
        record_source_fetch_success_in_transaction(
            session,
            owner_id=owner,
            source_key="x",
            selector_kind="author",
            selector_ref="writer",
            completed_at=now - timedelta(hours=1),
        )
    with factory() as session:
        assert session.get(EventAttentionSource, wildcard.id).last_successful_fetch_at is None
        assert session.get(EventAttentionSource, author.id).last_successful_fetch_at == now
        assert session.get(EventAttentionSource, author.id).revision == 1


def test_current_heat_rechecks_roles_group_identity_and_withdrawal(event_read_client):
    client = event_read_client
    owner, event, _, _, _ = _seed_heat(client)
    now = datetime.now(UTC)
    factory = client.app.state.session_factory
    with factory() as session:
        service = EventHeatService(session, clock=lambda: now)
        first = service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="source",
                selector_ref="x",
                name="第一",
                mode="editorial",
                scheduled=False,
            ),
        )
        service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="author",
                selector_ref="second-author",
                name="第二",
                mode="signal",
                scheduled=False,
            ),
        )
        assert service.get_attention(owner_id=owner, event_id=event).eligible
        service.upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="source",
                selector_ref="x",
                name="第一",
                mode="signal",
                scheduled=False,
                expected_revision=first.revision,
            ),
        )
        result = service.get_attention(owner_id=owner, event_id=event)
        assert not result.eligible and result.editorial_participant_count == 0
        assert service.list_hot(owner_id=owner, topic_id=None).items == []
        assert all(row.source_id != UUID(int=0) for row in result.roster)


def test_heat_job_writes_snapshot_and_history_is_bound_to_event_revision(event_read_client):
    from types import SimpleNamespace

    from core.config import Settings
    from events.heat import EventHeatExecutor
    from events.models import Event
    from jobs.models import Job

    now = datetime.now(UTC)
    owner, event, _, _, _ = _seed_heat(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session, session.begin():
        assert EventHeatService(session).enqueue_due_in_transaction(now=now, enabled=True) == 1
        assert EventHeatService(session).enqueue_due_in_transaction(now=now, enabled=True) == 0
        job = session.scalar(select(Job).where(Job.kind == "events.heat"))
        message = SimpleNamespace(
            kind=job.kind,
            job_id=job.id,
            operation_id=job.operation_id,
            owner_id=owner,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )
    executor = EventHeatExecutor(
        factory,
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1:15434/hotkey_test",
            events_cluster_enabled=True,
        ),
        clock=lambda: now,
    )
    assert executor.execute(message).status.value == "succeeded"
    assert executor.execute(message).status.value == "succeeded"
    with factory() as session:
        history = EventHeatService(session, clock=lambda: now).list_history(
            owner_id=owner, event_id=event
        )
        assert len(history.items) == 1 and history.event_revision == 1
    with factory() as session, session.begin():
        session.get(Event, event).revision = 2
    with factory() as session:
        assert (
            EventHeatService(session, clock=lambda: now)
            .list_history(owner_id=owner, event_id=event)
            .items
            == []
        )


def test_heat_api_read_is_no_store_and_source_role_write_requires_operator(event_read_client):
    owner, event, _, _, _ = _seed_heat(event_read_client)
    assert owner
    response = event_read_client.get(f"/api/events/{event}/heat")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert event_read_client.get("/api/events/hot").status_code == 200
    assert event_read_client.get("/api/events/attention-sources").status_code == 200
    denied = event_read_client.put(
        "/api/events/attention-sources",
        headers={"X-HotKey-CSRF": event_read_client.cookies["hotkey_csrf"]},
        json={
            "source_key": "x",
            "selector_kind": "source",
            "selector_ref": "x",
            "name": "编辑源",
            "mode": "editorial",
        },
    )
    assert denied.status_code == 403 and denied.json()["code"] == "operator_disabled"


def test_publication_story_helper_freezes_all_fixed_members_and_rechecks_revocation(
    event_read_client,
):
    from events.reads import load_publication_stories_in_transaction
    from evidence.schemas import DeletionReason
    from evidence.services import LifecycleService

    owner, event, _, fixed, _ = _seed_heat(event_read_client)
    now = datetime.now(UTC)
    factory = event_read_client.app.state.session_factory
    with factory() as session, session.begin():
        stories = load_publication_stories_in_transaction(
            session, owner_id=owner, event_ids=(event,), now=now
        )
        assert len(stories[event].members) == 2 and stories[event].heat is None
        assert fixed.latest_observation.content_version.id in {
            row.content_version_id for row in stories[event].members
        }
        assert not session.new and not session.dirty
    with factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            reason=DeletionReason.USER_REQUEST,
            resource_type="content_observation",
            resource_id=fixed.latest_observation.id,
        )
    with factory() as session, session.begin():
        assert (
            load_publication_stories_in_transaction(
                session, owner_id=owner, event_ids=(event,), now=now
            )
            == {}
        )
