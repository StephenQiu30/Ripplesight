from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_publication import editorial_client as editorial_client

from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job, OutboxMessage
from jobs.schemas import JobAcceptedMessage
from notifications.executor import NotificationExecutor
from notifications.models import NotificationDelivery, NotificationTarget
from notifications.scan import NotificationScanExecutor
from notifications.schemas import TargetInput
from notifications.services import NotificationService, NotificationTargetService
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


def _setup(client):
    owner, run, message, lease = _run(client)
    _budget(client, owner)
    _execute(client, owner, message, lease, ControlledClient())
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控摘要许可",
                reason="通知管线验证",
            ),
            now=NOW,
        )
        published = service.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=NOW
        )
        target = NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="selected", channel="feishu", enabled=True, subscriptions=("selected",)
            ),
            now=NOW,
        )
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
    from jobs.services import ResourceBudgetService

    with sessions() as session:
        ResourceBudgetService(session, clock=lambda: NOW).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="global.notification-test",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=NOW,
                enabled=True,
            ),
        )
    at = NOW + timedelta(minutes=5)
    settings = client.app.state.settings.model_copy(
        update={
            "notifications_enabled": True,
            "feishu_webhook_url": SecretStr(
                "https://open.feishu.cn/open-apis/bot/v2/hook/controlled"
            ),
        }
    )
    with sessions.begin() as session:
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 1
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 0
    scan_message, scan_lease = _lease(sessions, "notification.scan", at)
    NotificationScanExecutor(sessions, settings, clock=lambda: at).execute(scan_message, scan_lease)
    with sessions() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery and delivery.subject_id == run.content_id
        assert session.scalar(select(NotificationTarget)).revision == 1
    sender_message, sender_lease = _lease(sessions, "notification.send", at)
    return owner, run, published, target, at, settings, sender_message, sender_lease


def _lease(sessions, kind, at):
    with sessions() as session:
        job = session.scalar(select(Job).where(Job.kind == kind))
        outbox = session.scalar(select(OutboxMessage).where(OutboxMessage.aggregate_id == job.id))
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        session.rollback()
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: at).acquire(
            job_id=message.job_id,
            worker_id="controlled-notification",
        )
    return message, lease


def test_selected_scan_and_sender_use_actual_material_and_durable_receipt(editorial_client):
    _owner, _run_view, _published, _target, at, settings, message, lease = _setup(editorial_client)
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
        )
    ) as client:
        executor = NotificationExecutor(
            editorial_client.app.state.session_factory, settings, clock=lambda: at, client=client
        )
        executor.execute(message, lease)
        executor.execute(message, lease)
    assert len(calls) == 1 and "新模型" in calls[0].content.decode()
    with editorial_client.app.state.session_factory() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery.status == "succeeded" and delivery.attempt_count == 1
        assert delivery.provider_receipt["status"] == "accepted"


