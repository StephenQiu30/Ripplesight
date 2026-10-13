"""Actual writer to guarded public-board projection and lifecycle proof in isolated PG."""

from datetime import UTC, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_hotlist_persistence import (
    _accept,
    _execute,
    _message,
    _page,
    _ranked_page,
)
from tests.integration.test_hotlist_persistence import (
    runtime as runtime,
)

from content.hotlist import HotlistService
from content.hotlist_cleanup import HotlistSnapshotCleanup
from content.hotlist_material import entry_resource_id
from content.hotlist_reading import read_board_in_transaction
from content.hotlist_schemas import BOARD_FIELDS, ENTRY_FIELDS
from content.models import HotlistSnapshot
from core.errors import ApplicationError
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService
from jobs.execution import JobCompletion, JobExecutionService, MessageReference
from jobs.schemas import JobStatus
from publication.hotlist_schemas import HotlistPublicationGrant
from publication.hotlists import public_platform_trends_in_transaction
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService
from sources.contracts import HotlistEntry


def grant(runtime, now, **changes):
    values = dict(
        enabled=True,
        source_policy_version=1,
        board_fields=sorted(BOARD_FIELDS),
        entry_fields=sorted(ENTRY_FIELDS),
        license_name="Controlled public license",
        license_url="https://example.com/license",
        reviewed_at=runtime.due_at - timedelta(seconds=1),
        expires_at=now + timedelta(days=1),
        max_age_seconds=3600,
    )
    values.update(changes)
    with runtime.sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=runtime.owner_id,
            actor_id=runtime.owner_id,
            source_key="hotlist_weibo",
            now=now,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="hot_signal",
                license_name="private configuration",
                reason="Controlled test grant",
                hotlist_publication=HotlistPublicationGrant(**values),
            ),
        )


def read(runtime, now):
    with runtime.sessions.begin() as session:
        return public_platform_trends_in_transaction(session, owner_id=runtime.owner_id, now=now)[0]


def seed(runtime, entries=2):
    at = runtime.due_at + timedelta(minutes=2)
    job = _accept(runtime, runtime.due_at)
    _execute(runtime, job, _page(at, entries=entries))
    with runtime.sessions.begin() as session:
        identifier = session.scalar(select(HotlistSnapshot.id))
        board = read_board_in_transaction(
            session, owner_id=runtime.owner_id, snapshot_id=identifier, now=at
        )
        assert len(board.items) == entries
    return at, identifier, job


def test_writer_proof_and_default_public_denial(runtime):
    now, identifier, _ = seed(runtime)
    view = read(runtime, now)
    assert view.state == "not_configured" and view.items == []
    assert view.snapshot_id is None and view.observed_at is None and view.entry_count is None
    grant(runtime, now)
    view = read(runtime, now)
    assert view.state == "partial" and view.entry_count == 2 and view.snapshot_id == identifier
    assert view.license_url == "https://example.com/license"
    assert view.source_updated_at is None and view.items[0].native_rank is None
    assert view.rank_basis == "feed_position" and view.comparison_reason == "no_baseline"


@pytest.mark.parametrize("entries,expected", [(0, "empty"), (1, "partial")])
def test_genuine_empty_is_distinct_from_missing(runtime, entries, expected):
    now, _, _ = seed(runtime, entries)
    grant(runtime, now)
    view = read(runtime, now)
    assert view.state == expected and view.entry_count == entries


@pytest.mark.parametrize(
    "mode", ["deleted", "expired", "legacy", "tampered", "naive", "connection", "interval"]
)
def test_one_unreadable_position_or_proof_denies_whole_board(runtime, mode):
    now, identifier, _ = seed(runtime)
    grant(runtime, now)
    with runtime.sessions() as session:
        if mode == "deleted":
            LifecycleService(session, clock=lambda: now).request_deletion(
                owner_id=runtime.owner_id,
                operation_id=uuid4(),
                resource_type="hotlist_entry",
                resource_id=entry_resource_id(identifier, 2),
                reason=DeletionReason.USER_REQUEST,
            )
        else:
            with session.begin():
                row = session.get(HotlistSnapshot, identifier)
                if mode == "expired":
                    session.execute(
                        text("UPDATE evidence_resources SET expires_at=:now WHERE resource_id=:id"),
                        {"now": now, "id": entry_resource_id(identifier, 2)},
                    )
                elif mode == "legacy":
                    row.provenance = None
                elif mode == "tampered":
                    session.execute(
                        text("UPDATE hotlist_entries SET title='tampered' WHERE rank=2")
                    )
                else:
                    from content.hotlist_material import digest

                    value = dict(row.provenance)
                    if mode == "naive":
                        value["received_at"] = now.replace(tzinfo=None).isoformat()
                    if mode == "connection":
                        value["connection_id"] = str(uuid4())
                    if mode == "interval":
                        value["interval_seconds"] = 3600
                    payload = {k: v for k, v in value.items() if k != "digest"}
                    payload.update(
                        observed_at=row.observed_at.astimezone(UTC).isoformat(),
                        entry_count=row.entry_count,
                    )
                    value["digest"] = digest(payload)
                    row.provenance = value
    view = read(runtime, now)
    assert view.state == "unavailable" and view.entry_count is None and view.items == []
    with runtime.sessions() as session, pytest.raises(ApplicationError):
        HotlistService(session, clock=lambda: now).get_historical(
            owner_id=runtime.owner_id, source_key="hotlist_weibo", snapshot_id=identifier, limit=1
        )


