from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import ModuleType
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client

from publication.reading import (
    PublicationReadingService,
    full_text_grant_in_transaction,
    list_report_candidates_in_transaction,
    validate_report_candidates_in_transaction,
)
from publication.schemas import FrozenPublicationReference, SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    _freeze_publication_clock(monkeypatch, request.module)
    yield from _editorial_client.__wrapped__()


def _freeze_publication_clock(monkeypatch: pytest.MonkeyPatch, test_module: ModuleType) -> datetime:
    """Use one per-test clock for imported fixtures and fixed publication cutoffs."""
    import tests.integration.test_content_records as records
    import tests.integration.test_content_search as search
    import tests.integration.test_editorial_execution as editorial
    import tests.integration.test_publication as publication

    now = datetime.now(UTC)

    class FixtureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)

    # Imports happen at collection time; a full suite may reach these fixtures minutes later.
    # Freezing seed timestamps too keeps expiry and snapshot assertions on the same clock.
    monkeypatch.setattr(records, "datetime", FixtureDateTime)
    monkeypatch.setattr(search, "datetime", FixtureDateTime)
    for module in (editorial, publication, test_module):
        if hasattr(module, "NOW"):
            monkeypatch.setattr(module, "NOW", now)
    return now


def test_publication_gates_fixed_reports_and_permission_revocation_without_rewriting(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session, indexing_enabled=True)
        policy = service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                site_fulltext=True,
                indexable=True,
                license_name="受控许可",
                reason="公开许可测试",
            ),
            now=NOW,
        )
        first = service.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        assert first and first.changed and first.ledger == "upsert"
        replay = service.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        assert replay and not replay.changed and replay.revision == first.revision
    with sessions.begin() as session:
        reader = PublicationReadingService(session, indexing_enabled=True)
        assert not reader.items_in_transaction(owner_id=owner, now=NOW, selected=True).items
        detail = reader.detail_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)
        assert detail and detail.site_fulltext and not detail.syndicate_fulltext
        assert detail.body and detail.body.original
        assert not list_report_candidates_in_transaction(
            session,
            owner_id=owner,
            start=NOW - timedelta(days=1),
            end=NOW + timedelta(days=1),
            now=NOW,
        )
    later = NOW + timedelta(seconds=181)
    with sessions.begin() as session:
        candidates = list_report_candidates_in_transaction(
            session,
            owner_id=owner,
            start=NOW - timedelta(days=1),
            end=NOW + timedelta(days=1),
            now=later,
        )
        assert len(candidates) == 1
        ref = FrozenPublicationReference.model_validate(candidates[0].model_dump())
        assert validate_report_candidates_in_transaction(
            session, owner_id=owner, references=(ref,), now=later
        ).valid
        grant = full_text_grant_in_transaction(
            session,
            owner_id=owner,
            content_id=run.content_id,
            content_version_id=run.content_version_id,
            policy_revision=policy.revision,
            now=later,
        )
        assert grant.granted and grant.body
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=later,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                license_name="摘要许可",
                reason="撤销全文许可",
            ),
        )
    with sessions.begin() as session:
        detail = PublicationReadingService(session).detail_in_transaction(
            owner_id=owner, content_id=run.content_id, now=later
        )
        assert detail and detail.body is None and not detail.site_fulltext
        assert not validate_report_candidates_in_transaction(
            session, owner_id=owner, references=(ref,), now=later
        ).valid
        assert not full_text_grant_in_transaction(
            session,
            owner_id=owner,
            content_id=run.content_id,
            content_version_id=run.content_version_id,
            policy_revision=1,
            now=later,
        ).granted
        assert session.execute(text("SELECT revision FROM publication_records")).scalar_one() == 1
    with sessions.begin() as session:
        session.execute(
            text("UPDATE evidence_resources SET expires_at=collected_at+interval '1 second'")
        )
    with sessions.begin() as session:
        assert (
            PublicationReadingService(session).detail_in_transaction(
                owner_id=owner, content_id=run.content_id, now=later
            )
            is None
        )
        service = PublicationService(session)
        result = service.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=later
        )
        assert result and result.visibility == "withdrawn" and result.ledger == "remove"
        repeat = service.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=later
        )
        assert repeat and not repeat.changed


