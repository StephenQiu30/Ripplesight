# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from tests.integration.test_editorial_events import _selected
from tests.integration.test_editorial_execution import editorial_client  # noqa: F401

from ai.adapters.embeddings import EmbeddingClient, FrozenEmbeddingConfiguration
from ai.models import AiCall
from events.embedding_execution import (
    EventEmbeddingExecutor,
    EventEmbeddingService,
    load_compatible_event_vectors_in_transaction,
)
from events.embedding_models import EventContentEmbedding
from events.services import load_relevant_event_inputs_in_transaction
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
)
from jobs.services import ResourceBudgetService


def _embedding_budget(factory, owner, at):
    with factory() as session:
        service = ResourceBudgetService(session, clock=lambda: at)
        for scope, ref in (
            (BudgetScopeKind.GLOBAL, None),
            (BudgetScopeKind.SOURCE, "ai.embeddings"),
        ):
            service.save_budget_policy(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key=f"controlled.embedding-network.{scope.value}",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=scope,
                    scope_reference=ref,
                    limit_units=100,
                    window_seconds=86400,
                    window_anchor_at=at - timedelta(minutes=1),
                    enabled=True,
                ),
            )
            service.save_budget_policy(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key=f"controlled.embedding-spend.{scope.value}",
                    metric=BudgetMetric.PROVIDER_USD_MICROS,
                    scope_kind=scope,
                    scope_reference=ref,
                    limit_units=1000000,
                    window_seconds=86400,
                    window_anchor_at=at - timedelta(minutes=1),
                    enabled=True,
                ),
            )


def _setup(client, *, at, approve=True, paid=False):
    owner, _, factory = _selected(client)
    settings = client.app.state.settings.model_copy(
        update={
            "ai_enabled": True,
            "embeddings_enabled": True,
            "embedding_api_key": SecretStr("controlled"),
            "embedding_model": "controlled",
            "embedding_dimensions": 2,
            "embedding_base_url": "https://api.example.com/v1",
            "embedding_currency": "USD",
            "embedding_input_rate_micros_per_million": Decimal("1000000") if paid else Decimal(0),
            "ai_paid_requests_enabled": paid,
        }
    )
    _embedding_budget(factory, owner, at)
    if approve:
        with factory() as session:
            ResourceBudgetService(session, clock=lambda: at).save_component_policy(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key="ai.embeddings",
                    component_version="controlled",
                    cost_class=CostClass.PAID if paid else CostClass.LOCAL,
                    enabled_for_core=not paid,
                    terms_reference="controlled isolated transport, no real provider",
                    reviewed_at=at,
                ),
            )
    if paid:
        with factory() as session:
            service = ResourceBudgetService(session, clock=lambda: at)
            for scope in (BudgetScopeKind.GLOBAL, BudgetScopeKind.SOURCE):
                service.save_budget_policy(
                    owner_id=owner,
                    command=BudgetPolicyInput(
                        budget_key=f"controlled.embedding-spend.{scope.value}",
                        metric=BudgetMetric.PROVIDER_USD_MICROS,
                        scope_kind=scope,
                        scope_reference="ai.embeddings"
                        if scope is BudgetScopeKind.SOURCE
                        else None,
                        limit_units=1000000,
                        window_seconds=86400,
                        window_anchor_at=at - timedelta(minutes=1),
                        enabled=True,
                    ),
                )
    with factory() as session, session.begin():
        service = EventEmbeddingService(session, settings)
        assert service.enqueue_due_in_transaction(now=at, ai_enabled=True) == 1
        assert service.enqueue_due_in_transaction(now=at, ai_enabled=True) == 0
        job = session.scalar(select(Job).where(Job.kind == "events.embed"))
        message = SimpleNamespace(
            kind=job.kind,
            job_id=job.id,
            owner_id=owner,
            operation_id=job.operation_id,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: at).acquire(
            job_id=job.id, worker_id="controlled-embedding"
        )
    return owner, factory, settings, message, lease


def _client(requests, settings):
    def send(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "controlled",
                "data": [{"index": 0, "embedding": [0.6, 0.8]}],
                "usage": {"prompt_tokens": 15},
            },
        )

    return EmbeddingClient(
        base_url="https://api.example.com/v1",
        api_key="controlled",
        model="controlled",
        dimensions=2,
        timeout_seconds=5,
        transport=httpx.MockTransport(send),
        configuration=FrozenEmbeddingConfiguration.from_settings(settings),
    )


def test_embedding_revocation_after_prepare_denies_ai_and_budget_reservation(
    editorial_client, monkeypatch
):
    at = datetime.now(UTC) + timedelta(seconds=1)
    _, factory, settings, message, lease = _setup(editorial_client, at=at, paid=True)
    requests = []
    with factory() as session:
        before = session.execute(text("SELECT count(*) FROM resource_budget_reservations")).scalar()
        calls = session.execute(text("SELECT count(*) FROM ai_calls")).scalar()

    def revoke_after_prepare(_):
        with factory.begin() as session:
            session.execute(text("UPDATE source_access_policies SET enabled=false"))
        return _client(requests, settings)

    monkeypatch.setattr("events.embedding_execution.create_embedding_client", revoke_after_prepare)
    with pytest.raises(JobExecutionFailure, match="event_embedding_input_changed"):
        EventEmbeddingExecutor(factory, settings, clock=lambda: at).execute(message, lease)
    assert requests == []
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar() == calls
        assert (
            session.execute(text("SELECT count(*) FROM resource_budget_reservations")).scalar()
            == before
        )


