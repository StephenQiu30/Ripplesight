"""Freeze every selected benchmark model independently from eleven production defaults."""

from uuid import UUID

from sqlalchemy.orm import Session

from ai.capability_schemas import FrozenAiBenchmark, FrozenAiModel
from ai.capability_services import freeze_ai_routing_in_transaction, protected_model_catalog
from core.config import Settings, get_settings
from core.errors import ApplicationError
from jobs.services import load_job_execution_configuration


def freeze_ai_benchmark_in_transaction(
    session: Session, *, owner_id: UUID, models: list[str], settings: Settings | None = None
) -> FrozenAiBenchmark:
    settings = settings or get_settings()
    routing = freeze_ai_routing_in_transaction(session, owner_id=owner_id, settings=settings)
    catalog = protected_model_catalog(settings)
    if any(key not in catalog for key in models):
        raise ApplicationError("invalid_ai_input")
    return FrozenAiBenchmark(
        owner_id=owner_id,
        configuration_version=routing.configuration_version,
        models={
            key: FrozenAiModel(
                key=key,
                provider=catalog[key].provider_key,
                model=catalog[key].model,
                component_key=catalog[key].component_key,
                vision=catalog[key].vision,
                catalog_sha256=catalog[key].sha256,
            )
            for key in models
        },
    )


def load_ai_benchmark_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> tuple[FrozenAiBenchmark, FrozenAiModel] | None:
    if not session.in_transaction():
        raise RuntimeError("benchmark frozen reads require caller transaction")
    job = load_job_execution_configuration(session, job_id=job_id)
    if job is None or job.owner_id != owner_id or job.kind != "analysis.selectbench":
        return None
    raw = job.scope.get("ai_benchmark_models")
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw.encode()) > 65536:
        raise ApplicationError("invalid_ai_input")
    frozen = FrozenAiBenchmark.model_validate_json(raw)
    key = job.scope.get("benchmark_model_ref")
    if (
        frozen.owner_id != owner_id
        or frozen.sha256 != job.scope.get("ai_benchmark_hash")
        or not isinstance(key, str)
        or key not in frozen.models
    ):
        raise ApplicationError("ai_configuration_conflict")
    return frozen, frozen.models[key]