def test_silent_selected_material_clears_to_one_delivery_without_historical_resend(
    editorial_client,
):
    from analysis.editorial_schemas import EditorialOverrideInput
    from analysis.editorial_services import EditorialService
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
    from jobs.services import ResourceBudgetService
    from notifications.admission import enqueue_subject_in_transaction
    from notifications.materials import load_notification_material_in_transaction
    from publication.notification_reading import (
        list_selected_notification_candidates_in_transaction,
    )

    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控摘要许可",
                reason="静默推送受控验收",
            ),
            now=NOW,
        )
        NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="selected", channel="feishu", enabled=True, subscriptions=("selected",)
            ),
            now=NOW,
        )
    silent_at = NOW + timedelta(seconds=1)
    with sessions() as session:
        EditorialService(session, clock=lambda: silent_at).override(
            owner_id=owner,
            run_id=run.id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=0,
                silent=True,
                reason="暂不推送精选",
            ),
        )
    at = NOW + timedelta(minutes=5)
    with sessions.begin() as session:
        page = list_selected_notification_candidates_in_transaction(
            session, owner_id=owner, enabled_at=NOW, now=at
        )
        assert len(page.candidates) == 1 and page.candidates[0].silent
        assert (
            load_notification_material_in_transaction(
                session,
                owner_id=owner,
                kind="selected",
                subject_id=run.content_id,
                revision=page.candidates[0].publication_revision,
                locator={},
                now=at,
            )
            is None
        )
        assert session.scalar(select(NotificationDelivery)) is None
    with sessions() as session:
        result = EditorialService(session, clock=lambda: at).override(
            owner_id=owner,
            run_id=run.id,
            command=EditorialOverrideInput(
                operation_id=uuid4(),
                expected_manual_version=1,
                clear_fields=["silent"],
                reason="恢复原自动推送资格",
            ),
        )
        assert not result.result.silent
        ResourceBudgetService(session, clock=lambda: at).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="global.silent-test",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=NOW,
                enabled=True,
            ),
        )
    at += timedelta(minutes=5)
    with sessions.begin() as session:
        page = list_selected_notification_candidates_in_transaction(
            session, owner_id=owner, enabled_at=NOW, now=at
        )
        assert len(page.candidates) == 1 and not page.candidates[0].silent
        material = load_notification_material_in_transaction(
            session,
            owner_id=owner,
            kind="selected",
            subject_id=run.content_id,
            revision=page.candidates[0].publication_revision,
            locator={},
            now=at,
        )
        assert material and material.occurred_at == silent_at
        assert (
            enqueue_subject_in_transaction(session, owner_id=owner, material=material, now=at) == 1
        )
        assert (
            enqueue_subject_in_transaction(session, owner_id=owner, material=material, now=at) == 0
        )
    settings = editorial_client.app.state.settings.model_copy(
        update={
            "notifications_enabled": True,
            "feishu_webhook_url": SecretStr(
                "https://open.feishu.cn/open-apis/bot/v2/hook/controlled"
            ),
        }
    )
    sender_message, sender_lease = _lease(sessions, "notification.send", at)
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
        )
    ) as client:
        executor = NotificationExecutor(sessions, settings, clock=lambda: at, client=client)
        executor.execute(sender_message, sender_lease)
        executor.execute(sender_message, sender_lease)
    assert len(calls) == 1
    with sessions() as session:
        assert len(session.scalars(select(NotificationDelivery)).all()) == 1
        assert session.scalar(select(NotificationDelivery)).status == "succeeded"


def test_live_permission_revocation_blocks_queued_summary_before_transport(editorial_client):
    owner, run, published, _target, at, settings, message, lease = _setup(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=run.content_id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=published.revision,
                visibility="summary-only",
                reason="发送前撤销公开许可",
            ),
            now=at,
        )
    calls = []
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
            )
        ) as client,
        pytest.raises(JobExecutionFailure, match="notification_material_stale"),
    ):
        NotificationExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
    assert not calls


def test_uncertain_provider_result_is_terminal_unknown_and_never_auto_resent(editorial_client):
    _owner, _run_view, _published, _target, at, settings, message, lease = _setup(editorial_client)
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled lost response")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        executor = NotificationExecutor(
            editorial_client.app.state.session_factory, settings, clock=lambda: at, client=client
        )
        for _ in range(2):
            with pytest.raises(
                JobExecutionFailure, match="notification_delivery_unknown"
            ) as caught:
                executor.execute(message, lease)
            assert not caught.value.manual_retry_allowed and caught.value.retry_at is None
    assert len(calls) == 1
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(select(NotificationDelivery)).status == "unknown"


def test_saved_provider_receipt_resumes_without_a_second_external_request(
    editorial_client, monkeypatch
):
    _owner, _run_view, _published, _target, at, settings, message, lease = _setup(editorial_client)
    calls = []
    sessions = editorial_client.app.state.session_factory
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
        )
    ) as client:
        executor = NotificationExecutor(sessions, settings, clock=lambda: at, client=client)
        monkeypatch.setattr(executor, "_finish", lambda *args: (_ for _ in ()).throw(SystemExit()))
        with pytest.raises(SystemExit):
            executor.execute(message, lease)
        NotificationExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
    assert len(calls) == 1
    with sessions() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery.status == "succeeded" and delivery.provider_receipt["status"] == "accepted"


