from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.conftest import TEST_DATABASE_TRUNCATE

from ai.capability_routing import create_ai_client_for_frozen_model
from ai.capability_schemas import AiModelSwitchInput
from ai.capability_services import (
    AiCapabilityService,
    freeze_ai_job_scope_in_transaction,
    load_frozen_ai_routing_in_transaction,
)
from ai.schemas import AiCallError, AiCallStatus
from ai.services import (
    AiService,
    load_saved_ai_call_in_transaction,
    recover_abandoned_ai_calls_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import JobExecutionService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
    JobAcceptanceInput,
    JobObservationContext,
)
from jobs.services import ResourceBudgetService


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL required")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(TEST_DATABASE_TRUNCATE))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text(TEST_DATABASE_TRUNCATE))
        engine.dispose()


def _settings(currency="USD") -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://controlled@localhost/isolated",
        ai_enabled=True,
        ai_model="original-default",
        ai_openai_compatible_requests_enabled=True,
        ai_paid_requests_enabled=True,
        ai_model_catalog={
            "named": {
                "transport": "openai_compatible",
                "provider_key": "controlled",
                "model": "named-v1",
                "base_url": "https://models.example/v1",
                "api_key": "controlled-test-key",
                "vision": True,
                "currency": currency,
                "input_rate_micros_per_million": "1000000",
                "output_rate_micros_per_million": "2000000",
            },
            "alternate": {
                "transport": "codex",
                "provider_key": "codex_app_server",
                "model": "alternate-v2",
            },
        },
        ai_capability_models={"understand": "named"},
    )


def _job(engine, owner, settings, now):
    from jobs.services import JobService

    with sessionmaker(engine)() as session, session.begin():
        scope = freeze_ai_job_scope_in_transaction(session, owner_id=owner, settings=settings)
        return JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=owner,
            command=JobAcceptanceInput(
                operation_id=uuid4(),
                kind="analysis.editorial",
                observation=JobObservationContext(
                    configuration_ref="test:ai", configuration_version=1
                ),
                scope=scope,
            ),
        )


def _budgets(engine, owner, now, currency, *, source_spend=True):
    with sessionmaker(engine)() as session:
        budget = ResourceBudgetService(session, clock=lambda: now)
        budget.save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="ai.llm.controlled",
                component_version="controlled-v1",
                cost_class=CostClass.PAID,
                enabled_for_core=False,
                terms_reference="controlled-explicit-price-review",
                reviewed_at=now,
            ),
        )
        metric = (
            BudgetMetric.PROVIDER_USD_MICROS
            if currency == "USD"
            else BudgetMetric.PROVIDER_CNY_MICROS
        )
        for item in (BudgetMetric.ANALYSIS_ATTEMPT, BudgetMetric.NETWORK_REQUEST, metric):
            for scope in (BudgetScopeKind.GLOBAL, BudgetScopeKind.SOURCE):
                if item is BudgetMetric.ANALYSIS_ATTEMPT and scope is BudgetScopeKind.SOURCE:
                    continue
                if item is metric and scope is BudgetScopeKind.SOURCE and not source_spend:
                    continue
                budget.save_budget_policy(
                    owner_id=owner,
                    command=BudgetPolicyInput(
                        budget_key=f"{scope.value}.{item.value}",
                        metric=item,
                        scope_kind=scope,
                        scope_reference="ai.llm.controlled"
                        if scope is BudgetScopeKind.SOURCE
                        else None,
                        limit_units=1_000_000,
                        window_seconds=3600,
                        window_anchor_at=now - timedelta(minutes=1),
                        enabled=True,
                    ),
                )


