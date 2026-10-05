"""Atomic model selection and original AiCall statistics; no model calls on reads."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.capability_models import AiCapabilityConfiguration
from ai.capability_schemas import (
    AI_CAPABILITIES,
    AiCapabilityChoice,
    AiCostCircuitAckInput,
    AiCostCircuitView,
    AiModelChoice,
    AiModelConfigurationView,
    AiModelOverview,
    AiModelServerSpec,
    AiModelSwitchInput,
    AiModelUsageView,
    CapabilityKey,
    FrozenAiModel,
    FrozenAiRouting,
    capability_for_purpose,
    digest,
)
from ai.models import AiCall
from core.config import Settings, get_settings
from core.errors import ApplicationError
from jobs.services import load_job_execution_configuration
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    has_succeeded_action_target_in_transaction,
    list_action_audits_in_transaction,
    load_completed_audit_in_transaction,
)


def protected_model_catalog(settings: Settings) -> dict[str, AiModelServerSpec]:
    catalog = {
        "default": AiModelServerSpec(
            transport="codex",
            provider_key="codex_app_server",
            model=settings.ai_model,
            reasoning_tokens=settings.ai_reasoning_tokens,
            vision=True,
            timeout_seconds=min(600, int(settings.ai_timeout_seconds)),
        )
    }
    try:
        for key, raw in settings.ai_model_catalog.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key):
                raise ValueError("invalid protected model catalog key")
            defaults = (
                {"reasoning_tokens": settings.ai_reasoning_tokens} if key == "default" else {}
            )
            catalog[key] = AiModelServerSpec.model_validate({**defaults, **raw})
    except (ValidationError, ValueError):
        raise ApplicationError("invalid_ai_input") from None
    return catalog


def _current(session: Session, owner_id: UUID) -> AiCapabilityConfiguration | None:
    return session.scalar(
        select(AiCapabilityConfiguration)
        .where(
            AiCapabilityConfiguration.owner_id == owner_id,
        )
        .order_by(AiCapabilityConfiguration.version.desc())
        .limit(1)
    )


def _configuration(
    session: Session, *, owner_id: UUID, settings: Settings
) -> AiModelConfigurationView:
    row = _current(session, owner_id)
    catalog = protected_model_catalog(settings)
    overrides = row.overrides if row else {}
    capabilities = []
    for key, definition in AI_CAPABILITIES.items():
        candidate = overrides.get(key)
        origin = "admin"
        if candidate is None:
            candidate, origin = settings.ai_capability_models.get(key), "env"
        if candidate is None:
            candidate, origin = "default", "default"
        if candidate not in catalog:
            if origin == "admin":
                raise ApplicationError("ai_model_unavailable")
            candidate, origin = "default", "default"
        model = catalog[candidate]
        capabilities.append(
            AiCapabilityChoice(
                key=key,
                label=definition.label,
                env=definition.env,
                current=FrozenAiModel(
                    key=candidate,
                    provider=model.provider_key,
                    model=model.model,
                    component_key=model.component_key,
                    vision=model.vision,
                    catalog_sha256=model.sha256,
                ),
                source=origin,
            )
        )
    return AiModelConfigurationView(
        version=row.version if row else 0,
        created_at=row.created_at if row else None,
        capabilities=tuple(capabilities),
        choices=tuple(
            AiModelChoice(
                key=key,
                provider=model.provider_key,
                model=model.model,
                vision=model.vision,
                configured=model.configured,
                component_key=model.component_key,
                currency=model.currency,
                input_rate_micros_per_million=model.input_rate_micros_per_million,
                output_rate_micros_per_million=model.output_rate_micros_per_million,
            )
            for key, model in catalog.items()
        ),
        calls_enabled=settings.ai_enabled,
        paid_requests_enabled=settings.ai_paid_requests_enabled,
        compatible_requests_enabled=settings.ai_openai_compatible_requests_enabled,
    )


def freeze_ai_routing_in_transaction(
    session: Session, *, owner_id: UUID, settings: Settings | None = None
) -> FrozenAiRouting:
    if not session.in_transaction():
        raise RuntimeError("AI model routing freeze requires caller transaction")
    view = _configuration(session, owner_id=owner_id, settings=settings or get_settings())
    return FrozenAiRouting(
        owner_id=owner_id,
        configuration_version=view.version,
        models={item.key: item.current for item in view.capabilities},
    )


def freeze_ai_job_scope_in_transaction(
    session: Session, *, owner_id: UUID, settings: Settings | None = None
) -> dict[str, str]:
    routing = freeze_ai_routing_in_transaction(session, owner_id=owner_id, settings=settings)
    return {"ai_routing": routing.model_dump_json(), "ai_routing_hash": routing.sha256}


def load_frozen_ai_routing_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID
) -> FrozenAiRouting | None:
    cfg = load_job_execution_configuration(session, job_id=job_id)
    if cfg is None or cfg.owner_id != owner_id:
        raise ApplicationError("ai_configuration_conflict")
    raw = cfg.scope.get("ai_routing")
    if raw is None:
        return None  # Existing admitted Jobs retain their original explicit model contract.
    if not isinstance(raw, str) or len(raw.encode()) > 65536:
        raise ApplicationError("invalid_ai_input")
    try:
        routing = FrozenAiRouting.model_validate_json(raw)
    except ValidationError:
        raise ApplicationError("invalid_ai_input") from None
    if routing.owner_id != owner_id or cfg.scope.get("ai_routing_hash") != routing.sha256:
        raise ApplicationError("ai_configuration_conflict")
    return routing


class AiCapabilityService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session, self.settings, self.clock = session, settings, clock

    def get(self, *, owner_id: UUID) -> AiModelConfigurationView:
        self.session.rollback()
        with self.session.begin():
            return _configuration(self.session, owner_id=owner_id, settings=self.settings)

    def switch(self, *, owner_id: UUID, command: AiModelSwitchInput) -> AiModelConfigurationView:
        self.session.rollback()
        with self.session.begin():
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(f"ai-model-config:{owner_id}", 0)
                    )
                )
            )
            before = _configuration(self.session, owner_id=owner_id, settings=self.settings)
            _audit, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="models.switch",
                target_ref=f"capability:{command.capability}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                before_state=before.model_dump(mode="json"),
                now=self.clock(),
            )
            if replayed:
                done = load_completed_audit_in_transaction(
                    self.session, owner_id=owner_id, operation_id=command.operation_id
                )
                if done is not None:
                    return AiModelConfigurationView.model_validate(done)
            if before.version != command.expected_version:
                raise ApplicationError("ai_configuration_conflict")
            catalog = protected_model_catalog(self.settings)
            if command.model_key is not None and command.model_key not in catalog:
                raise ApplicationError("invalid_ai_input")
            current = _current(self.session, owner_id)
            overrides = dict(current.overrides) if current else {}
            if command.model_key is None:
                overrides.pop(command.capability, None)
            else:
                overrides[command.capability] = command.model_key
            self.session.add(
                AiCapabilityConfiguration(
                    owner_id=owner_id,
                    version=before.version + 1,
                    operation_id=command.operation_id,
                    input_hash=bytes.fromhex(digest(command.model_dump(mode="json"))),
                    overrides=overrides,
                    created_at=self.clock(),
                )
            )
            self.session.flush()
            after = _configuration(self.session, owner_id=owner_id, settings=self.settings)
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=after.model_dump(mode="json"),
                now=self.clock(),
            )
            return after

    def overview(self, *, owner_id: UUID, days: int = 7) -> AiModelOverview:
        if not 1 <= days <= 90:
            raise ApplicationError("invalid_ai_input")
        self.session.rollback()
        with self.session.begin():
            configuration = _configuration(self.session, owner_id=owner_id, settings=self.settings)
            rows = self.session.execute(
                select(
                    AiCall.purpose,
                    AiCall.provider,
                    AiCall.model,
                    AiCall.prompt_version,
                    AiCall.currency,
                    func.count().label("calls"),
                    func.count().filter(AiCall.status == "succeeded").label("succeeded"),
                    func.count().filter(AiCall.status == "running").label("running"),
                    func.count()
                    .filter(AiCall.status == "failed", AiCall.failure_code != "timeout")
                    .label("failed"),
                    func.count()
                    .filter(
                        (AiCall.status == "unknown")
                        | ((AiCall.status == "failed") & (AiCall.failure_code == "timeout"))
                    )
                    .label("unknown"),
                    func.percentile_disc(0.5)
                    .within_group(AiCall.duration_ms)
                    .filter(AiCall.status != "running")
                    .label("p50"),
                    func.percentile_disc(0.95)
                    .within_group(AiCall.duration_ms)
                    .filter(AiCall.status != "running")
                    .label("p95"),
                    func.sum(AiCall.input_tokens).label("input_tokens"),
                    func.sum(AiCall.cached_input_tokens).label("cached_input_tokens"),
                    func.sum(AiCall.output_tokens).label("output_tokens"),
                    func.sum(AiCall.cost_estimate_micros).label("estimate"),
                    func.sum(AiCall.cost_actual_micros).label("actual"),
                    func.sum(AiCall.cost_cap_micros).label("cap"),
                )
                .where(
                    AiCall.owner_id == owner_id,
                    AiCall.created_at >= self.clock() - timedelta(days=days),
                )
                .group_by(
                    AiCall.purpose,
                    AiCall.provider,
                    AiCall.model,
                    AiCall.prompt_version,
                    AiCall.currency,
                )
                .order_by(AiCall.purpose, AiCall.model)
            )
            usage = []
            for row in rows:
                try:
                    capability: CapabilityKey | Literal["embedding"] = (
                        "embedding"
                        if row.purpose == "events.embedding"
                        else capability_for_purpose(row.purpose)
                    )
                except ValueError:
                    continue  # Other original AI purposes remain in their own audit API.
                usage.append(
                    AiModelUsageView(
                        capability=capability,
                        purpose=row.purpose,
                        provider=row.provider,
                        model=row.model,
                        prompt_version=row.prompt_version,
                        currency=row.currency,
                        calls=row.calls,
                        succeeded=row.succeeded,
                        failed=row.failed,
                        unknown=row.unknown,
                        running=row.running,
                        latency_p50_ms=row.p50,
                        latency_p95_ms=row.p95,
                        input_tokens=row.input_tokens,
                        cached_input_tokens=row.cached_input_tokens,
                        output_tokens=row.output_tokens,
                        cost_estimate_micros=row.estimate,
                        cost_actual_micros=row.actual,
                        cost_cap_micros=row.cap,
                    )
                )
            history = list_action_audits_in_transaction(
                self.session, owner_id=owner_id, action="models.switch", limit=30
            )
            circuits = self.session.scalars(
                select(AiCall)
                .where(
                    AiCall.owner_id == owner_id,
                    AiCall.cost_actual_micros > AiCall.cost_cap_micros,
                )
                .order_by(AiCall.created_at.desc(), AiCall.id)
                .limit(100)
            ).all()
            return AiModelOverview(
                days=days,
                configuration=configuration,
                usage=tuple(usage),
                history=tuple(history),
                cost_circuits=tuple(
                    AiCostCircuitView.model_validate(
                        dict(
                            call_id=row.id,
                            provider=row.provider,
                            model=row.model,
                            currency=row.currency,
                            cost_actual_micros=row.cost_actual_micros,
                            cost_cap_micros=row.cost_cap_micros,
                            created_at=row.created_at,
                            acknowledged=has_succeeded_action_target_in_transaction(
                                self.session,
                                owner_id=owner_id,
                                action="ai.cost_circuit.ack",
                                target_ref=f"ai-call:{row.id}",
                            ),
                        )
                    )
                    for row in circuits
                ),
            )

    def acknowledge_cost_circuit(
        self, *, owner_id: UUID, command: AiCostCircuitAckInput
    ) -> AiModelConfigurationView:
        self.session.rollback()
        with self.session.begin():
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(f"ai-model-config:{owner_id}", 0)
                    )
                )
            )
            before = _configuration(self.session, owner_id=owner_id, settings=self.settings)
            _audit, replayed = accept_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="ai.cost_circuit.ack",
                target_ref=f"ai-call:{command.call_id}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                before_state=before.model_dump(mode="json"),
                now=self.clock(),
            )
            if replayed:
                completed = load_completed_audit_in_transaction(
                    self.session, owner_id=owner_id, operation_id=command.operation_id
                )
                if completed is not None:
                    return AiModelConfigurationView.model_validate(completed)
            if before.version != command.expected_version:
                raise ApplicationError("ai_configuration_conflict")
            row = self.session.scalar(
                select(AiCall)
                .where(AiCall.owner_id == owner_id, AiCall.id == command.call_id)
                .with_for_update()
            )
            if (
                row is None
                or row.status not in ("succeeded", "unknown")
                or row.cost_actual_micros is None
                or row.cost_cap_micros is None
                or row.cost_actual_micros <= row.cost_cap_micros
                or has_succeeded_action_target_in_transaction(
                    self.session,
                    owner_id=owner_id,
                    action="ai.cost_circuit.ack",
                    target_ref=f"ai-call:{command.call_id}",
                )
            ):
                raise ApplicationError("invalid_ai_input")
            current = _current(self.session, owner_id)
            self.session.add(
                AiCapabilityConfiguration(
                    owner_id=owner_id,
                    version=before.version + 1,
                    operation_id=command.operation_id,
                    input_hash=bytes.fromhex(digest(command.model_dump(mode="json"))),
                    overrides=dict(current.overrides) if current else {},
                    created_at=self.clock(),
                )
            )
            self.session.flush()
            after = _configuration(self.session, owner_id=owner_id, settings=self.settings)
            complete_audit_in_transaction(
                self.session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=after.model_dump(mode="json"),
                now=self.clock(),
            )
            return after
