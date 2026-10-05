"""Real PostgreSQL selection projection/ledger/outlets; reviewers supply an isolated DB.

The stored editorial and event outputs are controlled evidence, never real model acceptance.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import _source
from tests.integration.test_event_reading import _fixed_member_fields
from tests.integration.test_publication import editorial_client as editorial_client
from tests.integration.test_publication_distribution import _call
from tests.unit.test_selected_news_gate import candidate

from analysis.editorial_models import EditorialRun
from analysis.editorial_schemas import EditorialOverrideInput, EditorialRunInput
from analysis.editorial_services import EditorialService
from core.errors import ApplicationError
from events.fact_models import EventFact, EventFactAssignment, EventFactMember
from events.models import Event, EventMember
from publication.publication_models import PublicationRecord
from publication.reading import PublicationReadingService
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService

NOW = datetime.now(UTC)
TEXTS = [
    "Acme released model A.",
    "Model A has been unveiled by Acme.",
    "A reminder: Acme has released model A.",
    "Acme released model A with 30% faster inference.",
    "An unresolved model A report.",
]


def _seed(client: TestClient, *, grouping_enabled: bool = True):
    client.app.state.settings.events_cluster_enabled = grouping_enabled
    # These public materials have actual source dates, not discovery-time substitutes.
    owner, topic, posts = _seed_posts(
        client, [(f"模型新闻{i}", body) for i, body in enumerate(TEXTS)], dated=True, now=NOW
    )
    _source(client, owner)
    sessions = client.app.state.session_factory
    for index, post in enumerate(posts):
        version = post.latest_observation.content_version
        assert version is not None
        with sessions() as session:
            run = EditorialService(session, clock=lambda: NOW).request_run(
                owner_id=owner,
                content_id=post.id,
                source_key="x",
                command=EditorialRunInput(operation_id=uuid4(), content_version_id=version.id),
            )
        with sessions.begin() as session:
            row = session.get(EditorialRun, run.id)
            row.status = "complete"
            row.result = candidate(
                index + 1,
                quote=TEXTS[index],
                scope="unknown" if not grouping_enabled and index == 4 else "single",
            ).snapshot.run.result.model_dump(mode="json", by_alias=True)
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                release_delay_seconds=0,
                site_fulltext=True,
                license_name="受控来源许可",
                reason="精选门禁集成",
            ),
        )
        for post in posts:
            result = service.publish_in_transaction(owner_id=owner, content_id=post.id, now=NOW)
            assert result
            if grouping_enabled:
                assert not result.selected and result.ledger is None
    client.app.state.settings.public_publication_owner_id = owner
    return owner, topic, posts


def _group(client, owner, topic, posts):
    event, root, repeated, progress = uuid4(), uuid4(), uuid4(), uuid4()
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        session.add(
            Event(
                id=event,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="模型 A 发布",
                summary="受控关系输出",
                first_seen_at=NOW,
                first_seen_basis="published",
                status="active",
                merged_into_id=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for identity, index in ((root, 0), (repeated, 2), (progress, 3)):
            frame = candidate(index + 1, quote=TEXTS[index]).snapshot.run.result.structure.fact
            session.add(
                EventFact(
                    id=identity,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="模型 A 事实",
                    summary="受控确认发生",
                    status="confirmed",
                    merged_into_id=None,
                    frame=frame.model_dump(mode="json", by_alias=True),
                    first_seen_at=NOW,
                    first_seen_basis="published",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        session.flush()
        for identity in (root, repeated, progress):
            session.add(
                EventFactAssignment(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    event_id=event,
                    fact_id=identity,
                    root_fact_id=None if identity == root else root,
                    relation="root" if identity == root else "development",
                    added_revision=1,
                    removed_revision=None,
                    created_at=NOW,
                )
            )
        for index, post in enumerate(posts[:4]):
            identity = root if index < 2 else repeated if index == 2 else progress
            member_id = uuid4()
            session.add(
                EventMember(
                    id=member_id,
                    owner_id=owner,
                    topic_id=topic,
                    event_id=event,
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
                    fact_id=identity,
                    event_id=event,
                    event_member_id=member_id,
                    content_id=post.id,
                    content_version_id=post.latest_observation.content_version.id,
                    role="report" if index == 1 else "primary",
                    assignment_origin="model",
                    added_revision=1,
                    removed_revision=None,
                    created_at=NOW,
                )
            )
    return root


def _counts(client):
    with client.app.state.session_factory() as session:
        return tuple(
            session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "jobs",
                "ai_calls",
                "publication_revisions",
                "publication_selected_changes",
            )
        )


@pytest.mark.parametrize("categories", [(), ("ai-models",)])
def test_unresolved_stays_in_all_then_confirmed_selection_is_persisted_once_everywhere(
    editorial_client: TestClient,
    monkeypatch,
    categories,
):
    client = editorial_client
    owner, topic, posts = _seed(client)
    client.app.state.settings.public_publication_categories = categories
    for at in (NOW, NOW + timedelta(hours=1)):
        with client.app.state.session_factory.begin() as session:
            reader = PublicationReadingService(session)
            assert not reader.items_in_transaction(owner_id=owner, selected=True, now=at).items
            assert len(reader.items_in_transaction(owner_id=owner, now=at).items) == 5
            for row in session.scalars(select(EditorialRun)):
                assert row.failure_code == "editorial_selection_requires_review"
    _group(client, owner, topic, posts)
    # GET remains read-only; admission enters the audited projection/ledger through republish.
    before = _counts(client)
    with client.app.state.session_factory.begin() as session:
        assert (
            not PublicationReadingService(session)
            .items_in_transaction(owner_id=owner, selected=True, now=NOW + timedelta(minutes=1))
            .items
        )
    assert _counts(client) == before
    with client.app.state.session_factory.begin() as session:
        service = PublicationService(session)
        for post in reversed(posts):
            service.publish_in_transaction(owner_id=owner, content_id=post.id, now=NOW)
        selected = {
            row.content_id for row in session.scalars(select(PublicationRecord)) if row.selected
        }
        assert selected == {posts[0].id, posts[3].id}
        runs = {row.content_id: row for row in session.scalars(select(EditorialRun))}
        assert runs[posts[1].id].result["selection_gate"]["state"] == "duplicate"
        assert runs[posts[2].id].result["selection_gate"]["state"] == "redundant"
        assert runs[posts[4].id].failure_code == "editorial_selection_requires_review"
        assert runs[posts[0].id].failure_code is None
    before = _counts(client)
    with client.app.state.session_factory.begin() as session:
        for post in posts:
            replay = PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW
            )
            assert replay and not replay.changed
    assert _counts(client) == before

    import publication.application as application
    import publication.mcp as mcp

    class ReadingClock(datetime):
        @classmethod
        def now(cls, tz=None):
            at = NOW + timedelta(minutes=1)
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)

    monkeypatch.setattr(application, "datetime", ReadingClock)
    monkeypatch.setattr(mcp, "datetime", ReadingClock)
    expected = {str(posts[0].id), str(posts[3].id)}
    page = client.get("/public/api/items").json()
    assert {item["id"] for item in page["items"]} == expected
    assert len(client.get("/public/api/items?mode=all").json()["items"]) == 5
    assert {
        item["id"] for item in _call(client, "hotkey_get_latest", {})["structuredContent"]["items"]
    } == expected
    rss = ElementTree.fromstring(client.get("/public/feed.xml").text)
    assert {item.findtext("guid") for item in rss.findall("./channel/item")} == {
        f"hotkey:item:{identity}" for identity in expected
    }
    response = client.get("/api/publication/selected/snapshot")
    assert response.status_code == 200, response.text
    sync = response.json()
    assert {item["id"] for item in sync["items"]} == expected
    response = client.get(
        "/api/publication/selected/changes", params={"epoch": sync["epoch"], "since": 0}
    )
    assert response.status_code == 200, response.text
    changes = response.json()
    assert changes["epoch"] == sync["epoch"] and changes["sequence"] == sync["sequence"]
    assert {
        change["item"]["id"] for change in changes["changes"] if change["item"] is not None
    } == expected
    timeline = client.get("/api/publication/timeline").json()
    assert len(timeline["cards"]) == 1
    assert timeline["cards"][0]["item"]["id"] == str(posts[0].id)
    assert _counts(client) == before


def test_representative_replacement_and_ledger_are_atomic_and_withdrawal_falls_back(
    editorial_client,
):
    client = editorial_client
    owner, topic, posts = _seed(client)
    _group(client, owner, topic, posts)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        for post in posts:
            PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW
            )
    before = _counts(client)
    with sessions() as session:
        session.begin()
        run = session.scalar(select(EditorialRun).where(EditorialRun.content_id == posts[1].id))
        run.result = {**run.result, "score": 100}
        session.flush()
        PublicationService(session).publish_in_transaction(
            owner_id=owner, content_id=posts[1].id, now=NOW
        )
        assert {
            row.content_id for row in session.scalars(select(PublicationRecord)) if row.selected
        } == {posts[1].id, posts[3].id}
        session.rollback()
    assert _counts(client) == before
    with sessions.begin() as session:
        run = session.scalar(select(EditorialRun).where(EditorialRun.content_id == posts[1].id))
        run.result = {**run.result, "score": 100}
        session.flush()
        PublicationService(session).publish_in_transaction(
            owner_id=owner, content_id=posts[1].id, now=NOW
        )
        assert not session.get(PublicationRecord, (owner, posts[0].id)).selected
        row = session.get(PublicationRecord, (owner, posts[1].id))
        assert row.selected
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[1].id,
            now=NOW,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=row.revision,
                visibility="withdrawn",
                reason="撤回当前代表",
            ),
        )
        assert session.get(PublicationRecord, (owner, posts[0].id)).selected
        assert not row.selected


def test_manual_value_survives_republish_and_stale_correction_is_rejected(editorial_client):
    owner, topic, posts = _seed(editorial_client)
    _group(editorial_client, owner, topic, posts)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        run = session.scalar(select(EditorialRun).where(EditorialRun.content_id == posts[2].id))
        run_id = run.id
        EditorialService(session, clock=lambda: NOW).override(
            owner_id=owner,
            run_id=run_id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=0,
                selected=True,
                reason="人工核查独立价值",
            ),
        )

    with sessions.begin() as session:
        for post in posts:
            PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW
            )
        run = session.get(EditorialRun, run_id)
        assert run.manual_version == 1 and run.result["manual_overrides"]["selected"] is True
        assert session.get(PublicationRecord, (owner, posts[2].id)).selected
        assert EditorialService(session).enqueue_due_in_transaction(now=NOW) == 0
        assert run.result["manual_overrides"]["selected"] is True
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0

    with sessions() as session, pytest.raises(ApplicationError, match="editorial_version_conflict"):
        EditorialService(session, clock=lambda: NOW).override(
            owner_id=owner,
            run_id=run_id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=0,
                selected=False,
                reason="旧人工版本不能覆盖",
            ),
        )


def test_default_disabled_grouping_automatically_selects_without_manual_confirmation(
    editorial_client,
):
    client = editorial_client
    assert client.app.state.settings.events_cluster_enabled is False
    owner, _, posts = _seed(client, grouping_enabled=False)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        rows = {row.content_id: row for row in session.scalars(select(PublicationRecord))}
        assert sum(row.selected for row in rows.values()) == 2
        assert rows[posts[4].id].selected  # Unknown fact keeps the original model selection.
        runs = {row.content_id: row for row in session.scalars(select(EditorialRun))}
        assert all(row.manual_version == 0 and row.failure_code is None for row in runs.values())
        assert runs[posts[4].id].result["selection_gate"]["reason"] == "grouping_disabled"
        assert (
            sum(row.result["selection_gate"]["state"] == "duplicate" for row in runs.values()) == 3
        )
        assert all(
            row.data["event_id"] is None and row.data["fact_id"] is None for row in rows.values()
        )
        reader = PublicationReadingService(session)
        assert len(reader.items_in_transaction(owner_id=owner, selected=True, now=NOW).items) == 2
        assert len(reader.items_in_transaction(owner_id=owner, now=NOW).items) == 5
    before = _counts(client)
    with sessions.begin() as session:
        for post in posts:
            replay = PublicationService(session).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW
            )
            assert replay and not replay.changed
    assert _counts(client) == before
    assert len(client.get("/public/api/items").json()["items"]) == 2