def _manual_posts(client: TestClient, count: int):
    from tests.integration.test_content_search import _seed_posts
    from tests.integration.test_editorial_execution import _source

    from analysis.editorial_schemas import EditorialOverrideInput, EditorialRunInput
    from analysis.editorial_services import EditorialService

    owner, _, posts = _seed_posts(client, [(f"条目{i}", f"条目{i} 原始正文") for i in range(count)])
    _source(client, owner)
    for index, post in enumerate(posts):
        version = post.latest_observation.content_version
        assert version is not None
        with client.app.state.session_factory() as session:
            service = EditorialService(session, clock=lambda: NOW)
            run = service.request_run(
                owner_id=owner,
                content_id=post.id,
                source_key="x",
                command=EditorialRunInput(operation_id=uuid4(), content_version_id=version.id),
            )
            service.override(
                owner_id=owner,
                run_id=run.id,
                command=EditorialOverrideInput(
                    operation_id=uuid4(),
                    expected_manual_version=0,
                    selected=True,
                    title_zh=f"条目{index}",
                    summary_zh=f"条目{index} 人工摘要",
                    reason="受控人工测试",
                ),
            )
    with client.app.state.session_factory.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                site_fulltext=True,
                license_name="受控许可",
                reason="许可测试",
            ),
            now=NOW,
        )
    return owner, posts


def test_selected_watermark_never_leaps_pending_and_old_upsert_becomes_remove(
    editorial_client: TestClient,
) -> None:
    from core.errors import ApplicationError
    from publication.schemas import PublicationOverrideInput

    owner, posts = _manual_posts(editorial_client, 2)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        first = service.publish_in_transaction(owner_id=owner, content_id=posts[0].id, now=NOW)
        second = service.publish_in_transaction(
            owner_id=owner, content_id=posts[1].id, now=NOW, released_at=NOW - timedelta(hours=1)
        )
        assert first and second
    with sessions.begin() as session:
        reader = PublicationReadingService(session)
        epoch, watermark = reader.effective_sequence_in_transaction(owner_id=owner, now=NOW)
        assert watermark == 0
        assert reader.selected_snapshot_in_transaction(owner_id=owner, now=NOW).items == []
        assert (
            reader.selected_changes_in_transaction(
                owner_id=owner, epoch=epoch, since=0, now=NOW
            ).changes
            == []
        )
        # A different owner receives no ledger/material, and cursors do not grant access.
        assert reader.selected_snapshot_in_transaction(owner_id=uuid4(), now=NOW).items == []
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[0].id,
            now=NOW,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="summary-only",
                reason="限制披露",
            ),
        )
    with sessions.begin() as session:
        reader = PublicationReadingService(session)
        assert reader.effective_sequence_in_transaction(owner_id=owner, now=NOW) == (epoch, 3)
        changes = reader.selected_changes_in_transaction(
            owner_id=owner, epoch=epoch, since=0, now=NOW, limit=1
        )
        assert changes.changes[0].operation == "remove" and changes.changes[0].item is None
        assert changes.sequence == 1 and changes.next_cursor
        continued = reader.selected_changes_in_transaction(
            owner_id=owner, epoch=epoch, since=1, now=NOW
        )
        assert [change.operation for change in continued.changes] == ["upsert", "remove"]
        restricted = reader.detail_in_transaction(owner_id=owner, content_id=posts[0].id, now=NOW)
        assert restricted and restricted.body is None and restricted.reason is None
        assert restricted.tags == [] and not restricted.markdown_available
        snapshot = reader.selected_snapshot_in_transaction(owner_id=owner, now=NOW)
        assert [item.id for item in snapshot.items] == [posts[1].id]
    with sessions.begin() as session:
        PublicationService(session).reset_sync_epoch_in_transaction(owner_id=owner, now=NOW)
    with (
        sessions.begin() as session,
        pytest.raises(ApplicationError, match="publication_epoch_conflict"),
    ):
        PublicationReadingService(session).selected_changes_in_transaction(
            owner_id=owner, epoch=epoch, since=3, now=NOW
        )
    with sessions.begin() as session:
        rebuilt = PublicationReadingService(session).selected_snapshot_in_transaction(
            owner_id=owner, now=NOW, limit=10
        )
        assert rebuilt.epoch != epoch
        assert [item.id for item in rebuilt.items] == [posts[1].id]


