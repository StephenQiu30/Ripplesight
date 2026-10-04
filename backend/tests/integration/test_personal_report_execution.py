"""Personal reports use independent jobs and exact frozen PostgreSQL facts."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import editorial_client as _editorial_client

from core.errors import ApplicationError
from jobs.schemas import JobAcceptedMessage
from reports.models import Report
from reports.notification_reading import load_notification_report_in_transaction
from reports.schemas import ReportKind
from reports.services import DailyReportExecutor, ReportService, previous_weekly_window


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


def _message(sessions, job_id: UUID) -> JobAcceptedMessage:
    with sessions() as session:
        row = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:id"),
            {"id": job_id},
        ).one()
        return JobAcceptedMessage.model_validate(
            {
                **row.payload,
                "schema_version": 2,
                "message_id": row.id,
                "event_type": row.event_type,
            }
        )


def test_due_reports_freeze_before_execution_without_readiness_or_daily_success(
    editorial_client: TestClient,
) -> None:
    owner, topic, posts = _seed_posts(editorial_client, [("one", "one"), ("two", "two")])
    sessions = editorial_client.app.state.session_factory
    now = datetime.now(UTC)
    monday = now.date() + timedelta(days=(7 - now.weekday()) % 7 or 7)
    due = datetime.combine(monday, datetime.min.time(), UTC) + timedelta(hours=1)
    start, _ = previous_weekly_window(due)
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE monitor_topic_versions SET match_any='[\"one\"]'::jsonb WHERE topic_id=:id"
            ),
            {"id": topic},
        )
        session.execute(
            text(
                "UPDATE monitor_topics SET readiness_status='pending_source_readiness', "
                "weekly_report_enabled=true WHERE id=:id"
            ),
            {"id": topic},
        )
        session.execute(
            text("UPDATE content_observations SET published_at=:at WHERE content_id=:id"),
            {"id": posts[0].id, "at": start + timedelta(hours=12)},
        )
        session.execute(
            text("UPDATE content_observations SET published_at=:at WHERE content_id=:id"),
            {"id": posts[1].id, "at": due - timedelta(hours=12)},
        )
        assert not ReportService(session, clock=lambda: due).enqueue_due_in_transaction(
            now=due - timedelta(seconds=1)
        )
        assert not ReportService(session, clock=lambda: due).enqueue_due_in_transaction(
            now=due + timedelta(minutes=5)
        )
    cutoff = due + timedelta(minutes=10)
    with sessions.begin() as session:
        jobs = ReportService(session, clock=lambda: cutoff).enqueue_due_in_transaction(now=cutoff)
        assert {job.kind for job in jobs} == {"report.daily", "report.weekly"}
        assert len({job.operation_id for job in jobs}) == 2
        repeated = ReportService(session, clock=lambda: cutoff).enqueue_due_in_transaction(
            now=cutoff
        )
        assert {job.id for job in repeated} == {job.id for job in jobs}
        drafts = list(session.execute(text("SELECT id,kind,input_manifest FROM reports")))
        assert len(drafts) == 2
        for draft in drafts:
            with pytest.raises(ApplicationError, match="resource_not_found"):
                ReportService(session, clock=lambda: cutoff).get_report(
                    owner_id=owner, report_id=draft.id
                )
    # Weekly can complete before the daily job; its missing dates remain frozen.
    weekly = next(job for job in jobs if job.kind == "report.weekly")
    executor = DailyReportExecutor(
        sessions,
        settings=editorial_client.app.state.settings,
        clock=lambda: cutoff + timedelta(minutes=3),
    )
    result = executor.execute(_message(sessions, weekly.id))
    with sessions.begin() as session:
        report = session.get(Report, result.report_id)
        assert report is not None and report.status == "final" and report.kind == "weekly"
        assert report.cutoff_at == cutoff
        assert len(report.data["pending_contents"]) == 2
        assert len(report.input_manifest["missing_daily_dates"]) == 7
        assert report.generator == "template"
        assert "周报" in report.body_markdown and "未分析材料" in report.body_markdown
        details = ReportService(session, clock=lambda: cutoff + timedelta(minutes=3)).get_report(
            owner_id=owner, report_id=report.id
        )
        assert len(details.citations) == 2
        with pytest.raises(ApplicationError):
            ReportService(session).get_report(owner_id=uuid4(), report_id=report.id)
    daily = next(job for job in jobs if job.kind == "report.daily")
    executor.execute(_message(sessions, daily.id))
    with sessions.begin() as session:
        frozen = session.get(Report, result.report_id)
        assert frozen is not None and len(frozen.input_manifest["missing_daily_dates"]) == 7
        assert not ReportService(session, clock=lambda: cutoff).enqueue_due_in_transaction(
            now=cutoff
        )
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0


def test_weekly_pins_daily_versions_and_rechecks_reference_permissions(
    editorial_client: TestClient,
) -> None:
    owner, topic, _posts = _seed_posts(editorial_client, [("one", "one"), ("two", "two")])
    sessions = editorial_client.app.state.session_factory
    now = datetime.now(UTC) + timedelta(seconds=1)
    start, end = previous_weekly_window(now)
    with sessions.begin() as session:
        session.execute(
            text("UPDATE content_observations SET published_at=:at"),
            {"at": start + timedelta(hours=12)},
        )
        service = ReportService(session, clock=lambda: now)
        daily = []
        for offset in range(7):
            day = start + timedelta(days=offset)
            daily.append(
                service.generate_daily_in_transaction(
                    owner_id=owner,
                    topic_id=topic,
                    window_start=day,
                    window_end=day + timedelta(days=1),
                    cutoff_at=now,
                )
            )
        weekly = service.generate_weekly_in_transaction(
            owner_id=owner, topic_id=topic, window_start=start, window_end=end, cutoff_at=now
        )
        assert len(weekly.input_manifest.daily_reports) == 7
        assert weekly.data.missing_daily_dates == ()
        assert weekly.data.daily_totals_match is True
    later = now + timedelta(minutes=1)
    with sessions.begin() as session:
        service = ReportService(session, clock=lambda: later)
        revised_daily = service.regenerate_daily_in_transaction(
            owner_id=owner,
            topic_id=topic,
            window_start=start,
            window_end=start + timedelta(days=1),
            cutoff_at=later,
        )
        assert revised_daily.version == 2
        revised_weekly = service.regenerate_weekly_in_transaction(
            owner_id=owner, topic_id=topic, window_start=start, window_end=end, cutoff_at=later
        )
        assert revised_weekly.input_manifest == weekly.input_manifest
        assert revised_weekly.data == weekly.data
        assert revised_weekly.cutoff_at == now
        assert revised_weekly.input_manifest.daily_reports[0].report_id == daily[0].id
        assert revised_weekly.input_manifest.daily_reports[0].version == 1
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=weekly.id, version=1, now=later
            )
            is not None
        )
        session.execute(text("UPDATE reports SET status='draft' WHERE id=:id"), {"id": daily[0].id})
        assert (
            load_notification_report_in_transaction(
                session, owner_id=owner, report_id=weekly.id, version=1, now=later
            )
            is None
        )
        with pytest.raises(ApplicationError):
            service.get_report(owner_id=owner, report_id=weekly.id)
        items, _ = service.list_reports(
            owner_id=uuid4(),
            topic_id=None,
            date_from=None,
            date_to=None,
            kind=ReportKind.WEEKLY,
            cursor=None,
            limit=20,
        )
        assert items == []