def test_admin_env_default_freeze_cas_audit_and_idempotent_switch(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    sessions = sessionmaker(engine)
    with sessions() as session:
        service = AiCapabilityService(session, settings, clock=lambda: now)
        before = service.get(owner_id=owner)
        assert len(before.capabilities) == 11
        assert next(c for c in before.capabilities if c.key == "understand").source == "env"
        job = _job(engine, owner, settings, now)
        command = AiModelSwitchInput(
            operation_id=uuid4(),
            expected_version=0,
            capability="understand",
            model_key="alternate",
            reason="controlled model comparison",
        )
        after = service.switch(owner_id=owner, command=command)
        assert after.version == 1
        assert (
            next(c for c in after.capabilities if c.key == "understand").current.model
            == "alternate-v2"
        )
        assert service.switch(owner_id=owner, command=command) == after
        with pytest.raises(ApplicationError) as error:
            service.switch(
                owner_id=owner, command=command.model_copy(update={"operation_id": uuid4()})
            )
        assert error.value.code == "ai_configuration_conflict"
        reset = service.switch(
            owner_id=owner,
            command=AiModelSwitchInput(
                operation_id=uuid4(),
                expected_version=1,
                capability="understand",
                model_key=None,
                reason="restore environment selection",
            ),
        )
        assert reset.version == 2
        assert next(c for c in reset.capabilities if c.key == "understand").source == "env"
        assert len(service.overview(owner_id=owner).history) == 2
    with sessions() as session, session.begin():
        frozen = load_frozen_ai_routing_in_transaction(session, owner_id=owner, job_id=job.id)
        assert frozen.for_purpose("editorial.understand").model == "named-v1"
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ai_capability_configurations")) == 2


@pytest.mark.parametrize("currency", ["USD", "CNY"])
def test_paid_call_running_before_http_original_currency_and_no_fake_actual_cost(engine, currency):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings(currency)
    job = _job(engine, owner, settings, now)
    _budgets(engine, owner, now, currency)
    sessions = sessionmaker(engine)
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=job.id, worker_id="test"
        )
    requests = []

    def request(req):
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT status FROM ai_calls")) == "running"
        requests.append(req)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    with sessions() as session, session.begin():
        frozen = load_frozen_ai_routing_in_transaction(session, owner_id=owner, job_id=job.id)
    client = create_ai_client_for_frozen_model(
        settings, frozen.for_purpose("editorial.understand"), transport=httpx.MockTransport(request)
    )
    with sessions() as session:

        def guard(current):
            JobExecutionService(
                current, lease_seconds=30, clock=lambda: now
            ).require_current_operation_in_transaction(
                lease, owner_id=owner, operation_id=job.operation_id
            )

        completion = AiService(
            session,
            client,
            settings=settings,
            guard=guard,
            execution_epoch=lease.epoch,
            clock=lambda: now,
        ).complete(
            owner_id=owner,
            job_id=job.id,
            purpose="editorial.understand",
            prompt_version="controlled-v1",
            prompt="controlled admitted material",
            output_schema={"type": "object"},
        )
    client.close()
    assert len(requests) == 1
    with sessions() as session, session.begin():
        saved = load_saved_ai_call_in_transaction(
            session,
            owner_id=owner,
            call_id=completion.call_id,
            job_id=job.id,
            purpose="editorial.understand",
        )
        assert saved.status is AiCallStatus.SUCCEEDED and saved.model_key == "named"
        assert saved.routing_hash == frozen.sha256
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT currency,cost_estimate_micros,cost_actual_micros,status,"
                "cost_cap_micros FROM ai_calls"
            )
        ).one()
        assert tuple(row)[:4] == (currency, 110, None, "succeeded")
        assert row.cost_cap_micros > row.cost_estimate_micros
        assert connection.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 1
        used = (
            connection.execute(
                text(
                    "SELECT w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric=:metric"
                ),
                {"metric": f"provider_{currency.lower()}_micros"},
            )
            .scalars()
            .all()
        )
        # Supplier token usage supports an estimate; absent explicit fees keep both original caps.
        assert used == [row.cost_cap_micros, row.cost_cap_micros]


def test_missing_component_spend_budget_denies_before_any_http_or_running_call(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    job = _job(engine, owner, settings, now)
    _budgets(engine, owner, now, "USD", source_spend=False)
    sessions = sessionmaker(engine)
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=job.id, worker_id="test"
        )
    with sessions() as session, session.begin():
        frozen = load_frozen_ai_routing_in_transaction(session, owner_id=owner, job_id=job.id)
    requests = []
    client = create_ai_client_for_frozen_model(
        settings,
        frozen.for_purpose("editorial.understand"),
        transport=httpx.MockTransport(lambda request: requests.append(request)),
    )
    with sessions() as session, pytest.raises(AiCallError, match="unavailable") as error:
        AiService(
            session,
            client,
            settings=settings,
            guard=lambda current: JobExecutionService(
                current, lease_seconds=30, clock=lambda: now
            ).require_current_operation_in_transaction(
                lease, owner_id=owner, operation_id=job.operation_id
            ),
            execution_epoch=lease.epoch,
            clock=lambda: now,
        ).complete(
            owner_id=owner,
            job_id=job.id,
            purpose="editorial.understand",
            prompt_version="v1",
            prompt="material",
            output_schema={"type": "object"},
        )
    assert not error.value.outcome_unknown
    assert requests == []
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert connection.scalar(text("SELECT count(*) FROM resource_budget_reservations")) == 0
    client.close()


