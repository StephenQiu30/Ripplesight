"""Original budget ledger admission and settlement for one AI provider request."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobs.models import ResourceBudgetPolicy, ResourceBudgetReservation
from jobs.schemas import (
    AiTokenCostQuote,
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    BudgetScopeKind,
)
from jobs.services import BudgetPolicyUnavailableError, ResourceBudgetService


def reserve_ai_provider_budgets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    operation_id: UUID,
    call_id: UUID,
    component_key: str,
    quote: AiTokenCostQuote | None,
    now: datetime,
) -> None:
    """Caller transaction rolls all caps back on admission failure; no provider call here."""
    if not session.in_transaction():
        raise RuntimeError("AI provider budgets require caller transaction")
    if not component_key.startswith(("ai.llm.", "ai.embeddings")):
        raise ValueError("AI provider budgets require the actual provider component")
    context = BudgetContext(source_ref=component_key, job_ref=f"job:{operation_id.hex}")
    metrics: list[tuple[str, BudgetMetric, int, AiTokenCostQuote | None]] = [
        ("ai-provider-network", BudgetMetric.NETWORK_REQUEST, 1, None)
    ]
    if quote is not None:
        metric = (
            BudgetMetric.PROVIDER_USD_MICROS
            if quote.currency == "USD"
            else BudgetMetric.PROVIDER_CNY_MICROS
        )
        metrics.append(("ai-provider-spend", metric, quote.reservation_units, quote))
    budget = ResourceBudgetService(session, clock=lambda: now)
    for suffix, metric, cap, cost_quote in metrics:
        source_policy = session.scalar(
            select(ResourceBudgetPolicy.id)
            .where(
                ResourceBudgetPolicy.owner_id == owner_id,
                ResourceBudgetPolicy.metric == metric.value,
                ResourceBudgetPolicy.scope_kind == BudgetScopeKind.SOURCE.value,
                ResourceBudgetPolicy.scope_reference == component_key,
                ResourceBudgetPolicy.enabled.is_(True),
                ResourceBudgetPolicy.window_anchor_at <= now,
            )
            .with_for_update()
        )
        if source_policy is None:
            raise BudgetPolicyUnavailableError("AI provider needs an explicit component budget")
        decision = budget.reserve_budget_in_transaction(
            owner_id=owner_id,
            command=BudgetReservationInput(
                reservation_id=uuid5(call_id, suffix),
                operation_id=operation_id,
                metric=metric,
                requested_units=cap,
                context=context,
                cost_quote=cost_quote,
            ),
        )
        if decision.status is BudgetDecisionStatus.DELAYED:
            raise BudgetPolicyUnavailableError("AI provider budget is exhausted")


def settle_ai_provider_budgets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    call_id: UUID,
    cost_units: int | None,
    now: datetime,
) -> int | None:
    """Unknown cost consumes the original stored cap; late receipts never free it."""
    budget = ResourceBudgetService(session, clock=lambda: now)
    original_cap = None
    for suffix in ("ai-provider-network", "ai-provider-spend"):
        reservation_id = uuid5(call_id, suffix)
        rows = list(
            session.scalars(
                select(ResourceBudgetReservation)
                .where(
                    ResourceBudgetReservation.owner_id == owner_id,
                    ResourceBudgetReservation.reservation_id == reservation_id,
                )
                .with_for_update()
            )
        )
        if not rows:
            continue
        cap = rows[0].requested_units
        if any(row.requested_units != cap for row in rows):
            raise RuntimeError("original AI budget caps disagree")
        if suffix == "ai-provider-spend":
            original_cap = cap
        units = cap if cost_units is None else cost_units
        if suffix == "ai-provider-network":
            units = 1
        if all(row.status == "settled" for row in rows) and (
            suffix != "ai-provider-spend" or cost_units is None
        ):
            continue
        if suffix == "ai-provider-spend":
            budget.settle_provider_cost_receipt_in_transaction(
                owner_id=owner_id, reservation_id=reservation_id, actual_units=units
            )
        else:
            budget.settle_budget_reservation_in_transaction(
                owner_id=owner_id, reservation_id=reservation_id, actual_units=units
            )
    return original_cap
