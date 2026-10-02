from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from jobs.operator_maintenance import record_operator_notification_resolution_in_transaction
from notifications.models import NotificationDelivery
from notifications.schemas import (
    DeliveryResolutionInput,
    DeliveryStatus,
    NotificationDeliveryView,
    NotificationSubjectKind,
)
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)


class NotificationOperatorService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] | None = None):
        self._session, self._clock = session, clock or (lambda: datetime.now(UTC))

    def list_deliveries(
        self, *, owner_id: UUID, cursor: UUID | None = None, limit: int = 50
    ) -> tuple[tuple[NotificationDeliveryView, ...], UUID | None]:
        if not 1 <= limit <= 100:
            raise ValueError("delivery read limit must be bounded")
        self._session.rollback()
        try:
            query = select(NotificationDelivery).where(NotificationDelivery.owner_id == owner_id)
            if cursor is not None:
                query = query.where(NotificationDelivery.id > cursor)
            rows = list(
                self._session.scalars(query.order_by(NotificationDelivery.id).limit(limit + 1))
            )
            return tuple(self._view(row) for row in rows[:limit]), rows[limit - 1].id if len(
                rows
            ) > limit else None
        finally:
            self._session.rollback()

    def resolve(
        self, *, owner_id: UUID, delivery_id: UUID, command: DeliveryResolutionInput
    ) -> NotificationDeliveryView:
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            _audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="notification.resolve",
                target_ref=str(delivery_id),
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                saved = load_completed_audit_in_transaction(
                    self._session, owner_id=owner_id, operation_id=command.operation_id
                )
                if saved is None:
                    raise ApplicationError("operations_revision_conflict")
                return NotificationDeliveryView.model_validate(saved)
            row = self._session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.owner_id == owner_id,
                    NotificationDelivery.id == delivery_id,
                )
                .with_for_update()
            )
            if row is None:
                raise ApplicationError("resource_not_found")
            if row.status != "unknown" or row.revision != command.expected_revision:
                raise ApplicationError("operations_revision_conflict")
            if row.attempt_count >= 3 and command.outcome == "not_delivered":
                raise ApplicationError("operations_revision_conflict")
            try:
                record_operator_notification_resolution_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    delivery_id=delivery_id,
                    delivered=command.outcome == "delivered",
                    now=now,
                )
            except ValueError:
                raise ApplicationError("operations_revision_conflict") from None
            row.status = "succeeded" if command.outcome == "delivered" else "failed"
            row.last_error_code = (
                "operator_confirmed_delivery"
                if command.outcome == "delivered"
                else "operator_confirmed_not_delivered"
            )
            row.sent_at = now if command.outcome == "delivered" else None
            row.provider_receipt = {
                "transport": "operator",
                "status": command.outcome,
                "operation_id": str(command.operation_id),
                "confirmed_at": now.isoformat(),
            }
            row.revision, row.updated_at = row.revision + 1, now
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
    def _view(row: NotificationDelivery) -> NotificationDeliveryView:
        identity = row.report_id if row.subject_kind == "report" else row.subject_id
        if identity is None:
            raise ValueError("notification subject identity missing")
        return NotificationDeliveryView(
            id=row.id,
            revision=row.revision,
            target_id=row.target_id,
            target_revision=row.target_revision,
            subject_kind=cast(NotificationSubjectKind, row.subject_kind),
            subject_id=identity,
            subject_revision=row.report_version,
            status=DeliveryStatus(row.status),
            attempt_count=row.attempt_count,
            last_error_code=row.last_error_code,
            sent_at=row.sent_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provider_receipt=row.provider_receipt,
        )
