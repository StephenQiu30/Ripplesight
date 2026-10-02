from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.benchmark_services import freeze_ai_benchmark_in_transaction
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.evaluation_schemas import (
    RelationBenchCasesView,
    RelationBenchGoldInput,
    RelationBenchImportInput,
    SelectBenchAcceptedView,
    SelectBenchCaseInput,
    SelectBenchCasesView,
    SelectBenchCaseView,
    SelectBenchGoldCaseInput,
    SelectBenchGoldInput,
    SelectBenchImportInput,
    SelectBenchRunView,
)
from analysis.prompts import editorial_prompt_version
from core.config import Settings
from core.errors import ApplicationError
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from operations.services import accept_audit_in_transaction, complete_audit_in_transaction


def _hash(payload: object) -> bytes:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).digest()


def _confusion(cases: Sequence[dict[str, object]]) -> dict[str, object]:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "errors": 0, "either": 0}
    for case in cases:
        gold, decision = case["gold"], case.get("decision")
        if decision is None:
            counts["errors"] += 1
        if gold == "either":
            counts["either"] += 1
        elif decision is not None:
            counts[
                {
                    ("select", "select"): "tp",
                    ("reject", "select"): "fp",
                    ("reject", "reject"): "tn",
                    ("select", "reject"): "fn",
                }[(str(gold), str(decision))]
            ] += 1
    strict = len(cases) - counts["either"]
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return {
        **counts,
        "n": len(cases),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "accuracy": (tp + counts["tn"]) / strict if strict else None,
        "error_rate": counts["errors"] / len(cases) if cases else None,
    }


def score_model_report(cases: Sequence[dict[str, object]]) -> dict[str, object]:
    """Recompute metrics from decisions, never trust imported aggregate claims."""
    result = _confusion(cases)
    result["thresholds"] = [
        {
            "threshold": threshold,
            **_confusion(
                [
                    {
                        **case,
                        "decision": "select"
                        if float(cast(float, case["score"])) >= threshold
                        else "reject",
                    }
                    for case in cases
                    if case.get("score") is not None
                ]
            ),
        }
        for threshold in range(40, 91, 2)
    ]
    return result


