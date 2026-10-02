from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_content_search import _seed_posts

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from ai.services import AiService
from analysis.editorial_schemas import (
    EditorialOverrideInput,
    EditorialRunInput,
    EditorialRunView,
    EditorialSourceInput,
)
from analysis.editorial_services import EditorialExecutor, EditorialService
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import ExecutionLease, JobExecutionFailure, JobExecutionService
from jobs.schemas import JobAcceptedMessage, JobStatus
from main import create_app

NOW = datetime.now(UTC)


class ControlledClient:
    provider = "controlled"
    model = "controlled-editorial"

    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self.calls: list[str] = []
        self.callback = callback
        self.failure: AiFailureCode | None = None

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        self.calls.append(str(output_schema["title"]))
        if self.callback is not None:
            callback, self.callback = self.callback, None
            callback()
        if self.failure is not None:
            raise AiCallError(self.failure, "controlled failure")
        outputs = {
            "PrefilterOutput": {"label": "PASS", "reason": "公开模型发布"},
            "ScoreOutput": {"attentionScore": 90},
            "StructureOutput": {
                "category": "ai-models",
                "tags": ["模型"],
                "subjects": ["openai"],
                "fact": None,
            },
            "UnderstandOutput": {
                "itemType": "model_release",
                "authorRole": "principal",
                "tags": ["模型"],
                "editorialJudgment": "新模型可用",
                "titleZh": "OpenAI 发布新模型",
                "summaryZh": "OpenAI 发布新模型并公布公开使用方式。",
            },
        }
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output=outputs[str(output_schema["title"])],
            usage=AiTokenUsage(input_tokens=100, output_tokens=20),
            duration_ms=1,
        )


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    global NOW
    NOW = datetime.now(UTC)
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("editorial execution requires an isolated PostgreSQL database")
    with TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=url,
                log_level="WARNING",
                operator_token="controlled-editorial-operator",
            )
        )
    ) as client:
        yield client


def _source(client: TestClient, owner: UUID, *, operation_id: UUID | None = None) -> None:
    with client.app.state.session_factory() as session:
        EditorialService(session, clock=lambda: NOW).save_source(
            owner_id=owner,
            source_key="x",
            command=EditorialSourceInput(
                operation_id=operation_id or uuid4(),
                expected_revision=0,
                tier="T1",
                source_kind="x_search",
                name="受控官方来源",
                enabled=True,
            ),
        )


def _run(client: TestClient) -> tuple[UUID, EditorialRunView, JobAcceptedMessage, ExecutionLease]:
    owner, _, posts = _seed_posts(client, [("OpenAI new model", "OpenAI 发布新模型,公开 API。")])
    _source(client, owner)
    version = posts[0].latest_observation.content_version
    assert version is not None
    sessions = client.app.state.session_factory
    with sessions() as session:
        run = EditorialService(session, clock=lambda: NOW).request_run(
            owner_id=owner,
            content_id=posts[0].id,
            source_key="x",
            command=EditorialRunInput(operation_id=uuid4(), content_version_id=version.id),
        )
    assert run.job_id is not None
    with sessions() as session:
        outbox = session.execute(
            text("SELECT id, event_type, payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        payload = {
            **outbox.payload,
            "message_id": outbox.id,
            "event_type": outbox.event_type,
            "schema_version": 2,
        }
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).acquire(
            job_id=run.job_id, worker_id="controlled-editorial"
        )
    return owner, run, JobAcceptedMessage.model_validate(payload), lease


def _budget(client: TestClient, owner: UUID) -> None:
    # Reuse the existing budget test fixture while moving its frozen window to this test's clock.
    _enable_ai_budget(client.app.state.session_factory.kw["bind"], owner)
    with client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET window_anchor_at=:now, limit_units=50 "
                "WHERE owner_id=:owner"
            ),
            {"now": NOW, "owner": owner},
        )


def _execute(
    client: TestClient,
    owner: UUID,
    message: JobAcceptedMessage,
    lease: ExecutionLease,
    provider: ControlledClient,
) -> None:
    sessions = client.app.state.session_factory
    with sessions() as ai_session:
        result = EditorialExecutor(sessions, client.app.state.settings, clock=lambda: NOW).execute(
            message, lease, ai=AiService(ai_session, provider, clock=lambda: NOW)
        )
    assert result.status == JobStatus.SUCCEEDED


