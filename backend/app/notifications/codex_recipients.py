"""Original announcement receipts define the audience for Codex corrections."""

from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from monitors.codex_schemas import NotificationIntent
from notifications.models import NotificationDelivery
from notifications.schemas import NotificationSubjectMaterial


def codex_recipient_eligible_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    target_id: UUID,
    material: NotificationSubjectMaterial,
) -> bool:
    """Pending and proven failed announcements never authorize amend/withdraw sends."""
    if not session.in_transaction():
        raise RuntimeError("Codex recipient history requires caller transaction")
    if material.kind != "codex_reset":
        return True
    try:
        monitor_id = UUID(str(material.locator["monitor_id"]))
        intent = NotificationIntent.model_validate(material.locator["intent"])
    except (KeyError, ValueError):
        return False
    if uuid5(monitor_id, intent.event_id) != material.subject_id:
        return False
    if intent.action not in {"amend", "withdraw"}:
        return True
    # Same monitor/event identity, exact owner and exact target; don't infer history
    # from current subscriptions or from another target's successful receipt.
    original = session.scalar(
        select(NotificationDelivery.id)
        .where(
            NotificationDelivery.owner_id == owner_id,
            NotificationDelivery.target_id == target_id,
            NotificationDelivery.subject_kind == "codex_reset",
            NotificationDelivery.subject_id == material.subject_id,
            NotificationDelivery.status.in_(("succeeded", "sending", "unknown")),
            NotificationDelivery.frozen_payload["locator"]["monitor_id"].as_string()
            == str(monitor_id),
            NotificationDelivery.frozen_payload["locator"]["intent"]["event_id"].as_string()
            == intent.event_id,
            NotificationDelivery.frozen_payload["locator"]["intent"]["action"].as_string()
            == "announce",
        )
        .order_by(NotificationDelivery.id)
        .limit(1)
        .with_for_update()
    )
    return original is not None
