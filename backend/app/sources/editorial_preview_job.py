"""Fenced source preview execution through the original collector and Job ledgers."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_preview import (
    load_editorial_preview_profile_in_transaction,
    preview_profile_hash,
)
from connections.editorial_rsshub import require_editorial_rsshub_execution_in_transaction
from connections.editorial_services import PreparedEditorialRun
from core.config import Settings
from core.errors import ApplicationError
from jobs.editorial_preview import recover_editorial_preview_budgets_in_transaction
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionFailure,
    JobExecutionService,
)
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration
from operations.services import (
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.editorial_factory import ConfiguredEditorialCollectorFactory
from sources.editorial_preview_rules import preview_items
from sources.editorial_preview_schemas import EditorialSourcePreviewView
from sources.editorial_rsshub import EditorialRsshubAdmission
from sources.editorial_schemas import EditorialCursor, EditorialProfileView, EditorialRunResult


class EditorialSourcePreviewExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.sessions, self.settings, self.lease_seconds = sessions, settings, lease_seconds
        self.clock = clock or (lambda: datetime.now(UTC))
        self.transport = transport

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion | None:
        if message.kind != "source.editorial.preview":
            raise ValueError("source preview executor received another Job kind")
        started = monotonic()

        def stopped() -> bool:
            return bool(cancelled and cancelled()) or monotonic() - started >= 540

        def current(session: Session) -> ExecutionLease:
            return JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            ).require_current_operation_in_transaction(
                lease, owner_id=message.owner_id, operation_id=message.operation_id
            )

        with self.sessions.begin() as session:
            active = current(session)
            original_requests = JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            ).current_request_count_in_transaction(
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
            profile_id = UUID(str(config.scope["profile_id"]))
            revision = int(str(config.scope["revision"]))
            frozen_hash = config.scope["preview_profile_sha256"]
            profile = load_editorial_preview_profile_in_transaction(
                session,
                owner_id=message.owner_id,
                profile_id=profile_id,
                expected_revision=revision,
                now=self.clock(),
            )
            if preview_profile_hash(profile) != frozen_hash:
                raise self._failure("editorial_version_conflict")
            saved = load_completed_audit_in_transaction(
                session, owner_id=message.owner_id, operation_id=message.operation_id
            )
            if saved is not None:
                return self._completion(EditorialSourcePreviewView.model_validate(saved))
            abandoned = bool(active.checkpoint.get("source_preview_started"))
            if abandoned:
                recover_editorial_preview_budgets_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    operation_id=message.operation_id,
                    now=self.clock(),
                )

        def admission(session: Session) -> None:
            if stopped():
                raise ApplicationError("editorial_source_unavailable")
            current(session)
            admitted = load_editorial_preview_profile_in_transaction(
                session,
                owner_id=message.owner_id,
                profile_id=profile_id,
                expected_revision=revision,
                now=self.clock(),
                require_remote=True,
            )
            if preview_profile_hash(admitted) != frozen_hash:
                raise ApplicationError("editorial_version_conflict")

        def begin_request(session: Session) -> bool:
            admission(session)
            execution = JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            )
            live, allowed = execution.begin_request_in_transaction(lease)
            if allowed:
                execution.save_checkpoint_in_transaction(
                    live,
                    sequence=live.checkpoint_sequence + 1,
                    checkpoint={**live.checkpoint, "source_preview_started": True},
                )
            return allowed

        if abandoned:
            result = self._empty(profile, "unknown", "source_preview_outcome_unknown").model_copy(
                update={"requests": original_requests}
            )
        elif not self.settings.editorial_sources_enabled:
            result = self._empty(profile, "blocked", "editorial_sources_disabled")
        elif profile.configuration.kind not in {"rss", "web_list", "json_list", "x_search"}:
            result = self._empty(profile, "blocked", "source_preview_unsupported")
        else:
            try:
                with self.sessions.begin() as session:
                    admission(session)
                result = self._collect(profile, message, admission, begin_request, started)
            except ApplicationError as error:
                result = self._empty(profile, "blocked", error.code)
        if cancelled and cancelled():
            return None
        with self.sessions.begin() as session:
            live = current(session)
            if result.items or result.status == "complete":
                admission(session)
            if result.status == "unknown":
                recover_editorial_preview_budgets_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    job_id=message.job_id,
                    operation_id=message.operation_id,
                    now=self.clock(),
                )
            complete_audit_in_transaction(
                session,
                owner_id=message.owner_id,
                operation_id=message.operation_id,
                after_state=result.model_dump(mode="json"),
                now=self.clock(),
            )
            JobExecutionService(
                session, lease_seconds=self.lease_seconds, clock=self.clock
            ).save_checkpoint_in_transaction(
                live,
                sequence=live.checkpoint_sequence + 1,
                checkpoint={**live.checkpoint, "preview_status": result.status},
            )
        return self._completion(result)

    def _collect(
        self,
        profile: EditorialProfileView,
        message: JobMessage,
        admission: Callable[[Session], None],
        begin_request: Callable[[Session], bool],
        started: float,
    ) -> EditorialSourcePreviewView:
        settings = self.settings
        prepared = PreparedEditorialRun(
            result=EditorialRunResult(
                run_id=message.job_id,
                status="running",
                configuration_version=profile.configuration_version,
            ),
            profile=profile,
            cursor=EditorialCursor(initialized_at=self.clock()),
            known={},
            prepared_page=None,
            should_collect=True,
        )

        def rsshub_admission(
            session: Session, run: PreparedEditorialRun
        ) -> EditorialRsshubAdmission:
            return require_editorial_rsshub_execution_in_transaction(
                session,
                owner_id=message.owner_id,
                profile_id=run.profile.id,
                configuration_version=run.profile.configuration_version,
                revision=run.profile.revision,
                now=self.clock(),
            )

        registry = ConfiguredEditorialCollectorFactory(
            self.sessions,
            owner_id=message.owner_id,
            job_id=message.job_id,
            operation_id=message.operation_id,
            admission=admission,
            begin_request=begin_request,
            zero_supplier_fee_only=True,
            rsshub_admission=rsshub_admission,
            preview=True,
            public_enabled=settings.editorial_public_requests_enabled,
            x_authorized=settings.editorial_x_authorized,
            x_token=settings.editorial_x_token,
            x_post_unit_usd_micros=settings.editorial_x_post_unit_usd_micros,
            jina_authorized=settings.editorial_jina_authorized,
            jina_key=settings.editorial_jina_key,
            paid_caps_cny_micros=settings.editorial_paid_caps_cny_micros,
            jina_cny_per_million_tokens=settings.editorial_jina_cny_per_million_tokens,
            transport=self.transport,
            clock=self.clock,
        )(prepared)
        try:
            page = registry.collect(profile, prepared.cursor, {})
        finally:
            registry.close()
        return EditorialSourcePreviewView(
            mode="remote",
            status="complete" if page.status in {"complete", "unchanged"} else page.status,
            kind=profile.configuration.kind,
            count=len(page.materials),
            requests=page.request_count,
            ms=min(600000, int((monotonic() - started) * 1000)),
            items=preview_items(page.materials),
            reason=page.reason,
        )

    @staticmethod
    def _empty(
        profile: EditorialProfileView, status: str, reason: str
    ) -> EditorialSourcePreviewView:
        return EditorialSourcePreviewView.model_validate(
            dict(
                mode="remote",
                status=status,
                kind=profile.configuration.kind,
                count=0,
                ms=0,
                requests=0,
                items=(),
                reason=reason,
            )
        )

    def _completion(self, result: EditorialSourcePreviewView) -> JobCompletion:
        if result.status == "complete":
            return JobCompletion(status=JobStatus.SUCCEEDED)
        return JobCompletion(
            status=JobStatus.PARTIALLY_SUCCEEDED,
            failure=self._failure(result.reason or "source_preview_incomplete"),
        )

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.CONFIGURATION_UNAVAILABLE,
            occurred_at=self.clock(),
            next_action="核对原来源版本、许可与预算; 未知请求保持停止, 不自动再次请求",
            manual_retry_allowed=False,
        )
