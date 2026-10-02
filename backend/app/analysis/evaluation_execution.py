from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai.benchmark_services import load_ai_benchmark_in_transaction
from ai.capability_routing import create_ai_client_for_frozen_model
from ai.schemas import AiCallError, AiCallStatus, AiCompletion, AiFailureCode
from ai.services import AiService, create_ai_client, load_saved_ai_call_in_transaction
from analysis.editorial_pipeline import EditorialStep, next_editorial_step
from analysis.editorial_schemas import EditorialMaterial
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.evaluation_relations import POSITIVE, relation_metrics, relation_prompt_version
from analysis.evaluation_schemas import RelationGoldCaseInput, SelectBenchGoldCaseInput
from analysis.evaluation_services import _hash, score_model_report
from analysis.prompts import editorial_prompt_version
from core.config import Settings
from events.relations import RelationPairOutput, relation_pair_request
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration


class SelectBenchExecutor:
    """One model-case job, using production prefilter and independent double scoring."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._sessions, self._settings = sessions, settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def _failure(self, code: str, *, retry: bool = False) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_RESPONSE,
            occurred_at=self._clock(),
            next_action="核对评测固定材料、模型账本及已保存阶段",
            manual_retry_allowed=retry,
        )

    def _load(
        self, session: Session, message: JobMessage, lease: ExecutionLease
    ) -> tuple[SelectBenchRun, SelectBenchResult, dict[str, Any], dict[str, Any]]:
        JobExecutionService(
            session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
        ).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )
        configuration = load_job_execution_configuration(session, job_id=message.job_id)
        if (
            configuration is None
            or configuration.owner_id != message.owner_id
            or configuration.kind != message.kind
            or message.kind != "analysis.selectbench"
            or configuration.observation.configuration_ref != message.configuration_ref
            or configuration.observation.configuration_version != message.configuration_version
        ):
            raise self._failure("evaluation_input_invalid")
        try:
            run_id, result_id = (
                UUID(str(configuration.scope["run_id"])),
                UUID(str(configuration.scope["result_id"])),
            )
        except (ValueError, KeyError):
            raise self._failure("evaluation_input_invalid") from None
        run = session.scalar(
            select(SelectBenchRun)
            .where(SelectBenchRun.owner_id == message.owner_id, SelectBenchRun.id == run_id)
            .with_for_update()
        )
        row = session.scalar(
            select(SelectBenchResult)
            .where(
                SelectBenchResult.owner_id == message.owner_id,
                SelectBenchResult.run_id == run_id,
                SelectBenchResult.id == result_id,
            )
            .with_for_update()
        )
        if (
            run is None
            or row is None
            or configuration.scope.get("gold_fingerprint") != run.gold_fingerprint.hex()
        ):
            raise self._failure("evaluation_input_invalid")
        relation = (
            cast(dict[str, Any], run.summary.get("_evaluation", {})).get("kind") == "relation"
        )
        version = (
            relation_prompt_version()
            if relation
            else (
                "selectbench@"
                + hashlib.sha256(
                    editorial_prompt_version("prefilter", "selection-score").encode()
                ).hexdigest()[:20]
            )
        )
        if run.prompt_version != version:
            raise self._failure("evaluation_prompt_changed")
        state = cast(dict[str, Any], copy.deepcopy(run.summary))
        if _hash(state.get("_evaluation", {}).get("gold")) != run.gold_fingerprint:
            raise self._failure("evaluation_input_invalid")
        task = state.get("_evaluation", {}).get("tasks", {}).get(str(row.id))
        if (
            not isinstance(task, dict)
            or task.get("job_id") != str(message.job_id)
            or task.get("model") != row.model
            or message.operation_id != uuid5(run.operation_id, f"case:{row.model}:{row.case_id}")
        ):
            raise self._failure("evaluation_input_invalid")
        if task.get("case") not in state["_evaluation"]["gold"]:
            raise self._failure("evaluation_input_invalid")
        return run, row, state, task

    def _prepare(
        self, message: JobMessage, lease: ExecutionLease
    ) -> tuple[EditorialStep | None, str]:
        unknown = False
        with self._sessions() as session, session.begin():
            run, row, state, task = self._load(session, message, lease)
            frozen = load_ai_benchmark_in_transaction(
                session, owner_id=message.owner_id, job_id=message.job_id
            )
            for key in task.get("outputs", {}):
                saved = task.get("calls", {}).get(key)
                try:
                    call_id = UUID(saved["call_id"]) if isinstance(saved, dict) else None
                except (ValueError, KeyError):
                    call_id = None
                receipt = (
                    load_saved_ai_call_in_transaction(
                        session,
                        owner_id=message.owner_id,
                        call_id=call_id,
                        job_id=message.job_id,
                        purpose=f"analysis.selectbench.{key}",
                    )
                    if call_id is not None
                    else None
                )
                if receipt is None or receipt.status != AiCallStatus.SUCCEEDED:
                    raise self._failure("evaluation_call_evidence_missing")
                if frozen is not None and (
                    receipt.provider != frozen[1].provider
                    or receipt.model != frozen[1].model
                    or receipt.model_key != frozen[1].key
                    or receipt.routing_hash != frozen[0].sha256
                    or receipt.routing_version != frozen[0].configuration_version
                ):
                    raise self._failure("evaluation_call_evidence_missing")
            if row.decision is not None:
                return None, row.model
            if row.error_code in {"request_started", "evaluation_result_unknown"}:
                row.error_code = "evaluation_result_unknown"
                session.flush()
                self._summaries(session, run, state)
                unknown = True
            else:
                if state["_evaluation"].get("kind") == "relation":
                    pair = RelationGoldCaseInput.model_validate(task["case"])
                    saved = task["outputs"].get("relation-pair")
                    if saved is not None:
                        result = RelationPairOutput.model_validate(saved)
                        row.category = result.relation
                        row.relevance = pair.gold_relation
                        row.score = result.confidence * 100
                        row.decision = (
                            "select"
                            if result.relation in POSITIVE and result.confidence >= 0.8
                            else "reject"
                        )
                        row.reason, row.error_code = result.difference, None
                        task["pending_stage"] = None
                        session.flush()
                        self._summaries(session, run, state)
                        return None, row.model
                    version, instructions, prompt = relation_pair_request(pair.a, pair.b)
                    pair_step = EditorialStep(
                        "relation-pair", version, instructions, prompt, RelationPairOutput
                    )
                    row.error_code, task["pending_stage"] = "request_started", pair_step.key
                    run.summary = state
                    return pair_step, row.model
                case = SelectBenchGoldCaseInput.model_validate(task["case"])
                material = EditorialMaterial(
                    content_id=uuid5(run.id, f"gold:{case.case_id}"),
                    content_version_id=uuid5(run.id, f"gold-version:{case.case_id}"),
                    source_key="gold",
                    source_name=case.source_name,
                    source_kind=case.source_kind,
                    tier=case.tier,
                    title=case.title,
                    body=case.body,
                    body_complete=True,
                    published_at=case.published_at,
                    discovered_at=run.created_at,
                    first_party=case.first_party,
                    author=case.author,
                    url=case.url,
                    quoted_text=case.quoted_text,
                    quoted_author=case.quoted_author,
                )
                step = next_editorial_step(
                    material, task["outputs"], now=run.created_at, selection_only=True
                )
                if isinstance(step, dict):
                    row.decision = "select" if step["selected"] else "reject"
                    row.score = step["score"]
                    row.relevance = step["relevance"]
                    row.reason = str(step["prefilter"]["reason"])[:2000]
                    row.error_code = None
                    task["pending_stage"] = None
                    session.flush()
                    self._summaries(session, run, state)
                    return None, row.model
                row.error_code = "request_started"
                task["pending_stage"] = step.key
                run.summary = state
                return step, row.model
        if unknown:
            raise self._failure("evaluation_result_unknown")
        raise self._failure("evaluation_input_invalid")

    @staticmethod
    def _summaries(session: Session, run: SelectBenchRun, state: dict[str, Any]) -> None:
        rows = session.scalars(
            select(SelectBenchResult).where(
                SelectBenchResult.owner_id == run.owner_id, SelectBenchResult.run_id == run.id
            )
        ).all()
        for model in run.models:
            if state["_evaluation"].get("kind") == "relation":
                state[model] = relation_metrics(
                    [
                        {
                            "gold": row.relevance,
                            "relation": row.category,
                            "confidence": row.score / 100 if row.score is not None else None,
                        }
                        for row in rows
                        if row.model == model
                    ]
                )
                continue
            state[model] = score_model_report(
                [
                    {"gold": row.gold, "decision": row.decision, "score": row.score}
                    for row in rows
                    if row.model == model
                ]
            )
        state["execution"] = {
            "completed": sum(row.decision is not None for row in rows),
            "unknown": sum(row.error_code == "evaluation_result_unknown" for row in rows),
            "total": len(rows),
        }
        state["_evaluation"]["status"] = (
            "completed" if all(row.decision is not None for row in rows) else "pending"
        )
        run.summary = state

    def _save_response(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        step: EditorialStep,
        completion: AiCompletion,
    ) -> None:
        answer = step.output_type.model_validate(completion.output).model_dump(
            mode="json", by_alias=True
        )
        with self._sessions() as session, session.begin():
            run, row, state, task = self._load(session, message, lease)
            if (
                row.error_code != "request_started"
                or task.get("pending_stage") != step.key
                or completion.call_id is None
            ):
                raise self._failure("evaluation_input_invalid")
            task["outputs"][step.key] = answer
            task["calls"][step.key] = {
                "call_id": str(completion.call_id),
                "prompt_version": step.prompt_version,
                "model": completion.model,
            }
            task["pending_stage"] = None
            row.ai_call_id, row.error_code = completion.call_id, "response_saved"
            run.summary = state

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        if not self._settings.selectbench_enabled:
            raise self._failure("selectbench_disabled")
        for _ in range(4):
            step, model = self._prepare(message, lease)
            if step is None:
                return JobCompletion(status=JobStatus.SUCCEEDED)
            client = None
            try:
                with self._sessions() as session, session.begin():
                    frozen = load_ai_benchmark_in_transaction(
                        session, owner_id=message.owner_id, job_id=message.job_id
                    )
                if frozen is None:
                    client = create_ai_client(self._settings.model_copy(update={"ai_model": model}))
                elif frozen[1].component_key == "codex.app-server":
                    # Retain controlled Codex transports with this model's exact snapshot.
                    client = create_ai_client(
                        self._settings.model_copy(update={"ai_model": frozen[1].model})
                    )
                else:
                    client = create_ai_client_for_frozen_model(self._settings, frozen[1])
                with self._sessions() as session:
                    completion = AiService(
                        session,
                        client,
                        clock=self._clock,
                        settings=self._settings,
                        guard=lambda current: self._load(current, message, lease),
                        execution_epoch=lease.epoch,
                    ).complete(
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        purpose=f"analysis.selectbench.{step.key}",
                        prompt_version=step.prompt_version,
                        prompt=step.prompt,
                        instructions=step.instructions,
                        output_schema=step.output_type.model_json_schema(),
                    )
                self._save_response(message, lease, step, completion)
            except (AiCallError, ValidationError, ValueError) as error:
                unknown = isinstance(error, AiCallError) and error.outcome_unknown
                retry = isinstance(error, AiCallError) and error.code in {
                    AiFailureCode.UNAVAILABLE,
                    AiFailureCode.RATE_LIMITED,
                }
                code = (
                    "evaluation_result_unknown"
                    if unknown
                    else f"ai_{error.code.value}"
                    if isinstance(error, AiCallError)
                    else "evaluation_invalid_output"
                )
                with self._sessions() as session, session.begin():
                    run, row, state, _task = self._load(session, message, lease)
                    row.error_code = code
                    self._summaries(session, run, state)
                raise self._failure(code, retry=retry) from None
            finally:
                if client is not None:
                    client.close()
        raise self._failure("evaluation_stage_limit")