def test_target_enabled_inside_scan_window_waits_for_next_frozen_window(editorial_client):
    from datetime import UTC, datetime

    from tests.integration.test_content_records import _demo_scope

    owner = _demo_scope(editorial_client)
    sessions = editorial_client.app.state.session_factory
    start = datetime.fromtimestamp(int(NOW.timestamp()) // 300 * 300, UTC)
    enabled = start + timedelta(seconds=11)
    settings = editorial_client.app.state.settings.model_copy(
        update={"notifications_enabled": True}
    )
    with sessions.begin() as session:
        target = NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="mid-window", channel="feishu", enabled=True, subscriptions=("selected",)
            ),
            now=enabled,
        )
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=enabled) == 0
        assert (
            NotificationService(session, settings).enqueue_due_in_transaction(
                now=start + timedelta(seconds=299)
            )
            == 0
        )
        assert (
            NotificationService(session, settings).enqueue_due_in_transaction(
                now=start + timedelta(seconds=300)
            )
            == 1
        )
        assert (
            NotificationService(session, settings).enqueue_due_in_transaction(
                now=start + timedelta(seconds=301)
            )
            == 0
        )
    message, lease = _lease(sessions, "notification.scan", start + timedelta(seconds=301))
    NotificationScanExecutor(
        sessions, settings, clock=lambda: start + timedelta(seconds=301)
    ).execute(message, lease)
    with sessions() as session:
        job = session.scalar(select(Job).where(Job.kind == "notification.scan"))
        assert datetime.fromisoformat(job.scope["enabled_at"]) == target.enabled_at
        assert job.checkpoint["notification.section"] == 3
        assert session.scalar(select(NotificationDelivery)) is None


def test_known_rejection_retries_three_times_and_never_four(editorial_client):
    _owner, _run_view, _published, _target, at, settings, message, lease = _setup(editorial_client)
    requests = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (requests.append(request), httpx.Response(400))[1]
        )
    ) as client:
        executor = NotificationExecutor(
            editorial_client.app.state.session_factory, settings, clock=lambda: at, client=client
        )
        for _ in range(3):
            with pytest.raises(JobExecutionFailure, match="notification_delivery_failed") as caught:
                executor.execute(message, lease)
            assert caught.value.retry_at is not None and caught.value.max_attempts == 3
        with pytest.raises(JobExecutionFailure, match="notification_attempts_exhausted"):
            executor.execute(message, lease)
    assert len(requests) == 3
    with editorial_client.app.state.session_factory() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery.attempt_count == 3 and delivery.status == "failed"


def test_topic_report_email_requires_explicit_binding_and_uses_actual_smtp_receipt(
    editorial_client,
):
    from sqlalchemy import text
    from tests.integration.test_notification_report_reading import _reports
    from tests.unit.test_notification_smtp import FakeSmtp

    owner, report, _revision, now = _reports(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        for name in ("bound-email", "unbound-email"):
            NotificationTargetService(session).add_in_transaction(
                owner_id=owner,
                target=TargetInput(
                    name=name,
                    channel="email",
                    recipients=("controlled@example.test",),
                    enabled=True,
                    subscriptions=("report",),
                ),
                now=now - timedelta(seconds=1),
            )
        session.execute(
            text(
                "UPDATE monitor_topics SET notification_target_names='[\"bound-email\"]'::jsonb "
                "WHERE id=:topic"
            ),
            {"topic": report.topic_id},
        )
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
    from jobs.services import ResourceBudgetService

    with sessions() as session:
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="global.notification-test",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=now,
                enabled=True,
            ),
        )
    at = now + timedelta(minutes=5)
    settings = editorial_client.app.state.settings.model_copy(
        update={
            "notifications_enabled": True,
            "notification_smtp_enabled": True,
            "notification_smtp_host": "smtp.invalid",
            "notification_smtp_from_email": "hotkey@example.test",
        }
    )
    with sessions.begin() as session:
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 2
        scan_ids = list(session.scalars(select(Job.id).where(Job.kind == "notification.scan")))
    for scan_id in scan_ids:
        with sessions() as session:
            outbox = session.scalar(
                select(OutboxMessage).where(OutboxMessage.aggregate_id == scan_id)
            )
            scan_message = JobAcceptedMessage.model_validate(
                {
                    **outbox.payload,
                    "message_id": outbox.id,
                    "event_type": outbox.event_type,
                    "schema_version": 2,
                }
            )
            session.rollback()
            scan_lease = JobExecutionService(session, lease_seconds=300, clock=lambda: at).acquire(
                job_id=scan_id, worker_id="controlled-report-notification"
            )
        NotificationScanExecutor(sessions, settings, clock=lambda: at).execute(
            scan_message, scan_lease
        )
    with sessions() as session:
        rows = list(session.scalars(select(NotificationDelivery)))
        assert len(rows) == 1 and rows[0].report_id == report.id and rows[0].report_version == 1
    message, lease = _lease(sessions, "notification.send", at)
    smtp = FakeSmtp()
    NotificationExecutor(
        sessions, settings, clock=lambda: at, smtp_factory=lambda *args, **kwargs: smtp
    ).execute(message, lease)
    with sessions() as session:
        row = session.scalar(select(NotificationDelivery))
        assert row.status == "succeeded" and row.provider_receipt["status"] == "smtp_accepted"
        assert row.provider_receipt["accepted_recipient_count"] == 1
    assert "tls" in smtp.commands


