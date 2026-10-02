# ruff: noqa: F811
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from tests.integration.test_content_records import _demo_scope
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from db.metadata import metadata
from jobs.execution import JobExecutionFailure, JobExecutionService, MessageReference
from jobs.models import Job, OutboxMessage
from jobs.operator_maintenance import republish_due_jobs_in_transaction
from jobs.schemas import BudgetPolicyInput, JobAcceptanceInput, JobObservationContext
from jobs.services import JobService, ResourceBudgetService
from operations.heartbeat import ProcessHeartbeatReporter
from operations.maintenance import (
    OperationsMaintenanceExecutor,
    enqueue_due_maintenance_in_transaction,
    read_maintenance_state,
)
from operations.models import OperatorAuditOperation, ProcessHeartbeat
from operations.schemas import AuditResolutionInput, MaintenanceInput
from operations.services import OperationsService
from operations.watchdog import run_watchdog_once


def _accept(client, owner, action, *, backup_id=None):
    factory = client.app.state.session_factory
    with factory() as session:
        accepted = OperationsService(
            session, maintenance_enabled=True, backup_configured=True
        ).enqueue_maintenance(
            owner_id=owner,
            command=MaintenanceInput(
                operation_id=uuid4(), action=action, reason="受控维护验收", backup_id=backup_id
            ),
        )

        job = session.get(Job, accepted.job_id)
        return accepted, SimpleNamespace(
            kind=job.kind,
            job_id=job.id,
            owner_id=owner,
            operation_id=job.operation_id,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )


def test_actual_heartbeat_and_external_watchdog_complete_original_job_without_worker(
    event_read_client,
):
    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    reporter = ProcessHeartbeatReporter(factory, role="api")
    reporter.beat()
    settings = event_read_client.app.state.settings.model_copy(
        update={"operations_maintenance_enabled": True}
    )
    assert run_watchdog_once(factory, settings)
    assert not run_watchdog_once(factory, settings)
    reporter.stop()
    with factory() as session:
        heartbeat = session.scalar(
            select(ProcessHeartbeat).where(ProcessHeartbeat.instance_id == reporter.instance_id)
        )
        assert heartbeat.state == "stopping" and heartbeat.pid > 0
        audit = session.scalar(
            select(OperatorAuditOperation).where(
                OperatorAuditOperation.action == "maintenance.watchdog"
            )
        )
        job = session.get(Job, audit.job_id)
        assert audit.owner_id == owner
        assert audit.status == "succeeded" and job.status == "succeeded"
        assert "process.worker" in {finding["key"] for finding in audit.after_state["findings"]}
        assert not audit.after_state["delivered"]
        assert session.scalar(select(OutboxMessage)).published_at is None


def test_maintenance_schedules_actual_jobs_once_and_keeps_external_watchdog_distinct(
    event_read_client,
):
    client = event_read_client
    owner = _demo_scope(client)
    factory = client.app.state.session_factory
    settings = client.app.state.settings.model_copy(update={"operations_maintenance_enabled": True})
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        assert enqueue_due_maintenance_in_transaction(session, now=now, settings=settings) == 6
        assert enqueue_due_maintenance_in_transaction(session, now=now, settings=settings) == 0
    with factory() as session:
        state = read_maintenance_state(session, owner_id=owner, settings=settings, now=now)
        assert len(state.schedules) == 10
        assert not next(item for item in state.schedules if item.action == "backup").enabled
        assert any(item.key == "process.worker" for item in state.findings)
        audits = session.scalars(select(OperatorAuditOperation)).all()
        assert all(row.job_id is not None for row in audits)
        assert not any(row.action == "maintenance.watchdog" for row in audits)


def test_recovery_redispatches_original_job_without_reopening_unknown_terminal_jobs(
    event_read_client,
):
    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        jobs = []
        for _ in range(2):
            jobs.append(
                JobService(session).accept_in_transaction(
                    owner_id=owner,
                    command=JobAcceptanceInput(
                        operation_id=uuid4(),
                        kind="analysis.annotate",
                        scope={},
                        observation=JobObservationContext(
                            configuration_ref="controlled", configuration_version=1
                        ),
                    ),
                )
            )
        session.flush()
        now = datetime.now(UTC)
        for outbox in session.scalars(select(OutboxMessage)):
            outbox.published_at = now
        terminal = session.get(Job, jobs[1].id)
        terminal.status, terminal.completed_at = "failed", now
        terminal.last_error_code, terminal.last_error_category, terminal.last_error_at = (
            "ai_result_unknown",
            "invalid_response",
            now,
        )
        terminal.next_action, terminal.manual_retry_allowed = "人工核对", False
        session.flush()
        assert republish_due_jobs_in_transaction(session, owner_id=owner, now=now) == (jobs[0].id,)
        assert republish_due_jobs_in_transaction(session, owner_id=owner, now=now) == ()
        assert terminal.status == "failed" and not terminal.manual_retry_allowed
        assert (
            len(
                session.scalars(
                    select(OutboxMessage).where(OutboxMessage.aggregate_id == jobs[0].id)
                ).all()
            )
            == 2
        )