def test_newer_due_and_deleted_latest_never_fall_back(runtime):
    now, identifier, _ = seed(runtime)
    grant(runtime, now)
    due = runtime.due_at + timedelta(minutes=30)
    job = _accept(runtime, due)
    assert read(runtime, due + timedelta(seconds=3)).state == "collecting"
    second = due + timedelta(minutes=2)
    lease = _execute(runtime, job, _page(second, entries=1))
    message = _message(runtime, job)
    with runtime.sessions() as session:
        JobExecutionService(session, lease_seconds=75, clock=lambda: second).complete(
            lease,
            message=MessageReference(
                message_id=message.message_id,
                topic="hotkey.jobs.accepted.v2",
                partition=0,
                offset=1,
            ),
            completion=JobCompletion(status=JobStatus.SUCCEEDED),
        )
    with runtime.sessions.begin() as session:
        latest = session.scalar(select(HotlistSnapshot).where(HotlistSnapshot.job_id == job))
        latest_id = latest.id
    with runtime.sessions() as session:
        LifecycleService(session, clock=lambda: second).request_deletion(
            owner_id=runtime.owner_id,
            operation_id=uuid4(),
            resource_type="hotlist_entry",
            resource_id=entry_resource_id(latest_id, 1),
            reason=DeletionReason.USER_REQUEST,
        )
    assert read(runtime, second).state == "unavailable"
    HotlistSnapshotCleanup(runtime.sessions, clock=lambda: second)(str(latest_id))
    HotlistSnapshotCleanup(runtime.sessions, clock=lambda: second)(str(latest_id))
    view = read(runtime, second)
    assert view.state == "failed" and view.items == []
    with runtime.sessions.begin() as session:
        assert session.get(HotlistSnapshot, identifier) is not None
        assert session.get(HotlistSnapshot, latest_id) is None


def test_stale_and_permission_expiry_have_no_items(runtime):
    now, _, _ = seed(runtime)
    grant(runtime, now, max_age_seconds=60)
    assert read(runtime, now + timedelta(seconds=61)).state == "stale"
    denied = read(runtime, now + timedelta(days=1))
    assert denied.state == "not_configured" and denied.snapshot_id is None


def test_cleanup_requires_original_deletion_registration(runtime):
    now, identifier, _ = seed(runtime)
    with pytest.raises(ValueError, match="registered deletion"):
        HotlistSnapshotCleanup(runtime.sessions, clock=lambda: now)(str(identifier))
    assert read(runtime, now).state == "not_configured"


def test_duplicate_and_tracking_urls_do_not_invent_movements(runtime):
    now = runtime.due_at + timedelta(minutes=2)
    _execute(
        runtime,
        _accept(runtime, runtime.due_at),
        _ranked_page(
            now,
            (
                HotlistEntry(rank=1, title="A", url="https://example.com/a"),
                HotlistEntry(rank=2, title="A", url="https://example.com/a#top"),
                HotlistEntry(rank=3, title="B", url="https://example.com/b?utm_source=rss"),
            ),
        ),
    )
    grant(runtime, now)
    due = runtime.due_at + timedelta(minutes=30)
    _execute(
        runtime,
        _accept(runtime, due),
        _ranked_page(
            due + timedelta(minutes=2),
            (
                HotlistEntry(rank=1, title="A", url="https://example.com/a"),
                HotlistEntry(rank=2, title="B", url="https://example.com/b"),
                HotlistEntry(rank=3, title="A", url="https://example.com/a#top"),
            ),
        ),
    )
    view = read(runtime, due + timedelta(minutes=2))
    assert view.comparison_reason == "comparable"
    assert view.items[0].rank_delta is None and view.items[2].rank_delta is None
    assert view.items[1].rank_delta == 1


