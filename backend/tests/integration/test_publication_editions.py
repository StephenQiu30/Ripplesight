from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_publication import editorial_client as _editorial_client
from tests.integration.test_report_editions import _admit, _executor

from core.errors import ApplicationError
from publication.application import PublicationApplicationService
from publication.indexnow_reading import read_indexable_path_eligibilities_in_transaction
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    import tests.integration.test_report_editions as fixtures

    generator = _editorial_client.__wrapped__(request, monkeypatch)
    client = next(generator)
    from tests.integration.test_publication import NOW

    monkeypatch.setattr(fixtures, "NOW", NOW)
    try:
        yield client
    finally:
        generator.close()


def test_public_edition_current_revision_and_all_reference_index_permission(editorial_client):
    owner, edition, message, lease = _admit(editorial_client)
    _executor(editorial_client, edition).execute(message, lease)
    now = edition.window_end + timedelta(hours=2)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        app = PublicationApplicationService(
            session, origin="https://hotkey.example", indexing_enabled=True
        )
        public = app.edition(owner_id=owner, kind="daily", key=edition.key, now=now)
        assert public.canonical_url == f"https://hotkey.example/reports/daily/{edition.key}"
        assert public.entries and not public.indexable
        before = session.execute(text("SELECT count(*) FROM report_editions")).scalar_one()
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5
        session.rollback()
    with sessions.begin() as session:
        service = PublicationService(session, indexing_enabled=True)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=now,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                indexable=True,
                license_name="受控许可",
                reason="允许当前公开稿索引",
            ),
        )
        # A rights expansion needs a new audited publication, and invalidates the old report.
        service.publish_in_transaction(owner_id=owner, content_id=public.entries[0].id, now=now)
    with sessions() as session:
        with pytest.raises(ApplicationError, match="resource_not_found"):
            PublicationApplicationService(session, indexing_enabled=True).edition(
                owner_id=owner, kind="daily", key=edition.key, now=now
            )
        assert session.execute(text("SELECT count(*) FROM report_editions")).scalar_one() == before
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5


def test_edition_sitemap_and_indexing_recheck_source_policy_without_article_revision(
    editorial_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tests.integration.test_report_editions as fixtures

    class IndexablePublisher(PublicationService):
        def __init__(self, session):
            super().__init__(session, indexing_enabled=True)

        def save_source_policy_in_transaction(self, **kwargs):
            kwargs["command"] = kwargs["command"].model_copy(update={"indexable": True})
            return super().save_source_policy_in_transaction(**kwargs)

    with monkeypatch.context() as setup:
        setup.setattr(fixtures, "PublicationService", IndexablePublisher)
        owner, edition, message, lease = _admit(editorial_client)
    _executor(editorial_client, edition).execute(message, lease)
    now = edition.window_end + timedelta(hours=2)
    path = f"/reports/daily/{edition.key}"
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = PublicationApplicationService(
            session, origin="https://hotkey.example", indexing_enabled=True
        )
        assert service.edition(owner_id=owner, kind="daily", key=edition.key, now=now).indexable
        assert service.edition_catalogue(owner_id=owner, kind="daily", now=now).entries[0].indexable
        assert service.edition_navigation(
            owner_id=owner, kind="daily", key=edition.key, now=now
        ).current.indexable
        assert (
            service.daily_calendar(owner_id=owner, month=edition.key[:7], now=now)
            .entries[0]
            .indexable
        )
        assert path in service.sitemap_collection_shard(
            owner_id=owner, collection="reports", shard=0, now=now
        )
        assert "/sitemaps/reports-0.xml" in service.sitemap(owner_id=owner, now=now)
        session.rollback()
    with sessions.begin() as session:
        assert read_indexable_path_eligibilities_in_transaction(
            session, owner_id=owner, paths=[path], now=now
        ) == {path: True}
        revisions = session.scalar(text("SELECT count(*) FROM publication_revisions"))
        PublicationService(session, indexing_enabled=True).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=now,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                indexable=False,
                license_name="受控许可",
                reason="来源索引许可收紧",
            ),
        )
        assert session.scalar(text("SELECT count(*) FROM publication_revisions")) == revisions
        assert read_indexable_path_eligibilities_in_transaction(
            session, owner_id=owner, paths=[path], now=now
        ) == {path: False}
        assert path not in PublicationApplicationService(
            session, indexing_enabled=True
        ).sitemap_collection_shard(owner_id=owner, collection="reports", shard=0, now=now)
        catalogue = PublicationApplicationService(session, indexing_enabled=True).edition_catalogue(
            owner_id=owner, kind="daily", now=now
        )
        assert not catalogue.entries or not catalogue.entries[0].indexable
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5


