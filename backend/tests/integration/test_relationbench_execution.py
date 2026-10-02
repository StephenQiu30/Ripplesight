# ruff: noqa: F811
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_content_records import _demo_scope
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from ai.models import AiCall
from ai.schemas import AiCompletion, AiTokenUsage
from analysis.evaluation_execution import SelectBenchExecutor
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.evaluation_schemas import RelationBenchGoldInput, RelationBenchImportInput
from analysis.evaluation_services import SelectBenchService
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job


class ControlledRelationClient:
    provider = "codex_app_server"
    model = "controlled-relation"

    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={
                "a": "模型发布",
                "b": "发布后开发者测评",
                "relation": "SAME_STORY",
                "confidence": 0.9,
                "difference": "第二篇是对发布能力的直接测试",
            },
            usage=AiTokenUsage(input_tokens=20, output_tokens=10),
            duration_ms=1,
        )

    def close(self):
        pass


def _case(identity="release", relation="SAME_STORY"):
    return {
        "case_id": identity,
        "a": {"title": "OpenAI 发布模型", "source": "OpenAI", "first_party": True},
        "b": {"title": "开发者测试发布模型", "source": "独立媒体"},
        "gold_relation": relation,
        "stratum": "direct-development",
        "split": "held-out",
    }


def _queued(client):
    client.app.state.settings = client.app.state.settings.model_copy(
        update={
            "ai_enabled": True,
            "ai_model_catalog": {
                "controlled-relation": {
                    "transport": "codex",
                    "provider_key": "codex_app_server",
                    "model": "controlled-relation",
                }
            },
        }
    )
    owner = _demo_scope(client)
    factory = client.app.state.session_factory
    _enable_ai_budget(factory.kw["bind"], owner)
    command = RelationBenchGoldInput(
        operation_id=uuid4(),
        label="真实关系评测",
        reason="受控 provider 验证原账本",
        models=["controlled-relation"],
        cases=[_case()],
        sample_size=1,
        split="held-out",
    )
    with factory() as session:
        service = SelectBenchService(session, enabled=True, settings=client.app.state.settings)
        accepted = service.queue_relation_gold(owner_id=owner, command=command)
        assert service.queue_relation_gold(owner_id=owner, command=command).replayed
        row = session.get(Job, accepted.job_ids[0])
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
            job_id=message.job_id, worker_id="controlled-relation"
        )
    settings = client.app.state.settings.model_copy(update={"selectbench_enabled": True})
    return owner, factory, accepted, message, lease, settings


def test_relationbench_uses_production_pair_prompt_and_actual_ai_ledger(
    event_read_client, monkeypatch
):
    owner, factory, accepted, message, lease, settings = _queued(event_read_client)
    controlled = ControlledRelationClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda _: controlled)
    executor = SelectBenchExecutor(factory, settings)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(controlled.calls) == 1
    assert "开发者测试发布模型" in controlled.calls[0]["prompt"]
    assert "SAME_OCCURRENCE" in controlled.calls[0]["instructions"]
    with factory() as session:
        row = session.scalar(select(SelectBenchResult))
        call = session.get(AiCall, row.ai_call_id)
        assert call.job_id == message.job_id and call.owner_id == owner
        assert call.purpose == "analysis.selectbench.relation-pair"
        assert row.category == "SAME_STORY" and row.score == 90
        run = session.get(SelectBenchRun, accepted.run.id)
        assert run.summary["controlled-relation"]["accuracy"] == 1
        assert run.summary["execution"] == {"completed": 1, "unknown": 0, "total": 1}


def test_relationbench_saved_answer_resumes_without_a_second_provider_call(
    event_read_client, monkeypatch
):
    _, factory, _, message, lease, settings = _queued(event_read_client)
    controlled = ControlledRelationClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda _: controlled)
    executor = SelectBenchExecutor(factory, settings)
    save = executor._save_response

    def crash_after_save(*args, **kwargs):
        save(*args, **kwargs)
        raise SystemExit("controlled saved-answer crash")

    monkeypatch.setattr(executor, "_save_response", crash_after_save)
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    SelectBenchExecutor(factory, settings).execute(message, lease)
    assert len(controlled.calls) == 1
    with factory() as session:
        assert session.scalar(select(SelectBenchResult)).category == "SAME_STORY"


def test_relationbench_unsaved_answer_is_unknown_and_never_rebought(event_read_client, monkeypatch):
    _, factory, _, message, lease, settings = _queued(event_read_client)
    controlled = ControlledRelationClient()
    monkeypatch.setattr("analysis.evaluation_execution.create_ai_client", lambda _: controlled)
    executor = SelectBenchExecutor(factory, settings)
    monkeypatch.setattr(
        executor, "_save_response", lambda *_: (_ for _ in ()).throw(SystemExit("lost answer"))
    )
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    with pytest.raises(JobExecutionFailure, match="evaluation_result_unknown"):
        SelectBenchExecutor(factory, settings).execute(message, lease)
    assert len(controlled.calls) == 1


def test_relationbench_offline_metrics_errors_same_cases_and_owner_scoping(event_read_client):
    owner = _demo_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    relations = ("SAME_OCCURRENCE", "SAME_STORY", "UNRELATED", "ROUNDUP")
    cases = [_case(str(index), relation) for index, relation in enumerate(relations)]
    first = [
        {"case_id": str(index), "relation": relation, "confidence": 0.9}
        for index, relation in enumerate(relations)
    ]
    second = [
        {"case_id": "0", "relation": "UNRELATED", "confidence": 0.9},
        {"case_id": "1", "relation": None, "error_code": "invalid_output"},
        {"case_id": "2", "relation": "UNRELATED", "confidence": 0.9},
        {"case_id": "3", "relation": "UNRELATED", "confidence": 0.9},
    ]
    command = RelationBenchImportInput(
        operation_id=uuid4(),
        label="离线完整四分类",
        reason="相同 Gold 比较",
        models=["a", "b"],
        cases=cases,
        predictions={"a": first, "b": second},
    )
    with factory() as session:
        service = SelectBenchService(session, enabled=False)
        run = service.import_relation_report(owner_id=owner, command=command)
        assert run.kind == "relation" and run.summary["a"]["accuracy"] == 1
        assert run.summary["b"]["errors"] == 1
        assert run.summary["b"]["story_ties"][1]["fn"] == 1
        page = service.get_relation_cases(owner_id=owner, run_id=run.id, limit=1, disagree=True)
        assert page.items[0].case.case_id == "0" and page.next_cursor == "0"
        following = service.get_relation_cases(
            owner_id=owner, run_id=run.id, cursor=page.next_cursor, errors=True
        )
        assert [row.case.case_id for row in following.items] == ["1"]
        from core.errors import ApplicationError

        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.get_relation_cases(owner_id=uuid4(), run_id=run.id)
        assert session.scalar(select(Job)) is None
