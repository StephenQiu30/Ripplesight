from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from jobs.operator_budgets import save_operator_budget_in_transaction
from jobs.operator_maintenance import record_operator_delivery_resolution_in_transaction
from jobs.schemas import BudgetPolicyView, JobAcceptanceInput, JobObservationContext
from jobs.services import BudgetPolicyConflictError, JobService, ResourceBudgetService
from operations.attachments import validate_screenshot
from operations.models import (
    DictionaryVersion,
    Feedback,
    FeedbackAttachment,
    FeedbackCooldown,
    OperatorAuditOperation,
    ProcessHeartbeat,
)
from operations.schemas import (
    AuditResolutionInput,
    BudgetUpdateInput,
    DictionaryInput,
    DictionaryView,
    FeedbackInput,
    FeedbackSubmissionView,
    FeedbackUpdateInput,
    FeedbackUpdateView,
    FeedbackView,
    MaintenanceAcceptedView,
    MaintenanceInput,
    OperationsHealthView,
    OperatorAuditView,
    ProcessHeartbeatView,
)


def _fingerprint(payload: object) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).digest()


def _lock_operation(session: Session, owner: UUID, operation: UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"operations:{owner}:{operation}"},
    )


def accept_audit_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    operation_id: UUID,
    action: str,
    target_ref: str,
    reason: str,
    payload: dict[str, object],
    now: datetime,
    before_state: dict[str, object] | None = None,
    actor: str = "operator",
) -> tuple[OperatorAuditOperation, bool]:
    if not session.in_transaction():
        raise RuntimeError("operator audit requires caller transaction")
    if not reason.strip():
        raise ApplicationError("invalid_operations_input")
    _lock_operation(session, owner_id, operation_id)
    fingerprint = _fingerprint(
        {"action": action, "target_ref": target_ref, "reason": reason, "payload": payload}
    )
    existing = session.scalar(
        select(OperatorAuditOperation)
        .where(
            OperatorAuditOperation.owner_id == owner_id,
            OperatorAuditOperation.operation_id == operation_id,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise ApplicationError("idempotency_conflict")
        return existing, True
    row = OperatorAuditOperation(
        id=uuid4(),
        owner_id=owner_id,
        operation_id=operation_id,
        input_fingerprint=fingerprint,
        action=action,
        target_ref=target_ref,
        actor=actor,
        reason=reason.strip(),
        status="accepted",
        before_state=before_state or {},
        after_state={},
        job_id=None,
        error_code=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row, False


def load_current_dictionaries_in_transaction(
    session: Session, *, owner_id: UUID
) -> dict[str, DictionaryView]:
    if not session.in_transaction():
        raise RuntimeError("dictionary reads require caller transaction")
    return {
        row.kind: DictionaryView.model_validate(row, from_attributes=True)
        for row in session.scalars(
            select(DictionaryVersion).where(
                DictionaryVersion.owner_id == owner_id, DictionaryVersion.active.is_(True)
            )
        )
    }


def complete_audit_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    operation_id: UUID,
    after_state: dict[str, object],
    now: datetime | None = None,
) -> None:
    if not session.in_transaction():
        raise RuntimeError("audit completion requires caller transaction")
    row = session.scalar(
        select(OperatorAuditOperation)
        .where(
            OperatorAuditOperation.owner_id == owner_id,
            OperatorAuditOperation.operation_id == operation_id,
        )
        .with_for_update()
    )
    if row is None or row.status not in {"accepted", "succeeded"}:
        raise ApplicationError("operations_revision_conflict")
    if row.status == "succeeded" and row.after_state != after_state:
        raise ApplicationError("idempotency_conflict")
    row.status, row.after_state, row.updated_at = "succeeded", after_state, now or datetime.now(UTC)


def load_completed_audit_in_transaction(
    session: Session, *, owner_id: UUID, operation_id: UUID
) -> dict[str, object] | None:
    if not session.in_transaction():
        raise RuntimeError("audit reads require caller transaction")
    row = session.scalar(
        select(OperatorAuditOperation).where(
            OperatorAuditOperation.owner_id == owner_id,
            OperatorAuditOperation.operation_id == operation_id,
            OperatorAuditOperation.status == "succeeded",
        )
    )
    return json.loads(json.dumps(row.after_state)) if row is not None else None


def list_action_audits_in_transaction(
    session: Session, *, owner_id: UUID, action: str, limit: int = 30
) -> tuple[OperatorAuditView, ...]:
    if not session.in_transaction():
        raise RuntimeError("audit reads require caller transaction")
    if not 1 <= limit <= 100 or not action.strip() or len(action) > 100:
        raise ValueError("audit action and bounded limit are required")
    rows = session.scalars(
        select(OperatorAuditOperation)
        .where(OperatorAuditOperation.owner_id == owner_id, OperatorAuditOperation.action == action)
        .order_by(
            OperatorAuditOperation.updated_at.desc(),
            OperatorAuditOperation.created_at.desc(),
            OperatorAuditOperation.id.desc(),
        )
        .limit(limit)
    )
    return tuple(OperatorAuditView.model_validate(row, from_attributes=True) for row in rows)


def accept_maintenance_in_transaction(
    session: Session, *, owner_id: UUID, command: MaintenanceInput, now: datetime
) -> MaintenanceAcceptedView:
    audit, replayed = accept_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=command.operation_id,
        action=f"maintenance.{command.action}",
        target_ref=str(command.backup_id) if command.backup_id else command.action,
        reason=command.reason,
        payload=command.model_dump(mode="json"),
        now=now,
    )
    if replayed:
        if audit.job_id is None:
            raise ApplicationError("operations_revision_conflict")
        return MaintenanceAcceptedView(job_id=audit.job_id, audit_id=audit.id, replayed=True)
    job = JobService(session).accept_in_transaction(
        owner_id=owner_id,
        command=JobAcceptanceInput(
            operation_id=command.operation_id,
            kind="operations.maintenance",
            observation=JobObservationContext(
                configuration_ref="operations:v1", configuration_version=1
            ),
            scope={
                "action": command.action,
                "audit_id": str(audit.id),
                "backup_id": str(command.backup_id) if command.backup_id else None,
            },
        ),
    )
    audit.job_id = job.id
    return MaintenanceAcceptedView(job_id=job.id, audit_id=audit.id)


def record_process_heartbeat_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    role: Literal["api", "worker", "scheduler", "watchdog"],
    instance_id: str,
    pid: int,
    state: Literal["alive", "stopping", "error"],
    now: datetime,
    started_at: datetime,
    detail: dict[str, object] | None = None,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None or started_at.utcoffset() is None:
        raise RuntimeError("heartbeat needs an aware caller transaction")
    if not 0 < len(instance_id) <= 128 or pid <= 0:
        raise ValueError("heartbeat identity is invalid")
    values = detail or {}
    if len(json.dumps(values)) > 4096:
        raise ValueError("heartbeat detail exceeds limit")
    session.execute(
        insert(ProcessHeartbeat)
        .values(
            id=uuid4(),
            owner_id=owner_id,
            role=role,
            instance_id=instance_id,
            pid=pid,
            state=state,
            last_seen_at=now,
            started_at=started_at,
            detail=values,
        )
        .on_conflict_do_update(
            constraint="operations_process_heartbeats_instance_key",
            set_={"state": state, "last_seen_at": now, "detail": values},
            where=ProcessHeartbeat.last_seen_at <= now,
        )
    )


class OperationsService:
    def __init__(
        self,
        session: Session,
        *,
        feedback_secret: str | None = None,
        clock: Callable[[], datetime] | None = None,
        maintenance_enabled: bool = False,
        feedback_forward_enabled: bool = False,
        backup_configured: bool = False,
    ) -> None:
        self._session, self._secret = session, feedback_secret
        self._clock = clock or (lambda: datetime.now(UTC))
        self._maintenance_enabled, self._forward_enabled, self._backup_configured = (
            maintenance_enabled,
            feedback_forward_enabled,
            backup_configured,
        )

    def submit_feedback(
        self, *, owner_id: UUID, command: FeedbackInput, client_ip: str, user_agent: str
    ) -> FeedbackSubmissionView:
        if not self._secret:
            raise ApplicationError("feedback_disabled")
        source_hash = hmac.new(
            self._secret.encode(), f"{client_ip}|{user_agent[:512]}".encode(), hashlib.sha256
        ).digest()
        screenshot = None
        if command.screenshot:
            try:
                data = base64.b64decode(command.screenshot.data_base64, validate=True)
                dimensions = validate_screenshot(data, command.screenshot.mime)
            except (ValueError, binascii.Error) as error:
                raise ApplicationError("invalid_feedback_input") from error
            screenshot = (data, dimensions, hashlib.sha256(data).digest())
        payload = command.model_dump(mode="json", exclude={"screenshot"})
        payload["screenshot_sha256"] = screenshot[2].hex() if screenshot else None
        payload["screenshot_mime"] = command.screenshot.mime if command.screenshot else None
        fingerprint = _fingerprint(payload)
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            _lock_operation(self._session, owner_id, command.operation_id)
            existing = self._session.scalar(
                select(Feedback)
                .where(Feedback.owner_id == owner_id, Feedback.operation_id == command.operation_id)
                .with_for_update()
            )
            if existing:
                if existing.input_fingerprint != fingerprint or existing.source_hash != source_hash:
                    raise ApplicationError("idempotency_conflict")
                return FeedbackSubmissionView(
                    id=existing.id,
                    operation_id=existing.operation_id,
                    status=existing.status,
                    replayed=True,
                )
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"feedback:{owner_id}:{source_hash.hex()}"},
            )
            cooldown = self._session.get(FeedbackCooldown, (owner_id, source_hash))
            if cooldown:
                if cooldown.banned:
                    raise ApplicationError("feedback_banned")
                if now < cooldown.available_at:
                    raise ApplicationError(
                        "feedback_rate_limited",
                        context={
                            "retry_after": max(
                                1, math.ceil((cooldown.available_at - now).total_seconds())
                            )
                        },
                    )
                cooldown.available_at = now + timedelta(seconds=60)
                cooldown.updated_at = now
            else:
                self._session.add(
                    FeedbackCooldown(
                        owner_id=owner_id,
                        source_hash=source_hash,
                        available_at=now + timedelta(seconds=60),
                        banned=False,
                        ban_reason=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            row = Feedback(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                source_hash=source_hash,
                input_fingerprint=fingerprint,
                content=command.content,
                email=command.email,
                page_url=command.page_url,
                status="new",
                revision=1,
                note=None,
                forwarded_at=None,
                forward_error=None,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
            self._session.flush()
            if screenshot and command.screenshot:
                data, (width, height), sha = screenshot
                self._session.add(
                    FeedbackAttachment(
                        id=uuid4(),
                        owner_id=owner_id,
                        feedback_id=row.id,
                        mime=command.screenshot.mime,
                        data=data,
                        sha256=sha,
                        width=width,
                        height=height,
                        created_at=now,
                    )
                )
            return FeedbackSubmissionView(
                id=row.id, operation_id=row.operation_id, status=row.status
            )

    def list_feedback(
        self,
        *,
        owner_id: UUID,
        status: str | None = None,
        cursor: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[FeedbackView], UUID | None]:
        if not 1 <= limit <= 100 or status not in {
            None,
            "new",
            "reviewing",
            "resolved",
            "rejected",
            "deleted",
        }:
            raise ApplicationError("invalid_operations_input")
        self._session.rollback()
        with self._session.begin():
            statement = select(Feedback).where(Feedback.owner_id == owner_id)
            if status is not None:
                statement = statement.where(Feedback.status == status)
            if cursor is not None:
                statement = statement.where(Feedback.id > cursor)
            rows = list(self._session.scalars(statement.order_by(Feedback.id).limit(limit + 1)))
            page = rows[:limit]
            return [self._feedback_view(row) for row in page], page[-1].id if len(
                rows
            ) > limit else None

    def _feedback_view(self, row: Feedback) -> FeedbackView:
        attachment = self._session.scalar(
            select(FeedbackAttachment).where(
                FeedbackAttachment.owner_id == row.owner_id,
                FeedbackAttachment.feedback_id == row.id,
            )
        )
        cooldown = self._session.get(FeedbackCooldown, (row.owner_id, row.source_hash))
        return FeedbackView(
            id=row.id,
            revision=row.revision,
            content=row.content,
            email=row.email,
            page_url=row.page_url,
            status=cast(Literal["new", "reviewing", "resolved", "rejected", "deleted"], row.status),
            note=row.note,
            source_ref=row.source_hash.hex()[:16],
            banned=bool(cooldown and cooldown.banned),
            attachment_id=attachment.id if attachment else None,
            attachment_mime=attachment.mime if attachment else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            forwarded_at=row.forwarded_at,
            forward_error=row.forward_error,
        )

    def update_feedback(
        self, *, owner_id: UUID, feedback_id: UUID, command: FeedbackUpdateInput
    ) -> FeedbackUpdateView:
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="feedback.update",
                target_ref=str(feedback_id),
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                return FeedbackUpdateView.model_validate({**audit.after_state, "replayed": True})
            row = self._session.scalar(
                select(Feedback)
                .where(Feedback.owner_id == owner_id, Feedback.id == feedback_id)
                .with_for_update()
            )
            if row is None:
                raise ApplicationError("resource_not_found")
            if row.revision != command.expected_revision or row.status == "deleted":
                raise ApplicationError("operations_revision_conflict")
            audit.before_state = {"id": str(row.id), "revision": row.revision, "status": row.status}
            row.status = command.status
            row.note = command.note
            row.revision += 1
            row.updated_at = now
            if command.status == "deleted":
                row.content = row.email = row.page_url = row.note = None
                self._session.execute(
                    delete(FeedbackAttachment).where(
                        FeedbackAttachment.owner_id == owner_id,
                        FeedbackAttachment.feedback_id == row.id,
                    )
                )
            if command.banned is not None:
                cooldown = self._session.get(FeedbackCooldown, (owner_id, row.source_hash))
                assert cooldown is not None
                cooldown.banned = command.banned
                cooldown.ban_reason = command.reason if command.banned else None
                cooldown.updated_at = now
            result = FeedbackUpdateView(id=row.id, revision=row.revision, status=row.status)
            audit.status = "succeeded"
            audit.after_state = result.model_dump(mode="json")
            audit.updated_at = now
            return result

    def read_attachment(self, *, owner_id: UUID, attachment_id: UUID) -> tuple[bytes, str]:
        self._session.rollback()
        with self._session.begin():
            row = self._session.scalar(
                select(FeedbackAttachment).where(
                    FeedbackAttachment.owner_id == owner_id, FeedbackAttachment.id == attachment_id
                )
            )
            if row is None:
                raise ApplicationError("resource_not_found")
            if hashlib.sha256(row.data).digest() != row.sha256:
                raise ApplicationError("invalid_feedback_input")
            return row.data, row.mime

    def list_audit(
        self, *, owner_id: UUID, cursor: UUID | None = None, limit: int = 50
    ) -> tuple[list[OperatorAuditView], UUID | None]:
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_operations_input")
        self._session.rollback()
        with self._session.begin():
            statement = select(OperatorAuditOperation).where(
                OperatorAuditOperation.owner_id == owner_id
            )
            if cursor is not None:
                statement = statement.where(OperatorAuditOperation.id > cursor)
            rows = list(
                self._session.scalars(
                    statement.order_by(OperatorAuditOperation.id).limit(limit + 1)
                )
            )
            return [
                OperatorAuditView.model_validate(row, from_attributes=True) for row in rows[:limit]
            ], rows[limit - 1].id if len(rows) > limit else None

    def resolve_delivery(
        self, *, owner_id: UUID, audit_id: UUID, command: AuditResolutionInput
    ) -> OperatorAuditView:
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            operation, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="delivery.resolve",
                target_ref=str(audit_id),
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                return OperatorAuditView.model_validate(operation.after_state)
            target = self._session.scalar(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.owner_id == owner_id,
                    OperatorAuditOperation.id == audit_id,
                )
                .with_for_update()
            )
            if (
                target is None
                or target.status != "unknown"
                or target.job_id is None
                or target.action
                not in {
                    "maintenance.alerts",
                    "maintenance.digest",
                    "maintenance.watchdog",
                    "maintenance.feedback_forward",
                    "maintenance.source_health",
                    "indexnow.submit",
                }
            ):
                raise ApplicationError("operations_revision_conflict")
            try:
                record_operator_delivery_resolution_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    job_id=target.job_id,
                    delivered=command.outcome == "delivered",
                    now=now,
                )
            except ValueError as error:
                raise ApplicationError("operations_revision_conflict") from error
            delivered = command.outcome == "delivered"
            target.status, target.error_code, target.updated_at = (
                "succeeded" if delivered else "failed",
                None if delivered else "operator_confirmed_not_delivered",
                now,
            )
            target.after_state = {
                **target.after_state,
                "delivered": delivered,
                "operator_confirmation": command.outcome,
                "confirmed_at": now.isoformat(),
            }
            ids = target.after_state.get("feedback_ids")
            if target.action == "maintenance.feedback_forward" and isinstance(ids, list):
                for row in self._session.scalars(
                    select(Feedback)
                    .where(
                        Feedback.owner_id == owner_id,
                        Feedback.id.in_([UUID(str(value)) for value in ids]),
                    )
                    .with_for_update()
                ):
                    row.forward_error = None
                    row.forwarded_at = now if delivered else None
            result = OperatorAuditView.model_validate(target, from_attributes=True)
            operation.status, operation.after_state, operation.updated_at = (
                "succeeded",
                result.model_dump(mode="json"),
                now,
            )
            return result

    def update_budget(self, *, owner_id: UUID, command: BudgetUpdateInput) -> BudgetPolicyView:
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="budget.update",
                target_ref=command.policy.budget_key,
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                return BudgetPolicyView.model_validate(audit.after_state)
            try:
                result = save_operator_budget_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    command=command.policy,
                    expected_policy_version=command.expected_policy_version,
                    now=now,
                )
            except (BudgetPolicyConflictError, ValueError) as error:
                raise ApplicationError("operations_revision_conflict") from error
            audit.status, audit.after_state, audit.updated_at = (
                "succeeded",
                result.model_dump(mode="json"),
                now,
            )
            return result

    def enqueue_maintenance(
        self, *, owner_id: UUID, command: MaintenanceInput
    ) -> MaintenanceAcceptedView:
        if not self._maintenance_enabled:
            raise ApplicationError("invalid_operations_input")
        if command.action in {"backup", "verify_backup"} and not self._backup_configured:
            raise ApplicationError("invalid_operations_input")
        if command.action == "feedback_forward" and not self._forward_enabled:
            raise ApplicationError("invalid_operations_input")
        self._session.rollback()
        with self._session.begin():
            return accept_maintenance_in_transaction(
                self._session, owner_id=owner_id, command=command, now=self._clock()
            )

    def save_dictionary(self, *, owner_id: UUID, command: DictionaryInput) -> DictionaryView:
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="dictionary.update",
                target_ref=command.kind,
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            if replayed:
                return DictionaryView.model_validate(audit.after_state)
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"dictionary:{owner_id}:{command.kind}"},
            )
            current = self._session.scalar(
                select(DictionaryVersion)
                .where(
                    DictionaryVersion.owner_id == owner_id,
                    DictionaryVersion.kind == command.kind,
                    DictionaryVersion.active.is_(True),
                )
                .with_for_update()
            )
            version = current.version if current else 0
            if version != command.expected_version:
                raise ApplicationError("operations_revision_conflict")
            if current:
                current.active = False
            self._session.flush()
            row = DictionaryVersion(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                kind=command.kind,
                version=version + 1,
                active=True,
                content=command.content,
                input_fingerprint=_fingerprint(command.content),
                created_by=owner_id,
                created_at=now,
            )
            self._session.add(row)
            self._session.flush()
            result = DictionaryView.model_validate(row, from_attributes=True)
            audit.before_state = {"version": version}
            audit.after_state = result.model_dump(mode="json")
            audit.status = "succeeded"
            audit.updated_at = now
            return result

    def list_dictionaries(self, *, owner_id: UUID) -> list[DictionaryView]:
        self._session.rollback()
        with self._session.begin():
            return list(
                load_current_dictionaries_in_transaction(self._session, owner_id=owner_id).values()
            )

    def get_health(self, *, owner_id: UUID) -> OperationsHealthView:
        # Existing job issue projection owns its transaction; compose its DTO first.
        failure_issues = JobService(self._session).list_continuous_failure_issues(owner_id=owner_id)
        self._session.rollback()
        now = self._clock()
        with self._session.begin():
            heartbeats = []
            for row in self._session.scalars(
                select(ProcessHeartbeat)
                .where(ProcessHeartbeat.owner_id == owner_id)
                .order_by(ProcessHeartbeat.last_seen_at.desc())
                .limit(100)
            ):
                age = max(0, int((now - row.last_seen_at).total_seconds()))
                heartbeats.append(
                    ProcessHeartbeatView(
                        role=row.role,
                        instance_id=row.instance_id,
                        pid=row.pid,
                        state="stale"
                        if age > 90
                        else cast(Literal["alive", "stopping", "error"], row.state),
                        last_seen_at=row.last_seen_at,
                        started_at=row.started_at,
                        age_seconds=age,
                        detail=row.detail,
                    )
                )
            counts = {
                key: count
                for key, count in self._session.execute(
                    select(Feedback.status, func.count())
                    .where(Feedback.owner_id == owner_id)
                    .group_by(Feedback.status)
                )
            }
            return OperationsHealthView(
                generated_at=now,
                heartbeats=heartbeats,
                failure_issues=list(failure_issues),
                budgets=list(
                    ResourceBudgetService(self._session, clock=self._clock).budget_usage_snapshot(
                        owner_id=owner_id
                    )
                ),
                feedback_new_count=counts.get("new", 0),
                feedback_reviewing_count=counts.get("reviewing", 0),
                maintenance_enabled=self._maintenance_enabled,
                feedback_forward_enabled=self._forward_enabled,
                backup_configured=self._backup_configured,
            )


def has_succeeded_action_target_in_transaction(
    session: Session, *, owner_id: UUID, action: str, target_ref: str
) -> bool:
    if not session.in_transaction() or not 0 < len(action) <= 100 or not 0 < len(target_ref) <= 500:
        raise ValueError("audit acknowledgement requires caller transaction and exact identity")
    return (
        session.scalar(
            select(OperatorAuditOperation.id)
            .where(
                OperatorAuditOperation.owner_id == owner_id,
                OperatorAuditOperation.action == action,
                OperatorAuditOperation.target_ref == target_ref,
                OperatorAuditOperation.status == "succeeded",
            )
            .limit(1)
        )
        is not None
    )