def test_new_epoch_recovery_charges_original_cap_and_blocks_automatic_paid_repeat(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    clock = [now]
    job = _job(engine, owner, settings, now)
    _budgets(engine, owner, now, "USD")
    sessions = sessionmaker(engine)
    with sessions() as session:
        old = JobExecutionService(session, lease_seconds=30, clock=lambda: clock[0]).acquire(
            job_id=job.id, worker_id="old"
        )
    with sessions() as session, session.begin():
        frozen = load_frozen_ai_routing_in_transaction(session, owner_id=owner, job_id=job.id)
    requests = []

    def crash(request):
        requests.append(request)
        raise SystemExit("controlled process death after request admission")

    client = create_ai_client_for_frozen_model(
        settings, frozen.for_purpose("editorial.understand"), transport=httpx.MockTransport(crash)
    )
    with sessions() as session, pytest.raises(SystemExit):
        AiService(
            session,
            client,
            settings=settings,
            guard=lambda current: JobExecutionService(
                current, lease_seconds=30, clock=lambda: clock[0]
            ).require_current_operation_in_transaction(
                old, owner_id=owner, operation_id=job.operation_id
            ),
            execution_epoch=old.epoch,
            clock=lambda: clock[0],
        ).complete(
            owner_id=owner,
            job_id=job.id,
            purpose="editorial.understand",
            prompt_version="v1",
            prompt="material",
            output_schema={"type": "object"},
        )
    clock[0] += timedelta(seconds=31)
    with sessions() as session:
        new = JobExecutionService(session, lease_seconds=30, clock=lambda: clock[0]).acquire(
            job_id=job.id, worker_id="new"
        )
    with sessions() as session, session.begin():
        JobExecutionService(
            session, lease_seconds=30, clock=lambda: clock[0]
        ).require_current_operation_in_transaction(
            new, owner_id=owner, operation_id=job.operation_id
        )
        assert (
            recover_abandoned_ai_calls_in_transaction(
                session, owner_id=owner, job_id=job.id, current_epoch=new.epoch, now=clock[0]
            )
            == 1
        )
        assert (
            recover_abandoned_ai_calls_in_transaction(
                session, owner_id=owner, job_id=job.id, current_epoch=new.epoch, now=clock[0]
            )
            == 0
        )
    with sessions() as session, pytest.raises(AiCallError):
        AiService(
            session,
            client,
            settings=settings,
            guard=lambda current: JobExecutionService(
                current, lease_seconds=30, clock=lambda: clock[0]
            ).require_current_operation_in_transaction(
                new, owner_id=owner, operation_id=job.operation_id
            ),
            execution_epoch=new.epoch,
            clock=lambda: clock[0],
        ).complete(
            owner_id=owner,
            job_id=job.id,
            purpose="editorial.understand",
            prompt_version="v1",
            prompt="material",
            output_schema={"type": "object"},
        )
    assert len(requests) == 1
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status,cost_cap_micros,cost_actual_micros FROM ai_calls")
        ).one()
        assert row.status == "unknown" and row.cost_actual_micros is None
        used = (
            connection.execute(
                text(
                    "SELECT w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='provider_usd_micros'"
                )
            )
            .scalars()
            .all()
        )
        assert used == [row.cost_cap_micros, row.cost_cap_micros]
    client.close()


