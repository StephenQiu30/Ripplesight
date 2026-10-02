from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from tests.integration.test_codex_execution import _runtime_setup
from tests.integration.test_codex_resets import engine as engine

from core.config import Settings
from jobs.execution import JobExecutionFailure, JobExecutionService, MessageReference
from jobs.models import Job, OutboxMessage
from jobs.schemas import JobAcceptedMessage
from monitors.codex_schemas import Proposition, Recognition, ResetPostInput, ResetScope
from monitors.codex_services import CodexResetService
from notifications.admission import enqueue_codex_notifications_in_transaction
from notifications.executor import NotificationExecutor
from notifications.materials import load_notification_material_in_transaction
from notifications.models import NotificationDelivery
from notifications.operator import NotificationOperatorService
from notifications.schemas import DeliveryResolutionInput, TargetInput
from notifications.services import NotificationTargetService


def _lease_delivery(sessions, delivery_id, now):
    with sessions() as session:
        job = session.scalar(
            select(Job).where(Job.scope["delivery_id"].as_string() == str(delivery_id))
        )
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
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: now).acquire(
            job_id=job.id, worker_id="controlled-codex-recipients"
        )
        return message, lease


def _recognize(sessions, owner, monitor, now, action, *, event_id=None):
    def sink(session, partition, monitor_id, intents):
        return enqueue_codex_notifications_in_transaction(
            session, owner_id=partition, monitor_id=monitor_id, intents=intents, now=now
        )

    with sessions() as session:
        service = CodexResetService(session, clock=lambda: now, notification_sink=sink)
        external_id = "910001" if action == "announce" else "910002"
        source = ResetPostInput(
            external_id=external_id,
            text=f"Controlled Codex {action}",
            published_at=now,
            url=f"https://x.com/thsottiaux/status/{external_id}",
        )
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor.id,
            posts=(source,),
            expected_configuration_version=monitor.configuration_version,
        )
        prepared = service.prepare_next(owner_id=owner, monitor_id=monitor.id)
        attempt = service.begin_recognition(prepared=prepared)
        return service.apply_recognition(
            prepared=prepared,
            attempt_id=attempt,
            recognition=Recognition(
                relevant=True,
                needs_review=False,
                propositions=(
                    Proposition(
                        kind="direct_reset",
                        action=action,
                        real=True,
                        kind_explicit=True,
                        excerpt=source.text,
                        relates_to=event_id,
                        scope=ResetScope(audience_source="all paid users")
                        if action == "amend"
                        else ResetScope(),
                    ),
                ),
            ),
        )


def _setup(engine):
    sessions, owner, monitor, _, _, at = _runtime_setup(engine)
    with sessions.begin() as session:
        targets = {
            name: NotificationTargetService(session).add_in_transaction(
                owner_id=owner,
                target=TargetInput(
                    name=name, channel="feishu", enabled=True, subscriptions=("codex_reset",)
                ),
                now=at - timedelta(minutes=1),
            )
            for name in ("delivered", "delivering", "unknown", "pending", "failed")
        }
    announcement = _recognize(sessions, owner, monitor, at, "announce")
    assert announcement.notifications_enqueued == 5
    with sessions() as session:
        deliveries = {
            row.target_id: row.id for row in session.scalars(select(NotificationDelivery))
        }
    with sessions.begin() as session:
        first = session.get(NotificationDelivery, deliveries[targets["delivered"].id])
        current_material = load_notification_material_in_transaction(
            session,
            owner_id=owner,
            kind="codex_reset",
            subject_id=first.subject_id,
            revision=first.report_version,
            locator=first.frozen_payload["locator"],
            now=at,
        )
        assert current_material is not None
        assert current_material.fingerprint == first.frozen_payload["fingerprint"], (
            current_material.model_dump(mode="json"),
            first.frozen_payload,
        )
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=engine.url.render_as_string(False),
        notifications_enabled=True,
        job_lease_seconds=300,
        feishu_webhook_url=SecretStr("https://open.feishu.cn/open-apis/bot/v2/hook/controlled"),
    )
    calls = []

    def success(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 0})

    with httpx.Client(transport=httpx.MockTransport(success)) as client:
        message, lease = _lease_delivery(sessions, deliveries[targets["delivered"].id], at)
        NotificationExecutor(sessions, settings, clock=lambda: at, client=client).execute(
            message, lease
        )
    message, lease = _lease_delivery(sessions, deliveries[targets["delivering"].id], at)
    assert (
        NotificationExecutor(sessions, settings, clock=lambda: at)._prepare(message, lease)[1]
        == "sending"
    )

    def unknown(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled response lost")

    message, lease = _lease_delivery(sessions, deliveries[targets["unknown"].id], at)
    with httpx.Client(transport=httpx.MockTransport(unknown)) as client:
        sender = NotificationExecutor(sessions, settings, clock=lambda: at, client=client)
        with pytest.raises(JobExecutionFailure, match="notification_delivery_unknown") as error:
            sender.execute(message, lease)
        original_requests = len(calls)
        with pytest.raises(JobExecutionFailure, match="notification_delivery_unknown"):
            sender.execute(message, lease)
        assert len(calls) == original_requests
    with sessions() as session:
        JobExecutionService(session, lease_seconds=300, clock=lambda: at).record_failure(
            lease,
            failure=error.value,
            message=MessageReference(
                message_id=message.message_id, topic="controlled-codex", partition=0, offset=0
            ),
        )
    with sessions.begin() as session:
        failed = session.get(NotificationDelivery, deliveries[targets["failed"].id])
        failed.status, failed.last_error_code = "failed", "controlled_rejection"
    later = at + timedelta(minutes=2)
    foreign_owner = uuid4()
    with sessions.begin() as session:
        late = NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="late", channel="feishu", enabled=True, subscriptions=("codex_reset",)
            ),
            now=at + timedelta(minutes=1),
        )
        NotificationTargetService(session).add_in_transaction(
            owner_id=foreign_owner,
            target=TargetInput(
                name="foreign", channel="feishu", enabled=True, subscriptions=("codex_reset",)
            ),
            now=at,
        )
    return (
        sessions,
        owner,
        monitor,
        targets,
        late,
        deliveries,
        announcement,
        at,
        later,
        settings,
        foreign_owner,
    )


