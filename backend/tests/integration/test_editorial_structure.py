# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_editorial_execution import (
    ControlledClient,
    _budget,
    _execute,
    _run,
    editorial_client,  # noqa: F401
)

from analysis.editorial_models import EditorialRun, EditorialStage
from analysis.editorial_schemas import EditorialRunInput
from analysis.editorial_services import EditorialService
from analysis.event_reading import list_editorial_event_inputs_in_transaction
from events.models import EventCandidate
from events.services import EventCandidateService


class StructureClient(ControlledClient):
    def __init__(self, scope):
        super().__init__()
        self.scope = scope

    def complete(self, **kwargs):
        response = super().complete(**kwargs)
        if kwargs["output_schema"]["title"] == "StructureOutput":
            response.output.update(
                scope=self.scope,
                fact={
                    "title": "OpenAI 新模型发布",
                    "subject": "openai",
                    "action": "发布",
                    "object": "新模型",
                    "evidence": "x" * 601,
                    "conditions": [
                        {"quote": "OpenAI...公开 API。"},
                        {"quote": "OpenAI 发布新模型,公开 API。"},
                    ],
                },
            )
        return response


@pytest.mark.parametrize("scope", ["single", "unknown", "composite"])
def test_structure_fields_and_diagnostics_are_persisted_without_stage_failure(
    editorial_client, scope
):
    owner, run, message, lease = _run(editorial_client, dated=True)
    _budget(editorial_client, owner)
    provider = StructureClient(scope)
    _execute(editorial_client, owner, message, lease, provider)
    factory = editorial_client.app.state.session_factory
    with factory() as session:
        stored = session.get(EditorialRun, run.id)
        stage = session.scalar(
            select(EditorialStage).where(
                EditorialStage.run_id == run.id, EditorialStage.stage_key == "structure"
            )
        )
        assert stored.status == "complete" and stage.status == "succeeded"
        assert stage.ai_call_id is not None and stage.failure_code is None
        structure = stored.result["structure"]
        assert structure == stage.output and structure["scope"] == scope
        if scope == "composite":
            assert structure["fact"] is None
            assert structure["discards"] == [{"field": "fact", "reason": "composite"}]
        else:
            assert structure["fact"]["evidence"] is None
            assert structure["fact"]["conditions"] == [{"quote": "OpenAI 发布新模型,公开 API。"}]
            assert [item["reason"] for item in structure["discards"]] == ["too_long", "ellipsis"]
    at = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session, session.begin():
        items = list_editorial_event_inputs_in_transaction(
            session, since=at - timedelta(hours=1), now=at
        )
        if scope == "composite":
            assert items.items == ()
            assert (
                EventCandidateService(session).enqueue_due_in_transaction(now=at, ai_enabled=True)
                == 0
            )
            assert session.scalar(select(EventCandidate)) is None
        else:
            assert len(items.items) == 1
            assert items.items[0].fact_frame["conditions"] == structure["fact"]["conditions"]


@pytest.mark.parametrize("replaced_current", [False, True])
def test_template_hash_change_does_not_recalculate_completed_fixed_input(
    editorial_client, monkeypatch, replaced_current
):
    owner, run, message, lease = _run(editorial_client, dated=True)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, StructureClient("single"))
    factory = editorial_client.app.state.session_factory
    with factory() as session, session.begin():
        # Simulate an old completed template receipt; keep its source/material identity.
        stored = session.get(EditorialRun, run.id)
        stored.prompt_version = "editorial@old-template"
        session.execute(text("UPDATE editorial_sources SET scan_cursor=NULL"))
    monkeypatch.setattr(
        "analysis.editorial_services.pipeline_version", lambda: "editorial@new-template"
    )
    with factory() as session, session.begin():
        expected_ids = {run.id}
        if replaced_current:
            replacement = EditorialService(session).request_run_in_transaction(
                owner_id=owner,
                content_id=run.content_id,
                source_key=run.source_key,
                command=EditorialRunInput(
                    operation_id=uuid4(), content_version_id=run.content_version_id
                ),
            )
            expected_ids.add(replacement.id)
        assert EditorialService(session).enqueue_due_in_transaction(now=datetime.now(UTC)) == 0
        assert set(session.scalars(select(EditorialRun.id))) == expected_ids


def test_selection_only_completion_does_not_block_new_all_analysis(editorial_client, monkeypatch):
    owner, run, message, lease = _run(editorial_client, dated=True)
    _budget(editorial_client, owner)
    factory = editorial_client.app.state.session_factory
    with factory() as session, session.begin():
        stored = session.get(EditorialRun, run.id)
        stored.stages = "selection"
    _execute(editorial_client, owner, message, lease, StructureClient("single"))
    monkeypatch.setattr(
        "analysis.editorial_services.pipeline_version", lambda: "editorial@new-template"
    )
    with factory() as session, session.begin():
        assert EditorialService(session).enqueue_due_in_transaction(now=datetime.now(UTC)) == 1
        assert (
            session.scalar(select(EditorialRun.id).where(EditorialRun.stages == "all")) is not None
        )
