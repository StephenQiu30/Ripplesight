"""PostgreSQL-to-public-API proof for complete counts, time evidence and live permission."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_editorial_execution import NOW
from tests.integration.test_event_reading import _fixed_member_fields
from tests.integration.test_publication import _manual_posts
from tests.integration.test_publication import editorial_client as editorial_client

from core.errors import DependencyUnavailableError
from events.fact_models import EventFact, EventFactAssignment, EventFactMember
from events.models import Event, EventMember
from publication.application import PublicationApplicationService
from publication.schemas import PublicationOverrideInput
from publication.services import PublicationService


@pytest.mark.parametrize("fail_at", [1, 3])
def test_strict_capacity_reaches_recall_and_story_reads(editorial_client, monkeypatch, fail_at):
    import events.facts as module

    _seed_events(editorial_client, 2)
    original = module.load_fact_observation_inputs_in_transaction
    calls = []

    def capacity(*args, **kwargs):
        calls.append(kwargs.get("strict_capacity"))
        if len(calls) == fail_at:
            assert kwargs["strict_capacity"]
            # Controlled simulation of a mixed/backfill closure exceeding 2000 members.
            raise DependencyUnavailableError("publication_distribution_unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "load_fact_observation_inputs_in_transaction", capacity)
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "publication_distribution_unavailable"
    assert "overview" not in response.json() and calls == [True] * fail_at


def _seed_events(client, count, *, with_development=False):
    owner, posts = _manual_posts(client, count + int(with_development))
    sessions = client.app.state.session_factory
    identities = []
    with sessions.begin() as session:
        topic = session.execute(
            text("SELECT id FROM monitor_topics WHERE owner_id=:owner"), {"owner": owner}
        ).scalar_one()
        for index in range(count):
            identity, root = uuid4(), uuid4()
            identities.append(identity)
            identified = NOW - timedelta(days=2) if index % 2 == 0 else NOW
            session.add(
                Event(
                    id=identity,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title=f"event {index}",
                    summary="controlled public evidence",
                    first_seen_at=NOW - timedelta(days=100),
                    first_seen_basis="published",
                    status="active",
                    merged_into_id=None,
                    created_at=identified,
                    updated_at=NOW,
                )
            )
            session.flush()
            fact_posts = [(root, posts[index], "root")]
            if with_development and index == 0:
                fact_posts.append((uuid4(), posts[-1], "development"))
            for fact, post, relation in fact_posts:
                session.add(
                    EventFact(
                        id=fact,
                        owner_id=owner,
                        topic_id=topic,
                        revision=1,
                        title="fact",
                        summary="confirmed controlled fact",
                        status="confirmed",
                        merged_into_id=None,
                        frame=None,
                        first_seen_at=NOW - timedelta(days=100),
                        first_seen_basis="published",
                        created_at=identified,
                        updated_at=NOW,
                    )
                )
                session.flush()
                session.add(
                    EventFactAssignment(
                        id=uuid4(),
                        owner_id=owner,
                        topic_id=topic,
                        event_id=identity,
                        fact_id=fact,
                        root_fact_id=None if relation == "root" else root,
                        relation=relation,
                        added_revision=1,
                        removed_revision=None,
                        created_at=NOW,
                    )
                )
                member_id = uuid4()
                session.add(
                    EventMember(
                        id=member_id,
                        owner_id=owner,
                        topic_id=topic,
                        event_id=identity,
                        content_id=post.id,
                        content_version_id=post.latest_observation.content_version.id,
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
                        event_id=identity,
                        event_member_id=member_id,
                        content_id=post.id,
                        content_version_id=post.latest_observation.content_version.id,
                        role="primary",
                        assignment_origin="model",
                        added_revision=1,
                        removed_revision=None,
                        created_at=NOW,
                    )
                )
        session.flush()
        for post in posts:
            PublicationService(session).publish_in_transaction(
                owner_id=owner,
                content_id=post.id,
                now=NOW,
                released_at=NOW - timedelta(minutes=10),
            )
    return owner, posts, identities


def test_full_site_counts_exceed_list_limit_and_use_live_grouping_without_writes(editorial_client):
    owner, posts, identities = _seed_events(editorial_client, 52, with_development=True)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        # Simulate pending publication reconciliation: never use stored grouping JSON for recall.
        session.execute(
            text(
                "UPDATE publication_records SET projection = "
                "jsonb_set(projection, '{event_id}', 'null'::jsonb)"
            )
        )
        before = {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "publication_revisions",
                "publication_selected_changes",
                "jobs",
                "ai_calls",
            )
        }
    response = editorial_client.get("/api/publication/home?limit=2")
    assert response.status_code == 200, response.text
    body = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert body["scope"] == "public_readable_events" and body["ranking_basis"] == "heat_then_recent"
    assert body["overview"] == dict(
        total_events=52,
        new_events_24h=26,
        updated_events_24h=1,
        covered_sources=1,
        time_unknown_events=0,
        platform_count=None,
        negative_surge_count=None,
    )
    assert len(body["stories"]) == 2
    assert all(
        story["attention"] is None or not story["attention"]["eligible"]
        for story in body["stories"]
    )
    assert all(story["timing"]["snapshot_at"] == body["snapshot_at"] for story in body["stories"])
    detail = editorial_client.get(f"/api/publication/stories/{identities[0]}")
    assert detail.status_code == 200
    timing = detail.json()["timing"]
    assert timing["activity"] == "existing_updated" and timing["occurred_at"] is None
    assert timing["reference_basis"] == "published" and timing["development_fact_ids"]
    with sessions.begin() as session:
        assert {
            table: session.scalar(text(f"SELECT count(*) FROM {table}")) for table in before
        } == before
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM publication_records "
                    "WHERE projection->>'event_id' IS NOT NULL"
                )
            )
            == 0
        )
        # Revoking one member removes the entire canonical event and its update from the counts.
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[-1].id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="withdrawn",
                reason="controlled revoke",
            ),
            now=NOW,
        )
    after = editorial_client.get("/api/publication/home").json()
    assert after["overview"]["total_events"] == 51 and after["overview"]["updated_events_24h"] == 0
    assert len(after["stories"]) == 50
    with sessions() as session:
        foreign = PublicationApplicationService(session).home(owner_id=uuid4(), now=NOW)
        assert foreign.overview.total_events == 0


@pytest.mark.parametrize("origin", ["legacy", "manual"])
def test_only_current_nonlegacy_development_supports_old_event_update(editorial_client, origin):
    _owner, _, identities = _seed_events(editorial_client, 1, with_development=True)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        development = session.scalar(
            select(EventFactAssignment).where(
                EventFactAssignment.event_id == identities[0],
                EventFactAssignment.relation == "development",
            )
        )
        session.execute(
            text("UPDATE event_fact_members SET assignment_origin=:origin WHERE fact_id=:fact"),
            {"origin": origin, "fact": development.fact_id},
        )
    first = editorial_client.get("/api/publication/home").json()
    assert first["overview"]["updated_events_24h"] == int(origin == "manual")
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE event_fact_assignments SET removed_revision=2 WHERE relation='development'"
            )
        )
    assert (
        editorial_client.get("/api/publication/home").json()["overview"]["updated_events_24h"] == 0
    )


def test_empty_unconfigured_and_snapshot_transaction_contract(editorial_client):
    body = editorial_client.get("/api/publication/home").json()
    assert body["overview"]["total_events"] == 0 and body["stories"] == []
    assert editorial_client.get("/api/publication/home?limit=51").status_code == 422
    sessions = editorial_client.app.state.session_factory
    with (
        sessions.begin() as session,
        pytest.raises(RuntimeError, match="repeatable-read read-only"),
    ):
        PublicationApplicationService(session).home(owner_id=uuid4(), now=NOW)
    editorial_client.app.state.settings.public_publication_owner_id = None
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 503 and response.json()["code"] == "publication_not_configured"


@pytest.mark.parametrize("count", [2000, 2001])
def test_history_capacity_fails_before_full_material_load(editorial_client, count):
    owner, posts, identities = _seed_events(editorial_client, 1)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        current = session.scalar(select(EventMember).where(EventMember.event_id == identities[0]))
        event = session.get(Event, identities[0])
        event.revision = count * 2 + 1
        for index in range(1, count):
            session.add(
                EventMember(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=current.topic_id,
                    event_id=identities[0],
                    content_id=posts[0].id,
                    content_version_id=current.content_version_id,
                    **_fixed_member_fields(session, owner, posts[0]),
                    source_key="x",
                    representative_comment_id=None,
                    added_revision=index * 2,
                    removed_revision=index * 2 + 1,
                    assignment_origin="model",
                    created_at=NOW,
                )
            )
    response = editorial_client.get("/api/publication/home")
    if count == 2000:
        assert response.status_code == 200, response.text
        assert response.json()["overview"]["total_events"] == 1
    else:
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "publication_distribution_unavailable"
        assert "overview" not in response.json()


def test_full_readable_scope_rechecks_stored_and_current_recommendation_eligibility(
    editorial_client,
):
    _owner, _, identities = _seed_events(editorial_client, 1)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE publication_records SET eligible=false, projection="
                "jsonb_set(projection, '{eligible}', 'false'::jsonb)"
            )
        )
    assert editorial_client.get(f"/api/publication/stories/{identities[0]}").status_code == 200
    assert editorial_client.get("/api/publication/home").json()["overview"]["total_events"] == 1
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE editorial_runs SET result="
                "jsonb_set(result, '{relevance}', '\"block\"'::jsonb)"
            )
        )
    # Recommendation eligibility is narrower than complete public readability.
    detail = editorial_client.get(f"/api/publication/stories/{identities[0]}")
    assert detail.status_code == 200, detail.text
    assert editorial_client.get("/api/publication/home").json()["overview"]["total_events"] == 1
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE editorial_runs SET result="
                "jsonb_set(result, '{relevance}', '\"pass\"'::jsonb)"
            )
        )
        session.execute(
            text(
                "UPDATE publication_records SET selected=true, "
                "projection=jsonb_set(jsonb_set(projection, '{selected}', 'true'::jsonb), "
                "'{visible_after}', to_jsonb(CAST(:future AS timestamptz)))"
            ),
            {"future": NOW + timedelta(days=1)},
        )
    assert editorial_client.get("/api/publication/home").json()["overview"]["total_events"] == 0


@pytest.mark.parametrize("count", [2000, 2001])
def test_mixed_event_fact_closure_capacity_uses_real_rows(editorial_client, count):
    """Two individually small events overflow the shared recall closure, not history."""
    owner, _, identities = _seed_events(editorial_client, 2)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        roots = session.execute(
            select(EventMember, EventFactMember)
            .join(EventFactMember, EventFactMember.event_member_id == EventMember.id)
            .where(EventMember.event_id.in_(identities))
            .order_by(EventMember.event_id)
        ).all()
        records, versions, members, fact_members = [], [], [], []
        for index in range(count - 2):
            member, fact_member = roots[index % 2]
            content, version, identity = uuid4(), uuid4(), uuid4()
            records.append(
                dict(
                    id=content,
                    owner_id=owner,
                    source_key="x",
                    object_type="post",
                    external_id=str(content),
                    created_at=NOW,
                )
            )
            versions.append(
                dict(
                    id=version,
                    owner_id=owner,
                    content_id=content,
                    fingerprint=b"x" * 32,
                    text_scope="full",
                    text_origin="source",
                    title="capacity-only material",
                    created_at=NOW,
                )
            )
            members.append(
                dict(
                    id=identity,
                    owner_id=owner,
                    topic_id=member.topic_id,
                    event_id=member.event_id,
                    content_id=content,
                    content_version_id=version,
                    source_key="x",
                    added_revision=1,
                    assignment_origin="model",
                    created_at=NOW,
                )
            )
            fact_members.append(
                dict(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=member.topic_id,
                    fact_id=fact_member.fact_id,
                    event_id=member.event_id,
                    event_member_id=identity,
                    content_id=content,
                    content_version_id=version,
                    role="report",
                    assignment_origin="model",
                    added_revision=1,
                    created_at=NOW,
                )
            )
        # Within capacity these rows must fail the ALL-member permission gate because
        # they have no observation/grant. Overflow must instead fail the whole request.
        from content.models import ContentRecord, ContentVersion

        for model, values in (
            (ContentRecord, records),
            (ContentVersion, versions),
            (EventMember, members),
            (EventFactMember, fact_members),
        ):
            session.execute(model.__table__.insert(), values)
        assert (
            session.scalar(
                text(
                    "SELECT max(n) FROM (SELECT count(*) n FROM event_members GROUP BY event_id) t"
                )
            )
            < 2000
        )
        assert session.scalar(text("SELECT count(*) FROM event_fact_members")) == count
    response = editorial_client.get("/api/publication/home")
    if count == 2000:
        assert response.status_code == 200, response.text
        assert response.json()["overview"]["total_events"] == 0
    else:
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "publication_distribution_unavailable"
        assert "overview" not in response.json()


def test_digest_body_capacity_propagates_to_home(editorial_client, monkeypatch):
    """A recorded valid digest must preserve the strict capacity flag down its own import."""
    from types import SimpleNamespace

    import events.digest as digest
    from events.digest_prompts import event_digest_prompt_version
    from events.fact_models import EventDerivedContent

    owner, _, identities = _seed_events(editorial_client, 1)
    sessions = editorial_client.app.state.session_factory
    fingerprint = b"d" * 32
    with sessions.begin() as session:
        event = session.get(Event, identities[0])
        job_id = session.scalar(
            text("SELECT id FROM jobs WHERE owner_id=:owner LIMIT 1"), {"owner": owner}
        )
        session.add(
            EventDerivedContent(
                owner_id=owner,
                event_id=event.id,
                topic_id=event.topic_id,
                event_revision=event.revision,
                input_fingerprint=fingerprint,
                status="valid",
                title="controlled digest",
                summary="controlled digest body",
                latest_progress=None,
                ai_call_id=None,
                job_id=job_id,
                error_code=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    monkeypatch.setattr(
        digest,
        "load_job_execution_configuration",
        lambda *args, **kwargs: SimpleNamespace(
            owner_id=owner,
            kind="events.digest",
            scope={
                "event_id": str(identities[0]),
                "event_revision": 1,
                "input_fingerprint": fingerprint.hex(),
                "prompt_version": event_digest_prompt_version(),
            },
        ),
    )
    calls = []

    def overflow(*args, **kwargs):
        calls.append(kwargs.get("strict_capacity"))
        assert kwargs["strict_capacity"]
        raise DependencyUnavailableError("publication_distribution_unavailable")

    monkeypatch.setattr(digest, "load_fact_observation_inputs_in_transaction", overflow)
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "publication_distribution_unavailable"
    assert "overview" not in response.json() and calls == [True]