def test_editorial_runs_all_stages_once_and_replay_reuses_persisted_calls(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    provider = ControlledClient()
    _execute(editorial_client, owner, message, lease, provider)
    _execute(editorial_client, owner, message, lease, provider)
    assert provider.calls == [
        "PrefilterOutput",
        "ScoreOutput",
        "ScoreOutput",
        "StructureOutput",
        "UnderstandOutput",
    ]
    with editorial_client.app.state.session_factory() as session:
        view = EditorialService(session, clock=lambda: NOW).get_run(owner_id=owner, run_id=run.id)
        assert view.status == "complete" and view.result and view.result.selected
        assert session.execute(
            text(
                "SELECT count(*), count(DISTINCT ai_call_id) "
                "FROM editorial_stages WHERE run_id=:run"
            ),
            {"run": run.id},
        ).one() == (5, 5)
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5


def test_uncertain_call_is_preserved_and_never_repaid_on_recovery(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    provider = ControlledClient()
    provider.failure = AiFailureCode.TIMEOUT
    for _ in range(2):
        with pytest.raises(JobExecutionFailure, match="editorial_timeout"):
            _execute(editorial_client, owner, message, lease, provider)
    assert len(provider.calls) == 1
    with editorial_client.app.state.session_factory() as session:
        view = EditorialService(session, clock=lambda: NOW).get_run(owner_id=owner, run_id=run.id)
        assert view.status == "unknown" and view.failure_code == "editorial_timeout"
        assert session.execute(
            text("SELECT status, ai_call_id IS NOT NULL FROM editorial_stages WHERE run_id=:run"),
            {"run": run.id},
        ).one() == ("unknown", True)


def test_manual_correction_during_model_call_wins_over_late_automatic_result(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)

    def correct() -> None:
        with editorial_client.app.state.session_factory() as session:
            EditorialService(session, clock=lambda: NOW).override(
                owner_id=owner,
                run_id=run.id,
                command=EditorialOverrideInput(
                    operation_id=uuid4(),
                    expected_manual_version=0,
                    selected=False,
                    title_zh="人工复核标题",
                    summary_zh="人工决定暂不发布。",
                    reason="人工纠错",
                ),
            )

    provider = ControlledClient(correct)
    _execute(editorial_client, owner, message, lease, provider)
    assert len(provider.calls) == 1
    with editorial_client.app.state.session_factory() as session:
        view = EditorialService(session, clock=lambda: NOW).get_run(owner_id=owner, run_id=run.id)
        assert view.manual_version == 1 and view.result and view.result.manual
        assert not view.result.selected
        assert view.result.writing and view.result.writing.title_zh == "人工复核标题"


def test_frozen_material_revocation_prevents_paid_calls_and_read_leaks(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    with editorial_client.app.state.session_factory.begin() as session:
        session.execute(
            text("UPDATE evidence_resources SET expires_at=collected_at+interval '1 second'")
        )
    provider = ControlledClient()
    with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
        _execute(editorial_client, owner, message, lease, provider)
    assert not provider.calls
    with (
        editorial_client.app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="editorial_material_unavailable"),
    ):
        EditorialService(session, clock=lambda: NOW).get_run(owner_id=owner, run_id=run.id)


def test_concurrent_first_source_operation_has_one_identical_receipt(
    editorial_client: TestClient,
) -> None:
    owner, _, _ = _seed_posts(editorial_client, [("first", "first")])
    operation = uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_source, editorial_client, owner, operation_id=operation)
            for _ in range(2)
        ]
        for future in futures:
            future.result()
    with editorial_client.app.state.session_factory() as session:
        assert (
            session.execute(text("SELECT count(*) FROM editorial_source_versions")).scalar_one()
            == 1
        )


def test_restart_after_committed_stage_resumes_at_next_stage_without_second_charge(
    editorial_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from analysis import editorial_services

    original = editorial_services.next_editorial_step
    owner, _, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    provider = ControlledClient()

    def interrupt(material: Any, outputs: dict[str, Any], **options: Any) -> Any:
        if "prefilter" in outputs:
            raise RuntimeError("controlled restart between committed stages")
        return original(material, outputs, **options)

    monkeypatch.setattr(editorial_services, "next_editorial_step", interrupt)
    with pytest.raises(RuntimeError, match="controlled restart"):
        _execute(editorial_client, owner, message, lease, provider)
    assert provider.calls == ["PrefilterOutput"]
    monkeypatch.setattr(editorial_services, "next_editorial_step", original)
    _execute(editorial_client, owner, message, lease, provider)
    assert provider.calls == [
        "PrefilterOutput",
        "ScoreOutput",
        "ScoreOutput",
        "StructureOutput",
        "UnderstandOutput",
    ]


def test_http_admission_and_outbox_are_atomic_and_generated_result_contract_is_typed(
    editorial_client: TestClient,
) -> None:
    _owner, run, _, _ = _run(editorial_client)
    command = {"operation_id": str(uuid4()), "content_version_id": str(run.content_version_id)}
    assert (
        editorial_client.post(
            f"/api/editorial/contents/{run.content_id}/runs",
            params={"source_key": "x"},
            json=command,
        ).status_code
        == 401
    )
    token = {"X-HotKey-Operator-Token": "controlled-editorial-operator"}
    assert (
        editorial_client.post(
            f"/api/editorial/contents/{run.content_id}/runs",
            params={"source_key": "x"},
            json=command,
            headers=token,
        ).status_code
        == 403
    )
    headers = {**token, "X-HotKey-CSRF": "1"}
    response = editorial_client.post(
        f"/api/editorial/contents/{run.content_id}/runs",
        params={"source_key": "x"},
        json=command,
        headers=headers,
    )
    assert response.status_code == 202, response.json()
    assert response.json()["status"] == "queued" and response.json()["job_id"]
    replay = editorial_client.post(
        f"/api/editorial/contents/{run.content_id}/runs",
        params={"source_key": "x"},
        json=command,
        headers=headers,
    )
    assert replay.status_code == 202 and replay.json() == response.json()
    assert editorial_client.get(f"/api/editorial/runs/{response.json()['id']}").status_code == 200
    with editorial_client.app.state.session_factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
                {"job": response.json()["job_id"]},
            ).scalar_one()
            == 1
        )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0
    schemas = editorial_client.get("/openapi.json").json()["components"]["schemas"]
    assert "EditorialResultView" in schemas and "EditorialWritingView" in schemas


def test_cyclic_scheduler_scans_reach_material_beyond_first_hundred(
    editorial_client: TestClient,
) -> None:
    owner, _, posts = _seed_posts(editorial_client, [(f"post {i}", "中文正文") for i in range(165)])
    _source(editorial_client, owner)
    counts = []
    for _ in range(4):
        with editorial_client.app.state.session_factory.begin() as session:
            counts.append(
                EditorialService(session, clock=lambda: NOW).enqueue_due_in_transaction(
                    now=NOW, limit=100
                )
            )
    assert counts == [100, 65, 0, 0]
    with editorial_client.app.state.session_factory() as session:
        ids = session.execute(text("SELECT content_id FROM editorial_runs")).scalars().all()
    assert set(ids) == {post.id for post in posts}