def _leased_client(engine, owner, settings, now, handler, *, admission_guard=None):
    sessions = sessionmaker(engine)
    job = _job(engine, owner, settings, now)
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=job.id, worker_id="controlled-model"
        )
    with sessions.begin() as session:
        frozen = load_frozen_ai_routing_in_transaction(session, owner_id=owner, job_id=job.id)
    client = create_ai_client_for_frozen_model(
        settings, frozen.for_purpose("editorial.understand"), transport=httpx.MockTransport(handler)
    )

    def call():
        with sessions() as session:
            service = AiService(
                session,
                client,
                settings=settings,
                clock=lambda: now,
                guard=lambda current: JobExecutionService(
                    current, lease_seconds=30, clock=lambda: now
                ).require_current_operation_in_transaction(
                    lease, owner_id=owner, operation_id=job.operation_id
                ),
                execution_epoch=lease.epoch,
            )
            if admission_guard is not None:
                service = service.with_admission_guard(admission_guard, execution_epoch=lease.epoch)
            return service.complete(
                owner_id=owner,
                job_id=job.id,
                purpose="editorial.understand",
                prompt_version="controlled-v1",
                prompt="controlled material",
                output_schema={"type": "object"},
            )

    return client, call


def test_unknown_provider_price_is_not_zero_price_permission(engine):
    owner, now = uuid4(), datetime.now(UTC)
    settings = _settings()
    catalog = dict(settings.ai_model_catalog)
    catalog["named"] = {
        key: value
        for key, value in catalog["named"].items()
        if key
        not in {"currency", "input_rate_micros_per_million", "output_rate_micros_per_million"}
    }
    settings = settings.model_copy(update={"ai_model_catalog": catalog})
    _budgets(engine, owner, now, "USD")
    with sessionmaker(engine)() as session:
        ResourceBudgetService(session, clock=lambda: now).save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="ai.llm.controlled",
                component_version="unknown-price",
                cost_class=CostClass.UNKNOWN,
                enabled_for_core=False,
                terms_reference="No reviewed price",
                reviewed_at=now,
            ),
        )
    requests = []
    with pytest.raises(AiCallError) as error:
        _leased_client(engine, owner, settings, now, requests.append)
    assert not error.value.outcome_unknown and error.value.call_id is None
    assert requests == []
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert connection.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


def test_supplier_over_cap_is_original_success_and_blocks_until_exact_audited_ack(engine):
    from ai.capability_schemas import AiCostCircuitAckInput

    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    _budgets(engine, owner, now, "USD")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    client, call = _leased_client(engine, owner, settings, now, handler)
    original = client.complete

    def supplier_receipt(**kwargs):
        return original(**kwargs).model_copy(
            update={"cost_currency": "USD", "cost_actual_micros": 90_000}
        )

    client.complete = supplier_receipt
    completion = call()
    with pytest.raises(AiCallError) as blocked:
        call()
    assert not blocked.value.outcome_unknown and len(requests) == 1
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status,cost_actual_micros,cost_cap_micros FROM ai_calls")
        ).one()
        assert row.status == "succeeded" and row.cost_actual_micros == 90_000
        assert row.cost_actual_micros > row.cost_cap_micros
    with sessionmaker(engine)() as session:
        service = AiCapabilityService(session, settings, clock=lambda: now)
        overview = service.overview(owner_id=owner)
        assert len(overview.cost_circuits) == 1 and not overview.cost_circuits[0].acknowledged
        command = AiCostCircuitAckInput(
            operation_id=uuid4(),
            expected_version=0,
            call_id=completion.call_id,
            reason="Controlled supplier receipt reviewed",
        )
        after = service.acknowledge_cost_circuit(owner_id=owner, command=command)
        assert after.version == 1
        assert service.acknowledge_cost_circuit(owner_id=owner, command=command) == after
        with pytest.raises(ApplicationError) as stale:
            service.acknowledge_cost_circuit(
                owner_id=owner,
                command=command.model_copy(update={"operation_id": uuid4(), "expected_version": 0}),
            )
        assert stale.value.code == "ai_configuration_conflict"
        assert service.overview(owner_id=owner).cost_circuits[0].acknowledged
    second = call()
    assert len(requests) == 2 and second.call_id != completion.call_id
    with pytest.raises(AiCallError):
        call()
    assert len(requests) == 2
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM ai_calls WHERE status='succeeded'")) == 2
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM operations_audit_operations "
                    "WHERE action='ai.cost_circuit.ack' AND status='succeeded'"
                )
            )
            == 1
        )
    client.close()


