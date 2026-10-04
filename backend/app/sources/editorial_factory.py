"""Real source registry assembly through the original Job budget ledger.

Every flag/credential/quote defaults to denial. Controlled transports exercise the same
policy and metering code without making paid or public production requests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from uuid import UUID, uuid5

import httpx
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_services import EditorialSourceService, Guard, PreparedEditorialRun
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
    XApiPostReadCost,
)
from jobs.services import ResourceBudgetError, ResourceBudgetService
from sources.adapters.editorial_http import (
    EditorialHttpClient,
    EditorialSourceError,
    RequestOutcome,
)
from sources.adapters.editorial_jina import EditorialJinaReader
from sources.adapters.editorial_mp import DajialaEditorialClient, EditorialMpCollector
from sources.adapters.editorial_x import EditorialXCollector, OfficialEditorialXClient
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_rsshub import EditorialRsshubAdmission, rsshub_route_blocker
from sources.editorial_schemas import EditorialAuthorization, fingerprint


class EditorialRequestMeter:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        owner_id: UUID,
        job_id: UUID,
        run_id: UUID,
        operation_id: UUID,
        source_ref: str,
        connection_id: UUID | None,
        guard: Guard | None = None,
        begin_request: Callable[[Session], bool] | None = None,
        admission: Callable[[Session], None] | None = None,
        x_quote: XApiPostReadCost | None = None,
        paid_caps_cny_micros: Mapping[str, int] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions, self._owner, self._job, self._run, self._operation = (
            sessions,
            owner_id,
            job_id,
            run_id,
            operation_id,
        )
        self._guard, self._quote, self._caps, self._clock = (
            guard,
            x_quote,
            paid_caps_cny_micros or {},
            clock,
        )
        self._context = BudgetContext(
            source_ref=source_ref,
            connection_ref=str(connection_id) if connection_id else None,
            job_ref=str(job_id),
        )
        self._attempt = 0
        self._begin_request = begin_request
        self._admission = admission
        self._paid: dict[str, tuple[UUID, int]] = {}

    def _require_admission(self, session: Session) -> None:
        if self._admission is not None:
            with session.begin():
                self._admission(session)
        else:
            EditorialSourceService(session, clock=self._clock).require_run_admission(
                owner_id=self._owner, run_id=self._run, guard=self._guard
            )

    def before(self, attempt: int) -> bool:
        with self._sessions() as session:
            try:
                self._require_admission(session)
                with session.begin():
                    ledger = ResourceBudgetService(session, clock=self._clock)
                    network = uuid5(self._run, f"network:{attempt}")
                    if self._quote:
                        decision = ledger.reserve_x_api_request_budgets_in_transaction(
                            owner_id=self._owner,
                            operation_id=self._operation,
                            network_reservation_id=network,
                            spend_reservation_id=uuid5(self._run, f"x-spend:{attempt}"),
                            context=self._context,
                            quote=self._quote,
                        )
                    else:
                        decision = ledger.reserve_budget_in_transaction(
                            owner_id=self._owner,
                            command=BudgetReservationInput(
                                reservation_id=network,
                                operation_id=self._operation,
                                metric=BudgetMetric.NETWORK_REQUEST,
                                requested_units=1,
                                context=self._context,
                            ),
                        )
                        if decision.status is BudgetDecisionStatus.RESERVED:
                            ledger.begin_attempt_in_transaction(
                                owner_id=self._owner,
                                command=UsageAttemptInput(
                                    attempt_id=uuid5(self._run, f"usage:{attempt}"),
                                    operation_id=self._operation,
                                    component_key="collector.editorial",
                                    usage_kind=UsageKind.NETWORK_REQUEST,
                                    stage="source_request",
                                    started_at=self._clock(),
                                ),
                            )
                    allowed = decision.status is BudgetDecisionStatus.RESERVED
                    if allowed and self._begin_request is not None:
                        allowed = self._begin_request(session)
                        if not allowed:
                            ledger.settle_budget_reservation_in_transaction(
                                owner_id=self._owner, reservation_id=network, actual_units=0
                            )
                            if self._quote:
                                self._settle_x(session, attempt, 0)
                            else:
                                ledger.finish_attempt_in_transaction(
                                    owner_id=self._owner,
                                    attempt_id=uuid5(self._run, f"usage:{attempt}"),
                                    outcome=UsageOutcome.EMPTY,
                                    finished_at=self._clock(),
                                )
                    if allowed:
                        self._attempt = attempt
                    return allowed
            except (ApplicationError, ResourceBudgetError):
                session.rollback()
                return False

    def settle(self, attempt: int, outcome: RequestOutcome) -> None:
        with self._sessions.begin() as session:
            ledger = ResourceBudgetService(session, clock=self._clock)
            ledger.settle_budget_reservation_in_transaction(
                owner_id=self._owner,
                reservation_id=uuid5(self._run, f"network:{attempt}"),
                actual_units=1,
            )
            if self._quote:
                if outcome != "succeeded":
                    self._settle_x(session, attempt, None)
            else:
                ledger.finish_attempt_in_transaction(
                    owner_id=self._owner,
                    attempt_id=uuid5(self._run, f"usage:{attempt}"),
                    outcome=UsageOutcome.SUCCEEDED
                    if outcome == "succeeded"
                    else UsageOutcome.FAILED,
                    finished_at=self._clock(),
                )
            if outcome != "succeeded":
                for purpose, (reservation, cap) in tuple(self._paid.items()):
                    ledger.settle_budget_reservation_in_transaction(
                        owner_id=self._owner, reservation_id=reservation, actual_units=cap
                    )
                    del self._paid[purpose]

    def report_x_posts(self, count: int | None) -> None:
        with self._sessions.begin() as session:
            self._settle_x(session, self._attempt, count)

    def _settle_x(self, session: Session, attempt: int, count: int | None) -> None:
        assert self._quote is not None
        ResourceBudgetService(session, clock=self._clock).settle_budget_reservation_in_transaction(
            owner_id=self._owner,
            reservation_id=uuid5(self._run, f"x-spend:{attempt}"),
            actual_units=self._quote.settlement_units(count),
        )

    def before_paid(self, purpose: str) -> bool:
        cap = self._caps.get(purpose)
        if cap is None or not isinstance(cap, int) or cap <= 0:
            return False
        with self._sessions() as session:
            try:
                self._require_admission(session)
                with session.begin():
                    reservation = uuid5(self._run, f"paid:{purpose}:{self._attempt + 1}")
                    decision = ResourceBudgetService(
                        session, clock=self._clock
                    ).reserve_budget_in_transaction(
                        owner_id=self._owner,
                        command=BudgetReservationInput(
                            reservation_id=reservation,
                            operation_id=self._operation,
                            metric=BudgetMetric("provider_cny_micros"),
                            requested_units=cap,
                            context=self._context,
                        ),
                    )
                    if decision.status is BudgetDecisionStatus.RESERVED:
                        self._paid[purpose] = (reservation, cap)
                        return True
                    return False
            except (ApplicationError, ResourceBudgetError):
                session.rollback()
                return False

    def report_cost(self, purpose: str, amount: Decimal | None) -> None:
        pending = self._paid.pop(purpose, None)
        if pending is None:
            return
        reservation, cap = pending
        units = (
            int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING))
            if amount is not None
            else cap
        )
        exceeded = units > cap
        with self._sessions.begin() as session:
            ResourceBudgetService(
                session, clock=self._clock
            ).settle_budget_reservation_in_transaction(
                owner_id=self._owner,
                reservation_id=reservation,
                actual_units=cap if exceeded else units,
            )
        if exceeded:
            raise EditorialSourceError("provider_quote_exceeded", unknown=True)


class ConfiguredEditorialCollectorFactory:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        owner_id: UUID,
        job_id: UUID,
        operation_id: UUID,
        guard: Guard | None = None,
        begin_request: Callable[[Session], bool] | None = None,
        admission: Callable[[Session], None] | None = None,
        rsshub_admission: Callable[[Session, PreparedEditorialRun], EditorialRsshubAdmission]
        | None = None,
        zero_supplier_fee_only: bool = True,
        preview: bool = False,
        public_enabled: bool = False,
        x_authorized: bool = False,
        x_token: SecretStr | None = None,
        x_post_unit_usd_micros: int | None = None,
        mp_authorized: bool = False,
        mp_key: SecretStr | None = None,
        jina_authorized: bool = False,
        jina_key: SecretStr | None = None,
        paid_caps_cny_micros: Mapping[str, int] | None = None,
        jina_cny_per_million_tokens: Decimal | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions, self._owner, self._job, self._operation, self._guard = (
            sessions,
            owner_id,
            job_id,
            operation_id,
            guard,
        )
        self._public, self._x, self._mp, self._jina = (
            public_enabled,
            x_authorized,
            mp_authorized,
            jina_authorized,
        )
        self._xtoken, self._mpkey, self._jkey = x_token, mp_key, jina_key
        self._xprice, self._caps, self._jprice = (
            x_post_unit_usd_micros,
            paid_caps_cny_micros or {},
            jina_cny_per_million_tokens,
        )
        self._transport, self._clock = transport, clock
        self._begin_request = begin_request
        self._admission, self._preview = admission, preview
        self._rsshub_admission, self._zero_fee = rsshub_admission, zero_supplier_fee_only

    def __call__(self, prepared: PreparedEditorialRun) -> EditorialSourceRegistry:
        p = prepared.profile
        c = p.configuration
        kind = c.kind
        if self._zero_fee and (
            kind in {"x_search", "mp_account"} or (c.url or "").startswith("https://r.jina.ai/")
        ):
            return EditorialSourceRegistry(
                clock=self._clock, blocked_reason="free_only_paid_source"
            )
        if c.rsshub and (blocker := rsshub_route_blocker(c.rsshub)):
            return EditorialSourceRegistry(clock=self._clock, blocked_reason=blocker)
        x_enabled = (
            kind == "x_search"
            and self._x
            and self._xtoken is not None
            and self._xprice is not None
            and self._xprice > 0
        )
        mp_enabled = (
            kind == "mp_account"
            and self._mp
            and self._mpkey is not None
            and all(self._caps.get(k, 0) > 0 for k in ("mp_history", "mp_article"))
        )
        jina_url = (c.url or "").startswith("https://r.jina.ai/")
        jina_enabled = (
            jina_url
            and self._jina
            and self._jkey is not None
            and self._caps.get("jina_listing", 0) > 0
            and self._jprice is not None
        )
        enabled = (
            x_enabled
            if kind == "x_search"
            else mp_enabled
            if kind == "mp_account"
            else jina_enabled
            if jina_url
            else self._public
        )
        authorization = EditorialAuthorization(
            connection_enabled=enabled,
            owner_authorized=enabled,
            budget_confirmed=enabled,
            credentials_ready=enabled,
        )
        quote = (
            XApiPostReadCost(max_posts=100, unit_price_usd_micros=self._xprice)
            if x_enabled and self._xprice
            else None
        )
        ref = (
            "x"
            if kind == "x_search"
            else "dajiala"
            if kind == "mp_account"
            else "jina"
            if jina_url
            else p.source_key
        )
        meter = EditorialRequestMeter(
            self._sessions,
            owner_id=self._owner,
            job_id=self._job,
            run_id=prepared.result.run_id,
            operation_id=self._operation,
            source_ref=ref,
            connection_id=p.connection_id,
            guard=self._guard,
            begin_request=self._begin_request,
            admission=self._admission,
            x_quote=quote,
            paid_caps_cny_micros=self._caps,
            clock=self._clock,
        )
        hosts = (
            frozenset({"api.x.com"})
            if kind == "x_search"
            else frozenset({"www.dajiala.com"})
            if kind == "mp_account"
            else frozenset(c.allowed_hosts)
        )
        http = EditorialHttpClient(
            allowed_hosts=hosts,
            authorization=authorization,
            before_request=meter.before,
            settle_request=meter.settle,
            transport=self._transport,
            allow_network=enabled,
            rsshub=c.rsshub,
            rsshub_configuration_sha256=fingerprint(c.model_dump(mode="json")).hex()
            if c.rsshub
            else None,
            rsshub_admission=(lambda: self._require_rsshub_admission(prepared))
            if c.rsshub
            else None,
            clock=self._clock,
        )
        xclient = (
            OfficialEditorialXClient(http, bearer=self._xtoken, report_posts=meter.report_x_posts)
            if x_enabled and self._xtoken
            else None
        )
        mpclient = (
            DajialaEditorialClient(
                http, key=self._mpkey, report_cost=meter.report_cost, before_paid=meter.before_paid
            )
            if mp_enabled and self._mpkey
            else None
        )
        jina = (
            EditorialJinaReader(
                http,
                key=self._jkey,
                allowed_targets=frozenset(c.allowed_hosts) - {"r.jina.ai"},
                before_paid=meter.before_paid,
                report_cost=meter.report_cost,
                cny_per_million_tokens=self._jprice,
            )
            if jina_enabled and self._jkey
            else None
        )
        return EditorialSourceRegistry(
            http=http,
            x=EditorialXCollector(xclient, fresh_pages=1 if self._preview else 10)
            if xclient
            else None,
            mp=EditorialMpCollector(mpclient, authorization=authorization) if mpclient else None,
            jina=jina,
            clock=self._clock,
            preview=self._preview,
        )

    def _require_rsshub_admission(self, prepared: PreparedEditorialRun) -> EditorialRsshubAdmission:
        if self._rsshub_admission is None:
            raise EditorialSourceError("rsshub_route_review_required", blocked=True)
        with self._sessions.begin() as session:
            try:
                return self._rsshub_admission(session, prepared)
            except ApplicationError as error:
                reason = str(error.context.get("reason") or "rsshub_admission_changed")
                raise EditorialSourceError(reason, blocked=True) from None
            except (
                SourceAccessUnavailableError,
                RetentionPolicyUnavailableError,
                ResourceBudgetError,
            ):
                raise EditorialSourceError(
                    "rsshub_source_policy_unavailable", blocked=True
                ) from None