@pytest.mark.parametrize("action", ["amend", "withdraw"])
def test_codex_corrections_only_admit_prior_announcement_recipients(engine, action):
    sessions, owner, monitor, targets, late, original, announce, _, later, _, foreign = _setup(
        engine
    )
    outcome = _recognize(sessions, owner, monitor, later, action, event_id=announce.event_ids[0])
    assert outcome.notifications_enqueued == 3
    expected = {targets[name].id for name in ("delivered", "delivering", "unknown")}
    with sessions.begin() as session:
        corrections = tuple(
            session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.frozen_payload["locator"]["intent"]["action"].as_string()
                    == action
                )
            )
        )
        assert {row.target_id for row in corrections} == expected
        assert all(row.owner_id == owner and row.target_id != late.id for row in corrections)
        assert len(corrections) == 3
        assert (
            session.get(NotificationDelivery, original[targets["unknown"].id]).status == "unknown"
        )
        assert (
            enqueue_codex_notifications_in_transaction(
                session,
                owner_id=owner,
                monitor_id=monitor.id,
                intents=outcome.notifications,
                now=later,
            )
            == 0
        )
        assert (
            enqueue_codex_notifications_in_transaction(
                session,
                owner_id=foreign,
                monitor_id=monitor.id,
                intents=outcome.notifications,
                now=later,
            )
            == 0
        )


@pytest.mark.parametrize("action", ["amend", "withdraw"])
def test_codex_correction_rechecks_original_receipt_before_sending(engine, action):
    sessions, owner, monitor, targets, _, original, announce, _, later, settings, _ = _setup(engine)
    _recognize(sessions, owner, monitor, later, action, event_id=announce.event_ids[0])
    with sessions() as session:
        row = session.get(NotificationDelivery, original[targets["unknown"].id])
        revision = row.revision
    with sessions() as session:
        NotificationOperatorService(session, clock=lambda: later).resolve(
            owner_id=owner,
            delivery_id=original[targets["unknown"].id],
            command=DeliveryResolutionInput(
                operation_id=uuid4(),
                expected_revision=revision,
                reason="controlled destination verified no original announcement",
                outcome="not_delivered",
            ),
        )
    with sessions() as session:
        correction = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.target_id == targets["unknown"].id,
                NotificationDelivery.frozen_payload["locator"]["intent"]["action"].as_string()
                == action,
            )
        )
        correction_id = correction.id
    message, lease = _lease_delivery(sessions, correction_id, later)
    calls = []
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (calls.append(request), httpx.Response(200, json={"code": 0}))[1]
            )
        ) as client,
        pytest.raises(JobExecutionFailure, match="notification_target_stale"),
    ):
        NotificationExecutor(sessions, settings, clock=lambda: later, client=client).execute(
            message, lease
        )
    assert calls == []
    with sessions() as session:
        row = session.get(NotificationDelivery, correction_id)
        assert row.status == "pending" and row.attempt_count == 0