def test_public_http_uses_same_snapshot_without_writes_or_source_requests(runtime, monkeypatch):
    import os
    from datetime import datetime

    from fastapi.testclient import TestClient
    from sqlalchemy import event

    import publication.application as application
    from core.config import Settings
    from main import create_app

    now, identifier, _ = seed(runtime)
    grant(runtime, now)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(application, "datetime", Clock)
    app = create_app(
        Settings(
            environment="test",
            database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
            public_publication_owner_id=runtime.owner_id,
            log_level="WARNING",
        )
    )
    with TestClient(app) as client:
        engine = app.state.session_factory.kw["bind"]
        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lower().strip())

        event.listen(engine, "before_cursor_execute", capture)
        result = client.get("/api/publication/home")
        event.remove(engine, "before_cursor_execute", capture)
    assert result.status_code == 200, result.text
    board = result.json()["platform_trends"][0]
    assert board["snapshot_id"] == str(identifier) and len(board["items"]) == 2
    assert len(result.json()["platform_trends"]) == 6
    assert not any(sql.startswith(("insert", "update", "delete")) for sql in statements)


def test_no_snapshot_and_source_version_mismatch(runtime):
    now = runtime.due_at + timedelta(minutes=2)
    grant(runtime, now)
    assert read(runtime, now).state == "no_snapshot"
    with runtime.sessions.begin() as session:
        session.execute(text("UPDATE source_access_policies SET policy_version=policy_version+1"))
    view = read(runtime, now)
    assert view.state == "not_configured" and view.reasons == ["policy_changed"]
    assert view.items == []


def test_history_extra_unreadable_board_cannot_control_cursor(runtime):
    _now, identifier, _ = seed(runtime)
    due = runtime.due_at + timedelta(minutes=30)
    _execute(runtime, _accept(runtime, due), _page(due + timedelta(minutes=2), entries=1))
    with runtime.sessions() as session:
        LifecycleService(session, clock=lambda: due + timedelta(minutes=2)).request_deletion(
            owner_id=runtime.owner_id,
            operation_id=uuid4(),
            resource_type="hotlist_entry",
            resource_id=entry_resource_id(identifier, 2),
            reason=DeletionReason.USER_REQUEST,
        )
    with runtime.sessions() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        HotlistService(session, clock=lambda: due + timedelta(minutes=2)).list_history(
            owner_id=runtime.owner_id, source_key="hotlist_weibo", limit=1
        )


def test_entry_withdrawal_stops_derived_reads_before_cleanup_and_keeps_other_job(runtime):
    from tests.integration.test_hotlist_persistence import _add_active_topics

    from content.models import ContentObservation
    from content.services import ContentService

    (topic,) = _add_active_topics(runtime, (("AI topic", "AI"),))
    first = _accept(runtime, runtime.due_at)
    at = runtime.due_at + timedelta(minutes=2)
    page = _ranked_page(
        at, (HotlistEntry(rank=1, title="AI headline", url="https://example.com/shared"),)
    )
    _execute(runtime, first, page)
    due = runtime.due_at + timedelta(minutes=30)
    second = _accept(runtime, due)
    now = due + timedelta(minutes=2)
    _execute(runtime, second, page.model_copy(update={"observed_at": now}))
    with runtime.sessions.begin() as session:
        identifier = session.scalar(
            select(HotlistSnapshot.id).where(HotlistSnapshot.job_id == first)
        )
        other = session.scalar(
            select(ContentObservation.id).where(ContentObservation.job_id == second)
        )
    with runtime.sessions() as session:
        LifecycleService(session, clock=lambda: now).request_deletion(
            owner_id=runtime.owner_id,
            operation_id=uuid4(),
            resource_type="hotlist_entry",
            resource_id=entry_resource_id(identifier, 1),
            reason=DeletionReason.USER_REQUEST,
        )
        visible, _ = ContentService(session, clock=lambda: now).list_contents(
            owner_id=runtime.owner_id, topic_id=topic, cursor=None, limit=10
        )
        assert len(visible) == 1 and visible[0].latest_observation.id == other
        service = HotlistService(session, clock=lambda: now)
        latest = service.get_latest(owner_id=runtime.owner_id, source_key="hotlist_weibo")
        fixed = service.get_historical(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            snapshot_id=latest.snapshot_id,
            limit=1,
        )
        for view in (latest, fixed):
            assert [
                (item.previous_rank, item.rank_delta, item.rank_change) for item in view.items
            ] == [(None, None, "unknown")]

    HotlistSnapshotCleanup(runtime.sessions, clock=lambda: now)(str(identifier))
    with runtime.sessions.begin() as session:
        assert session.get(ContentObservation, other) is not None
        assert (
            session.scalar(select(ContentObservation.id).where(ContentObservation.job_id == first))
            is None
        )