def test_unknown_operator_resolution_is_cas_audited_and_changes_only_original_job_retry(
    editorial_client,
):
    from jobs.execution import MessageReference
    from jobs.services import JOB_ACCEPTED_TOPIC
    from notifications.operator import NotificationOperatorService
    from notifications.schemas import DeliveryResolutionInput

    owner, _run_view, _published, _target, at, settings, message, lease = _setup(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("controlled"))
            )
        ) as client,
        pytest.raises(JobExecutionFailure) as caught,
    ):
        NotificationExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
    with sessions() as session:
        JobExecutionService(session, lease_seconds=300, clock=lambda: at).record_failure(
            lease,
            message=MessageReference(
                message_id=message.message_id, topic=JOB_ACCEPTED_TOPIC, partition=0, offset=1
            ),
            failure=caught.value,
        )
        row = session.scalar(select(NotificationDelivery))
        delivery_id, revision = row.id, row.revision
    command = DeliveryResolutionInput(
        operation_id=uuid4(),
        expected_revision=revision,
        reason="已在受控目的地核对消息记录,确认未送达",
        outcome="not_delivered",
    )
    with sessions() as session:
        service = NotificationOperatorService(session, clock=lambda: at)
        result = service.resolve(owner_id=owner, delivery_id=delivery_id, command=command)
        assert result.status == "failed" and result.revision == revision + 1
        assert service.resolve(owner_id=owner, delivery_id=delivery_id, command=command) == result
        job = session.get(Job, message.job_id)
        assert job.status == "failed" and job.manual_retry_allowed
        assert job.last_error_code == "notification_delivery_not_delivered"
        session.rollback()
        from core.errors import ApplicationError

        with pytest.raises(ApplicationError, match="operations_revision_conflict"):
            service.resolve(
                owner_id=owner,
                delivery_id=delivery_id,
                command=command.model_copy(update={"operation_id": uuid4()}),
            )