def test_republish_cancellation_commits_domain_state_then_existing_job_acks_cancel(
    editorial_client: TestClient,
) -> None:
    from datetime import UTC, datetime

    from jobs.execution import JobExecutionService, MessageReference
    from jobs.schemas import JobAcceptedMessage
    from jobs.services import JOB_ACCEPTED_TOPIC, JobService
    from publication.application import PublicationApplicationService
    from publication.execution import PublicationRepublishExecutor
    from publication.schemas import RepublishInput

    owner, _posts = _manual_posts(editorial_client, 1)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        run = PublicationApplicationService(session).republish(
            owner_id=owner,
            source_key="x",
            command=RepublishInput(operation_id=uuid4(), expected_policy_revision=1),
        )
    at = datetime.now(UTC) + timedelta(seconds=1)
    with sessions() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        execution = JobExecutionService(session, lease_seconds=30, clock=lambda: at)
        lease = execution.acquire(job_id=run.job_id, worker_id="publication-cancel-test")
        JobService(session, clock=lambda: at).request_cancel(owner_id=owner, job_id=run.job_id)
    result = PublicationRepublishExecutor(sessions, clock=lambda: at).execute(
        message, lease, cancelled=lambda: True
    )
    assert result is None
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: at).complete(
            lease,
            message=MessageReference(message.message_id, JOB_ACCEPTED_TOPIC, 0, 0),
            completion=result,
        )
    with sessions.begin() as session:
        assert (
            session.execute(text("SELECT status FROM publication_republish_runs")).scalar_one()
            == "cancelled"
        )
        assert (
            session.execute(
                text("SELECT status FROM jobs WHERE id=:job"), {"job": run.job_id}
            ).scalar_one()
            == "cancelled"
        )
        assert session.execute(text("SELECT count(*) FROM publication_records")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM processed_messages")).scalar_one() == 1


def test_republish_admission_outbox_restart_and_unpublished_completed_material(
    editorial_client: TestClient,
) -> None:
    from jobs.execution import JobExecutionService
    from jobs.schemas import JobAcceptedMessage, JobStatus
    from publication.application import PublicationApplicationService
    from publication.execution import PublicationRepublishExecutor
    from publication.schemas import RepublishInput

    owner, _posts = _manual_posts(editorial_client, 105)
    sessions = editorial_client.app.state.session_factory
    command = RepublishInput(operation_id=uuid4(), expected_policy_revision=1)
    with sessions() as session:
        service = PublicationApplicationService(session)
        run = service.republish(owner_id=owner, source_key="x", command=command)
        replay = service.republish(owner_id=owner, source_key="x", command=command)
        assert replay == run
    with sessions.begin() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
                {"job": run.job_id},
            ).scalar_one()
            == 1
        )
    from datetime import UTC, datetime

    execution_at = datetime.now(UTC) + timedelta(seconds=1)
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: execution_at).acquire(
            job_id=run.job_id, worker_id="publication-controlled"
        )
    calls = []

    def interrupt(sequence, checkpoint):
        calls.append((sequence, checkpoint))
        raise RuntimeError("controlled restart after business page commit")

    executor = PublicationRepublishExecutor(sessions, clock=lambda: execution_at)
    with pytest.raises(RuntimeError, match="controlled restart"):
        executor.execute(message, lease, checkpoint=interrupt)
    with sessions.begin() as session:
        assert session.execute(text("SELECT count(*) FROM publication_records")).scalar_one() == 100
    result = executor.execute(message, lease)
    assert result.status == JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    with sessions.begin() as session:
        assert session.execute(
            text("SELECT count(*),count(DISTINCT content_id) FROM publication_records")
        ).one() == (105, 105)
        assert (
            session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 105
        )
        assert session.execute(
            text("SELECT status,processed_count FROM publication_republish_runs")
        ).one() == ("completed", 105)
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
        reader = PublicationReadingService(session)
        later = execution_at + timedelta(seconds=181)
        page = reader.items_in_transaction(owner_id=owner, now=later, limit=20, selected=True)
        assert len(page.items) == 20 and page.next_cursor
        nextpage = reader.items_in_transaction(
            owner_id=owner, now=later, limit=20, selected=True, cursor=page.next_cursor
        )
        assert len(nextpage.items) == 20 and not set(item.id for item in page.items) & set(
            item.id for item in nextpage.items
        )
        public = PublicationApplicationService(session)
        searched = public.items(owner_id=owner, q="条目", mode="all", limit=10, now=later)
        assert len(searched.items) == 10 and searched.next_cursor
        again = public.items(
            owner_id=owner, q="条目", mode="all", limit=10, now=later, cursor=searched.next_cursor
        )
        assert len(again.items) == 10 and not set(item.id for item in searched.items) & set(
            item.id for item in again.items
        )


