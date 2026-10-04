"""Actual grouped-source Worker entry using the original Job and source receipts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID, uuid5

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_group import (
    begin_editorial_group_runs_in_transaction,
    hold_editorial_group_runs_in_transaction,
    require_editorial_group_admission_in_transaction,
)
from connections.editorial_services import EditorialSourceService
from core.config import Settings
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from jobs.editorial_budgets import (
    EditorialGroupBudgetRequest,
    recover_editorial_group_budgets_in_transaction,
    reserve_editorial_group_budgets_in_transaction,
    settle_editorial_group_budgets_in_transaction,
)
from jobs.editorial_member import load_editorial_group_manifest_in_transaction
from jobs.editorial_schemas import EditorialGroupManifest
from jobs.execution import (
    ExecutionLease,
    JobCompletion,
    JobExecutionError,
    JobExecutionFailure,
    JobExecutionService,
)
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    JobFailureCategory,
    JobMessage,
    JobStatus,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
    XApiPostReadCost,
)
from jobs.services import (
    ResourceBudgetError,
    ResourceBudgetService,
    load_job_execution_configuration,
)
from sources.adapters.editorial_http import (
    EditorialHttpClient,
    RequestOutcome,
)
from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.editorial_group_collect import collect_editorial_group
from sources.editorial_job import SOURCE_JOB_TIMEOUT_SECONDS
from sources.editorial_schemas import EditorialAuthorization, EditorialPage


class EditorialXGroupJobExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport: httpx.BaseTransport | None = None,
        zero_supplier_fee_only: bool = True,
    ) -> None:
        self._sessions, self._settings, self._lease_seconds = sessions, settings, lease_seconds
        self._clock, self._transport = clock, transport
        self._zero_supplier_fee_only = zero_supplier_fee_only

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self._clock(),
            next_action=(
                "核对全部分组成员、许可与成员 provider_usd_micros/source 预算; 未知请求须人工核验"
            ),
            manual_retry_allowed=False,
        )

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> JobCompletion | None:
        if message.kind != "source.editorial.x_group":
            raise ValueError("another Job kind reached grouped X executor")
        if not self._settings.editorial_sources_enabled:
            raise self._failure("editorial_sources_disabled")
        if self._zero_supplier_fee_only:
            raise self._failure("free_only_paid_source")
        if cancelled is not None and cancelled():
            return None
        deadline = monotonic() + SOURCE_JOB_TIMEOUT_SECONDS - 60

        def stopped() -> bool:
            return (cancelled is not None and cancelled()) or monotonic() >= deadline

        def guard(session: Session, owner: UUID, job: UUID) -> bool:
            if stopped() or owner != message.owner_id or job != message.job_id:
                return False
            try:
                JobExecutionService(
                    session, lease_seconds=self._lease_seconds, clock=self._clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=owner, operation_id=message.operation_id
                )
                return True
            except JobExecutionError:
                return False

        with self._sessions.begin() as session:
            if not guard(session, message.owner_id, message.job_id):
                raise self._failure("editorial_job_mismatch")
            actual = load_job_execution_configuration(session, job_id=message.job_id)
            manifest = load_editorial_group_manifest_in_transaction(
                session, owner_id=message.owner_id, job_id=message.job_id
            )
            if (
                actual is None
                or manifest is None
                or actual.operation_id != message.operation_id
                or actual.kind != message.kind
                or actual.observation.configuration_ref != message.configuration_ref
                or actual.observation.configuration_version != message.configuration_version
                or actual.observation.source_key != message.source_key
                or actual.observation.source_capability != message.source_capability
            ):
                raise self._failure("editorial_job_mismatch")
        locked = []
        with self._sessions() as locks:
            try:
                for member in sorted(manifest.members, key=lambda m: str(m.profile_id)):
                    key = int.from_bytes(member.profile_id.bytes[:8], "big", signed=True)
                    if not locks.scalar(text("SELECT pg_try_advisory_lock(:key)"), dict(key=key)):
                        raise self._failure("editorial_version_conflict")
                    locked.append(key)
                locks.commit()
                return self._execute_locked(message, lease, manifest, guard, stopped)
            finally:
                for key in reversed(locked):
                    locks.execute(text("SELECT pg_advisory_unlock(:key)"), dict(key=key))
                locks.commit()

    def _execute_locked(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        manifest: EditorialGroupManifest,
        guard: Callable[[Session, UUID, UUID], bool],
        stopped: Callable[[], bool],
    ) -> JobCompletion:
        with self._sessions.begin() as session:
            if not guard(session, manifest.owner_id, message.job_id):
                raise self._failure("editorial_job_mismatch")
            recover_editorial_group_budgets_in_transaction(
                session,
                owner_id=manifest.owner_id,
                operation_id=message.operation_id,
                job_id=message.job_id,
                member_sources=tuple(m.source_key for m in manifest.members),
                now=self._clock(),
            )
        try:
            with self._sessions.begin() as session:
                prepared = begin_editorial_group_runs_in_transaction(
                    session,
                    manifest=manifest,
                    job_id=message.job_id,
                    operation_id=message.operation_id,
                    guard=guard,
                    now=self._clock(),
                )
        except (ApplicationError, SourceAccessUnavailableError, RetentionPolicyUnavailableError):
            return self._hold_group(message, manifest, guard, "group_admission_changed")

        def group_guard(session: Session, owner: UUID, job: UUID) -> bool:
            try:
                require_editorial_group_admission_in_transaction(
                    session,
                    manifest=manifest,
                    job_id=job,
                    guard=guard,
                    now=self._clock(),
                )
                return owner == manifest.owner_id
            except (
                ApplicationError,
                SourceAccessUnavailableError,
                RetentionPolicyUnavailableError,
            ):
                return False

        ready = all(p.should_collect for p in prepared)
        enabled = (
            self._settings.editorial_x_authorized
            and self._settings.editorial_x_token is not None
            and self._settings.editorial_x_post_unit_usd_micros is not None
        )
        if ready and enabled:
            assert self._settings.editorial_x_post_unit_usd_micros is not None
            assert self._settings.editorial_x_token is not None
            quote = XApiPostReadCost(
                max_posts=100, unit_price_usd_micros=self._settings.editorial_x_post_unit_usd_micros
            )
            pending: EditorialGroupBudgetRequest | None = None
            unknown_cost = False

            def finish(
                count: int | None, counts: Mapping[str, int] | None, *, network: int = 1
            ) -> None:
                nonlocal pending, unknown_cost
                if pending is None:
                    return
                request = pending
                with self._sessions.begin() as s:
                    settle_editorial_group_budgets_in_transaction(
                        s,
                        owner_id=message.owner_id,
                        command=request,
                        member_posts=counts,
                        returned_posts=count,
                        network_units=network,
                        now=self._clock(),
                    )
                    ResourceBudgetService(s, clock=self._clock).finish_attempt_in_transaction(
                        owner_id=message.owner_id,
                        attempt_id=uuid5(request.reservation_id, "usage"),
                        outcome=UsageOutcome.EMPTY
                        if not network
                        else UsageOutcome.FAILED
                        if count is None
                        else UsageOutcome.SUCCEEDED,
                        finished_at=self._clock(),
                    )
                if count is None:
                    unknown_cost = True
                pending = None

            def before(attempt: int) -> bool:
                nonlocal pending
                if pending is not None:
                    finish(None, None)
                if stopped():
                    return False
                request = EditorialGroupBudgetRequest(
                    operation_id=message.operation_id,
                    reservation_id=uuid5(message.job_id, f"group-request:{attempt}"),
                    context=BudgetContext(
                        source_ref="x",
                        connection_ref=str(manifest.connection_id),
                        job_ref=str(message.job_id),
                    ),
                    member_sources=tuple(m.source_key for m in manifest.members),
                    manifest_sha256=manifest.sha256,
                    quote=quote,
                )
                try:
                    with self._sessions.begin() as s:
                        require_editorial_group_admission_in_transaction(
                            s,
                            manifest=manifest,
                            job_id=message.job_id,
                            guard=guard,
                            now=self._clock(),
                            require_running=True,
                        )
                        decision = reserve_editorial_group_budgets_in_transaction(
                            s, owner_id=message.owner_id, command=request, now=self._clock()
                        )
                        if decision.status != BudgetDecisionStatus.RESERVED:
                            return False
                        ResourceBudgetService(s, clock=self._clock).begin_attempt_in_transaction(
                            owner_id=message.owner_id,
                            command=UsageAttemptInput(
                                attempt_id=uuid5(request.reservation_id, "usage"),
                                operation_id=message.operation_id,
                                component_key="collector.editorial",
                                usage_kind=UsageKind.NETWORK_REQUEST,
                                stage="source_group_request",
                                started_at=self._clock(),
                            ),
                        )
                        _, allowed = JobExecutionService(
                            s, lease_seconds=self._lease_seconds, clock=self._clock
                        ).begin_request_in_transaction(lease)
                    pending = request
                    if not allowed:
                        finish(0, {m.source_key: 0 for m in manifest.members}, network=0)
                    return allowed
                except (
                    ApplicationError,
                    ResourceBudgetError,
                    SourceAccessUnavailableError,
                    RetentionPolicyUnavailableError,
                ):
                    return False

            def settled(attempt: int, outcome: RequestOutcome) -> None:
                if outcome != "succeeded":
                    finish(None, None)

            http = EditorialHttpClient(
                allowed_hosts=frozenset({"api.x.com"}),
                authorization=EditorialAuthorization(
                    connection_enabled=True,
                    owner_authorized=True,
                    budget_confirmed=True,
                    credentials_ready=True,
                ),
                before_request=before,
                settle_request=settled,
                cancelled=stopped,
                max_requests=25,
                max_seconds=300,
                transport=self._transport,
                allow_network=True,
            )
            client = OfficialEditorialXClient(
                http,
                bearer=self._settings.editorial_x_token,
                report_posts=lambda count: finish(None, None) if count is None else None,
            )
            try:
                pages = collect_editorial_group(
                    manifest,
                    {p.profile.id: (p.profile, p.cursor, p.known) for p in prepared},
                    client,
                    now=self._clock(),
                    report_cost=finish,
                )
                if unknown_cost:
                    pages = {
                        i: p.model_copy(
                            update={"status": "unknown", "reason": "group_cost_unknown"}
                        )
                        for i, p in pages.items()
                    }
            finally:
                if pending is not None:
                    finish(None, None)
                http.close()
        elif ready:
            pages = {
                p.profile.id: EditorialPage(
                    status="blocked",
                    reason="source_authorization_required",
                    cursor=p.cursor,
                    observed_at=self._clock(),
                )
                for p in prepared
            }
        else:
            pages = {}
        results = []
        for item in prepared:
            try:
                with self._sessions() as s:
                    service = EditorialSourceService(s, clock=self._clock)
                    if item.profile.id in pages:
                        service.stage_page(
                            owner_id=message.owner_id,
                            run_id=item.result.run_id,
                            page=pages[item.profile.id],
                            guard=group_guard,
                        )
                    results.append(
                        service.apply_page(
                            owner_id=message.owner_id,
                            run_id=item.result.run_id,
                            guard=group_guard,
                        )
                    )
            except (
                ApplicationError,
                SourceAccessUnavailableError,
                RetentionPolicyUnavailableError,
            ):
                return self._hold_group(message, manifest, guard, "group_admission_changed")
        if stopped():
            return JobCompletion(
                status=JobStatus.PARTIALLY_SUCCEEDED,
                failure=self._failure("editorial_deadline_exceeded"),
            )
        if all(r.status == "succeeded" for r in results):
            return JobCompletion(status=JobStatus.SUCCEEDED)
        reason = next(
            (r.reason for r in results if r.status != "succeeded" and r.reason),
            "editorial_group_incomplete",
        )
        return JobCompletion(status=JobStatus.PARTIALLY_SUCCEEDED, failure=self._failure(reason))

    def _hold_group(
        self,
        message: JobMessage,
        manifest: EditorialGroupManifest,
        guard: Callable[[Session, UUID, UUID], bool],
        reason: str,
    ) -> JobCompletion:
        with self._sessions.begin() as session:
            if guard(session, manifest.owner_id, message.job_id):
                hold_editorial_group_runs_in_transaction(
                    session,
                    manifest=manifest,
                    job_id=message.job_id,
                    guard=guard,
                    now=self._clock(),
                    reason=reason,
                )
        return JobCompletion(status=JobStatus.PARTIALLY_SUCCEEDED, failure=self._failure(reason))