def test_cleanup_failure_rolls_back_material_but_never_restores_read_permission(
    runtime, monkeypatch
):
    import content.hotlist_cleanup as cleanup

    now, identifier, _ = seed(runtime)
    grant(runtime, now)
    with runtime.sessions() as session:
        LifecycleService(session, clock=lambda: now).request_deletion(
            owner_id=runtime.owner_id,
            operation_id=uuid4(),
            resource_type="hotlist_entry",
            resource_id=entry_resource_id(identifier, 1),
            reason=DeletionReason.USER_REQUEST,
        )
    original = cleanup.request_related_resource_deletions_in_transaction

    def failure(*args, **kwargs):
        raise RuntimeError("controlled cleanup failure")

    monkeypatch.setattr(cleanup, "request_related_resource_deletions_in_transaction", failure)
    with pytest.raises(RuntimeError, match="controlled cleanup failure"):
        HotlistSnapshotCleanup(runtime.sessions, clock=lambda: now)(str(identifier))
    with runtime.sessions.begin() as session:
        assert session.get(HotlistSnapshot, identifier) is not None
    assert read(runtime, now).state == "unavailable"
    monkeypatch.setattr(cleanup, "request_related_resource_deletions_in_transaction", original)
    HotlistSnapshotCleanup(runtime.sessions, clock=lambda: now)(str(identifier))
    assert read(runtime, now).items == []


def test_optional_public_fields_are_minimized_even_when_native_values_are_present(runtime):
    from content.hotlist_schemas import ENTRY_REQUIRED

    now = runtime.due_at + timedelta(minutes=2)
    page = _ranked_page(
        now,
        (
            HotlistEntry(
                rank=1,
                title="A",
                url="https://example.com/a",
                summary="private summary",
                heat="1000",
                heat_unit="views",
                native_id="native-a",
                native_rank=10,
                published_at=now,
            ),
        ),
    )
    page = page.model_copy(update={"source_updated_at": now})
    _execute(runtime, _accept(runtime, runtime.due_at), page)
    grant(runtime, now, entry_fields=sorted(ENTRY_REQUIRED))
    view = read(runtime, now)
    assert view.items[0].title == "A"
    assert view.items[0].summary is None and view.items[0].native_id is None
    assert view.items[0].native_rank is None and view.items[0].heat is None
    assert view.items[0].published_at is None


def test_available_requires_verified_source_time_and_all_native_fields(runtime):
    now = runtime.due_at + timedelta(minutes=2)
    page = _ranked_page(
        now,
        (
            HotlistEntry(
                rank=1,
                title="A",
                url="https://example.com/a",
                heat="1000",
                heat_unit="views",
                native_id="native-a",
                native_rank=10,
            ),
        ),
    )
    _execute(
        runtime,
        _accept(runtime, runtime.due_at),
        page.model_copy(update={"source_updated_at": now}),
    )
    grant(runtime, now)
    view = read(runtime, now)
    assert view.state == "available" and view.reasons == []
    assert view.items[0].native_rank == 10 and view.items[0].rank == 1


def test_metadata_only_observation_cannot_bypass_missing_job_source_context(runtime):
    from tests.integration.test_hotlist_persistence import _add_active_topics

    from content.models import ContentObservation
    from content.services import ContentService

    (topic,) = _add_active_topics(runtime, (("AI topic", "AI"),))
    job = _accept(runtime, runtime.due_at)
    now = runtime.due_at + timedelta(minutes=2)
    _execute(
        runtime,
        job,
        _ranked_page(now, (HotlistEntry(rank=1, title="AI", url="https://example.com/a"),)),
    )
    with runtime.sessions.begin() as session:
        observation = session.scalar(
            select(ContentObservation).where(ContentObservation.job_id == job)
        )
        observation.content_version_id = None
    with runtime.sessions() as session:
        service = ContentService(session, clock=lambda: now)
        values, _ = service.list_contents(
            owner_id=runtime.owner_id, topic_id=topic, cursor=None, limit=10
        )
        assert len(values) == 1 and values[0].latest_observation.content_version is None
    with runtime.sessions.begin() as session:
        session.execute(
            text("UPDATE jobs SET source_capability=NULL,source_key=NULL WHERE id=:job"),
            {"job": job},
        )
    with runtime.sessions() as session:
        values, _ = ContentService(session, clock=lambda: now).list_contents(
            owner_id=runtime.owner_id, topic_id=topic, cursor=None, limit=10
        )
        assert values == []
