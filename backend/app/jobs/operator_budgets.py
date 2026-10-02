from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from jobs.models import ResourceBudgetPolicy
from jobs.schemas import BudgetPolicyInput, BudgetPolicyView
from jobs.services import BudgetPolicyConflictError, ResourceBudgetService


def save_operator_budget_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    command: BudgetPolicyInput,
    expected_policy_version: int,
    now: datetime,
) -> BudgetPolicyView:
    """CAS the existing ledger policy in the caller's audit transaction."""
    if not session.in_transaction() or now.utcoffset() is None or expected_policy_version < 0:
        raise ValueError("budget CAS requires transaction, aware clock and a valid version")
    row = session.scalar(
        select(ResourceBudgetPolicy)
        .where(
            ResourceBudgetPolicy.owner_id == owner_id,
            ResourceBudgetPolicy.budget_key == command.budget_key,
        )
        .with_for_update()
    )
    if row is None:
        if expected_policy_version != 0:
            raise BudgetPolicyConflictError("policy version changed")
        inserted = session.scalar(
            insert(ResourceBudgetPolicy)
            .values(
                id=uuid4(),
                owner_id=owner_id,
                **command.model_dump(mode="python"),
                policy_version=1,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
            .returning(ResourceBudgetPolicy.id)
        )
        if inserted is None:
            raise BudgetPolicyConflictError(
                "policy was concurrently created or source window exists"
            )
    elif row.policy_version != expected_policy_version:
        raise BudgetPolicyConflictError("policy version changed")
    return ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
        owner_id=owner_id, command=command
    )
