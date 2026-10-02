"""One grouped HTTP cost, constrained by original aggregate and member budgets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobs.models import ResourceBudgetPolicy, ResourceBudgetReservation, ResourceUsageAttempt
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationDecision,
    BudgetReservationInput,
    BudgetResumeCondition,
    UsageOutcome,
    XApiPostReadCost,
)
from jobs.services import (
    BudgetPolicyUnavailableError,
    BudgetReservationConflictError,
    ResourceBudgetService,
)


class EditorialGroupBudgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    reservation_id: UUID
    context: BudgetContext
    member_sources: tuple[str, ...] = Field(min_length=2, max_length=24)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote: XApiPostReadCost

    @model_validator(mode="after")
    def distinct_sources(self) -> Self:
        import re

        if (
            self.context.source_ref != "x"
            or not self.context.connection_ref
            or not self.context.job_ref
        ):
            raise ValueError("group cost needs original X connection and Job context")
        if len(set(self.member_sources)) != len(self.member_sources) or any(
            not re.fullmatch(r"ed_x_search_[a-f0-9]{32}", s) for s in self.member_sources
        ):
            raise ValueError("group source attribution must be distinct frozen member identities")
        return self


def _id(command: EditorialGroupBudgetRequest, kind: str, source: str = "x") -> UUID:
    return uuid5(command.reservation_id, f"{kind}:{source}")


def _reserve_member(
    session: Session,
    *,
    owner_id: UUID,
    command: EditorialGroupBudgetRequest,
    source: str,
    metric: BudgetMetric,
    now: datetime,
    required: bool,
) -> BudgetReservationDecision | None:
    ledger = ResourceBudgetService(session, clock=lambda: now)
    reservation = _id(command, metric.value, source)
    units = 1 if metric == BudgetMetric.NETWORK_REQUEST else command.quote.reservation_units
    context = BudgetContext(
        source_ref=source,
        connection_ref=command.context.connection_ref,
        job_ref=command.context.job_ref,
    )
    ordinary = BudgetReservationInput(
        reservation_id=reservation,
        operation_id=command.operation_id,
        metric=metric,
        requested_units=units,
        context=context,
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "context": context.model_dump(),
                "manifest": command.manifest_sha256,
                "quote": command.quote.model_dump(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).digest()
    existing = ledger._locked_reservations(owner_id, reservation)
    if existing:
        if any(r.status != "reserved" for r in existing):
            raise BudgetReservationConflictError("group request already crossed its paid boundary")
        return ledger._reservation_replay(existing, ordinary, digest)
    policies = list(
        session.scalars(
            select(ResourceBudgetPolicy)
            .where(
                ResourceBudgetPolicy.owner_id == owner_id,
                ResourceBudgetPolicy.enabled.is_(True),
                ResourceBudgetPolicy.metric == metric.value,
                ResourceBudgetPolicy.scope_kind == "source",
                ResourceBudgetPolicy.scope_reference == source,
                ResourceBudgetPolicy.window_anchor_at <= now,
            )
            .order_by(ResourceBudgetPolicy.id)
            .with_for_update()
        )
    )
    if not policies:
        if required:
            raise BudgetPolicyUnavailableError(
                "every X group member needs an approved provider_usd_micros/source budget"
            )
        return None
    windows = [(p, ledger._locked_current_window(p, now)) for p in policies]
    limiting = [
        (p, w) for p, w in windows if p.limit_units - w.used_units - w.reserved_units < units
    ]
    if limiting:
        return BudgetReservationDecision(
            status=BudgetDecisionStatus.DELAYED,
            reservation_id=reservation,
            operation_id=command.operation_id,
            metric=metric,
            requested_units=units,
            remaining_units=max(
                0, min(p.limit_units - w.used_units - w.reserved_units for p, w in windows)
            ),
            limiting_budget_keys=tuple(p.budget_key for p, w in limiting),
            resume_condition=BudgetResumeCondition.NEXT_WINDOW,
            retry_at=max(w.window_end for p, w in limiting),
        )
    for policy, window in windows:
        remaining = policy.limit_units - window.used_units - window.reserved_units - units
        window.reserved_units += units
        window.updated_at = now
        session.add(
            ResourceBudgetReservation(
                id=uuid4(),
                owner_id=owner_id,
                reservation_id=reservation,
                operation_id=command.operation_id,
                budget_policy_id=policy.id,
                budget_window_id=window.id,
                policy_version=policy.policy_version,
                limit_units=policy.limit_units,
                metric=metric.value,
                budget_mode="cumulative",
                requested_units=units,
                actual_units=None,
                released_units=None,
                remaining_units_after=remaining,
                context_fingerprint=digest,
                status="reserved",
                created_at=now,
                settled_at=None,
            )
        )
    session.flush()
    return BudgetReservationDecision(
        status=BudgetDecisionStatus.RESERVED,
        reservation_id=reservation,
        operation_id=command.operation_id,
        metric=metric,
        requested_units=units,
        remaining_units=min(p.limit_units - w.used_units - w.reserved_units for p, w in windows),
        limiting_budget_keys=(),
        resume_condition=None,
        retry_at=None,
    )


def reserve_editorial_group_budgets_in_transaction(
    session: Session, *, owner_id: UUID, command: EditorialGroupBudgetRequest, now: datetime
) -> BudgetReservationDecision:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("group reserve requires aware caller transaction")
    ledger = ResourceBudgetService(session, clock=lambda: now)
    with session.begin_nested() as transaction:
        aggregate = ledger.reserve_x_api_request_budgets_in_transaction(
            owner_id=owner_id,
            operation_id=command.operation_id,
            network_reservation_id=_id(command, "network"),
            spend_reservation_id=_id(command, "spend"),
            context=command.context,
            quote=command.quote,
        )
        if aggregate.status != BudgetDecisionStatus.RESERVED:
            transaction.rollback()
            return aggregate
        for source in sorted(command.member_sources):
            for metric, required in (
                (BudgetMetric.NETWORK_REQUEST, False),
                (BudgetMetric.PROVIDER_USD_MICROS, True),
            ):
                result = _reserve_member(
                    session,
                    owner_id=owner_id,
                    command=command,
                    source=source,
                    metric=metric,
                    now=now,
                    required=required,
                )
                if result is not None and result.status != BudgetDecisionStatus.RESERVED:
                    transaction.rollback()
                    return result
        return aggregate


def settle_editorial_group_budgets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    command: EditorialGroupBudgetRequest,
    member_posts: Mapping[str, int] | None,
    returned_posts: int | None,
    network_units: int,
    now: datetime,
) -> None:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("group settlement requires aware caller transaction")
    if network_units not in (0, 1):
        raise ValueError("one group HTTP can consume only one network request")
    if (returned_posts is None) != (member_posts is None):
        raise ValueError("unknown author allocation must retain all conservative caps")
    if member_posts is not None and (
        set(member_posts) != set(command.member_sources)
        or any(type(n) is not int or n < 0 for n in member_posts.values())
        or sum(member_posts.values()) != returned_posts
    ):
        raise ValueError("each paid post needs exactly one frozen author attribution")
    ledger = ResourceBudgetService(session, clock=lambda: now)
    with session.begin_nested():
        ledger.settle_budget_reservation_in_transaction(
            owner_id=owner_id, reservation_id=_id(command, "network"), actual_units=network_units
        )
        ledger.settle_budget_reservation_in_transaction(
            owner_id=owner_id,
            reservation_id=_id(command, "spend"),
            actual_units=command.quote.settlement_units(returned_posts),
        )
        for source in sorted(command.member_sources):
            network = _id(command, BudgetMetric.NETWORK_REQUEST.value, source)
            if ledger._locked_reservations(owner_id, network):
                ledger.settle_budget_reservation_in_transaction(
                    owner_id=owner_id, reservation_id=network, actual_units=network_units
                )
            ledger.settle_budget_reservation_in_transaction(
                owner_id=owner_id,
                reservation_id=_id(command, BudgetMetric.PROVIDER_USD_MICROS.value, source),
                actual_units=command.quote.settlement_units(
                    member_posts[source] if member_posts is not None else None
                ),
            )


def recover_editorial_group_budgets_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    operation_id: UUID,
    job_id: UUID,
    member_sources: tuple[str, ...],
    now: datetime,
) -> int:
    """Charge persisted request caps after an abandoned group execution, without HTTP."""
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("group recovery requires aware caller transaction")
    ledger = ResourceBudgetService(session, clock=lambda: now)
    recovered = 0
    for number in range(1, 26):
        request_id = uuid5(job_id, f"group-request:{number}")
        ids = [uuid5(request_id, "network:x"), uuid5(request_id, "spend:x")]
        ids.extend(
            uuid5(request_id, f"{metric}:{source}")
            for source in member_sources
            for metric in ("network_request", "provider_usd_micros")
        )
        for reservation_id in ids:
            rows = ledger._locked_reservations(owner_id, reservation_id)
            if not rows or all(r.status != "reserved" for r in rows):
                continue
            if any(r.operation_id != operation_id or r.status != "reserved" for r in rows):
                raise BudgetReservationConflictError("group recovery identity or status changed")
            cap = rows[0].requested_units
            if any(r.requested_units != cap for r in rows):
                raise BudgetReservationConflictError("group request caps disagree")
            ledger.settle_budget_reservation_in_transaction(
                owner_id=owner_id, reservation_id=reservation_id, actual_units=cap
            )
            recovered += 1
        attempt_id = uuid5(request_id, "usage")
        attempt = session.scalar(
            select(ResourceUsageAttempt)
            .where(
                ResourceUsageAttempt.owner_id == owner_id,
                ResourceUsageAttempt.operation_id == operation_id,
                ResourceUsageAttempt.attempt_id == attempt_id,
                ResourceUsageAttempt.stage == "source_group_request",
            )
            .with_for_update()
        )
        if attempt is not None and attempt.outcome == UsageOutcome.STARTED.value:
            ledger.finish_attempt_in_transaction(
                owner_id=owner_id,
                attempt_id=attempt_id,
                outcome=UsageOutcome.FAILED,
                finished_at=now,
            )
    return recovered


def recover_source_icon_attempts_in_transaction(
    session: Session, *, owner_id: UUID, operation_id: UUID, now: datetime
) -> int:
    """Recover original network attempts from persisted icon stages, without a request."""
    stages = tuple(
        session.scalars(
            select(ResourceUsageAttempt.stage)
            .where(
                ResourceUsageAttempt.owner_id == owner_id,
                ResourceUsageAttempt.operation_id == operation_id,
                ResourceUsageAttempt.stage.startswith("source.icons."),
                ResourceUsageAttempt.outcome == UsageOutcome.STARTED.value,
            )
            .distinct()
        )
    )
    ledger = ResourceBudgetService(session, clock=lambda: now)
    return sum(
        len(
            ledger.recover_abandoned_attempts_in_transaction(
                owner_id=owner_id,
                operation_id=operation_id,
                component_key="source.icons",
                stage=stage,
                finished_at=now,
            )
        )
        for stage in stages
    )
