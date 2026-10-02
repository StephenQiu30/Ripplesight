"""Domain-owned scheduler reads and a Worker assembly helper; no independent queue."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from ai.services import AiService
from core.config import Settings
from core.errors import ApplicationError
from monitors.codex_models import CodexResetMonitor, CodexResetMonitorVersion, CodexResetScanGap
from monitors.codex_scan import CodexResetScanService, ResetContextSource, ResetSource
from monitors.codex_schemas import (
    CodexMonitorDue,
    CodexTickResult,
    MonitorConfiguration,
    MonitorView,
    ScanAuthorization,
)
from monitors.codex_services import CodexNotificationAdmission, CodexResetService
from monitors.codex_time import aware

type SourceFactory = Callable[
    [Session, MonitorView, UUID | None],
    tuple[ResetSource | None, ResetContextSource | None, ScanAuthorization],
]
type NotificationSink = CodexNotificationAdmission


def list_due_codex_monitors_in_transaction(
    session: Session, *, now: datetime
) -> tuple[CodexMonitorDue, ...]:
    """Read domain due points; JobService/CollectionDueWindowService own admission and Outbox."""
    if not session.in_transaction():
        raise RuntimeError("Codex due read requires the scheduler transaction")
    current = aware(now)
    monitors = session.scalars(
        select(CodexResetMonitor)
        .where(CodexResetMonitor.enabled.is_(True))
        .order_by(CodexResetMonitor.owner_id, CodexResetMonitor.id)
    ).all()
    result = []
    for monitor in monitors:
        unknown = session.scalar(
            select(CodexResetScanGap.id)
            .where(
                CodexResetScanGap.owner_id == monitor.owner_id,
                CodexResetScanGap.monitor_id == monitor.id,
                CodexResetScanGap.state != "complete",
                CodexResetScanGap.failure_code.in_(
                    ("source_request_running", "source_unknown", "context_unknown")
                ),
            )
            .limit(1)
        )
        if unknown is not None:
            continue
        version = session.get(
            CodexResetMonitorVersion, (monitor.owner_id, monitor.id, monitor.configuration_version)
        )
        if version is None:
            raise RuntimeError("missing Codex configuration version")
        config = MonitorConfiguration.model_validate(version.configuration)
        interval = (
            config.hot_interval_seconds
            if monitor.hot_until and monitor.hot_until > current
            else config.normal_interval_seconds
        )
        due_at = (
            aware(monitor.last_attempt_at) + timedelta(seconds=interval)
            if monitor.last_attempt_at
            else aware(monitor.created_at)
        )
        if due_at <= current + timedelta(seconds=30):
            result.append(
                CodexMonitorDue(
                    owner_id=monitor.owner_id,
                    monitor_id=monitor.id,
                    configuration_version=monitor.configuration_version,
                    monitor_revision=monitor.revision,
                    due_at=due_at,
                    interval_seconds=interval,
                    configuration=config,
                )
            )
    return tuple(result)


class CodexResetExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        settings: Settings | None = None,
        source_factory: SourceFactory | None = None,
        ai_factory: Callable[[Session], AiService | None] | None = None,
        notification_sink: NotificationSink | None = None,
        execution_guard: Callable[[Session], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._source_factory = source_factory
        self._ai_factory = ai_factory
        self._notification_sink = notification_sink
        self._execution_guard = execution_guard
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        configuration_version: int,
        job_id: UUID | None = None,
        lookback_hours: int | None = None,
        force: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> CodexTickResult:
        is_cancelled = cancelled or (lambda: False)

        def current_execution(session: Session) -> bool:
            return not is_cancelled() and (
                self._execution_guard is None or self._execution_guard(session)
            )

        if is_cancelled():
            return CodexTickResult(status="cancelled", reason="cancelled")
        with self._sessions() as session:
            service = CodexResetService(
                session,
                clock=self._clock,
                settings=self._settings,
                execution_guard=current_execution,
                notification_sink=self._notification_sink,
            )
            monitor = service.get_monitor(owner_id=owner_id, monitor_id=monitor_id)
            if not monitor.enabled:
                return CodexTickResult(status="blocked", reason="monitor_disabled")
            if monitor.configuration_version != configuration_version:
                raise ApplicationError("codex_version_conflict")
            with session.begin():
                if not current_execution(session):
                    return CodexTickResult(status="blocked", reason="execution_not_current")
            bind = session.get_bind()
            if not isinstance(bind, Engine):
                raise RuntimeError("Codex executor requires an engine-owned session")
            # Hold one tick lock across source/model/push preparation, as the upstream tick did.
            # The scan's own short lock also protects independently requested collection rounds.
            with bind.connect() as lock_connection:
                acquired = lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                    {"key": f"codex-reset-tick:{owner_id}:{monitor_id}"},
                )
                lock_connection.commit()
                if not acquired:
                    return CodexTickResult(status="skipped", reason="overlapping_tick")
                try:
                    source, context_source, authorization = (None, None, ScanAuthorization())
                    if self._source_factory is not None:
                        source, context_source, authorization = self._source_factory(
                            session, monitor, job_id
                        )
                        if session.in_transaction():
                            raise RuntimeError(
                                "source factory must finish its admission transaction"
                            )
                    scanner = CodexResetScanService(
                        session,
                        source=source,
                        context_source=context_source,
                        execution_guard=current_execution,
                        cancelled=is_cancelled,
                        clock=self._clock,
                    )
                    collected = scanner.collect(
                        owner_id=owner_id,
                        monitor_id=monitor_id,
                        authorization=authorization,
                        lookback_hours=lookback_hours,
                        force=force,
                    )
                    if is_cancelled():
                        return CodexTickResult(
                            status="cancelled", reason="cancelled", collected=collected
                        )
                    if self._ai_factory is not None:
                        service = CodexResetService(
                            session,
                            ai=self._ai_factory(session),
                            settings=self._settings,
                            execution_guard=current_execution,
                            clock=self._clock,
                            notification_sink=self._notification_sink,
                        )
                    recovered_notifications = service.enqueue_pending_notifications(
                        owner_id=owner_id, monitor_id=monitor_id
                    )
                    result = service.process_pending(
                        owner_id=owner_id,
                        monitor_id=monitor_id,
                        job_id=job_id,
                        cancelled=is_cancelled,
                    )
                    if is_cancelled():
                        return CodexTickResult(
                            status="cancelled",
                            reason="cancelled",
                            collected=collected,
                            processed=result["processed"],
                            failed=result["failed"],
                        )
                    with session.begin():
                        if not current_execution(session):
                            return CodexTickResult(
                                status="blocked",
                                reason="execution_not_current",
                                collected=collected,
                                processed=result["processed"],
                                failed=result["failed"],
                            )
                    intents = service.notification_intents(owner_id=owner_id, monitor_id=monitor_id)
                    enqueued = recovered_notifications + result["notifications_enqueued"]
                    snap = service.snapshot(owner_id=owner_id, monitor_id=monitor_id)
                    verified = False
                    if (
                        collected.status in {"collected", "skipped"}
                        and snap.monitor.last_collected_at
                    ):
                        verified = service.verify_if_complete(
                            owner_id=owner_id,
                            monitor_id=monitor_id,
                            collected_at=snap.monitor.last_collected_at,
                        )
                    status = (
                        "blocked"
                        if collected.status == "blocked"
                        else "partial"
                        if (
                            collected.status == "partial"
                            or result["failed"]
                            or snap.monitor.pending_count
                            or snap.monitor.review_count
                            or snap.monitor.held_window_count
                            or (intents and self._notification_sink is None)
                        )
                        else "succeeded"
                    )
                    return CodexTickResult.model_validate(
                        {
                            "status": status,
                            "reason": collected.reason,
                            "collected": collected,
                            "processed": result["processed"],
                            "failed": result["failed"],
                            "notification_intents": intents,
                            "notifications_enqueued": enqueued,
                            "verified": verified,
                        }
                    )
                finally:
                    close_source = getattr(source, "close", None)
                    if close_source is not None:
                        close_source()
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                        {"key": f"codex-reset-tick:{owner_id}:{monitor_id}"},
                    )
                    lock_connection.commit()
