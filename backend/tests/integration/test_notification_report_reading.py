from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import editorial_client as _editorial_client
from tests.integration.test_report_editions import _admit, _executor

from core.errors import ApplicationError
from jobs.schemas import JobStatus
from reports.edition_schemas import EditionCorrectionInput
from reports.edition_services import EditionService
from reports.notification_reading import (
    list_first_final_notification_editions_in_transaction,
    list_first_final_notification_reports_in_transaction,
    load_notification_edition_in_transaction,
    load_notification_report_in_transaction,
)
from reports.schemas import ReportView
from reports.services import ReportService


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


def _reports(client: TestClient) -> tuple[UUID, ReportView, ReportView, datetime]:
    owner, topic, _ = _seed_posts(client, [("first", "first body"), ("second", "second body")])
    now = datetime.now(UTC)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        service = ReportService(session, clock=lambda: now)
        args = {
            "owner_id": owner,
            "topic_id": topic,
            "window_start": now - timedelta(days=1),
            "window_end": now,
            "cutoff_at": now,
        }
        first = service.generate_daily_in_transaction(**args)
        revised = service.regenerate_daily_in_transaction(**args)
    assert len(first.input_manifest.content_version_ids) == 2
    return owner, first, revised, now


def test_topic_report_first_final_enable_time_owner_and_all_input_retention(
    editorial_client: TestClient,
) -> None:
    owner, first, revised, now = _reports(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        page = list_first_final_notification_reports_in_transaction(
            session, owner_id=owner, enabled_at=now - timedelta(seconds=1), now=now
        )
        assert [value.report_id for value in page.reports] == [first.id]
        assert page.reports[0].body_markdown and len(page.reports[0].fingerprint) == 64
        assert page.next_after_report_id is None
        assert not list_first_final_notification_reports_in_transaction(
            session,
            owner_id=owner,
            enabled_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=2),
        ).reports
        assert (
            load_notification_report_in_transaction(
                session, owner_id=uuid4(), report_id=first.id, version=first.version, now=now
            )
            is None
        )
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=first.id, version=revised.version, now=now
            )
            is None
        )
    # Losing one non-representative frozen observation invalidates the whole body.
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE evidence_resources SET expires_at=collected_at+interval '1 second' "
                "WHERE owner_id=:owner AND resource_id=:observation"
            ),
            {"owner": owner, "observation": first.input_manifest.observation_ids[-1]},
        )
    with sessions.begin() as session:
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=first.id, version=first.version, now=now
            )
            is None
        )
        assert not list_first_final_notification_reports_in_transaction(
            session, owner_id=owner, enabled_at=now - timedelta(seconds=1), now=now
        ).reports


def test_topic_report_current_field_permission_blocks_frozen_body(
    editorial_client: TestClient,
) -> None:
    owner, report, _, now = _reports(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=report.id, version=1, now=now
            )
            is not None
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET field_purposes=field_purposes-'body' "
                "WHERE owner_id=:owner"
            ),
            {"owner": owner},
        )
    with sessions.begin() as session:
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=report.id, version=1, now=now
            )
            is None
        )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ReportService(session, clock=lambda: now).get_report(
                owner_id=owner, report_id=report.id
            )


def test_edition_notifications_never_fall_back_to_first_revision_after_correction(
    editorial_client: TestClient,
) -> None:
    owner, edition, message, lease = _admit(editorial_client)
    assert (
        _executor(editorial_client, edition).execute(message, lease).status == JobStatus.SUCCEEDED
    )
    at = edition.window_end + timedelta(hours=2)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        page = list_first_final_notification_editions_in_transaction(
            session, owner_id=owner, enabled_at=at - timedelta(seconds=1), now=at
        )
        assert [item.edition_id for item in page.editions] == [edition.id]
    with sessions() as session:
        corrected = EditionService(session, clock=lambda: at).correct(
            owner_id=owner,
            actor_id=owner,
            edition_id=edition.id,
            command=EditionCorrectionInput(
                operation_id=uuid4(),
                expected_revision=1,
                title="人工复核刊期",
                lead="引用核对后修订。",
                highlights=[],
                themes=[],
                reason="通知历史版本边界",
            ),
        )
    with sessions.begin() as session:
        assert (
            load_notification_edition_in_transaction(
                session, owner_id=owner, edition_id=edition.id, revision=1, now=at
            )
            is None
        )
        assert (
            load_notification_edition_in_transaction(
                session, owner_id=owner, edition_id=corrected.id, revision=2, now=at
            )
            is not None
        )
        assert not list_first_final_notification_editions_in_transaction(
            session, owner_id=owner, enabled_at=at - timedelta(seconds=1), now=at
        ).editions
