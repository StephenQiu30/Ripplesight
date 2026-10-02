"""Model cost circuit facts from the original AiCall ledger, without changing configuration."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.models import AiCall
from operations.services import has_succeeded_action_target_in_transaction


@dataclass(frozen=True, slots=True)
class ModelCostCircuit:
    provider: str
    model: str
    currency: str | None
    actual_micros: int
    cap_micros: int
    call_id: UUID
    opened_at: datetime


def load_model_cost_circuits_in_transaction(
    session: Session, *, owner_id: UUID
) -> tuple[ModelCostCircuit, ...]:
    if not session.in_transaction():
        raise ValueError("cost circuit facts require caller transaction")
    rows = session.scalars(
        select(AiCall)
        .where(AiCall.owner_id == owner_id, AiCall.cost_actual_micros > AiCall.cost_cap_micros)
        .order_by(AiCall.provider, AiCall.model, AiCall.created_at.desc(), AiCall.id.desc())
    )
    return tuple(
        ModelCostCircuit(
            row.provider,
            row.model,
            row.currency,
            int(row.cost_actual_micros or 0),
            int(row.cost_cap_micros or 0),
            row.id,
            row.created_at,
        )
        for row in rows
        if not has_succeeded_action_target_in_transaction(
            session, owner_id=owner_id, action="ai.cost_circuit.ack", target_ref=f"ai-call:{row.id}"
        )
    )
