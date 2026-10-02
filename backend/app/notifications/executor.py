from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin
from uuid import UUID, uuid5

import httpx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    JobFailureCategory,
    JobMessage,
    JobStatus,
)
from jobs.services import (
    BudgetPolicyUnavailableError,
    ResourceBudgetService,
    load_job_execution_configuration,
)
from monitors.notification_preferences import load_topic_notification_target_names_in_transaction
from notifications.admission import subject_delivery_operation_id
from notifications.card import notification_card
from notifications.codex_recipients import codex_recipient_eligible_in_transaction
from notifications.feishu import FeishuDeliveryError, FeishuWebhook
from notifications.materials import load_notification_material_in_transaction
from notifications.models import NotificationDelivery, NotificationTarget
from notifications.schemas import NotificationChannel, NotificationSubjectMaterial, TargetView
from notifications.services import NotificationTargetService
from notifications.smtp import SmtpDeliveryError, SmtpSender

_NAMESPACE = UUID("646d61d6-4139-4032-b96c-157d7a4da487")


class NotificationExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        client: httpx.Client | None = None,
        smtp_factory: Callable[..., Any] | None = None,
    ):
        self._sessions, self._settings = sessions, settings
        self._clock, self._client, self._smtp_factory = (
            clock or (lambda: datetime.now(UTC)),
            client,
            smtp_factory,
        )

    def _guard(self, session: Session, message: JobMessage, lease: ExecutionLease) -> None:
        if lease.job_id != message.job_id:
            raise ValueError("notification job/lease mismatch")
        JobExecutionService(
            session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
        ).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if message.kind != "notification.send":
            raise ValueError("notification executor received another task kind")
        delivery_id, status, material, target, reservation = self._prepare(message, lease)
        if status == "succeeded":
            return JobCompletion(status=JobStatus.SUCCEEDED)
        if status == "receipt_saved":
            self._finish(message, lease, delivery_id)
            return JobCompletion(status=JobStatus.SUCCEEDED)
        if status == "unknown":
            raise self._failure("notification_delivery_unknown", manual=False)
        assert material is not None and target is not None and reservation is not None
        try:
            receipt = self._send(delivery_id, material, target)
        except (FeishuDeliveryError, SmtpDeliveryError) as error:
            self._record_failure(message, lease, delivery_id, error)
            raise AssertionError("failure recording must raise") from error
        finally:
            # Outbound accounting records the attempt even after cancellation or lease loss.
            with self._sessions() as session, session.begin():
                ResourceBudgetService(
                    session, clock=self._clock
                ).settle_budget_reservation_in_transaction(
                    owner_id=message.owner_id, reservation_id=reservation, actual_units=1
                )
        self._save_receipt(message, lease, delivery_id, receipt)
        self._finish(message, lease, delivery_id)
        return JobCompletion(status=JobStatus.SUCCEEDED)

    def _prepare(
        self, message: JobMessage, lease: ExecutionLease
    ) -> tuple[UUID, str, NotificationSubjectMaterial | None, TargetView | None, UUID | None]:
        with self._sessions() as session, session.begin():
            self._guard(session, message, lease)
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("notification_job_mismatch")
            delivery_id = UUID(str(configuration.scope["delivery_id"]))
            row = session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.owner_id == message.owner_id,
                )
            )
            if row is None:
                raise self._failure("notification_delivery_missing")
            # Source-owned Codex material locks the monitor first, matching producer lock order.
            material = None
            if row.status not in {"succeeded", "unknown", "sending"}:
                frozen = NotificationSubjectMaterial.model_validate(row.frozen_payload)
                material = load_notification_material_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    kind=frozen.kind,
                    subject_id=frozen.subject_id,
                    revision=frozen.revision,
                    locator=frozen.locator,
                    now=self._clock(),
                )
                if (
                    material is None
                    or material.fingerprint != frozen.fingerprint
                    or material.dedupe_key != frozen.dedupe_key
                    or bytes.fromhex(material.fingerprint) != row.input_fingerprint
                ):
                    raise self._failure("notification_material_stale", manual=False)
            target = session.scalar(
                select(NotificationTarget)
                .where(
                    NotificationTarget.id == row.target_id,
                    NotificationTarget.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            row = session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            assert row is not None
            if target is None:
                raise self._failure("notification_target_missing")
            frozen = NotificationSubjectMaterial.model_validate(row.frozen_payload)
            if message.operation_id != subject_delivery_operation_id(
                frozen, owner_id=message.owner_id, target_id=target.id
            ):
                raise self._failure("notification_job_mismatch")
            if row.status == "succeeded":
                return delivery_id, "succeeded", None, None, None
            if row.status == "sending":
                if row.provider_receipt.get("status") in {"accepted", "smtp_accepted"}:
                    return delivery_id, "receipt_saved", None, None, None
                row.status, row.last_error_code, row.updated_at = (
                    "unknown",
                    "notification_delivery_unknown",
                    self._clock(),
                )
                row.revision += 1
                return delivery_id, "unknown", None, None, None
            if row.status == "unknown":
                return delivery_id, "unknown", None, None, None
            if not self._settings.notifications_enabled:
                raise self._failure("notification_disabled")
            if (
                not target.enabled
                or target.revision != row.target_revision
                or frozen.kind not in target.subscriptions
                or frozen.occurred_at < (target.enabled_at or target.created_at)
            ):
                raise self._failure("notification_target_stale", manual=False)
            assert material is not None
            if not codex_recipient_eligible_in_transaction(
                session, owner_id=message.owner_id, target_id=target.id, material=material
            ):
                raise self._failure("notification_target_stale", manual=False)
            if material.expires_at is not None and material.expires_at <= self._clock():
                raise self._failure("notification_material_expired", manual=False)
            if material.kind == "report":
                from reports.notification_reading import load_notification_report_in_transaction

                report = load_notification_report_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    report_id=material.subject_id,
                    version=material.revision,
                    now=self._clock(),
                )
                names = load_topic_notification_target_names_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    topic_ids=(report.topic_id,) if report is not None else (),
                )
                if report is None or target.name not in names.get(report.topic_id, ()):
                    raise self._failure("notification_topic_binding_stale", manual=False)
            self._require_transport(target)
            if row.attempt_count >= 3:
                raise self._failure("notification_attempts_exhausted", manual=False)
            reservation = uuid5(_NAMESPACE, f"{row.id}:{row.attempt_count + 1}")
            try:
                decision = ResourceBudgetService(
                    session, clock=self._clock
                ).reserve_budget_in_transaction(
                    owner_id=message.owner_id,
                    command=BudgetReservationInput(
                        reservation_id=reservation,
                        operation_id=message.operation_id,
                        metric=BudgetMetric.NETWORK_REQUEST,
                        requested_units=1,
                        context=BudgetContext(
                            source_ref="notifications", job_ref=str(message.job_id)
                        ),
                    ),
                )
            except BudgetPolicyUnavailableError:
                raise self._failure("notification_budget_unavailable") from None
            if decision.status != BudgetDecisionStatus.RESERVED:
                raise self._failure("notification_budget_denied")
            _, permitted = JobExecutionService(
                session,
                lease_seconds=self._settings.job_lease_seconds,
                clock=self._clock,
            ).begin_request_in_transaction(lease)
            if not permitted:
                raise self._failure("notification_cancelled", manual=False)
            row.status, row.attempt_count, row.last_error_code = (
                "sending",
                row.attempt_count + 1,
                "request_started",
            )
            row.revision, row.updated_at = row.revision + 1, self._clock()
            return (
                delivery_id,
                "sending",
                material,
                NotificationTargetService._view(target),
                reservation,
            )

    def _require_transport(self, target: NotificationTarget) -> None:
        if target.channel == "email":
            if (
                not self._settings.notification_smtp_enabled
                or self._settings.notification_smtp_host is None
                or self._settings.notification_smtp_from_email is None
            ):
                raise self._failure("notification_smtp_unconfigured")
        elif self._settings.feishu_webhook_url is None:
            raise self._failure("notification_feishu_unconfigured")
        if (
            target.channel == "feishu"
            and target.secret_env
            and not os.environ.get(target.secret_env)
        ):
            raise self._failure("notification_feishu_secret_unconfigured")

    def _send(
        self, delivery_id: UUID, material: NotificationSubjectMaterial, target: TargetView
    ) -> dict[str, object]:
        url = urljoin(
            self._settings.web_base_url.rstrip("/") + "/", material.reading_url.lstrip("/")
        )
        if target.channel is NotificationChannel.EMAIL:
            return SmtpSender(self._settings, factory=self._smtp_factory).send(
                delivery_id=delivery_id,
                recipients=target.recipients,
                title=material.title,
                text=material.text,
                reading_url=url,
                now=self._clock(),
            )
        webhook = self._settings.feishu_webhook_url
        assert webhook is not None
        secret = (
            SecretStr(os.environ[target.secret_env])
            if target.secret_env
            else self._settings.feishu_secret
        )
        card = notification_card(title=material.title, text=material.text, reading_url=url)
        owned = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(10, connect=5), follow_redirects=False
        )
        try:
            FeishuWebhook(url=webhook, secret=secret, client=client).send(card, now=self._clock())
        finally:
            if owned:
                client.close()
        return {
            "transport": "feishu",
            "status": "accepted",
            "received_at": self._clock().isoformat(),
        }

    def _save_receipt(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        delivery_id: UUID,
        receipt: dict[str, object],
    ) -> None:
        with self._sessions() as session, session.begin():
            self._guard(session, message, lease)
            row = session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            if row is None or row.status != "sending":
                raise self._failure("notification_delivery_unknown", manual=False)
            row.provider_receipt, row.last_error_code, row.updated_at = (
                receipt,
                "receipt_saved",
                self._clock(),
            )
            row.revision += 1

    def _finish(self, message: JobMessage, lease: ExecutionLease, delivery_id: UUID) -> None:
        with self._sessions() as session, session.begin():
            self._guard(session, message, lease)
            row = session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            if row is None or row.provider_receipt.get("status") not in {
                "accepted",
                "smtp_accepted",
            }:
                raise self._failure("notification_delivery_unknown", manual=False)
            row.status, row.last_error_code, row.sent_at, row.updated_at = (
                "succeeded",
                None,
                self._clock(),
                self._clock(),
            )
            row.revision += 1

    def _record_failure(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        delivery_id: UUID,
        error: FeishuDeliveryError | SmtpDeliveryError,
    ) -> None:
        with self._sessions() as session, session.begin():
            self._guard(session, message, lease)
            row = session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            assert row is not None
            row.status, row.last_error_code, row.updated_at = (
                ("unknown" if error.uncertain else "failed"),
                error.code,
                self._clock(),
            )
            row.revision += 1
        if error.uncertain:
            raise self._failure("notification_delivery_unknown", manual=False)
        raise JobExecutionFailure(
            error_code="notification_delivery_failed",
            category=JobFailureCategory.TRANSIENT,
            occurred_at=self._clock(),
            next_action="核对通知目的地配置后重试",
            retry_at=self._clock() + timedelta(seconds=30),
            max_attempts=3,
        )

    def _failure(self, code: str, *, manual: bool = True) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.CONFIGURATION_UNAVAILABLE,
            occurred_at=self._clock(),
            next_action="核对通知配置;未知结果需人工核对目的地",
            manual_retry_allowed=manual,
        )