def test_codex_recognition_admits_into_the_same_ledger_and_late_withdrawal_blocks_send(
    editorial_client,
):
    from tests.integration.test_codex_execution import _runtime_setup

    from monitors.codex_schemas import Proposition, Recognition, ResetPostInput
    from monitors.codex_services import CodexResetService
    from notifications.admission import enqueue_codex_notifications_in_transaction

    sessions, owner, monitor, _tick_message, _tick_lease, at = _runtime_setup(
        editorial_client.app.state.session_factory.kw["bind"]
    )
    with sessions.begin() as session:
        NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="codex-alert", channel="feishu", enabled=True, subscriptions=("codex_reset",)
            ),
            now=at - timedelta(minutes=1),
        )

    def sink(session, owner_id, monitor_id, intents):
        return enqueue_codex_notifications_in_transaction(
            session, owner_id=owner_id, monitor_id=monitor_id, intents=intents, now=at
        )

    with sessions() as session:
        service = CodexResetService(session, clock=lambda: at, notification_sink=sink)
        source = ResetPostInput(
            external_id="300001",
            text="Will reset Codex limits today",
            published_at=at,
            url="https://x.com/thsottiaux/status/300001",
        )
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor.id,
            posts=(source,),
            expected_configuration_version=monitor.configuration_version,
        )
        prepared = service.prepare_next(owner_id=owner, monitor_id=monitor.id)
        attempt = service.begin_recognition(prepared=prepared)
        outcome = service.apply_recognition(
            prepared=prepared,
            attempt_id=attempt,
            recognition=Recognition(
                relevant=True,
                needs_review=False,
                propositions=(
                    Proposition(
                        kind="direct_reset",
                        action="announce",
                        real=True,
                        kind_explicit=True,
                        excerpt=source.text,
                    ),
                ),
            ),
        )
        assert outcome.notifications_enqueued == 1
        intents = outcome.notifications
    with sessions.begin() as session:
        assert (
            enqueue_codex_notifications_in_transaction(
                session, owner_id=owner, monitor_id=monitor.id, intents=intents, now=at
            )
            == 0
        )
        row = session.scalar(select(NotificationDelivery))
        assert row.subject_kind == "codex_reset" and row.subject_id is not None
        assert row.frozen_payload["locator"]["intent"]["event_id"] == intents[0].event_id
    later = at + timedelta(seconds=1)
    with sessions() as session:
        service = CodexResetService(session, clock=lambda: later)
        withdrawn = ResetPostInput(
            external_id="300002",
            text="Reset is cancelled",
            published_at=later,
            url="https://x.com/thsottiaux/status/300002",
        )
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor.id,
            posts=(withdrawn,),
            expected_configuration_version=monitor.configuration_version,
        )
        prepared = service.prepare_next(owner_id=owner, monitor_id=monitor.id)
        attempt = service.begin_recognition(prepared=prepared)
        service.apply_recognition(
            prepared=prepared,
            attempt_id=attempt,
            recognition=Recognition(
                relevant=True,
                needs_review=False,
                propositions=(
                    Proposition(
                        kind="direct_reset",
                        action="withdraw",
                        real=True,
                        kind_explicit=True,
                        excerpt=withdrawn.text,
                        relates_to=intents[0].event_id,
                    ),
                ),
            ),
        )
    message, lease = _lease(sessions, "notification.send", later)
    settings = editorial_client.app.state.settings.model_copy(
        update={
            "notifications_enabled": True,
            "feishu_webhook_url": SecretStr(
                "https://open.feishu.cn/open-apis/bot/v2/hook/controlled"
            ),
        }
    )
    calls = []
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
            )
        ) as client,
        pytest.raises(JobExecutionFailure, match="notification_material_stale"),
    ):
        NotificationExecutor(sessions, settings, clock=lambda: later, client=client).execute(
            message, lease
        )
    assert not calls


def test_operator_target_api_is_closed_without_token_and_uses_revision_cas(editorial_client):
    from tests.integration.test_content_records import _demo_scope

    from core.errors import ApplicationError
    from notifications.schemas import TargetSaveInput

    owner = _demo_scope(editorial_client)
    editorial_client.app.state.settings = editorial_client.app.state.settings.model_copy(
        update={"operator_token": None}
    )
    disabled = editorial_client.get("/api/operations/notification-targets")
    assert disabled.status_code == 403
    assert disabled.json()["code"] == "operator_disabled"
    editorial_client.app.state.settings = editorial_client.app.state.settings.model_copy(
        update={"operator_token": SecretStr("controlled-operator")}
    )
    for authentication_headers in ({}, {"X-HotKey-Operator-Token": "invalid-operator"}):
        unauthenticated = editorial_client.get(
            "/api/operations/notification-targets", headers=authentication_headers
        )
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "operator_authentication_required"
    command = TargetSaveInput(
        operation_id=uuid4(),
        expected_revision=0,
        reason="首次配置邮件",
        target=TargetInput(name="target-cas", channel="email", recipients=("reader@example.test",)),
    )
    headers = {"X-HotKey-Operator-Token": "controlled-operator"}
    empty = editorial_client.get("/api/operations/notification-targets", headers=headers)
    assert empty.status_code == 200 and empty.json() == []
    assert (
        editorial_client.put(
            "/api/operations/notification-targets",
            headers=headers,
            json=command.model_dump(mode="json"),
        ).status_code
        == 403
    )
    headers["X-HotKey-CSRF"] = "1"
    accepted = editorial_client.put(
        "/api/operations/notification-targets",
        headers=headers,
        json=command.model_dump(mode="json"),
    )
    assert accepted.status_code == 200
    target = accepted.json()
    assert not target["enabled"] and target["enabled_at"] is None and target["revision"] == 1
    assert (
        editorial_client.put(
            "/api/operations/notification-targets",
            headers=headers,
            json=command.model_dump(mode="json"),
        ).json()
        == target
    )
    with editorial_client.app.state.session_factory() as session:
        service = NotificationTargetService(session)
        from datetime import UTC, datetime

        update = TargetSaveInput(
            operation_id=uuid4(),
            target_id=UUID(target["id"]),
            expected_revision=1,
            reason="开启已配置目标",
            target=command.target.model_copy(update={"enabled": True}),
        )
        now = datetime.now(UTC)
        assert service.save(owner_id=owner, command=update, now=now).revision == 2
        with pytest.raises(ApplicationError, match="operations_revision_conflict"):
            service.save(
                owner_id=owner, command=update.model_copy(update={"operation_id": uuid4()}), now=NOW
            )
    stale = editorial_client.put(
        "/api/operations/notification-targets",
        headers=headers,
        json=update.model_copy(update={"operation_id": uuid4()}).model_dump(mode="json"),
    )
    assert stale.status_code == 409 and stale.json()["code"] == "operations_revision_conflict"
    unchanged = editorial_client.get("/api/operations/notification-targets", headers=headers)
    assert unchanged.status_code == 200
    assert len(unchanged.json()) == 1
    assert unchanged.json()[0]["enabled"] and unchanged.json()[0]["revision"] == 2


