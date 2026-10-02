"""Official X assembly reuses the editable-source HTTP and original budget ledger."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid5

import httpx
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_services import require_official_x_connection_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from evidence.services import SourceAccessUnavailableError
from jobs.execution import ExecutionLease, JobExecutionService
from jobs.schemas import JobMessage, XApiPostReadCost
from monitors.codex_schemas import ContextPost, MonitorView, ScanAuthorization
from monitors.codex_services import CodexResetService
from sources.adapters.editorial_http import EditorialHttpClient
from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.adapters.editorial_x_reset import OfficialXResetSearchSource
from sources.adapters.x_context import OfficialXContextReader
from sources.contracts import SourcePost
from sources.editorial_factory import EditorialRequestMeter
from sources.editorial_schemas import EditorialAuthorization


class _ResetContextBridge:
    def __init__(self, reader: OfficialXContextReader) -> None:
        self._reader = reader

    def context_for(self, post: SourcePost, *, max_reply_depth: int) -> tuple[ContextPost, ...]:
        return tuple(
            ContextPost.model_validate(item.model_dump())
            for item in self._reader.read_context(post, max_reply_depth=max_reply_depth)
        )


class ConfiguredCodexSourceFactory:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        lease_seconds: int = 30,
        cancelled: Callable[[], bool] = lambda: False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport: httpx.BaseTransport | None = None,
        expected_revision: int | None = None,
    ) -> None:
        self._sessions, self._settings, self._message, self._lease = (
            sessions,
            settings,
            message,
            lease,
        )
        self._lease_seconds, self._cancelled, self._clock, self._transport = (
            lease_seconds,
            cancelled,
            clock,
            transport,
        )
        self._expected_revision = expected_revision

    def __call__(
        self, session: Session, monitor: MonitorView, job_id: UUID | None
    ) -> tuple[OfficialXResetSearchSource | None, _ResetContextBridge | None, ScanAuthorization]:
        s, c, message = self._settings, monitor.configuration, self._message
        if (
            not s.editorial_x_authorized
            or s.editorial_x_token is None
            or s.editorial_x_post_unit_usd_micros is None
            or c.connection_id is None
            or c.connection_version is None
            or c.author_external_id is None
            or job_id != message.job_id
        ):
            return None, None, ScanAuthorization()

        connection_id, connection_version = c.connection_id, c.connection_version

        def admission(current: Session) -> None:
            if self._cancelled():
                raise ApplicationError("codex_monitor_disabled")
            JobExecutionService(
                current, lease_seconds=self._lease_seconds, clock=self._clock
            ).require_current_operation_in_transaction(
                self._lease,
                owner_id=message.owner_id,
                operation_id=message.operation_id,
            )
            live = CodexResetService(current, clock=self._clock)._monitor(
                message.owner_id, monitor.id, lock=True
            )
            if (
                not live.enabled
                or live.configuration_version != monitor.configuration_version
                or live.revision != monitor.revision
                or (
                    self._expected_revision is not None and live.revision != self._expected_revision
                )
            ):
                raise ApplicationError("codex_version_conflict")
            require_official_x_connection_in_transaction(
                current,
                owner_id=message.owner_id,
                connection_id=connection_id,
                connection_version=connection_version,
                now=self._clock(),
            )

        try:
            with session.begin():
                admission(session)
        except (ApplicationError, SourceAccessUnavailableError):
            return None, None, ScanAuthorization()

        def begin_request(current: Session) -> bool:
            _, allowed = JobExecutionService(
                current, lease_seconds=self._lease_seconds, clock=self._clock
            ).begin_request_in_transaction(self._lease)
            return allowed

        meter = EditorialRequestMeter(
            self._sessions,
            owner_id=message.owner_id,
            job_id=message.job_id,
            run_id=uuid5(message.job_id, "codex-official-source"),
            operation_id=message.operation_id,
            source_ref="x",
            connection_id=connection_id,
            admission=admission,
            begin_request=begin_request,
            x_quote=XApiPostReadCost(
                max_posts=100, unit_price_usd_micros=s.editorial_x_post_unit_usd_micros
            ),
            clock=self._clock,
        )
        http = EditorialHttpClient(
            allowed_hosts=frozenset({"api.x.com"}),
            authorization=EditorialAuthorization(
                connection_enabled=True,
                owner_authorized=True,
                credentials_ready=True,
                budget_confirmed=True,
            ),
            before_request=meter.before,
            settle_request=meter.settle,
            cancelled=self._cancelled,
            max_requests=25,
            max_seconds=90,
            transport=self._transport,
            allow_network=True,
        )
        client = OfficialEditorialXClient(
            http, bearer=s.editorial_x_token, report_posts=meter.report_x_posts
        )
        return (
            OfficialXResetSearchSource(client, http, clock=self._clock),
            _ResetContextBridge(OfficialXContextReader(client)),
            ScanAuthorization(
                connection_enabled=True,
                credentials_confirmed=True,
                owner_authorized=True,
                budget_confirmed=True,
            ),
        )