@pytest.mark.parametrize("action", ["alerts", "source_health"])
def test_operations_unknown_delivery_is_not_sent_again_and_can_be_operator_resolved(
    event_read_client,
    action,
):
    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session:
        ResourceBudgetService(session).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="network.global",
                metric="network_request",
                scope_kind="global",
                limit_units=20,
                window_seconds=86400,
                window_anchor_at=now - timedelta(hours=1),
                enabled=True,
            ),
        )
    accepted, message = _accept(event_read_client, owner, action)
    calls = []

    def response(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled lost response", request=request)

    settings = event_read_client.app.state.settings.model_copy(
        update={
            "operations_maintenance_enabled": True,
            "operations_alerts_enabled": True,
            "operations_webhook_url": SecretStr(
                "https://open.feishu.cn/open-apis/bot/v2/hook/controlled"
            ),
        }
    )
    with factory() as session:
        execution = JobExecutionService(session, lease_seconds=300)
        lease = execution.acquire(job_id=message.job_id, worker_id="controlled-worker")
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        executor = OperationsMaintenanceExecutor(factory, settings, client=client)
        with pytest.raises(JobExecutionFailure, match="operations_delivery_unknown") as failure:
            executor.execute(message, lease)
        assert not failure.value.manual_retry_allowed
        with factory() as session:
            JobExecutionService(session, lease_seconds=300).record_failure(
                lease, message=MessageReference(uuid4(), "controlled", 0, 1), failure=failure.value
            )
        with pytest.raises(JobExecutionFailure, match="operations_result_unknown"):
            executor.execute(message)
    assert len(calls) == 1
    with factory() as session:
        assert session.get(OperatorAuditOperation, accepted.audit_id).status == "unknown"
        resolved = OperationsService(session).resolve_delivery(
            owner_id=owner,
            audit_id=accepted.audit_id,
            command=AuditResolutionInput(
                operation_id=uuid4(), reason="目的地确无这条消息", outcome="not_delivered"
            ),
        )
        assert resolved.status == "failed"
        assert session.get(Job, message.job_id).manual_retry_allowed
        budget = ResourceBudgetService(session).budget_usage_snapshot(owner_id=owner)[0]
        assert budget.used_units == 1 and budget.reserved_units == 0


@pytest.fixture
def restore_database_url() -> Iterator[SecretStr]:
    source_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if source_url is None:
        pytest.skip("isolated PostgreSQL test database is required")
    parsed = make_url(source_url)
    name = f"hotkey_restore_{uuid4().hex}"
    engine = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        try:
            yield SecretStr(parsed.set(database=name).render_as_string(hide_password=False))
        finally:
            with engine.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
    finally:
        engine.dispose()


def test_backup_and_isolated_restore_verify_real_dump_and_all_registered_tables(
    event_read_client, tmp_path, restore_database_url
):
    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    settings = event_read_client.app.state.settings.model_copy(
        update={
            "operations_maintenance_enabled": True,
            "operations_backup_directory": tmp_path,
            "operations_restore_database_url": restore_database_url,
        }
    )
    executor = OperationsMaintenanceExecutor(factory, settings)
    accepted, message = _accept(event_read_client, owner, "backup")
    executor.execute(message)
    executor.execute(message)
    with factory() as session:
        backup = session.get(OperatorAuditOperation, accepted.audit_id)
        assert backup.status == "succeeded" and not backup.after_state["restore_verified"]
        backup_id = backup.after_state["backup_id"]
        assert backup.after_state["table_count"] == len(metadata.tables)
        assert len(list(tmp_path.glob("hotkey-backup-*"))) == 1
    restore_accepted, restore_message = _accept(
        event_read_client, owner, "verify_backup", backup_id=backup_id
    )
    executor.execute(restore_message)
    with factory() as session:
        proof = session.get(OperatorAuditOperation, restore_accepted.audit_id)
        assert proof.after_state["restore_verified"]
        assert proof.after_state["table_count"] == len(metadata.tables)
        assert proof.after_state["evidence_objects_verified"] == 0
        assert not proof.after_state["production_restore"]


def test_source_health_weekly_compares_ingestion_windows_and_sends_once_via_original_audit(
    event_read_client,
):
    from sqlalchemy import text
    from tests.integration.test_editorial_source_profiles import setup

    from connections.editorial_models import EditorialSourceProfile

    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _, owner, source, _ = setup(session)
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        profile = session.get(EditorialSourceProfile, source.id)
        profile.created_at = now - timedelta(days=20)
        profile.health, profile.failure_count = "failing", 4
        profile.last_failure_code = "controlled_source_failure"
        for age in (1, 2, 8):
            identity = uuid4()
            session.execute(
                text(
                    "INSERT INTO content_records "
                    "(id,owner_id,source_key,object_type,external_id,created_at) "
                    "VALUES (:id,:owner,:key,'post',:external,:at)"
                ),
                {
                    "id": identity,
                    "owner": owner,
                    "key": source.source_key,
                    "external": str(identity),
                    "at": now - timedelta(days=age),
                },
            )
    with factory() as session:
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="controlled.operations.network",
                metric="network_request",
                scope_kind="global",
                limit_units=10,
                window_seconds=86400,
                window_anchor_at=now - timedelta(minutes=1),
                enabled=True,
            ),
        )
    accepted, message = _accept(event_read_client, owner, "source_health")
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: now).acquire(
            job_id=message.job_id, worker_id="controlled-weekly-operations"
        )
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 0})

    settings = event_read_client.app.state.settings.model_copy(
        update={
            "operations_maintenance_enabled": True,
            "operations_alerts_enabled": True,
            "operations_webhook_url": SecretStr(
                "https://open.feishu.cn/open-apis/bot/v2/hook/controlled"
            ),
        }
    )
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        executor = OperationsMaintenanceExecutor(
            factory, settings, clock=lambda: now, client=client
        )
        executor.execute(message, lease)
        executor.execute(message, lease)
    assert len(calls) == 1
    assert b"controlled_source_failure" in calls[0].content and len(calls[0].content) <= 18 * 1024
    with factory() as session:
        audit = session.get(OperatorAuditOperation, accepted.audit_id)
        report = audit.after_state["source_health_summary"]
        assert report["collected_current"] == 2 and report["collected_previous"] == 1
        assert report["failing_sources"] == 1 and report["selected_current"] == 0
        assert audit.status == "succeeded" and audit.after_state["delivered"]
        assert (
            len(
                session.scalars(
                    select(OperatorAuditOperation).where(
                        OperatorAuditOperation.owner_id == owner,
                        OperatorAuditOperation.action == "maintenance.source_health",
                    )
                ).all()
            )
            == 1
        )