def test_authenticated_http_mcp_formats_and_operator_permissions_make_no_writes(
    editorial_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xml.etree import ElementTree

    owner, posts = _manual_posts(editorial_client, 1)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        PublicationService(session).publish_in_transaction(
            owner_id=owner, content_id=posts[0].id, now=NOW, released_at=NOW - timedelta(minutes=1)
        )
    paths = [
        "/api/publication/items",
        "/api/publication/selected/snapshot",
        "/api/publication/hot",
        "/feed.xml",
        "/feed/full.xml",
        "/feed/all.xml",
        "/feed/category/ai-models.xml",
        "/feed/daily.xml",
        "/feed/weekly.xml",
        "/feed/monthly.xml",
        "/llms.txt",
        "/agent.md",
        "/robots.txt",
        "/sitemap.xml",
        "/selected.md",
        f"/items/{posts[0].id}.md",
    ]
    with sessions.begin() as session:
        before = session.execute(text("SELECT count(*) FROM jobs")).scalar_one()
    for path in paths:
        response = editorial_client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers.get("x-request-id")
        if path.startswith("/feed") or path == "/sitemap.xml":
            ElementTree.fromstring(response.text)
    thirdparty = editorial_client.get(f"/api/publication/items/{posts[0].id}")
    site = editorial_client.get(f"/api/publication/items/{posts[0].id}/site")
    assert thirdparty.status_code == 200 and thirdparty.json()["body"] is None
    assert site.status_code == 200 and site.json()["body"]["original"]
    assert editorial_client.put("/api/publication/sources/x/policy", json={}).status_code == 401
    assert editorial_client.get("/api/publication/policies").status_code == 401
    with monkeypatch.context() as disabled_operator:
        disabled_operator.setattr(
            editorial_client.app.state,
            "settings",
            editorial_client.app.state.settings.model_copy(update={"operator_token": None}),
        )
        assert editorial_client.put("/api/publication/sources/x/policy", json={}).status_code == 403
        assert editorial_client.get("/api/publication/policies").status_code == 403
    assert editorial_client.get("/mcp").status_code == 405
    headers = {
        "Accept": "application/json, text/event-stream",
        "Origin": editorial_client.app.state.settings.web_base_url,
    }
    initialized = editorial_client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    assert (
        initialized.status_code == 200
        and initialized.json()["result"]["protocolVersion"] == "2025-06-18"
    )
    tools = editorial_client.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert tools.status_code == 200 and len(tools.json()["result"]["tools"]) == 5
    called = editorial_client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "hotkey_get_latest", "arguments": {}},
        },
    )
    assert (
        called.status_code == 200
        and len(called.json()["result"]["structuredContent"]["items"]) == 1
    )
    assert (
        editorial_client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        ).status_code
        == 202
    )
    assert (
        editorial_client.post(
            "/mcp",
            headers={**headers, "Origin": "https://attacker.example"},
            json={"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ).status_code
        == 400
    )
    assert (
        editorial_client.post(
            "/mcp",
            headers={"Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ).status_code
        == 406
    )
    assert editorial_client.get(f"/items/{posts[0].id}.jsonld").status_code == 404
    assert "Disallow: /" in editorial_client.get("/robots.txt").text
    with sessions.begin() as session:
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == before
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM publication_revisions")).scalar_one() == 1