def test_supplier_over_cap_charges_full_original_windows_and_blocks_another_model(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    _budgets(engine, owner, now, "USD")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE resource_budget_policies SET limit_units=80000 "
                "WHERE metric='provider_usd_micros' AND scope_kind='global'"
            )
        )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    client, call = _leased_client(engine, owner, settings, now, handler)
    original = client.complete
    client.complete = lambda **kwargs: original(**kwargs).model_copy(
        update={"cost_currency": "USD", "cost_actual_micros": 90000}
    )
    completion = call()
    client.close()
    with engine.connect() as connection:
        windows = connection.execute(
            text(
                "SELECT w.used_units,w.reserved_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.metric='provider_usd_micros'"
            )
        ).all()
        assert windows == [(90000, 0), (90000, 0)]
        reservations = connection.execute(
            text(
                "SELECT actual_units,released_units FROM resource_budget_reservations "
                "WHERE metric='provider_usd_micros'"
            )
        ).all()
        assert reservations == [(90000, 0), (90000, 0)]
    # Repeated receipts cannot double debit or refund a settled original request.
    from jobs.ai_budgets import settle_ai_provider_budgets_in_transaction

    with sessionmaker(engine).begin() as session:
        budget = ResourceBudgetService(session, clock=lambda: now)
        from uuid import uuid5

        with pytest.raises(ValueError, match="cannot exceed requested"):
            budget.settle_budget_reservation_in_transaction(
                owner_id=owner,
                reservation_id=uuid5(completion.call_id, "ai-provider-spend"),
                actual_units=90000,
            )
        with pytest.raises(ValueError, match="original AI provider cost"):
            budget.settle_provider_cost_receipt_in_transaction(
                owner_id=owner,
                reservation_id=uuid5(completion.call_id, "ai-provider-network"),
                actual_units=2,
            )

    with sessionmaker(engine).begin() as session:
        settle_ai_provider_budgets_in_transaction(
            session, owner_id=owner, call_id=completion.call_id, cost_units=90000, now=now
        )
    catalog = dict(settings.ai_model_catalog)
    catalog["named"] = {**catalog["named"], "model": "another-model-v2"}
    other_settings = settings.model_copy(update={"ai_model_catalog": catalog})
    other_client, other_call = _leased_client(engine, owner, other_settings, now, handler)
    with pytest.raises(AiCallError):
        other_call()
    other_client.close()
    assert len(requests) == 1
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 1
        assert (
            connection.scalar(
                text(
                    "SELECT sum(used_units) FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='provider_usd_micros'"
                )
            )
            == 180000
        )


def test_unknown_price_compatible_transport_cannot_use_free_component_to_send(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    catalog = dict(settings.ai_model_catalog)
    catalog["named"] = {
        key: value
        for key, value in catalog["named"].items()
        if key
        not in {"currency", "input_rate_micros_per_million", "output_rate_micros_per_million"}
    }
    settings = settings.model_copy(
        update={"ai_model_catalog": catalog, "ai_paid_requests_enabled": False}
    )
    _budgets(engine, owner, now, "USD")
    with sessionmaker(engine)() as session:
        ResourceBudgetService(session, clock=lambda: now).save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="ai.llm.controlled",
                component_version="incorrect-free",
                cost_class=CostClass.ZERO_PRICE,
                enabled_for_core=True,
                terms_reference="Free policy is not provider price evidence",
                reviewed_at=now,
            ),
        )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    with pytest.raises(AiCallError):
        client, call = _leased_client(engine, owner, settings, now, handler)
        try:
            call()
        finally:
            client.close()
    assert requests == []
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 0
        assert connection.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


