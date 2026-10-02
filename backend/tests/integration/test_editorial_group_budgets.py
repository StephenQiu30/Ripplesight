from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from tests.integration.test_editorial_source_profiles import NOW, budgets
from tests.integration.test_editorial_source_profiles import engine as engine

from jobs.editorial_budgets import (
    EditorialGroupBudgetRequest,
    reserve_editorial_group_budgets_in_transaction,
    settle_editorial_group_budgets_in_transaction,
)
from jobs.schemas import BudgetContext, BudgetMetric, BudgetPolicyInput, XApiPostReadCost
from jobs.services import ResourceBudgetError, ResourceBudgetService


def test_group_budget_global_once_members_split_and_missing_member_is_atomic(engine):
    owner, connection, job = uuid4(), uuid4(), uuid4()
    refs = tuple("ed_x_search_" + uuid4().hex for _ in range(2))
    request = EditorialGroupBudgetRequest(
        operation_id=uuid4(),
        reservation_id=uuid4(),
        context=BudgetContext(source_ref="x", connection_ref=str(connection), job_ref=str(job)),
        member_sources=refs,
        manifest_sha256="a" * 64,
        quote=XApiPostReadCost(max_posts=100, unit_price_usd_micros=10),
    )
    with Session(engine) as session:
        budgets(session, owner)
        ledger = ResourceBudgetService(session, clock=lambda: NOW)

        def save(metric, ref, key):
            ledger.save_budget_policy(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key=key,
                    metric=metric,
                    scope_kind="source" if ref else "global",
                    scope_reference=ref,
                    limit_units=10000,
                    window_seconds=3600,
                    window_anchor_at=NOW - timedelta(minutes=1),
                    enabled=True,
                ),
            )

        save(BudgetMetric.X_API_USD_MICROS, None, "x.global")
        save(BudgetMetric.X_API_USD_MICROS, "x", "x.source")
        save(BudgetMetric.PROVIDER_USD_MICROS, refs[0], "x.member0")
        with pytest.raises(ResourceBudgetError), session.begin():
            reserve_editorial_group_budgets_in_transaction(
                session, owner_id=owner, command=request, now=NOW
            )
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM resource_budget_reservations")) == 0
        save(BudgetMetric.PROVIDER_USD_MICROS, refs[1], "x.member1")
        for i, ref in enumerate(refs):
            save(BudgetMetric.NETWORK_REQUEST, ref, f"net.member{i}")
        with session.begin():
            decision = reserve_editorial_group_budgets_in_transaction(
                session, owner_id=owner, command=request, now=NOW
            )
            assert decision.status == "reserved"
        with session.begin():
            settle_editorial_group_budgets_in_transaction(
                session,
                owner_id=owner,
                command=request,
                member_posts={refs[0]: 2, refs[1]: 1},
                returned_posts=3,
                network_units=1,
                now=NOW,
            )
        with session.begin():
            rows = session.execute(
                text(
                    "SELECT p.budget_key,w.used_units,w.reserved_units FROM "
                    "resource_budget_windows w JOIN resource_budget_policies p ON "
                    "p.id=w.budget_policy_id"
                )
            ).all()
            values = {r.budget_key: (r.used_units, r.reserved_units) for r in rows}
        assert values["controlled.network_request"] == (1, 0)
        assert values["x.global"] == values["x.source"] == (30, 0)
        assert values["x.member0"] == (20, 0) and values["x.member1"] == (10, 0)
        assert values["net.member0"] == values["net.member1"] == (1, 0)
        with session.begin():
            settle_editorial_group_budgets_in_transaction(
                session,
                owner_id=owner,
                command=request,
                member_posts={refs[0]: 2, refs[1]: 1},
                returned_posts=3,
                network_units=1,
                now=NOW,
            )
        with pytest.raises(ResourceBudgetError), session.begin():
            reserve_editorial_group_budgets_in_transaction(
                session, owner_id=owner, command=request, now=NOW
            )
