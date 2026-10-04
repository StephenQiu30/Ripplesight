from datetime import datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from monitors.codex_schemas import NotificationIntent
from notifications.codex_recipients import codex_recipient_eligible_in_transaction
from notifications.email_subscription import email_target_eligible_in_transaction
from notifications.materials import load_notification_material_in_transaction
from notifications.models import NotificationDelivery, NotificationTarget
from notifications.schemas import NotificationSubjectMaterial
from notifications.services import DELIVERY_OPERATION_NAMESPACE, delivery_operation_id


def subject_delivery_operation_id(
    material: NotificationSubjectMaterial, *, owner_id: UUID, target_id: UUID
) -> UUID:
    if material.kind == "report":
        return delivery_operation_id(
            report_id=material.subject_id, version=material.revision, target_id=target_id
        )
    return uuid5(
        DELIVERY_OPERATION_NAMESPACE,
        f"{owner_id}:{material.kind}:{target_id}:{material.dedupe_key}",
    )


def enqueue_subject_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    material: NotificationSubjectMaterial,
    now: datetime,
    target_ids: tuple[UUID, ...] | None = None,
) -> int:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("notification admission requires aware caller transaction")
    if material.occurred_at > now or (
        material.expires_at is not None and material.expires_at <= now
    ):
        return 0
    query = select(NotificationTarget).where(
        NotificationTarget.owner_id == owner_id, NotificationTarget.enabled.is_(True)
    )
    if target_ids is not None:
        query = query.where(NotificationTarget.id.in_(target_ids))
    accepted = 0
    for target in session.scalars(query.with_for_update()):
        if material.kind not in target.subscriptions or material.occurred_at < (
            target.enabled_at or target.created_at
        ):
            continue
        if not email_target_eligible_in_transaction(session, owner_id=owner_id, target=target):
            continue
        if not codex_recipient_eligible_in_transaction(
            session, owner_id=owner_id, target_id=target.id, material=material
        ):
            continue
        delivery_id = uuid4()
        payload = material.model_dump(mode="json")
        inserted = session.execute(
            insert(NotificationDelivery)
            .values(
                id=delivery_id,
                owner_id=owner_id,
                report_id=material.subject_id if material.kind == "report" else None,
                report_version=material.revision,
                subject_kind=material.kind,
                subject_id=material.subject_id if material.kind != "report" else None,
                target_id=target.id,
                target_revision=target.revision,
                input_fingerprint=bytes.fromhex(material.fingerprint),
                frozen_payload=payload,
                provider_receipt={},
                dedupe_key=material.dedupe_key,
                status="pending",
                attempt_count=0,
                revision=1,
                expires_at=material.expires_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
            .returning(NotificationDelivery.id)
        ).scalar_one_or_none()
        if inserted is None:
            continue
        JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=subject_delivery_operation_id(
                    material, owner_id=owner_id, target_id=target.id
                ),
                kind="notification.send",
                scope={"delivery_id": str(delivery_id)},
                observation=JobObservationContext(
                    configuration_ref=f"report:{material.subject_id}"
                    if material.kind == "report"
                    else f"notification:{delivery_id.hex}",
                    configuration_version=material.revision,
                ),
            ),
        )
        accepted += 1
    return accepted


def enqueue_codex_notifications_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    monitor_id: UUID,
    intents: tuple[NotificationIntent, ...],
    now: datetime,
) -> int:
    if not session.in_transaction() or len(intents) > 20:
        raise RuntimeError("Codex notification admission requires bounded caller transaction")
    accepted = 0
    from monitors.codex_notification import read_codex_notification_in_transaction

    for intent in intents:
        actual = read_codex_notification_in_transaction(
            session, owner_id=owner_id, monitor_id=monitor_id, intent=intent, now=now
        )
        if actual is None:
            continue
        material = load_notification_material_in_transaction(
            session,
            owner_id=owner_id,
            kind="codex_reset",
            subject_id=uuid5(monitor_id, intent.event_id),
            revision=actual.event.revision,
            locator={"monitor_id": str(monitor_id), "intent": intent.model_dump(mode="json")},
            now=now,
        )
        if material is not None:
            accepted += enqueue_subject_in_transaction(
                session, owner_id=owner_id, material=material, now=now
            )
    return accepted