def test_duplicate_success_receipt_below_cap_does_not_increase_original_debt(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    _budgets(engine, owner, now, "USD")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    client, call = _leased_client(engine, owner, settings, now, handler)
    original = client.complete
    client.complete = lambda **kwargs: original(**kwargs).model_copy(
        update={"cost_currency": "USD", "cost_actual_micros": 20}
    )
    completion = call()
    with engine.connect() as connection:
        original_stats = connection.execute(
            text("SELECT input_tokens,output_tokens,cost_estimate_micros FROM ai_calls")
        ).one()
    with sessionmaker(engine)() as session:
        assert not AiService(session, client, settings=settings, clock=lambda: now)._finish(
            owner,
            completion.call_id,
            status=AiCallStatus.SUCCEEDED,
            failure=None,
            completion=completion,
            quote=None,
        )
        assert not AiService(session, client, settings=settings, clock=lambda: now)._finish(
            owner,
            completion.call_id,
            status=AiCallStatus.UNKNOWN,
            failure=None,
            completion=None,
            quote=None,
        )
    client.close()
    assert len(requests) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT input_tokens,output_tokens,cost_estimate_micros FROM ai_calls")
            ).one()
            == original_stats
        )
        assert connection.execute(
            text(
                "SELECT w.used_units,w.reserved_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.metric='provider_usd_micros'"
            )
        ).all() == [(20, 0), (20, 0)]


def test_bound_domain_guard_runs_only_at_admission_and_keeps_original_provider_receipt(engine):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    _budgets(engine, owner, now, "USD")
    calls, valid = [], [True]

    def domain_guard(session):
        assert session.in_transaction()
        calls.append("admission")
        assert valid[0], "material revoked after preparation"

    def handler(request):
        valid[0] = False
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    client, call = _leased_client(
        engine, owner, settings, now, handler, admission_guard=domain_guard
    )
    completion = call()
    assert calls == ["admission"] and completion.call_id is not None
    # The original receipt survives late revocation; the next request is rejected before admission.
    with pytest.raises(AssertionError, match="material revoked"):
        call()
    client.close()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 1
        assert connection.scalar(text("SELECT status FROM ai_calls")) == "succeeded"


@pytest.mark.parametrize("outcome", ["missing_usage", "invalid_usage", "late_receipt"])
def test_known_fee_remains_full_debt_when_outcome_unknown_or_receipt_late(engine, outcome):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    _budgets(engine, owner, now, "USD")
    requests, errors = [], []

    def provider_response(request):
        requests.append(request)
        if outcome == "late_receipt":
            with engine.connect() as connection:
                job_id = connection.scalar(text("SELECT job_id FROM ai_calls"))
            with sessionmaker(engine)() as session:
                lease = JobExecutionService(
                    session, lease_seconds=30, clock=lambda: now + timedelta(seconds=31)
                ).acquire(job_id=job_id, worker_id="new-epoch-before-old-receipt")
            with sessionmaker(engine).begin() as session:
                JobExecutionService(
                    session, lease_seconds=30, clock=lambda: now + timedelta(seconds=31)
                ).require_current_operation_in_transaction(
                    lease,
                    owner_id=owner,
                    operation_id=session.scalar(
                        text("SELECT operation_id FROM jobs WHERE id=:id"), {"id": job_id}
                    ),
                )
                assert (
                    recover_abandoned_ai_calls_in_transaction(
                        session,
                        owner_id=owner,
                        job_id=job_id,
                        current_epoch=lease.epoch,
                        now=now + timedelta(seconds=31),
                    )
                    == 1
                )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    def handler(request):
        try:
            return provider_response(request)
        except Exception as error:
            errors.append(repr(error))
            raise

    client, call = _leased_client(engine, owner, settings, now, handler)
    original = client.complete

    def receipt(**kwargs):
        result = original(**kwargs)
        update = {"cost_currency": "USD", "cost_actual_micros": 90000}
        if outcome == "missing_usage":
            update["usage_reported"] = False
        elif outcome == "invalid_usage":
            update["usage"] = result.usage.model_copy(update={"input_tokens": 1000000})
        return result.model_copy(update=update)

    client.complete = receipt
    with pytest.raises(AiCallError) as failure:
        call()
    client.close()
    assert errors == []
    assert failure.value.outcome_unknown and len(requests) == 1
    with engine.connect() as connection:
        row = connection.execute(text("SELECT status,cost_actual_micros FROM ai_calls")).one()
        assert row.status == "unknown" and row.cost_actual_micros == 90000
        assert connection.execute(
            text(
                "SELECT w.used_units,w.reserved_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.metric='provider_usd_micros'"
            )
        ).all() == [(90000, 0), (90000, 0)]
    from ai.capability_schemas import AiCostCircuitAckInput
    from jobs.ai_budgets import settle_ai_provider_budgets_in_transaction

    with sessionmaker(engine).begin() as session:
        settle_ai_provider_budgets_in_transaction(
            session, owner_id=owner, call_id=failure.value.call_id, cost_units=1, now=now
        )
    with sessionmaker(engine)() as session:
        service = AiCapabilityService(session, settings, clock=lambda: now)
        service.acknowledge_cost_circuit(
            owner_id=owner,
            command=AiCostCircuitAckInput(
                operation_id=uuid4(),
                expected_version=0,
                call_id=failure.value.call_id,
                reason="Reviewed known fee; outcome stays unknown",
            ),
        )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT status FROM ai_calls")) == "unknown"
        assert (
            connection.scalar(
                text(
                    "SELECT sum(used_units) FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='provider_usd_micros'"
                )
            )
            == 180000
        )


