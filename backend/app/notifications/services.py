from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.config import Settings
from core.errors import ApplicationError
from notifications.models import NotificationTarget
from notifications.schemas import (
    NotificationChannel,
    TargetInput,
    TargetSaveInput,
    TargetView,
)
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)

DELIVERY_OPERATION_NAMESPACE = UUID("8acccf68-f7a3-4f27-bc8c-70d41a20b175")


def delivery_operation_id(*, report_id: UUID, version: int, target_id: UUID) -> UUID:
    return uuid5(DELIVERY_OPERATION_NAMESPACE, f"{report_id}:{version}:{target_id}")


class NotificationTargetService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_in_transaction(
        self, *, owner_id: UUID, target: TargetInput, now: datetime
    ) -> TargetView:
        if not self._session.in_transaction():
            raise RuntimeError("target creation requires the caller's transaction")
        if target.channel is NotificationChannel.FEISHU and target.recipients:
            raise ValueError("Feishu webhook targets have no recipients")
        if (
            self._session.scalar(
                select(NotificationTarget.id).where(
                    NotificationTarget.owner_id == owner_id, NotificationTarget.name == target.name
                )
            )
            is not None
        ):
            raise ValueError("notification target name already exists")
        model = NotificationTarget(
            id=uuid4(),
            owner_id=owner_id,
            name=target.name,
            channel=target.channel.value,
            recipients=list(target.recipients),
            secret_env=target.secret_env,
            enabled=target.enabled,
            enabled_at=now if target.enabled else None,
            revision=1,
            subscriptions=list(target.subscriptions),
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        self._session.flush()
        return self._view(model)

    def list(self, *, owner_id: UUID) -> tuple[TargetView, ...]:
        rows = self._session.scalars(
            select(NotificationTarget)
            .where(NotificationTarget.owner_id == owner_id)
            .order_by(NotificationTarget.name)
        ).all()
        return tuple(self._view(row) for row in rows)

    def save(self, *, owner_id: UUID, command: TargetSaveInput, now: datetime) -> TargetView:
        self._session.rollback()
        with self._session.begin():
            _audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="notification.target",
                target_ref=str(command.target_id or command.target.name),
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                state = load_completed_audit_in_transaction(
                    self._session, owner_id=owner_id, operation_id=command.operation_id
                )
                if state is None:
                    raise ApplicationError("operations_revision_conflict")
                return TargetView.model_validate(state)
            if command.target_id is None:
                if (
                    self._session.scalar(
                        select(NotificationTarget.id).where(
                            NotificationTarget.owner_id == owner_id,
                            NotificationTarget.name == command.target.name,
                        )
                    )
                    is not None
                ):
                    raise ApplicationError("operations_revision_conflict")
                result = self.add_in_transaction(owner_id=owner_id, target=command.target, now=now)
            else:
                row = self._session.scalar(
                    select(NotificationTarget)
                    .where(
                        NotificationTarget.owner_id == owner_id,
                        NotificationTarget.id == command.target_id,
                    )
                    .with_for_update()
                )
                if row is None:
                    raise ApplicationError("resource_not_found")
                if row.revision != command.expected_revision:
                    raise ApplicationError("operations_revision_conflict")
                if (
                    self._session.scalar(
                        select(NotificationTarget.id).where(
                            NotificationTarget.owner_id == owner_id,
                            NotificationTarget.name == command.target.name,
                            NotificationTarget.id != row.id,
                        )
                    )
                    is not None
                ):
                    raise ApplicationError("operations_revision_conflict")
                row.name, row.channel, row.recipients, row.secret_env = (
                    command.target.name,
                    command.target.channel.value,
                    list(command.target.recipients),
                    command.target.secret_env,
                )
                row.enabled, row.subscriptions = (
                    command.target.enabled,
                    list(command.target.subscriptions),
                )
                row.enabled_at = now if row.enabled else None
                row.revision += 1
                row.updated_at = now
                result = self._view(row)
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=result.model_dump(mode="json"),
                now=now,
            )
            return result

    @staticmethod
    def _view(model: NotificationTarget) -> TargetView:
        return TargetView(
            id=model.id,
            name=model.name,
            channel=NotificationChannel(model.channel),
            recipients=tuple(model.recipients),
            secret_env=model.secret_env,
            enabled=model.enabled,
            revision=model.revision,
            enabled_at=model.enabled_at,
            subscriptions=tuple(model.subscriptions),
            created_at=model.created_at,
        )


class NotificationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def enqueue_due_in_transaction(self, *, now: datetime) -> int:
        from notifications.scan import enqueue_notification_scans_in_transaction

        return enqueue_notification_scans_in_transaction(
            self._session, settings=self._settings, now=now
        )


def mark_interrupted_sending_in_transaction(
    session: Session, *, delivery_id: UUID, now: datetime
) -> None:
    if not session.in_transaction():
        raise RuntimeError("notification recovery requires caller transaction")
    session.execute(
        text("""
        UPDATE notification_deliveries SET status = 'unknown', revision=revision+1,
            last_error_code = 'notification_delivery_unknown', updated_at = :now
        WHERE id = :delivery_id AND status = 'sending'
            AND COALESCE(provider_receipt->>'status', '') NOT IN ('accepted', 'smtp_accepted')
    """),
        {"delivery_id": delivery_id, "now": now.astimezone(UTC)},
    )
