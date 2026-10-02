# ruff: noqa: F811
from uuid import uuid4

import pytest
from tests.integration.test_content_records import _user_scope
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from analysis.evaluation_schemas import SelectBenchImportInput
from analysis.evaluation_services import SelectBenchService
from core.errors import ApplicationError


def test_selectbench_persists_same_gold_recomputes_and_filters_disagreements(event_read_client):
    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    cases = [
        {
            "case_id": "a",
            "title": "应选择",
            "gold": "select",
            "decision": "select",
            "score": 80,
            "stratum": "news",
        },
        {
            "case_id": "b",
            "title": "应拒绝",
            "gold": "reject",
            "decision": "select",
            "score": 70,
            "stratum": "advertisement",
        },
    ]
    command = SelectBenchImportInput(
        operation_id=uuid4(),
        label="受控离线黄金集",
        prompt_version="select-v1",
        reason="复核模型筛选",
        models={
            "first": cases,
            "second": [cases[0], {**cases[1], "decision": "reject", "score": 20}],
        },
    )
    with factory() as session:
        service = SelectBenchService(session)
        run = service.import_report(owner_id=owner, command=command)
        assert run.sample_size == 2 and len(run.gold_fingerprint) == 64
        assert run.summary["first"]["precision"] == 0.5
        assert service.import_report(owner_id=owner, command=command).replayed
        filtered = service.get_cases(
            owner_id=owner, run_id=run.id, model="first", outcome="fp", disagree=True
        )
        assert [case.case_id for case in filtered.items] == ["b"]
        assert filtered.items[0].by_model["second"].decision == "reject"
        page = service.get_cases(owner_id=owner, run_id=run.id, limit=1)
        assert page.next_cursor == "a"
        assert (
            service.get_cases(owner_id=owner, run_id=run.id, cursor=page.next_cursor)
            .items[0]
            .case_id
            == "b"
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.get_cases(owner_id=uuid4(), run_id=run.id)
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.import_report(
                owner_id=owner, command=command.model_copy(update={"label": "不同报告"})
            )