def test_model_usage_counts_running_without_latency_bias_and_includes_embedding(engine):
    from ai.models import AiCall

    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    with sessionmaker(engine).begin() as session:
        for purpose, status, duration in (
            ("editorial.understand", "succeeded", 50),
            ("editorial.understand", "running", 0),
            ("events.embedding", "succeeded", 80),
        ):
            session.add(
                AiCall(
                    id=uuid4(),
                    owner_id=owner,
                    job_id=None,
                    purpose=purpose,
                    provider="controlled",
                    model="model",
                    prompt_version="v1",
                    input_fingerprint=bytes(32),
                    status=status,
                    failure_code=None,
                    input_tokens=10,
                    cached_input_tokens=0,
                    output_tokens=5,
                    reasoning_output_tokens=0,
                    duration_ms=duration,
                    created_at=now,
                    currency="CNY",
                    cost_estimate_micros=20,
                    cost_actual_micros=None,
                )
            )
    with sessionmaker(engine)() as session:
        view = AiCapabilityService(session, settings, clock=lambda: now).overview(owner_id=owner)
    usage = {item.capability: item for item in view.usage}
    assert usage["understand"].calls == 2 and usage["understand"].running == 1
    assert usage["understand"].latency_p50_ms == usage["understand"].latency_p95_ms == 50
    assert usage["embedding"].calls == 1 and usage["embedding"].currency == "CNY"
    assert len(view.configuration.capabilities) == 11


@pytest.mark.parametrize("reported_cost", [None, 90000])
def test_explicit_reviewed_zero_price_compatible_model_does_not_require_paid_flag(
    engine, reported_cost
):
    owner, now, settings = uuid4(), datetime.now(UTC), _settings()
    catalog = dict(settings.ai_model_catalog)
    catalog["named"] = {
        **catalog["named"],
        "input_rate_micros_per_million": "0",
        "output_rate_micros_per_million": "0",
    }
    settings = settings.model_copy(
        update={"ai_model_catalog": catalog, "ai_paid_requests_enabled": False}
    )
    _budgets(engine, owner, now, "USD")
    with sessionmaker(engine)() as session:
        ResourceBudgetService(session, clock=lambda: now).save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="ai.llm.controlled",
                component_version="reviewed-zero",
                cost_class=CostClass.ZERO_PRICE,
                enabled_for_core=True,
                terms_reference="Explicit supplier free contract",
                reviewed_at=now,
            ),
        )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"accepted":true}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    client, call = _leased_client(engine, owner, settings, now, handler)
    if reported_cost is not None:
        original = client.complete
        client.complete = lambda **kwargs: original(**kwargs).model_copy(
            update={"cost_currency": "USD", "cost_actual_micros": reported_cost}
        )
    call()
    assert len(requests) == 1
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT cost_estimate_micros,cost_cap_micros,cost_actual_micros FROM ai_calls")
        ).one()
        assert row.cost_estimate_micros == row.cost_cap_micros == 0
        assert row.cost_actual_micros == reported_cost
        assert connection.execute(
            text(
                "SELECT w.used_units,w.reserved_units FROM resource_budget_windows w "
                "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                "WHERE p.metric='provider_usd_micros'"
            )
        ).all() == [(reported_cost or 0, 0), (reported_cost or 0, 0)]
    client.close()