def test_real_report_keyset_scan_checkpoints_and_continuation_do_not_starve_tail(
    editorial_client, monkeypatch
):
    from sqlalchemy import text
    from tests.integration.test_notification_report_reading import _reports

    from reports.notification_reading import list_first_final_notification_reports_in_transaction
    from reports.services import ReportService

    owner, first, _revised, now = _reports(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = ReportService(session, clock=lambda: now)
        for day in range(2, 53):
            service.generate_daily_in_transaction(
                owner_id=owner,
                topic_id=first.topic_id,
                window_start=now - timedelta(days=day),
                window_end=now - timedelta(days=day - 1),
                cutoff_at=now,
            )
        NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="paged-reports", channel="feishu", enabled=True, subscriptions=("report",)
            ),
            now=now - timedelta(seconds=1),
        )
        session.execute(
            text(
                "UPDATE monitor_topics SET notification_target_names='[\"paged-reports\"]'::jsonb "
                "WHERE id=:topic"
            ),
            {"topic": first.topic_id},
        )
    # Shrink only the real SQL helper's page size, keeping its exact fixed-material guards.
    monkeypatch.setattr(
        "notifications.scan.list_first_final_notification_reports_in_transaction",
        lambda session, **kwargs: list_first_final_notification_reports_in_transaction(
            session, **kwargs, limit=1
        ),
    )
    at = now + timedelta(minutes=5)
    settings = editorial_client.app.state.settings.model_copy(
        update={"notifications_enabled": True}
    )
    with sessions.begin() as session:
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 1
    message, lease = _lease(sessions, "notification.scan", at)
    executor = NotificationScanExecutor(sessions, settings, clock=lambda: at)
    executor.execute(message, lease)
    with sessions() as session:
        original = session.get(Job, message.job_id)
        assert original.checkpoint_sequence == 50 and original.checkpoint["notification.cursor"]
        continuation = session.scalar(
            select(Job).where(Job.kind == "notification.scan", Job.id != message.job_id)
        )
        assert (
            continuation
            and continuation.scope["cursor"] == original.checkpoint["notification.cursor"]
        )
        outbox = session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == continuation.id)
        )
        next_message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        session.rollback()
        next_lease = JobExecutionService(session, lease_seconds=300, clock=lambda: at).acquire(
            job_id=next_message.job_id, worker_id="notification-continuation"
        )
    executor.execute(next_message, next_lease)
    executor.execute(next_message, next_lease)
    with sessions() as session:
        assert len(list(session.scalars(select(NotificationDelivery)))) == 52
        assert len(list(session.scalars(select(Job).where(Job.kind == "notification.scan")))) == 2
        assert session.get(Job, next_message.job_id).checkpoint["notification.section"] == 3
