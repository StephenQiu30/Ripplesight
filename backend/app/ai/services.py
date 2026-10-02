from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from ai.adapters.codex_app_server import CodexAppServerClient
from ai.benchmark_services import load_ai_benchmark_in_transaction
from ai.capability_routing import create_ai_client_for_frozen_model
from ai.capability_schemas import AiPriceQuote, FrozenAiModel
from ai.capability_services import load_frozen_ai_routing_in_transaction
from ai.embedding_services import load_frozen_embedding_configuration_in_transaction
from ai.models import AiCall
from ai.schemas import (
    AiCallError,
    AiCallStatus,
    AiCompletion,
    AiFailureCode,
    AiImageInput,
    AiTokenUsage,
    SavedAiCallView,
)
from core.config import Settings
from jobs.ai_budgets import (
    reserve_ai_provider_budgets_in_transaction,
    settle_ai_provider_budgets_in_transaction,
)
from jobs.schemas import (
    AiTokenCostQuote,
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetError, ResourceBudgetService
from operations.services import has_succeeded_action_target_in_transaction

AI_COMPONENT_KEY = "codex.app-server"
_AI_USAGE_STAGE = "analysis.call"


class AiCompletionClient(Protocol):
    provider: str

    @property
    def model(self) -> str: ...

    def complete(
        self,
        *,
        prompt: str,
        output_schema: Mapping[str, Any],
        instructions: str = "",
    ) -> AiCompletion: ...

    def close(self) -> None: ...


class AiRoutingLineage(Protocol):
    @property
    def configuration_version(self) -> int: ...

    @property
    def sha256(self) -> str: ...


def create_ai_client(settings: Settings) -> AiCompletionClient:
    if not settings.ai_enabled:
        raise AiCallError(AiFailureCode.UNAVAILABLE, "analysis is disabled")
    command: Sequence[str] = shlex.split(settings.ai_command)
    if len(command) != 2 or Path(command[0]).name != "codex" or command[1] != "app-server":
        raise AiCallError(AiFailureCode.UNAVAILABLE, "analysis command is not Codex app-server")
    client = CodexAppServerClient(
        model=settings.ai_model,
        command=command,
        effort=settings.ai_effort,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    client.capability_settings = settings
    return client


def load_saved_ai_call_in_transaction(
    session: Session, *, owner_id: UUID, call_id: UUID, job_id: UUID, purpose: str
) -> SavedAiCallView | None:
    if not session.in_transaction():
        raise RuntimeError("saved AI calls require caller transaction")
    row = session.scalar(
        select(AiCall).where(
            AiCall.owner_id == owner_id,
            AiCall.id == call_id,
            AiCall.job_id == job_id,
            AiCall.purpose == purpose,
        )
    )
    if row is None:
        return None
    return SavedAiCallView(
        id=row.id,
        provider=row.provider,
        model=row.model,
        model_key=row.model_key,
        routing_version=row.routing_version,
        routing_hash=row.routing_hash.hex() if row.routing_hash else None,
        status=AiCallStatus(row.status),
        input_fingerprint=row.input_fingerprint.hex(),
    )


def recover_abandoned_ai_calls_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, current_epoch: int, now: datetime
) -> int:
    """After caller verifies the new lease, quarantine only original lower-epoch calls."""
    if not session.in_transaction() or current_epoch < 1 or now.utcoffset() is None:
        raise ValueError("AI recovery needs a caller transaction, valid epoch and aware clock")
    rows = list(
        session.scalars(
            select(AiCall)
            .where(
                AiCall.owner_id == owner_id,
                AiCall.job_id == job_id,
                AiCall.status == AiCallStatus.RUNNING.value,
                AiCall.execution_epoch < current_epoch,
            )
            .order_by(AiCall.id)
            .with_for_update()
        )
    )
    budget = ResourceBudgetService(session, clock=lambda: now)
    for row in rows:
        settle_ai_provider_budgets_in_transaction(
            session,
            owner_id=owner_id,
            call_id=row.id,
            cost_units=None,
            now=now,
        )
        budget.settle_budget_reservation_in_transaction(
            owner_id=owner_id,
            reservation_id=row.id,
            actual_units=1,
        )
        budget.finish_attempt_in_transaction(
            owner_id=owner_id,
            attempt_id=row.id,
            outcome=UsageOutcome.FAILED,
            finished_at=max(now, row.created_at),
        )
        row.status, row.failure_code = AiCallStatus.UNKNOWN.value, AiFailureCode.TIMEOUT.value
        row.duration_ms = max(0, int((now - row.created_at).total_seconds() * 1000))
    return len(rows)


class AiService:
    def __init__(
        self,
        session: Session,
        client: AiCompletionClient,
        *,
        clock: Callable[[], datetime] | None = None,
        settings: Settings | None = None,
        guard: Callable[[Session], object] | None = None,
        execution_epoch: int | None = None,
    ) -> None:
        bind = session.get_bind()
        engine = bind.engine if isinstance(bind, Connection) else bind
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))
        self._settings = settings or getattr(client, "capability_settings", None)
        self._guard, self._epoch = guard, execution_epoch
        self._admission_guard: Callable[[Session], object] | None = None
        if execution_epoch is not None and execution_epoch < 1:
            raise ValueError("AI execution epoch must be positive")

    def with_admission_guard(
        self,
        guard: Callable[[Session], object],
        *,
        execution_epoch: int | None = None,
    ) -> AiService:
        """Bind an owning domain's final material check without replacing existing guards."""
        if (
            execution_epoch is not None
            and self._epoch is not None
            and execution_epoch != self._epoch
        ):
            raise ValueError("AI execution epoch cannot change while binding admission")

        def combined(session: Session) -> None:
            if self._admission_guard is not None:
                self._admission_guard(session)
            guard(session)

        with self._sessions() as session:
            bound = AiService(
                session,
                self._client,
                clock=self._clock,
                settings=self._settings,
                guard=self._guard,
                execution_epoch=self._epoch if execution_epoch is None else execution_epoch,
            )
        bound._admission_guard = combined
        return bound

    def _route(
        self, owner_id: UUID, job_id: UUID | None, purpose: str
    ) -> tuple[AiCompletionClient, FrozenAiModel | None, AiRoutingLineage | None, bool]:
        routing = None
        if purpose == "events.embedding":
            if job_id is not None:
                with self._sessions() as session, session.begin():
                    profile = load_frozen_embedding_configuration_in_transaction(
                        session, owner_id=owner_id, job_id=job_id
                    )
                if profile is not None:
                    if getattr(self._client, "embedding_configuration", None) != profile:
                        raise AiCallError(AiFailureCode.UNAVAILABLE, "frozen embedding differs")
                    return self._client, profile.model_identity, profile, False
            return self._client, None, None, False
        if purpose.startswith("analysis.selectbench.") and job_id is not None:
            with self._sessions() as session, session.begin():
                benchmark = load_ai_benchmark_in_transaction(
                    session, owner_id=owner_id, job_id=job_id
                )
            if benchmark is not None:
                benchmark_profile, model = benchmark
                if (
                    model.component_key == "codex.app-server"
                    and self._client.provider == model.provider
                    and self._client.model == model.model
                ):
                    return self._client, model, benchmark_profile, False
                if self._settings is None:
                    raise AiCallError(
                        AiFailureCode.UNAVAILABLE, "benchmark model needs protected settings"
                    )
                return (
                    create_ai_client_for_frozen_model(self._settings, model),
                    model,
                    benchmark_profile,
                    True,
                )
        if self._settings is not None and job_id is not None:
            with self._sessions() as session, session.begin():
                routing = load_frozen_ai_routing_in_transaction(
                    session,
                    owner_id=owner_id,
                    job_id=job_id,
                )
        if routing is None:
            return self._client, None, None, False
        model = routing.for_purpose(purpose)
        current = getattr(self._client, "frozen_model", None)
        if current == model:
            return self._client, model, routing, False
        assert self._settings is not None
        return create_ai_client_for_frozen_model(self._settings, model), model, routing, True

    def complete(
        self,
        *,
        owner_id: UUID,
        job_id: UUID | None,
        purpose: str,
        prompt_version: str,
        prompt: str,
        output_schema: Mapping[str, Any],
        instructions: str = "",
        images: Sequence[AiImageInput] = (),
    ) -> AiCompletion:
        if not 0 < len(purpose) <= 128 or not 0 < len(prompt_version) <= 128:
            raise ValueError("AI purpose and prompt version must contain at most 128 characters")
        if self._settings is not None and not self._settings.ai_enabled:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "AI calls are paused")
        client, model, routing, owned = self._route(owner_id, job_id, purpose)
        try:
            images = images[:1]
            if not 0 < len(client.provider) <= 64 or not 0 < len(client.model) <= 128:
                raise ValueError("AI provider or model exceeds the original ledger bound")
            if images and (model is not None and not model.vision):
                images = ()  # Text-only compatible selections never claim to have seen an image.
            call_id, started_at = uuid4(), self._clock()
            fingerprint = _input_fingerprint(
                model=client.model,
                prompt_version=prompt_version,
                prompt=prompt,
                output_schema=output_schema,
                instructions=instructions,
                provider=client.provider,
                routing_hash=routing.sha256 if routing else None,
                image_hashes=tuple(image.sha256 for image in images),
            )
            pricing = getattr(client, "pricing_spec", None)
            quote = None
            if pricing is not None:
                quote = pricing.quote(
                    input_tokens_cap=len(prompt.encode())
                    + len(instructions.encode())
                    + len(json.dumps(dict(output_schema), ensure_ascii=False).encode())
                    + sum(image.input_tokens_cap for image in images)
                    + 1024,
                    output_tokens_cap=pricing.max_output_tokens,
                )
            paid = quote is not None and quote.cap_micros > 0
            if paid and (
                self._settings is None
                or not self._settings.ai_paid_requests_enabled
                or self._guard is None
                or self._epoch is None
                or job_id is None
                or routing is None
                or model is None
            ):
                raise AiCallError(AiFailureCode.UNAVAILABLE, "paid AI requires a frozen leased job")
            try:
                self._reserve(
                    owner_id=owner_id,
                    job_id=job_id,
                    call_id=call_id,
                    purpose=purpose,
                    prompt_version=prompt_version,
                    fingerprint=fingerprint,
                    started_at=started_at,
                    client=client,
                    model=model,
                    routing=routing,
                    quote=quote,
                    paid=paid,
                )
            except ResourceBudgetError:
                raise AiCallError(
                    AiFailureCode.UNAVAILABLE, "AI request admission was denied before sending"
                ) from None
            try:
                if images:
                    multimodal = getattr(client, "complete_multimodal", None)
                    if multimodal is None:
                        raise AiCallError(AiFailureCode.UNAVAILABLE, "client has no image input")
                    completion = cast(
                        AiCompletion,
                        multimodal(
                            prompt=prompt,
                            output_schema=output_schema,
                            instructions=instructions,
                            images=images[:1],
                        ),
                    )
                else:
                    completion = client.complete(
                        prompt=prompt,
                        output_schema=output_schema,
                        instructions=instructions,
                    )
                if completion.provider != client.provider or completion.model != client.model:
                    raise AiCallError(
                        AiFailureCode.INVALID_OUTPUT, "provider model receipt differs"
                    )
            except AiCallError as error:
                unknown = (
                    error.outcome_unknown
                    or error.code == AiFailureCode.TIMEOUT
                    or (paid and error.code != AiFailureCode.RATE_LIMITED)
                )
                error.outcome_unknown = unknown
                self._finish(
                    owner_id,
                    call_id,
                    status=AiCallStatus.UNKNOWN if unknown else AiCallStatus.FAILED,
                    failure=error.code,
                    completion=None,
                    quote=quote,
                )
                error.call_id = call_id
                raise
            except Exception as error:
                failure = AiCallError(
                    AiFailureCode.FAILED, "AI client failed unexpectedly", outcome_unknown=paid
                )
                self._finish(
                    owner_id,
                    call_id,
                    status=AiCallStatus.UNKNOWN if paid else AiCallStatus.FAILED,
                    failure=failure.code,
                    completion=None,
                    quote=quote,
                )
                failure.call_id = call_id
                raise failure from error
            unknown = bool(paid and not completion.usage_reported)
            active = self._finish(
                owner_id,
                call_id,
                status=AiCallStatus.UNKNOWN if unknown else AiCallStatus.SUCCEEDED,
                failure=AiFailureCode.TIMEOUT if unknown else None,
                completion=completion,
                quote=quote,
            )
            if not active or unknown:
                raise AiCallError(
                    AiFailureCode.TIMEOUT,
                    "original AI outcome remains unknown",
                    call_id=call_id,
                    outcome_unknown=True,
                )
            if self._guard is not None:
                with self._sessions() as session, session.begin():
                    self._guard(session)
            return completion.model_copy(update={"call_id": call_id})
        finally:
            if owned:
                client.close()

    def _reserve(
        self,
        *,
        owner_id: UUID,
        job_id: UUID | None,
        call_id: UUID,
        purpose: str,
        prompt_version: str,
        fingerprint: bytes,
        started_at: datetime,
        client: AiCompletionClient,
        model: FrozenAiModel | None,
        routing: AiRoutingLineage | None,
        quote: AiPriceQuote | None,
        paid: bool,
    ) -> None:
        operation_id = job_id or call_id
        with self._sessions() as session, session.begin():
            if self._guard is not None:
                self._guard(session)
            if self._admission_guard is not None:
                self._admission_guard(session)
            if (
                paid
                and session.scalar(
                    select(AiCall.id)
                    .where(
                        AiCall.owner_id == owner_id,
                        AiCall.job_id == job_id,
                        AiCall.purpose == purpose,
                        AiCall.status.in_(("running", "unknown")),
                    )
                    .limit(1)
                )
                is not None
            ):
                raise AiCallError(
                    AiFailureCode.TIMEOUT,
                    "original paid AI call requires manual review",
                    outcome_unknown=True,
                )
            component = (
                model.component_key if model else getattr(client, "component_key", AI_COMPONENT_KEY)
            )
            over_cap = session.scalars(
                select(AiCall.id).where(
                    AiCall.owner_id == owner_id,
                    AiCall.provider == client.provider,
                    AiCall.model == client.model,
                    AiCall.cost_actual_micros > AiCall.cost_cap_micros,
                )
            ).all()
            if any(
                not has_succeeded_action_target_in_transaction(
                    session,
                    owner_id=owner_id,
                    action="ai.cost_circuit.ack",
                    target_ref=f"ai-call:{identity}",
                )
                for identity in over_cap
            ):
                raise AiCallError(AiFailureCode.UNAVAILABLE, "model cost circuit is open")
            if component.startswith(("ai.llm.", "ai.embeddings")):
                provider_quote = None
                if quote is not None:
                    assert model is not None
                    provider_quote = AiTokenCostQuote(
                        currency=quote.currency,
                        # Even a reviewed free supplier needs an original fee ledger for anomalies.
                        reservation_units=max(1, quote.cap_micros),
                        model_price_hash=model.catalog_sha256,
                    )
                reserve_ai_provider_budgets_in_transaction(
                    session,
                    owner_id=owner_id,
                    operation_id=operation_id,
                    call_id=call_id,
                    component_key=component,
                    quote=provider_quote,
                    now=started_at,
                )
            budget = ResourceBudgetService(session, clock=self._clock)
            decision = budget.reserve_budget_in_transaction(
                owner_id=owner_id,
                command=BudgetReservationInput(
                    reservation_id=call_id,
                    operation_id=operation_id,
                    metric=BudgetMetric.ANALYSIS_ATTEMPT,
                    requested_units=1,
                    context=BudgetContext(job_ref=f"job:{job_id.hex}" if job_id else None),
                ),
            )
            if decision.status is BudgetDecisionStatus.DELAYED:
                raise AiCallError(
                    AiFailureCode.RATE_LIMITED,
                    "analysis budget is exhausted",
                    retry_at=decision.retry_at,
                )
            attempt = budget.begin_attempt_in_transaction(
                owner_id=owner_id,
                approved_paid_ai=paid,
                command=UsageAttemptInput(
                    attempt_id=call_id,
                    operation_id=operation_id,
                    component_key=component,
                    usage_kind=UsageKind.ANALYSIS_ATTEMPT,
                    stage=_AI_USAGE_STAGE,
                    started_at=started_at,
                ),
            )
            if attempt.outcome is not UsageOutcome.STARTED:
                raise AiCallError(AiFailureCode.FAILED, "analysis attempt is already settled")
            session.add(
                AiCall(
                    id=call_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    purpose=purpose,
                    provider=client.provider,
                    model=client.model,
                    prompt_version=prompt_version,
                    input_fingerprint=fingerprint,
                    status=AiCallStatus.RUNNING.value,
                    failure_code=None,
                    input_tokens=0,
                    cached_input_tokens=0,
                    output_tokens=0,
                    reasoning_output_tokens=0,
                    duration_ms=0,
                    created_at=started_at,
                    model_key=model.key if model else None,
                    routing_version=routing.configuration_version if routing else None,
                    routing_hash=bytes.fromhex(routing.sha256) if routing else None,
                    currency=quote.currency if quote else None,
                    cost_cap_micros=quote.cap_micros if quote else None,
                    execution_epoch=self._epoch,
                )
            )

    def _finish(
        self,
        owner_id: UUID,
        call_id: UUID,
        *,
        status: AiCallStatus,
        failure: AiFailureCode | None,
        completion: AiCompletion | None,
        quote: AiPriceQuote | None,
    ) -> bool:
        now = self._clock()
        with self._sessions() as session, session.begin():
            row = session.scalar(
                select(AiCall)
                .where(
                    AiCall.owner_id == owner_id,
                    AiCall.id == call_id,
                )
                .with_for_update()
            )
            if row is None:
                raise RuntimeError("original running AI call is missing")
            active = row.status == AiCallStatus.RUNNING.value
            usage = completion.usage if completion else AiTokenUsage()
            estimate = None
            actual = None
            if quote is not None and completion and completion.usage_reported:
                if (
                    usage.input_tokens > quote.input_tokens_cap
                    or usage.output_tokens > quote.output_tokens_cap
                ):
                    status, failure = AiCallStatus.UNKNOWN, AiFailureCode.INVALID_OUTPUT
                else:
                    estimate = quote.estimate(
                        usage.input_tokens, usage.cached_input_tokens, usage.output_tokens
                    )
            if (
                completion
                and row.currency is not None
                and completion.cost_actual_micros is not None
                and completion.cost_currency == row.currency
            ):
                actual = completion.cost_actual_micros
            if row.cost_actual_micros is not None:
                actual = max(actual or 0, row.cost_actual_micros)
            if active or actual is not None:
                charged_cost = actual
                if actual is None and quote is not None and quote.cap_micros == 0:
                    charged_cost = 0
                if actual is not None and (
                    (active and status is not AiCallStatus.SUCCEEDED)
                    or row.status == AiCallStatus.UNKNOWN.value
                ):
                    charged_cost = max(row.cost_cap_micros or 0, actual)
                settle_ai_provider_budgets_in_transaction(
                    session,
                    owner_id=owner_id,
                    call_id=call_id,
                    # Unknown outcomes retain their cap; known higher fees raise the original debt.
                    cost_units=charged_cost,
                    now=now,
                )
            if active:
                budget = ResourceBudgetService(session, clock=self._clock)
                budget.settle_budget_reservation_in_transaction(
                    owner_id=owner_id,
                    reservation_id=call_id,
                    actual_units=1,
                )
                budget.finish_attempt_in_transaction(
                    owner_id=owner_id,
                    attempt_id=call_id,
                    outcome=UsageOutcome.SUCCEEDED
                    if status is AiCallStatus.SUCCEEDED
                    else UsageOutcome.FAILED,
                    finished_at=max(now, row.created_at),
                )
                row.status, row.failure_code = status.value, failure.value if failure else None
            if not active and completion is None:
                return False
            row.input_tokens, row.cached_input_tokens = (
                usage.input_tokens,
                usage.cached_input_tokens,
            )
            row.output_tokens, row.reasoning_output_tokens = (
                usage.output_tokens,
                usage.reasoning_output_tokens,
            )
            row.duration_ms = (
                completion.duration_ms
                if completion
                else max(0, int((now - row.created_at).total_seconds() * 1000))
            )
            if estimate is not None:
                row.cost_estimate_micros = estimate
            row.cost_actual_micros = actual
            return active and row.status == AiCallStatus.SUCCEEDED.value


def _input_fingerprint(
    *,
    model: str,
    prompt_version: str,
    prompt: str,
    output_schema: Mapping[str, Any],
    instructions: str = "",
    provider: str | None = None,
    routing_hash: str | None = None,
    image_hashes: tuple[str, ...] = (),
) -> bytes:
    normalized_input = json.dumps(
        [
            "ai-input-v3",
            provider,
            model,
            routing_hash,
            image_hashes,
            prompt_version,
            instructions,
            prompt,
            dict(output_schema),
        ],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(normalized_input.encode()).digest()