def test_public_catalogue_streams_past_500_failed_keys_and_never_revives_old_revision(
    editorial_client: TestClient,
) -> None:
    from copy import deepcopy
    from datetime import date

    from reports.edition_models import ReportEdition
    from reports.edition_reading import load_current_edition_in_transaction
    from reports.edition_rules import period_window

    owner, edition, message, lease = _admit(editorial_client)
    _executor(editorial_client, edition).execute(message, lease)
    now = edition.window_end + timedelta(hours=2)
    sessions = editorial_client.app.state.session_factory
    base_day = date.fromisoformat(edition.key)
    yesterday = (base_day - timedelta(days=1)).isoformat()
    hidden_key = (base_day - timedelta(days=2)).isoformat()
    oldest = (base_day - timedelta(days=700)).isoformat()
    with sessions.begin() as session:
        original = session.get(ReportEdition, edition.id)
        assert original is not None
        template = {
            column.name: deepcopy(getattr(original, column.name))
            for column in ReportEdition.__table__.columns
        }

        def seed(key: str, *, status: str = "complete", revision: int = 1):
            values = deepcopy(template)
            start, end = period_window("daily", key)
            values.update(
                id=uuid4(),
                operation_id=uuid4(),
                period_key=key,
                revision=revision,
                window_start=start,
                window_end=end,
                cutoff_at=end,
                job_id=None,
                ai_call_id=None,
                status=status,
                generator="template",
                created_at=now - timedelta(seconds=1),
                updated_at=now - timedelta(seconds=1),
                reason="受控固定刊期归档; 不调用模型",
            )
            if status != "complete":
                values.update(content=None, body_markdown=None, failure_code="controlled_missing")
            session.add(ReportEdition(**values))

        for key in (yesterday, hidden_key, oldest):
            seed(key)
        seed(hidden_key, status="queued", revision=2)
        for offset in range(10, 560):
            seed((base_day - timedelta(days=offset)).isoformat(), status="failed")
    with sessions.begin() as session:
        service = PublicationApplicationService(session)
        first = service.edition_catalogue(owner_id=owner, kind="daily", limit=1, now=now)
        assert [entry.key for entry in first.entries] == [edition.key]
        assert first.next_before_key == edition.key
        second = service.edition_catalogue(
            owner_id=owner, kind="daily", before_key=first.next_before_key, limit=1, now=now
        )
        assert [entry.key for entry in second.entries] == [yesterday]
        assert second.next_before_key == yesterday
        third = service.edition_catalogue(
            owner_id=owner, kind="daily", before_key=second.next_before_key, limit=1, now=now
        )
        assert [entry.key for entry in third.entries] == [oldest] and third.next_before_key is None
        navigation = service.edition_navigation(
            owner_id=owner, kind="daily", key=yesterday, now=now
        )
        assert navigation.current.key == yesterday
        assert navigation.previous.key == oldest and navigation.next.key == edition.key
        month = edition.key[:7]
        calendar = service.daily_calendar(owner_id=owner, month=month, now=now)
        assert {entry.key for entry in calendar.entries} == {
            key for key in (edition.key, yesterday, oldest) if key.startswith(month)
        }
        assert hidden_key not in {entry.key for entry in calendar.entries}
        assert (
            load_current_edition_in_transaction(
                session, owner_id=owner, kind="daily", key=hidden_key, now=now
            )
            is None
        )
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5
        assert session.scalar(text("SELECT count(*) FROM report_editions")) == 555
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=now,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="isolated",
                license_name="撤回许可",
                reason="当前归档所有参考撤回",
            ),
        )
    with sessions() as session:
        service = PublicationApplicationService(session)
        assert service.edition_catalogue(owner_id=owner, kind="daily", now=now).entries == []
        assert service.daily_calendar(owner_id=owner, month=edition.key[:7], now=now).entries == []
        nav = service.edition_navigation(owner_id=owner, kind="daily", key=yesterday, now=now)
        assert nav.current is None and nav.previous is None and nav.next is None
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5
        assert session.scalar(text("SELECT count(*) FROM report_editions")) == 555
