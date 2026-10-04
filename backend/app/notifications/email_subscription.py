"""Account-owned report subscription on the original notification target ledger."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.config import Settings
from core.errors import ApplicationError
from identity.notification_reading import load_bound_notification_email_in_transaction
from notifications.models import NotificationTarget
from notifications.schemas import ReportEmailSubscriptionInput, ReportEmailSubscriptionView
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)

REPORT_EMAIL_TARGET_NAME = "我的报告邮箱"
_NAMESPACE = UUID("ab2abfe1-a1e3-4403-a1e6-ffbb857d85f3")


def report_email_target_id(owner_id: UUID) -> UUID:
    return uuid5(_NAMESPACE, str(owner_id))


def email_target_eligible_in_transaction(
    session: Session, *, owner_id: UUID, target: NotificationTarget
) -> bool:
    if target.id != report_email_target_id(owner_id):
        return True
    email = load_bound_notification_email_in_transaction(session, owner_id=owner_id)
    return (
        email is not None
        and target.channel == "email"
        and target.recipients == [email]
        and target.subscriptions == ["report"]
    )


class ReportEmailSubscriptionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session, self._settings = session, settings

    def read(self, *, owner_id: UUID) -> ReportEmailSubscriptionView:
        target = self._session.scalar(
            select(NotificationTarget).where(
                NotificationTarget.owner_id == owner_id,
                NotificationTarget.id == report_email_target_id(owner_id),
            )
        )
        email = load_bound_notification_email_in_transaction(self._session, owner_id=owner_id)
        return self._view(email, target)

    def save(
        self, *, owner_id: UUID, command: ReportEmailSubscriptionInput
    ) -> ReportEmailSubscriptionView:
        self._session.rollback()
        now = datetime.now(UTC)
        with self._session.begin():
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"report-email-subscription:{owner_id}"},
            )
            _audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="notification.email-subscription",
                target_ref=str(report_email_target_id(owner_id)),
                reason="用户更新个人报告邮件订阅",
                actor="user",
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                state = load_completed_audit_in_transaction(
                    self._session, owner_id=owner_id, operation_id=command.operation_id
                )
                if state is None:
                    raise ApplicationError("operations_revision_conflict")
                return ReportEmailSubscriptionView.model_validate(state)
            email = load_bound_notification_email_in_transaction(self._session, owner_id=owner_id)
            target = self._session.scalar(
                select(NotificationTarget)
                .where(
                    NotificationTarget.owner_id == owner_id,
                    NotificationTarget.id == report_email_target_id(owner_id),
                )
                .with_for_update()
            )
            if command.expected_revision != (target.revision if target else 0):
                raise ApplicationError("operations_revision_conflict")
            if command.enabled and email is None:
                raise ApplicationError("notification_email_not_bound")
            if target is None and email is not None:
                # The subscription advisory lock serializes first creation and revision CAS.
                if (
                    self._session.scalar(
                        select(NotificationTarget.id).where(
                            NotificationTarget.owner_id == owner_id,
                            NotificationTarget.name == REPORT_EMAIL_TARGET_NAME,
                        )
                    )
                    is not None
                ):
                    raise ApplicationError("operations_revision_conflict")
                target = NotificationTarget(
                    id=report_email_target_id(owner_id),
                    owner_id=owner_id,
                    name=REPORT_EMAIL_TARGET_NAME,
                    channel="email",
                    recipients=[email],
                    secret_env=None,
                    enabled=command.enabled,
                    enabled_at=now if command.enabled else None,
                    revision=1,
                    subscriptions=["report"],
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(target)
            elif target is not None:
                changed = target.enabled != command.enabled or (
                    command.enabled and target.recipients != [email]
                )
                if changed:
                    target.enabled = command.enabled
                    if command.enabled:
                        assert email is not None
                        target.recipients = [email]
                    target.enabled_at = now if command.enabled else None
                    target.revision += 1
                    target.updated_at = now
            self._session.flush()
            result = self._view(email, target)
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=result.model_dump(mode="json"),
                now=now,
            )
            return result

    def _view(
        self, email: str | None, target: NotificationTarget | None
    ) -> ReportEmailSubscriptionView:
        settings = self._settings
        matches = target is not None and email is not None and target.recipients == [email]
        return ReportEmailSubscriptionView(
            email=email,
            enabled=bool(target and target.enabled and matches),
            revision=target.revision if target else 0,
            target_name=REPORT_EMAIL_TARGET_NAME,
            email_matches_target=matches,
            delivery_available=bool(
                settings.notifications_enabled
                and settings.notification_smtp_enabled
                and settings.notification_smtp_host
                and settings.notification_smtp_from_email
            ),
        )