class SelectBenchService:
    def __init__(
        self,
        session: Session,
        *,
        enabled: bool = False,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._session, self._clock = session, clock or (lambda: datetime.now(UTC))
        self._enabled = enabled
        self.settings = settings

    def queue_relation_gold(
        self, *, owner_id: UUID, command: RelationBenchGoldInput
    ) -> SelectBenchAcceptedView:
        from analysis.evaluation_relations import RelationBenchService

        return RelationBenchService(
            self._session, enabled=self._enabled, clock=self._clock, settings=self.settings
        ).save(owner_id=owner_id, command=command)

    def import_relation_report(
        self, *, owner_id: UUID, command: RelationBenchImportInput
    ) -> SelectBenchRunView:
        return self.queue_relation_gold(owner_id=owner_id, command=command).run

    def get_relation_cases(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
        cursor: str | None = None,
        limit: int = 100,
        disagree: bool = False,
        errors: bool = False,
    ) -> RelationBenchCasesView:
        from analysis.evaluation_relations import RelationBenchService

        return RelationBenchService(
            self._session, enabled=self._enabled, clock=self._clock, settings=self.settings
        ).get_cases(
            owner_id=owner_id,
            run_id=run_id,
            cursor=cursor,
            limit=limit,
            disagree=disagree,
            errors=errors,
        )

    def queue_gold(
        self, *, owner_id: UUID, command: SelectBenchGoldInput
    ) -> SelectBenchAcceptedView:
        if not self._enabled:
            raise ApplicationError("selectbench_disabled")
        now = self._clock()
        candidates = [
            case for case in command.cases if command.split is None or case.split == command.split
        ]
        strata: dict[str, list[SelectBenchGoldCaseInput]] = {}
        for case in sorted(candidates, key=lambda item: item.case_id):
            strata.setdefault(case.stratum or "unclassified", []).append(case)
        rng = random.Random(command.seed)
        for group in strata.values():
            rng.shuffle(group)
        selected: list[SelectBenchGoldCaseInput] = []
        while len(selected) < min(command.sample_size, len(candidates)):
            for key in sorted(strata):
                if strata[key] and len(selected) < command.sample_size:
                    selected.append(strata[key].pop())
        gold = [
            case.model_dump(mode="json") for case in sorted(selected, key=lambda item: item.case_id)
        ]
        version = (
            "selectbench@"
            + hashlib.sha256(
                editorial_prompt_version("prefilter", "selection-score").encode()
            ).hexdigest()[:20]
        )
        self._session.rollback()
        with self._session.begin():
            _audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="selectbench.run",
                target_ref=command.label,
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            row = self._session.scalar(
                select(SelectBenchRun).where(
                    SelectBenchRun.owner_id == owner_id,
                    SelectBenchRun.operation_id == command.operation_id,
                )
            )
            if row is not None:
                state = cast(dict[str, object], row.summary.get("_evaluation", {}))
                return SelectBenchAcceptedView(
                    run=self._run_view(row, replayed=True),
                    job_ids=[UUID(str(value)) for value in cast(list[object], state["job_ids"])],
                    replayed=True,
                )
            if replayed:
                raise ApplicationError("evaluation_input_conflict")
            model_snapshot = freeze_ai_benchmark_in_transaction(
                self._session, owner_id=owner_id, models=command.models, settings=self.settings
            )
            row = SelectBenchRun(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                input_fingerprint=_hash(command.model_dump(mode="json")),
                gold_fingerprint=_hash(gold),
                label=command.label,
                prompt_version=version,
                split=command.split,
                seed=command.seed,
                sample_size=len(gold),
                models=command.models,
                summary={},
                imported_by=owner_id,
                created_at=now,
            )
            self._session.add(row)
            self._session.flush()
            jobs = []
            tasks: dict[str, object] = {}
            for model in command.models:
                for gold_case in gold:
                    result = SelectBenchResult(
                        id=uuid4(),
                        owner_id=owner_id,
                        run_id=row.id,
                        model=model,
                        case_id=str(gold_case["case_id"]),
                        title=str(gold_case["title"]),
                        gold=str(gold_case["gold"]),
                        stratum=gold_case["stratum"],
                        error_code="pending",
                        created_at=now,
                    )
                    self._session.add(result)
                    job = JobService(self._session, clock=self._clock).accept_in_transaction(
                        owner_id=owner_id,
                        command=JobAcceptanceInput(
                            operation_id=uuid5(
                                command.operation_id, f"case:{model}:{gold_case['case_id']}"
                            ),
                            kind="analysis.selectbench",
                            scope={
                                "ai_benchmark_models": model_snapshot.model_dump_json(),
                                "ai_benchmark_hash": model_snapshot.sha256,
                                "benchmark_model_ref": model,
                                "run_id": str(row.id),
                                "result_id": str(result.id),
                                "gold_fingerprint": row.gold_fingerprint.hex(),
                            },
                            observation=JobObservationContext(
                                configuration_ref=f"selectbench:{row.id.hex}",
                                configuration_version=1,
                            ),
                        ),
                    )
                    jobs.append(job.id)
                    tasks[str(result.id)] = {
                        "case": gold_case,
                        "model": model,
                        "job_id": str(job.id),
                        "outputs": {},
                        "calls": {},
                        "pending_stage": None,
                    }
            row.summary = {
                "_evaluation": {
                    "model_snapshots": model_snapshot.model_dump(mode="json"),
                    "model_snapshot_hash": model_snapshot.sha256,
                    "job_ids": [str(value) for value in jobs],
                    "gold": gold,
                    "tasks": tasks,
                    "status": "pending",
                }
            }
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state={"run_id": str(row.id), "job_ids": [str(value) for value in jobs]},
                now=now,
            )
            self._session.flush()
            return SelectBenchAcceptedView(run=self._run_view(row), job_ids=jobs)

    def import_report(
        self, *, owner_id: UUID, command: SelectBenchImportInput
    ) -> SelectBenchRunView:
        self._session.rollback()
        now = self._clock()
        payload = command.model_dump(mode="json")
        with self._session.begin():
            audit, replayed = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="selectbench.import",
                target_ref=command.label,
                reason=command.reason,
                payload=payload,
                now=now,
            )
            if replayed:
                row = self._session.scalar(
                    select(SelectBenchRun).where(
                        SelectBenchRun.owner_id == owner_id,
                        SelectBenchRun.operation_id == command.operation_id,
                    )
                )
                if row is None:
                    raise ApplicationError("evaluation_input_conflict")
                return self._run_view(row, replayed=True)
            names = sorted(command.models)
            gold = sorted(
                [
                    (case.case_id, case.title, case.stratum, case.gold)
                    for case in command.models[names[0]]
                ]
            )
            row = SelectBenchRun(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                input_fingerprint=_hash(payload),
                gold_fingerprint=_hash(gold),
                label=command.label,
                prompt_version=command.prompt_version,
                split=command.split,
                seed=command.seed,
                sample_size=len(gold),
                models=names,
                summary={
                    name: score_model_report([case.model_dump() for case in command.models[name]])
                    for name in names
                },
                imported_by=owner_id,
                created_at=now,
            )
            self._session.add(row)
            self._session.flush()
            for model, cases in command.models.items():
                for case in cases:
                    self._session.add(
                        SelectBenchResult(
                            id=uuid4(),
                            owner_id=owner_id,
                            run_id=row.id,
                            model=model,
                            **case.model_dump(),
                            ai_call_id=None,
                            created_at=now,
                        )
                    )
            audit.status, audit.after_state, audit.updated_at = (
                "succeeded",
                {
                    "run_id": str(row.id),
                    "gold_fingerprint": row.gold_fingerprint.hex(),
                    "models": names,
                    "sample_size": row.sample_size,
                },
                now,
            )
            return self._run_view(row)

    @staticmethod
    def _run_view(row: SelectBenchRun, *, replayed: bool = False) -> SelectBenchRunView:
        return SelectBenchRunView.model_validate(
            {
                **row.__dict__,
                "gold_fingerprint": row.gold_fingerprint.hex(),
                "replayed": replayed,
                "kind": cast(dict[str, object], row.summary.get("_evaluation", {})).get(
                    "kind", "selection"
                ),
                "summary": {
                    key: value for key, value in row.summary.items() if not key.startswith("_")
                },
            }
        )

    def list_runs(self, *, owner_id: UUID, limit: int = 100) -> list[SelectBenchRunView]:
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_evaluation_input")
        self._session.rollback()
        with self._session.begin():
            return [
                self._run_view(row)
                for row in self._session.scalars(
                    select(SelectBenchRun)
                    .where(SelectBenchRun.owner_id == owner_id)
                    .order_by(SelectBenchRun.created_at.desc(), SelectBenchRun.id.desc())
                    .limit(limit)
                )
            ]

    def get_cases(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
        model: str | None = None,
        outcome: Literal["tp", "fp", "tn", "fn", "either", "error"] | None = None,
        stratum: str | None = None,
        disagree: bool = False,
        cursor: str | None = None,
        limit: int = 100,
    ) -> SelectBenchCasesView:
        if not 1 <= limit <= 400 or (cursor is not None and len(cursor) > 200):
            raise ApplicationError("invalid_evaluation_input")
        self._session.rollback()
        with self._session.begin():
            run = self._session.scalar(
                select(SelectBenchRun).where(
                    SelectBenchRun.owner_id == owner_id, SelectBenchRun.id == run_id
                )
            )
            if run is None:
                raise ApplicationError("resource_not_found")
            if (
                cast(dict[str, object], run.summary.get("_evaluation", {})).get("kind")
                == "relation"
            ):
                raise ApplicationError("invalid_evaluation_input")
            selected_model = model or run.models[0]
            if selected_model not in run.models:
                raise ApplicationError("invalid_evaluation_input")
            groups: dict[str, SelectBenchCaseView] = {}
            strata: dict[str, int] = {}
            for row in self._session.scalars(
                select(SelectBenchResult)
                .where(SelectBenchResult.owner_id == owner_id, SelectBenchResult.run_id == run_id)
                .order_by(SelectBenchResult.case_id, SelectBenchResult.model)
            ):
                if row.case_id not in groups:
                    groups[row.case_id] = SelectBenchCaseView(
                        case_id=row.case_id,
                        title=row.title,
                        stratum=row.stratum,
                        gold=cast(Literal["select", "reject", "either"], row.gold),
                        by_model={},
                    )
                    key = row.stratum or "unclassified"
                    strata[key] = strata.get(key, 0) + 1
                groups[row.case_id].by_model[row.model] = SelectBenchCaseInput.model_validate(
                    row, from_attributes=True
                )
            matches = []
            for key, case in groups.items():
                if (cursor is not None and key <= cursor) or (
                    stratum is not None and case.stratum != stratum
                ):
                    continue
                result = case.by_model[selected_model]
                actual = (
                    "error"
                    if result.decision is None
                    else "either"
                    if case.gold == "either"
                    else {
                        ("select", "select"): "tp",
                        ("reject", "select"): "fp",
                        ("reject", "reject"): "tn",
                        ("select", "reject"): "fn",
                    }[(case.gold, result.decision)]
                )
                if (outcome is not None and actual != outcome) or (
                    disagree
                    and len(
                        {
                            item.decision
                            for item in case.by_model.values()
                            if item.decision is not None
                        }
                    )
                    <= 1
                ):
                    continue
                matches.append(case)
            return SelectBenchCasesView(
                run=self._run_view(run),
                items=matches[:limit],
                next_cursor=matches[limit - 1].case_id if len(matches) > limit else None,
                strata=strata,
            )