def test_quiet_collection_waits_for_real_worker_startup_grace_and_respects_source_switch(
    event_read_client,
):
    from tests.integration.test_editorial_source_profiles import setup

    from operations.maintenance import maintenance_findings
    from operations.services import record_process_heartbeat_in_transaction

    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _, owner, _, _ = setup(session)
    now = datetime.now(UTC)
    settings = event_read_client.app.state.settings.model_copy(
        update={
            "operations_maintenance_enabled": True,
            "editorial_sources_enabled": True,
            "editorial_public_requests_enabled": True,
            "operations_quiet_minutes": 360,
        }
    )
    with factory() as session, session.begin():
        record_process_heartbeat_in_transaction(
            session,
            owner_id=owner,
            role="worker",
            instance_id="controlled-worker",
            pid=1,
            state="alive",
            now=now,
            started_at=now - timedelta(minutes=10),
            detail={},
        )
    with factory() as session:
        assert "content.collect" not in {
            row.key
            for row in maintenance_findings(session, owner_id=owner, settings=settings, now=now)[0]
        }
    with factory() as session, session.begin():
        worker = session.scalar(
            select(ProcessHeartbeat).where(
                ProcessHeartbeat.owner_id == owner, ProcessHeartbeat.role == "worker"
            )
        )
        worker.started_at = now - timedelta(minutes=21)
    with factory() as session:
        assert "content.collect" in {
            row.key
            for row in maintenance_findings(session, owner_id=owner, settings=settings, now=now)[0]
        }
    with factory() as session:
        assert "content.collect" not in {
            row.key
            for row in maintenance_findings(
                session,
                owner_id=owner,
                settings=settings.model_copy(update={"editorial_sources_enabled": False}),
                now=now,
            )[0]
        }
