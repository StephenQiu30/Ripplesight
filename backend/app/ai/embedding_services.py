"""Read an original Job's independent embedding configuration in caller transaction."""

from uuid import UUID

from sqlalchemy.orm import Session

from ai.embedding_contract import FrozenEmbeddingConfiguration
from jobs.services import load_job_execution_configuration


def load_frozen_embedding_configuration_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> FrozenEmbeddingConfiguration | None:
    if not session.in_transaction():
        raise RuntimeError("embedding contract requires caller transaction")
    job = load_job_execution_configuration(session, job_id=job_id)
    if job is None or job.owner_id != owner_id or job.kind != "events.embed":
        return None
    raw = job.scope.get("embedding_configuration")
    if not isinstance(raw, str):
        return None
    frozen = FrozenEmbeddingConfiguration.model_validate_json(raw)
    if job.scope.get("embedding_configuration_hash") != frozen.sha256:
        raise ValueError("embedding configuration hash differs from the admitted job")
    return frozen
