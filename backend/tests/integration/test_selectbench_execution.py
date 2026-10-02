# ruff: noqa: F811
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_content_records import _demo_scope
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from ai.schemas import AiCompletion, AiTokenUsage
from analysis.evaluation_execution import SelectBenchExecutor
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.evaluation_schemas import SelectBenchGoldInput
from analysis.evaluation_services import SelectBenchService
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job


class FakeSelectionClient:
    provider = "codex_app_server"
    model = "controlled-bench"

    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        output = (
            {"label": "PASS", "reason": "模型发布"}
            if len(self.calls) == 1
            else {"attentionScore": 90 if len(self.calls) == 2 else 80}
        )
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output=output,
            usage=AiTokenUsage(input_tokens=10, output_tokens=5),
            duration_ms=1,
        )

    def close(self):
        pass


def _queued(client):
    client.app.state.settings = client.app.state.settings.model_copy(
        update={
            "ai_enabled": True,
            "ai_model_catalog": {
                "controlled-bench": {
                    "transport": "codex",
                    "provider_key": "codex_app_server",
                    "model": "controlled-bench",
                }
            },
        }
    )
    owner = _demo_scope(client)
    factory = client.app.state.session_factory
    _enable_ai_budget(factory.kw["bind"], owner)
    command = SelectBenchGoldInput(
        operation_id=uuid4(),
        label="生产筛选评测",
        reason="受控验证",
        models=["controlled-bench"],
        sample_size=1,
        cases=[
            {
                "case_id": "release",
                "title": "OpenAI 发布新模型",
                "body": "OpenAI 官方发布具有全新能力的模型,供开发者测试使用。",
                "gold": "select",
                "tier": "T2",
            }
        ],
    )
    with factory() as session:
        service = SelectBenchService(session, enabled=True, settings=client.app.state.settings)
        accepted = service.queue_gold(owner_id=owner, command=command)
        assert service.queue_gold(owner_id=owner, command=command).replayed
        job = session.get(Job, accepted.job_ids[0])
        message = SimpleNamespace(
            job_id=job.id,
            operation_id=job.operation_id,
            owner_id=owner,
            kind=job.kind,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )
        session.rollback()
        lease = JobExecutionService(session, lease_seconds=300).acquire(
            job_id=job.id, worker_id="controlled-bench"
        )
    return owner, accepted, message, lease


def test_benchmark_runs_actual_prefilter_and_two_independent_scores(event_read_client, monkeypatch):
    _owner, accepted, message, lease = _queued(event_read_client)
    fake = FakeSelectionClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda settings: fake)
    factory = event_read_client.app.state.session_factory
    settings = event_read_client.app.state.settings.model_copy(update={"selectbench_enabled": True})
    executor = SelectBenchExecutor(factory, settings)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(fake.calls) == 3
    with factory() as session:
        row = session.scalar(select(SelectBenchResult))
        assert row.decision == "select" and row.score == 85 and row.error_code is None
        assert row.ai_call_id is not None
        run = session.get(SelectBenchRun, accepted.run.id)
        assert run.summary["controlled-bench"]["accuracy"] == 1
        assert set(run.summary["_evaluation"]["tasks"][str(row.id)]["outputs"]) == {
            "prefilter",
            "score-1",
            "score-2",
        }


def test_benchmark_lost_unsaved_response_is_unknown_and_never_called_again(
    event_read_client, monkeypatch
):
    _owner, _accepted, message, lease = _queued(event_read_client)
    fake = FakeSelectionClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda settings: fake)
    factory = event_read_client.app.state.session_factory
    settings = event_read_client.app.state.settings.model_copy(update={"selectbench_enabled": True})
    executor = SelectBenchExecutor(factory, settings)
    monkeypatch.setattr(
        executor,
        "_save_response",
        lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit("controlled crash")),
    )
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    assert len(fake.calls) == 1
    with pytest.raises(JobExecutionFailure, match="evaluation_result_unknown") as failure:
        SelectBenchExecutor(factory, settings).execute(message, lease)
    assert not failure.value.manual_retry_allowed and len(fake.calls) == 1


