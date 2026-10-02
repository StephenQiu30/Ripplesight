"""Official announcement Job entry with original lease/AI/notification composition."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError
from ai.services import AiService, create_ai_client
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionError,
    JobExecutionFailure,
    JobExecutionService,
)
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration
from monitors.codex_execution import CodexResetExecutor, NotificationSink
from monitors.codex_runtime import ConfiguredCodexSourceFactory
from monitors.codex_services import CodexResetService


class CodexResetJobExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        notification_sink: NotificationSink | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sessions, self._settings, self._lease_seconds, self._clock = (
            sessions,
            settings,
            lease_seconds,
            clock,
        )
        self._sink, self._transport = notification_sink, transport

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion | None:
        if message.kind != "monitor.codex_reset.tick":
            raise ValueError("Codex executor received another kind")
        if not self._settings.codex_resets_enabled:
            raise self._failure("codex_monitor_disabled")
        deadline = monotonic() + 600 + 20 * self._settings.ai_execution_timeout_seconds - 60
        frozen_monitor: tuple[UUID, int] | None = None

        def stopped() -> bool:
            return (cancelled is not None and cancelled()) or monotonic() >= deadline

        def guard(session: Session) -> bool:
            if stopped():
                return False
            try:
                JobExecutionService(
                    session, lease_seconds=self._lease_seconds, clock=self._clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=message.owner_id, operation_id=message.operation_id
                )
                if frozen_monitor is not None:
                    current = CodexResetService(
                        session, clock=self._clock, settings=self._settings
                    )._monitor(message.owner_id, frozen_monitor[0], lock=True)
                    if (
                        not current.enabled
                        or current.revision != frozen_monitor[1]
                        or current.configuration_version != message.configuration_version
                    ):
                        return False
                return True
            except (JobExecutionError, ApplicationError):
                return False

        with self._sessions.begin() as session:
            if not guard(session):
                return None
            config = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                config is None
                or config.kind != message.kind
                or config.owner_id != message.owner_id
                or config.operation_id != message.operation_id
                or config.observation.configuration_ref != message.configuration_ref
                or config.observation.configuration_version != message.configuration_version
                or config.observation.source_key != message.source_key
                or config.observation.source_capability != message.source_capability
            ):
                raise self._failure("codex_job_mismatch")
            try:
                monitor_id = UUID(str(config.scope["monitor_id"]))
                expected_revision = int(str(config.scope["revision"]))
                if expected_revision < 1:
                    raise ValueError
                lookback = config.scope.get("lookback_hours")
                lookback_hours = int(str(lookback)) if lookback is not None else None
                if lookback_hours is not None and not 1 <= lookback_hours <= 168:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                raise self._failure("codex_job_mismatch") from None
            current_monitor = CodexResetService(
                session, clock=self._clock, settings=self._settings
            )._monitor(message.owner_id, monitor_id, lock=True)
            if current_monitor.revision != expected_revision:
                raise self._failure("codex_job_mismatch")
            frozen_monitor = (monitor_id, expected_revision)
        clients = []

        def ai(session: Session) -> AiService | None:
            if not self._settings.ai_enabled:
                return None
            try:
                client = create_ai_client(self._settings)
            except AiCallError:
                return None
            clients.append(client)
            return AiService(
                session,
                client,
                clock=self._clock,
                settings=self._settings,
                guard=lambda current: JobExecutionService(
                    current, lease_seconds=self._lease_seconds, clock=self._clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=message.owner_id, operation_id=message.operation_id
                ),
                execution_epoch=lease.epoch,
            )

        source = ConfiguredCodexSourceFactory(
            self._sessions,
            self._settings,
            message,
            lease,
            lease_seconds=self._lease_seconds,
            cancelled=stopped,
            clock=self._clock,
            transport=self._transport,
            expected_revision=expected_revision,
        )
        try:
            result = CodexResetExecutor(
                self._sessions,
                settings=self._settings,
                source_factory=source,
                ai_factory=ai,
                notification_sink=self._sink,
                execution_guard=guard,
                clock=self._clock,
            ).execute(
                owner_id=message.owner_id,
                monitor_id=monitor_id,
                configuration_version=message.configuration_version,
                job_id=message.job_id,
                lookback_hours=lookback_hours,
                force=config.scope.get("force") is True,
                cancelled=stopped,
            )
        except ApplicationError as error:
            raise self._failure(error.code) from None
        finally:
            for client in clients:
                client.close()
        if cancelled and cancelled():
            return None
        if result.status == "succeeded":
            return JobCompletion(status=JobStatus.SUCCEEDED)
        return JobCompletion(
            status=JobStatus.PARTIALLY_SUCCEEDED,
            failure=self._failure(result.reason or "codex_reset_partial"),
        )

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self._clock(),
            next_action="核验官方X准入、模型预算和来源/识别未知回执; 在公告运营页带原因复核",
            manual_retry_allowed=False,
        )
