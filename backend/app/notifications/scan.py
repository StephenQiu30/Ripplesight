from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionFailure,
    JobExecutionService,
    ScheduleWindow,
    scheduled_operation_id,
)
from jobs.operator_maintenance import accept_notification_scan_in_transaction
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from monitors.notification_preferences import load_topic_notification_target_names_in_transaction
from notifications.admission import enqueue_subject_in_transaction
from notifications.materials import load_notification_material_in_transaction
from notifications.models import NotificationTarget
from notifications.schemas import NotificationSubjectKind
from publication.notification_reading import list_selected_notification_candidates_in_transaction
from reports.notification_reading import (
    list_first_final_notification_editions_in_transaction,
    list_first_final_notification_reports_in_transaction,
)

_NAMESPACE = UUID("0401bf9f-8e09-4b35-a975-14f6c16a19ed")
_SECTIONS: tuple[NotificationSubjectKind, ...] = ("report", "edition", "selected")


def enqueue_notification_scans_in_transaction(
    session: Session, *, settings: Settings, now: datetime
) -> int:
    if not settings.notifications_enabled:
        return 0
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("notification scan schedule requires aware caller transaction")
    start = datetime.fromtimestamp(int(now.timestamp()) // 300 * 300, UTC)
    accepted = 0
    for target in session.scalars(
        select(NotificationTarget).where(NotificationTarget.enabled.is_(True))
    ):
        if not set(target.subscriptions).intersection(_SECTIONS):
            continue
        if (target.enabled_at or target.created_at) > start:
            # Freeze the window boundary deterministically; first scan waits for the next window.
            continue
        result = accept_notification_scan_in_transaction(
            session,
            now=now,
            owner_id=target.owner_id,
            command=JobAcceptanceInput(
                operation_id=scheduled_operation_id(
                    target.owner_id,
                    "notification.scan",
                    f"notification:{target.id.hex}:{target.revision}",
                    ScheduleWindow(start=start, end=start + timedelta(minutes=5)),
                ),
                kind="notification.scan",
                observation=JobObservationContext(
                    configuration_ref=f"notification-target:{target.id}",
                    configuration_version=target.revision,
                ),
                scope={
                    "target_id": str(target.id),
                    "target_revision": target.revision,
                    "enabled_at": (target.enabled_at or target.created_at)
                    .astimezone(UTC)
                    .isoformat(),
                    "scan_at": start.isoformat(),
                    "section": 0,
                    "cursor": None,
                },
            ),
        )
        accepted += result
    return accepted


class NotificationScanExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._sessions, self._settings, self._clock = (
            sessions,
            settings,
            clock or (lambda: datetime.now(UTC)),
        )

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if message.kind != "notification.scan" or lease.job_id != message.job_id:
            raise ValueError("notification scan job/lease mismatch")
        if not self._settings.notifications_enabled:
            raise self._failure("notification_disabled")
        current = lease
        for _ in range(50):
            with self._sessions() as session, session.begin():
                execution = JobExecutionService(
                    session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
                )
                current = execution.require_current_operation_in_transaction(
                    current, owner_id=message.owner_id, operation_id=message.operation_id
                )
                configuration = load_job_execution_configuration(session, job_id=message.job_id)
                if (
                    configuration is None
                    or configuration.kind != message.kind
                    or configuration.observation.configuration_ref != message.configuration_ref
                    or configuration.observation.configuration_version
                    != message.configuration_version
                ):
                    raise self._failure("notification_scan_mismatch")
                scope = configuration.scope
                target_id = UUID(str(scope["target_id"]))
                target = session.scalar(
                    select(NotificationTarget).where(
                        NotificationTarget.id == target_id,
                        NotificationTarget.owner_id == message.owner_id,
                    )
                )
                enabled_at = datetime.fromisoformat(str(scope["enabled_at"]))
                scan_at = datetime.fromisoformat(str(scope["scan_at"]))
                if enabled_at.utcoffset() is None or scan_at.utcoffset() is None:
                    raise self._failure("notification_scan_mismatch")
                if (
                    target is None
                    or not target.enabled
                    or target.revision != scope["target_revision"]
                    or (target.enabled_at or target.created_at) != enabled_at
                ):
                    raise self._failure("notification_target_stale")
                section = int(str(current.checkpoint.get("notification.section", scope["section"])))
                cursor_text = current.checkpoint.get("notification.cursor", scope.get("cursor"))
                cursor = UUID(str(cursor_text)) if cursor_text else None
                if section >= len(_SECTIONS):
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                kind = _SECTIONS[section]
                next_cursor = None
                if kind in target.subscriptions:
                    next_cursor = self._page(
                        session, message.owner_id, target, kind, cursor, enabled_at, scan_at
                    )
                if next_cursor is not None and cursor is not None and next_cursor.int <= cursor.int:
                    raise self._failure("notification_scan_cursor_invalid")
                next_section = section if next_cursor else section + 1
                current = execution.save_checkpoint_in_transaction(
                    current,
                    sequence=current.checkpoint_sequence + 1,
                    checkpoint={
                        "notification.section": next_section,
                        "notification.cursor": str(next_cursor) if next_cursor else None,
                    },
                )
                if next_section >= len(_SECTIONS):
                    return JobCompletion(status=JobStatus.SUCCEEDED)
        # Each continuation advances a real typed page. It cannot loop on an empty cursor.
        with self._sessions() as session, session.begin():
            JobExecutionService(
                session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
            ).require_current_operation_in_transaction(
                current, owner_id=message.owner_id, operation_id=message.operation_id
            )
            JobService(session, clock=self._clock).accept_in_transaction(
                owner_id=message.owner_id,
                command=JobAcceptanceInput(
                    operation_id=uuid5(_NAMESPACE, f"{message.operation_id}:{current.checkpoint}"),
                    kind="notification.scan",
                    observation=JobObservationContext(
                        configuration_ref=message.configuration_ref,
                        configuration_version=message.configuration_version,
                    ),
                    scope={
                        **scope,
                        "section": current.checkpoint["notification.section"],
                        "cursor": current.checkpoint["notification.cursor"],
                    },
                ),
            )
        return JobCompletion(status=JobStatus.SUCCEEDED)

    def _page(
        self,
        session: Session,
        owner: UUID,
        target: NotificationTarget,
        kind: NotificationSubjectKind,
        cursor: UUID | None,
        enabled_at: datetime,
        scan_at: datetime,
    ) -> UUID | None:
        now = self._clock()
        references: list[tuple[UUID, int]] = []
        if kind == "report":
            page = list_first_final_notification_reports_in_transaction(
                session, owner_id=owner, enabled_at=enabled_at, now=now, after_report_id=cursor
            )
            names = load_topic_notification_target_names_in_transaction(
                session,
                owner_id=owner,
                topic_ids=tuple({report.topic_id for report in page.reports}),
            )
            references = [
                (report.report_id, report.version)
                for report in page.reports
                if target.name in names.get(report.topic_id, ())
            ]
            next_cursor = page.next_after_report_id
        elif kind == "edition":
            editions = list_first_final_notification_editions_in_transaction(
                session, owner_id=owner, enabled_at=enabled_at, now=now, after_edition_id=cursor
            )
            references = [(item.edition_id, item.revision) for item in editions.editions]
            next_cursor = editions.next_after_edition_id
        else:
            selected = list_selected_notification_candidates_in_transaction(
                session, owner_id=owner, enabled_at=enabled_at, now=now, after_content_id=cursor
            )
            references = [
                (item.content_id, item.publication_revision) for item in selected.candidates
            ]
            next_cursor = selected.next_after_content_id
        for identity, revision in references:
            material = load_notification_material_in_transaction(
                session,
                owner_id=owner,
                kind=kind,
                subject_id=identity,
                revision=revision,
                locator={},
                now=now,
            )
            if material is not None and material.occurred_at <= scan_at:
                enqueue_subject_in_transaction(
                    session, owner_id=owner, material=material, now=now, target_ids=(target.id,)
                )
        return next_cursor

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self._clock(),
            next_action="核对通知目标版本与扫描进度",
            manual_retry_allowed=False,
        )