def test_benchmark_saved_prefilter_resumes_without_repeating_paid_stage(
    event_read_client, monkeypatch
):
    _owner, _accepted, message, lease = _queued(event_read_client)
    fake = FakeSelectionClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda settings: fake)
    factory = event_read_client.app.state.session_factory
    settings = event_read_client.app.state.settings.model_copy(update={"selectbench_enabled": True})
    executor = SelectBenchExecutor(factory, settings)
    save = executor._save_response

    def crash_after_save(*args, **kwargs):
        save(*args, **kwargs)
        raise SystemExit("controlled crash after durable response")

    monkeypatch.setattr(executor, "_save_response", crash_after_save)
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    assert len(fake.calls) == 1
    SelectBenchExecutor(factory, settings).execute(message, lease)
    assert len(fake.calls) == 3
    with factory() as session:
        assert session.scalar(select(SelectBenchResult)).decision == "select"


def test_benchmark_stale_lease_cannot_begin_any_provider_call(event_read_client, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from jobs.execution import StaleExecutionLeaseError

    _owner, _accepted, message, lease = _queued(event_read_client)
    fake = FakeSelectionClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda settings: fake)
    factory = event_read_client.app.state.session_factory
    with factory() as session, session.begin():
        session.get(Job, message.job_id).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with factory() as session:
        current = JobExecutionService(session, lease_seconds=300).acquire(
            job_id=message.job_id, worker_id="replacement-bench"
        )
    assert current.epoch > lease.epoch
    settings = event_read_client.app.state.settings.model_copy(update={"selectbench_enabled": True})
    with pytest.raises(StaleExecutionLeaseError):
        SelectBenchExecutor(factory, settings).execute(message, lease)
    assert fake.calls == []


def test_named_benchmark_models_stay_distinct_after_production_score_switch(
    event_read_client,
    monkeypatch,
):
    from ai.capability_schemas import AiModelSwitchInput
    from ai.capability_services import AiCapabilityService
    from ai.models import AiCall

    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    settings = event_read_client.app.state.settings.model_copy(
        update={
            "selectbench_enabled": True,
            "ai_enabled": True,
            "ai_model_catalog": {
                key: {"transport": "codex", "provider_key": "codex_app_server", "model": value}
                for key, value in (("bench-a", "actual-a"), ("bench-b", "actual-b"))
            },
        }
    )
    _enable_ai_budget(factory.kw["bind"], owner)
    with factory() as session:
        accepted = SelectBenchService(session, enabled=True, settings=settings).queue_gold(
            owner_id=owner,
            command=SelectBenchGoldInput(
                operation_id=uuid4(),
                label="Independent protected models",
                reason="Comparison",
                models=["bench-a", "bench-b"],
                sample_size=1,
                cases=[
                    {
                        "case_id": "one",
                        "title": "OpenAI new model",
                        "body": "Official new model",
                        "gold": "select",
                        "tier": "T2",
                    }
                ],
            ),
        )
        AiCapabilityService(session, settings).switch(
            owner_id=owner,
            command=AiModelSwitchInput(
                operation_id=uuid4(),
                expected_version=0,
                capability="score",
                model_key="bench-b",
                reason="Production choice changed after benchmark acceptance",
            ),
        )
    clients = {}
    for actual in ("actual-a", "actual-b"):
        client = FakeSelectionClient()
        client.model = actual
        clients[actual] = client
    monkeypatch.setattr(
        "analysis.evaluation_execution.create_ai_client", lambda current: clients[current.ai_model]
    )
    for job_id in accepted.job_ids:
        with factory() as session:
            row = session.get(Job, job_id)
            message = SimpleNamespace(
                job_id=row.id,
                operation_id=row.operation_id,
                owner_id=owner,
                kind=row.kind,
                configuration_ref=row.configuration_ref,
                configuration_version=row.configuration_version,
            )
            session.rollback()
            lease = JobExecutionService(session, lease_seconds=300).acquire(
                job_id=job_id, worker_id="comparison"
            )
        SelectBenchExecutor(factory, settings).execute(message, lease)
    assert [len(client.calls) for client in clients.values()] == [3, 3]
    with factory() as session:
        calls = list(session.scalars(select(AiCall)))
        assert {call.model for call in calls} == {"actual-a", "actual-b"}
        assert {call.model_key for call in calls} == {"bench-a", "bench-b"}
        assert {call.routing_version for call in calls} == {0}
        assert len({call.routing_hash for call in calls}) == 1
        assert len(calls) == 6
