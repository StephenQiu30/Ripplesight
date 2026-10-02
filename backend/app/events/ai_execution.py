"""Original Job routing for event stages; model switches never reinterpret admitted work."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from ai.capability_routing import create_ai_client_for_frozen_model
from ai.capability_schemas import FrozenAiRouting, digest
from ai.capability_services import (
    freeze_ai_job_scope_in_transaction,
    load_frozen_ai_routing_in_transaction,
)
from ai.schemas import AiCallStatus, SavedAiCallView
from ai.services import AiCompletionClient, load_saved_ai_call_in_transaction
from core.config import Settings


def freeze_event_ai_scope_in_transaction(
    session: Session, *, owner_id: UUID, settings: Settings
) -> dict[str, str]:
    return freeze_ai_job_scope_in_transaction(session, owner_id=owner_id, settings=settings)


def event_ai_contract(routing: FrozenAiRouting, purposes: tuple[str, ...]) -> str:
    return digest(
        {purpose: routing.for_purpose(purpose).model_dump(mode="json") for purpose in purposes}
    )


def load_event_ai_contract_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, purposes: tuple[str, ...], legacy_model: str
) -> str:
    routing = load_frozen_ai_routing_in_transaction(session, owner_id=owner_id, job_id=job_id)
    return event_ai_contract(routing, purposes) if routing is not None else legacy_model


def create_event_stage_client(
    sessions: sessionmaker[Session],
    *,
    owner_id: UUID,
    job_id: UUID,
    purpose: str,
    settings: Settings,
    legacy_factory: Callable[[Settings], AiCompletionClient],
) -> AiCompletionClient:
    with sessions() as session, session.begin():
        routing = load_frozen_ai_routing_in_transaction(session, owner_id=owner_id, job_id=job_id)
    return (
        create_ai_client_for_frozen_model(settings, routing.for_purpose(purpose))
        if routing is not None
        else legacy_factory(settings)
    )


def load_verified_event_call_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, call_id: UUID, purpose: str
) -> SavedAiCallView | None:
    call = load_saved_ai_call_in_transaction(
        session, owner_id=owner_id, call_id=call_id, job_id=job_id, purpose=purpose
    )
    if call is None or call.status is not AiCallStatus.SUCCEEDED:
        return None
    routing = load_frozen_ai_routing_in_transaction(session, owner_id=owner_id, job_id=job_id)
    if routing is not None:
        model = routing.for_purpose(purpose)
        if (
            call.provider != model.provider
            or call.model != model.model
            or call.model_key != model.key
            or call.routing_version != routing.configuration_version
            or call.routing_hash != routing.sha256
        ):
            return None
    return call
