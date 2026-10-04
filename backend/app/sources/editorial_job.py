"""Lease-fenced source Worker entry. No second queue or provider retries."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_rsshub import require_editorial_rsshub_execution_in_transaction
from connections.editorial_services import PreparedEditorialRun
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
from sources.editorial_body import LocalEditorialBodyFetcher
from sources.editorial_body_meter import EditorialBodyRequestMeter
from sources.editorial_execution import EditorialSourceExecutor
from sources.editorial_factory import ConfiguredEditorialCollectorFactory
from sources.editorial_rsshub import EditorialRsshubAdmission
from sources.editorial_schemas import fingerprint

SOURCE_JOB_TIMEOUT_SECONDS = 600


class EditorialSourceJobExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sessions, self._settings, self._lease_seconds = sessions, settings, lease_seconds
        self._clock, self._transport = clock, transport

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion | None:
        if message.kind not in {"source.editorial.poll", "source.editorial.ingest"}:
            raise ValueError("editable source executor received another kind")
        if not self._settings.editorial_sources_enabled:
            raise self._failure("editorial_sources_disabled")
        deadline = monotonic() + SOURCE_JOB_TIMEOUT_SECONDS - 60

        def stopped() -> bool:
            return (cancelled is not None and cancelled()) or monotonic() >= deadline

        with self._sessions.begin() as session:
            JobExecutionService(
                session, lease_seconds=self._lease_seconds, clock=self._clock
            ).require_current_operation_in_transaction(
                lease, owner_id=message.owner_id, operation_id=message.operation_id
            )
            config = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                config is None
                or config.owner_id != message.owner_id
                or config.operation_id != message.operation_id
                or config.kind != message.kind
                or config.observation.configuration_ref != message.configuration_ref
                or config.observation.configuration_version != message.configuration_version
                or config.observation.source_key != message.source_key
                or config.observation.source_capability != message.source_capability
            ):
                raise self._failure("editorial_job_mismatch")
            try:
                profile_id = UUID(str(config.scope["profile_id"]))
                revision = int(str(config.scope["revision"]))
            except (KeyError, ValueError, TypeError):
                raise self._failure("editorial_job_mismatch") from None

        def guard(session: Session, owner_id: UUID, job_id: UUID) -> bool:
            if stopped() or owner_id != message.owner_id or job_id != lease.job_id:
                return False
            try:
                JobExecutionService(
                    session, lease_seconds=self._lease_seconds, clock=self._clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=owner_id, operation_id=message.operation_id
                )
                return True
            except JobExecutionError:
                return False

        settings = self._settings

        def begin_request(session: Session) -> bool:
            if stopped():
                return False
            _, allowed = JobExecutionService(
                session,
                lease_seconds=self._lease_seconds,
                clock=self._clock,
            ).begin_request_in_transaction(lease)
            return allowed

        def rsshub_admission(
            session: Session, prepared: PreparedEditorialRun
        ) -> EditorialRsshubAdmission:
            return require_editorial_rsshub_execution_in_transaction(
                session,
                owner_id=message.owner_id,
                profile_id=prepared.profile.id,
                configuration_version=message.configuration_version,
                revision=revision,
                now=self._clock(),
            )

        factory = ConfiguredEditorialCollectorFactory(
            self._sessions,
            owner_id=message.owner_id,
            job_id=message.job_id,
            operation_id=message.operation_id,
            guard=guard,
            begin_request=begin_request,
            zero_supplier_fee_only=True,
            rsshub_admission=rsshub_admission,
            public_enabled=settings.editorial_public_requests_enabled,
            x_authorized=settings.editorial_x_authorized,
            x_token=settings.editorial_x_token,
            x_post_unit_usd_micros=settings.editorial_x_post_unit_usd_micros,
            mp_authorized=settings.editorial_mp_authorized,
            mp_key=settings.editorial_mp_key,
            jina_authorized=settings.editorial_jina_authorized,
            jina_key=settings.editorial_jina_key,
            paid_caps_cny_micros=settings.editorial_paid_caps_cny_micros,
            jina_cny_per_million_tokens=settings.editorial_jina_cny_per_million_tokens,
            transport=self._transport,
            clock=self._clock,
        )

        def body_factory(prepared: PreparedEditorialRun) -> LocalEditorialBodyFetcher:
            body = prepared.profile.configuration.body_extraction
            digest = fingerprint(prepared.profile.configuration.model_dump(mode="json")).hex()
            if (
                body is None
                or prepared.profile.connection_id is None
                or not settings.firecrawl_enabled
                or not settings.editorial_public_requests_enabled
            ):
                return LocalEditorialBodyFetcher(
                    base_url=settings.firecrawl_base_url,
                    configuration_sha256=digest,
                    clock=self._clock,
                )
            meter = EditorialBodyRequestMeter(
                self._sessions,
                lease=lease,
                source_ref=prepared.profile.source_key,
                connection_id=prepared.profile.connection_id,
                max_target_requests=body.max_target_requests,
                guard=guard,
                lease_seconds=self._lease_seconds,
                clock=self._clock,
            )
            return LocalEditorialBodyFetcher(
                base_url=settings.firecrawl_base_url,
                configuration_sha256=digest,
                admission=meter.admission,
                before_request=meter.before_request,
                settle=meter.settle,
                transport=self._transport,
                clock=self._clock,
            )

        try:
            result = EditorialSourceExecutor(
                self._sessions,
                collector_factory=factory,
                body_fetcher_factory=body_factory,
                execution_guard=guard,
                clock=self._clock,
            ).execute(
                owner_id=message.owner_id,
                profile_id=profile_id,
                configuration_version=message.configuration_version,
                revision=revision,
                job_id=message.job_id,
                operation_id=message.operation_id,
            )
        except ApplicationError as error:
            raise self._failure(error.code) from None
        if stopped():
            return (
                None
                if cancelled and cancelled()
                else JobCompletion(
                    status=JobStatus.PARTIALLY_SUCCEEDED,
                    failure=self._failure("editorial_deadline_exceeded"),
                )
            )
        if result.status == "succeeded":
            return JobCompletion(status=JobStatus.SUCCEEDED)
        return JobCompletion(
            status=JobStatus.PARTIALLY_SUCCEEDED,
            failure=self._failure(result.reason or f"editorial_source_{result.status}"),
        )

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self._clock(),
            next_action="核对来源许可、凭据与预算; 未知外部请求须在来源运营页复核后再受理",
            manual_retry_allowed=False,
        )