def test_real_embedding_protocol_uses_original_ledger_and_fixed_vectors_on_free_replay(
    editorial_client, monkeypatch
):
    at = datetime.now(UTC) + timedelta(seconds=1)
    owner, factory, settings, message, lease = _setup(editorial_client, at=at)
    requests = []
    monkeypatch.setattr(
        "events.embedding_execution.create_embedding_client", lambda _: _client(requests, settings)
    )
    executor = EventEmbeddingExecutor(factory, settings, clock=lambda: at)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(requests) == 1 and requests[0].url.path == "/v1/embeddings"
    with factory() as session, session.begin():
        row = session.scalar(select(EventContentEmbedding))
        call = session.scalar(select(AiCall).where(AiCall.purpose == "events.embedding"))
        assert row.status == "valid" and row.ai_call_id == call.id and call.input_tokens == 15
        inputs = load_relevant_event_inputs_in_transaction(
            session, since=at - timedelta(days=14), now=at
        )
        assert load_compatible_event_vectors_in_transaction(
            session, owner_id=owner, inputs=inputs, settings=settings, now=at
        ) == {row.content_version_id: (0.6, 0.8)}
        assert (
            load_compatible_event_vectors_in_transaction(
                session,
                owner_id=owner,
                inputs=inputs,
                settings=settings.model_copy(update={"embedding_dimensions": 3}),
                now=at,
            )
            == {}
        )
        assert (
            load_compatible_event_vectors_in_transaction(
                session,
                owner_id=owner,
                inputs=inputs,
                settings=settings.model_copy(update={"ai_enabled": False}),
                now=at,
            )
            == {}
        )


def test_embedding_does_not_borrow_codex_component_approval_for_a_new_supplier(
    editorial_client, monkeypatch
):
    at = datetime.now(UTC) + timedelta(seconds=1)
    _, _, settings, message, lease = _setup(editorial_client, at=at, approve=False)
    requests = []
    monkeypatch.setattr(
        "events.embedding_execution.create_embedding_client", lambda _: _client(requests, settings)
    )
    with pytest.raises(JobExecutionFailure):
        EventEmbeddingExecutor(
            editorial_client.app.state.session_factory, settings, clock=lambda: at
        ).execute(message, lease)
    assert requests == []


def test_saved_embedding_response_recovers_without_second_http_and_missing_response_stops_unknown(
    editorial_client, monkeypatch
):
    at = datetime.now(UTC) + timedelta(seconds=1)
    _, factory, settings, message, lease = _setup(editorial_client, at=at)
    requests = []
    monkeypatch.setattr(
        "events.embedding_execution.create_embedding_client", lambda _: _client(requests, settings)
    )
    executor = EventEmbeddingExecutor(factory, settings, clock=lambda: at)
    original = executor._prepare
    count = 0

    def stop_after_saved(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("controlled process death after saved response")
        return original(*args)

    monkeypatch.setattr(executor, "_prepare", stop_after_saved)
    with pytest.raises(RuntimeError):
        executor.execute(message, lease)
    with factory() as session:
        assert session.scalar(select(EventContentEmbedding)).status == "response_saved"
    EventEmbeddingExecutor(factory, settings, clock=lambda: at).execute(message, lease)
    assert len(requests) == 1
    with factory() as session, session.begin():
        row = session.scalar(select(EventContentEmbedding))
        row.status, row.vector, row.dimensions, row.ai_call_id = "running", None, None, None
    with pytest.raises(JobExecutionFailure, match="event_embedding_result_unknown"):
        EventEmbeddingExecutor(factory, settings, clock=lambda: at).execute(message, lease)
    assert len(requests) == 1


def test_paid_embedding_missing_usage_stays_unknown_and_settles_original_cap_without_repeat(
    editorial_client, monkeypatch
):
    at = datetime.now(UTC) + timedelta(seconds=1)
    owner, factory, settings, message, lease = _setup(editorial_client, at=at, paid=True)
    requests = []

    def send(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "controlled",
                "data": [{"index": 0, "embedding": [0.6, 0.8]}],
            },
        )

    def client(_):
        return EmbeddingClient(
            base_url=settings.embedding_base_url,
            api_key="controlled",
            model=settings.embedding_model,
            dimensions=2,
            timeout_seconds=5,
            configuration=FrozenEmbeddingConfiguration.from_settings(settings),
            transport=httpx.MockTransport(send),
        )

    monkeypatch.setattr("events.embedding_execution.create_embedding_client", client)
    executor = EventEmbeddingExecutor(factory, settings, clock=lambda: at)
    for _ in range(2):
        with pytest.raises(JobExecutionFailure, match="event_embedding_result_unknown"):
            executor.execute(message, lease)
    assert len(requests) == 1
    with factory() as session:
        call = session.scalar(select(AiCall).where(AiCall.purpose == "events.embedding"))
        row = session.scalar(select(EventContentEmbedding))
        assert call.status == "unknown" and call.currency == "USD" and call.cost_cap_micros > 0
        assert call.cost_actual_micros is None and call.execution_epoch == lease.epoch
        assert call.model_key == "embedding" and call.provider == "api.example.com"
        assert row.status == "unknown" and row.vector is None
        budgets = ResourceBudgetService(session, clock=lambda: at).budget_usage_snapshot(
            owner_id=owner
        )
        spend = [value for value in budgets if value.metric == "provider_usd_micros"]
        assert len(spend) == 2 and all(value.used_units == call.cost_cap_micros for value in spend)
