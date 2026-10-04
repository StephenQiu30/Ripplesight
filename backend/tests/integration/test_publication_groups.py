from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_editorial_execution import NOW
from tests.integration.test_event_reading import _fixed_member_fields
from tests.integration.test_publication import _manual_posts
from tests.integration.test_publication import editorial_client as editorial_client

from core.errors import ApplicationError
from events.fact_models import EventFact, EventFactAssignment, EventFactMember
from events.models import Event, EventMember
from publication.application import PublicationApplicationService
from publication.group_schemas import PublicReadingFilters
from publication.indexnow_reading import read_indexable_path_eligibilities_in_transaction
from publication.reading_groups import (
    developments_in_transaction,
    fact_reports_in_transaction,
    timeline_in_transaction,
)
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


def test_group_reading_real_fixed_facts_revision_cursors_and_live_permission_changes(
    editorial_client: TestClient,
):
    owner, posts = _manual_posts(editorial_client, 3)
    sessions = editorial_client.app.state.session_factory
    event, root, development = uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        topic = session.execute(
            text("SELECT id FROM monitor_topics WHERE owner_id=:owner"), {"owner": owner}
        ).scalar_one()
        session.add(
            Event(
                id=event,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="事件",
                summary="固定事实",
                first_seen_at=NOW,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for fact in (root, development):
            session.add(
                EventFact(
                    id=fact,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="事实",
                    summary="正式确认事实",
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
        for fact in (root, development):
            session.add(
                EventFactAssignment(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    event_id=event,
                    fact_id=fact,
                    root_fact_id=None if fact == root else root,
                    relation="root" if fact == root else "development",
                    added_revision=1,
                    removed_revision=None,
                    created_at=NOW,
                )
            )
        for index, post in enumerate(posts):
            version = post.latest_observation.content_version.id
            member = uuid4()
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
                    fact_id=root if index < 2 else development,
                    event_id=event,
                    event_member_id=member,
                    content_id=post.id,
                    content_version_id=version,
                    role="primary" if index in {0, 2} else "report",
                    assignment_origin="model",
                    added_revision=1,
                    removed_revision=None,
                    created_at=NOW,
                )
            )
        session.flush()
        PublicationService(session, indexing_enabled=True).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                site_fulltext=True,
                indexable=True,
                license_name="受控事件索引许可",
                reason="检验全部固定成员的索引资格",
            ),
        )
        for post in posts:
            PublicationService(session, indexing_enabled=True).publish_in_transaction(
                owner_id=owner, content_id=post.id, now=NOW, released_at=NOW - timedelta(minutes=1)
            )
    later = NOW + timedelta(seconds=181)
    with sessions.begin() as session:
        path = f"/discover/stories/{event}"
        assert read_indexable_path_eligibilities_in_transaction(
            session, owner_id=owner, paths=[path], now=later
        ) == {path: True}
        assert path in PublicationApplicationService(
            session, indexing_enabled=True
        ).sitemap_collection_shard(owner_id=owner, collection="stories", shard=0, now=later)
        timeline = timeline_in_transaction(
            session, owner_id=owner, filters=PublicReadingFilters(), now=later
        )
        assert len(timeline.cards) == 1 and timeline.cards[0].group.development_count == 2
        assert timeline.cards[0].group.report_count == 3 and sum(timeline.day_counts.values()) == 1
        reports = fact_reports_in_transaction(
            session,
            owner_id=owner,
            fact_id=root,
            filters=PublicReadingFilters(),
            now=later,
            limit=1,
        )
        assert len(reports.reports) == 1 and reports.next_cursor
        second = fact_reports_in_transaction(
            session,
            owner_id=owner,
            fact_id=root,
            filters=PublicReadingFilters(),
            now=later,
            limit=1,
            cursor=reports.next_cursor,
        )
        assert len(second.reports) == 1 and not second.next_cursor
        assert reports.reports[0].id != second.reports[0].id
        progress = developments_in_transaction(
            session,
            owner_id=owner,
            event_id=event,
            filters=PublicReadingFilters(),
            now=later,
            limit=1,
        )
        assert progress.developments[0].fact_id == development and progress.next_cursor
        with pytest.raises(ApplicationError, match="invalid_publication_cursor"):
            developments_in_transaction(
                session,
                owner_id=owner,
                event_id=event,
                filters=PublicReadingFilters(channel="x"),
                now=later,
                limit=1,
                cursor=progress.next_cursor,
            )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 3
    with sessions.begin() as session:
        # Source-only narrowing creates no article revision, but the current ALL gate changes.
        PublicationService(session, indexing_enabled=True).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=later,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=2,
                participation_mode="editorial",
                site_fulltext=True,
                indexable=False,
                license_name="受控事件索引许可",
                reason="撤销索引许可,保持站内正文许可",
            ),
        )
        assert read_indexable_path_eligibilities_in_transaction(
            session, owner_id=owner, paths=[path], now=later
        ) == {path: False}
        assert session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 3
        assert path not in PublicationApplicationService(
            session, indexing_enabled=True
        ).sitemap_collection_shard(owner_id=owner, collection="stories", shard=0, now=later)
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[0].id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="summary-only",
                reason="撤回完整公开报道",
            ),
            now=later,
        )
    with sessions.begin() as session:
        with pytest.raises(ApplicationError, match="publication_revision_conflict"):
            fact_reports_in_transaction(
                session,
                owner_id=owner,
                fact_id=root,
                filters=PublicReadingFilters(),
                now=later,
                limit=1,
                cursor=reports.next_cursor,
            )
        page = timeline_in_transaction(
            session, owner_id=owner, filters=PublicReadingFilters(), now=later
        )
        assert page.cards[0].group.report_count == 2
        assert page.cards[0].item.id != posts[0].id
        assert session.execute(text("SELECT count(*) FROM event_facts")).scalar_one() == 2
    with sessions() as session:
        service = PublicationApplicationService(session)
        directory = service.topic_directory(owner_id=owner, now=later)
        assert directory.topics and not any(topic.indexable for topic in directory.topics)
        assert service.topic_page(owner_id=owner, slug="openai", now=later).items == []
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.topic_page(owner_id=owner, slug="missing", now=later)
    for path in [
        "/api/publication/timeline",
        f"/api/publication/facts/{root}/reports",
        f"/api/publication/stories/{event}/developments",
        "/api/publication/topics",
        "/api/publication/topics/openai",
    ]:
        response = editorial_client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.headers["cache-control"] == "no-store"
