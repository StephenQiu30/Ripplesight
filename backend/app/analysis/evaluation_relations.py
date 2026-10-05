from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.benchmark_services import freeze_ai_benchmark_in_transaction
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.evaluation_schemas import (
    RelationBenchCasesView,
    RelationBenchCaseView,
    RelationBenchGoldInput,
    RelationBenchImportInput,
    RelationGoldCaseInput,
    RelationPredictionInput,
    SelectBenchAcceptedView,
)
from core.config import Settings
from core.errors import ApplicationError
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from operations.services import accept_audit_in_transaction, complete_audit_in_transaction

RELATIONS = ("SAME_OCCURRENCE", "SAME_STORY", "UNRELATED", "ROUNDUP")
POSITIVE = {"SAME_OCCURRENCE", "SAME_STORY"}


def parse_relation_gold_jsonl(value: str) -> list[RelationGoldCaseInput]:
    if len(value) > 20000000:
        raise ValueError("gold exceeds 20 million characters")
    rows, seen = [], set()
    for line, raw in enumerate(value.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("//"):
            continue
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("row must be object")
            if "caseId" in data:
                sampling = data.get("samplingContext") or {}

                def report(item: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "title": item.get("title"),
                        "source": item.get("source"),
                        "first_party": item.get("firstParty", False),
                        "published_at": item.get("publishedAt"),
                        "summary": item.get("summary"),
                        "frame": item.get("frame"),
                    }

                data = {
                    "case_id": data["caseId"],
                    "a": report(data["a"]),
                    "b": report(data["b"]),
                    "gold_relation": data["gold"]["relation"],
                    "stratum": sampling.get("samplingStratum"),
                    "split": sampling.get("benchmarkSplit"),
                }
            case = RelationGoldCaseInput.model_validate(data)
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
            raise ValueError(f"line {line}: invalid relation gold fields") from None
        if case.case_id in seen:
            raise ValueError(f"line {line}: duplicate case identity")
        seen.add(case.case_id)
        rows.append(case)
        if len(rows) > 5000:
            raise ValueError(f"line {line}: more than 5000 cases")
    if not rows:
        raise ValueError("gold contains no cases")
    return rows


def relation_metrics(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    matrix = {gold: {prediction: 0 for prediction in RELATIONS} for gold in RELATIONS}
    valid = [row for row in cases if row.get("relation") in RELATIONS]
    for row in valid:
        matrix[row["gold"]][row["relation"]] += 1
    per_class = {}
    for relation in RELATIONS:
        tp = matrix[relation][relation]
        fp = sum(matrix[gold][relation] for gold in RELATIONS if gold != relation)
        support = sum(matrix[relation].values())
        fn = support - tp
        precision, recall = tp / max(1, tp + fp), tp / max(1, tp + fn)
        per_class[relation] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            "support": support,
        }
    ties = []
    for threshold in (0.75, 0.8, 0.85, 0.9, 0.95):
        counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "errors": len(cases) - len(valid)}
        for row in valid:
            gold = row["gold"] in POSITIVE
            predicted = row["relation"] in POSITIVE and row["confidence"] >= threshold
            counts[
                "tp" if gold and predicted else "fp" if predicted else "fn" if gold else "tn"
            ] += 1
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision, recall = tp / max(1, tp + fp), tp / max(1, tp + fn)
        ties.append(
            {
                **counts,
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            }
        )
    return {
        "sample_size": len(cases),
        "evaluated": len(valid),
        "errors": len(cases) - len(valid),
        "accuracy": sum(matrix[r][r] for r in RELATIONS) / len(valid) if valid else None,
        "macro_f1": sum(row["f1"] for row in per_class.values()) / len(RELATIONS),
        "confusion_matrix": matrix,
        "per_class": per_class,
        "story_ties": ties,
    }


def relation_prompt_version() -> str:
    from analysis.prompts import editorial_prompt_version

    return "relationbench@" + editorial_prompt_version("group-pair").split("@")[-1]


def compare_relation_versions(
    cases: Sequence[RelationGoldCaseInput],
    predictions_by_version: Mapping[str, Sequence[RelationPredictionInput]],
    *,
    baseline_version: str,
) -> dict[str, Any]:
    """Compare frozen old/new outputs on identical gold, without storage or model calls.

    Keys are the actual receipt prompt versions, not model names. A failed case must
    have an explicit error prediction; silently dropping cases would bias the metrics.
    """
    expected = {case.case_id for case in cases}
    if not 1 <= len(cases) <= 5000 or len(expected) != len(cases):
        raise ValueError("comparison requires unique nonempty gold cases")
    if (
        not 2 <= len(predictions_by_version) <= 5
        or baseline_version not in predictions_by_version
        or any(not version.strip() or len(version) > 200 for version in predictions_by_version)
    ):
        raise ValueError("comparison requires explicit baseline and prompt versions")
    ordered = sorted(cases, key=lambda case: case.case_id)
    by_version = {}
    by_case: dict[str, dict[str, RelationPredictionInput]] = {}
    for version, predictions in predictions_by_version.items():
        if len(predictions) != len(expected) or {row.case_id for row in predictions} != expected:
            raise ValueError("prompt versions must compare the same unique cases")
        indexed = {row.case_id: row for row in predictions}
        by_case[version] = indexed
        by_version[version] = relation_metrics(
            [
                {
                    "gold": case.gold_relation,
                    "relation": indexed[case.case_id].relation,
                    "confidence": indexed[case.case_id].confidence,
                }
                for case in ordered
            ]
        )
    baseline = by_version[baseline_version]
    deltas = {}
    for version, metrics in by_version.items():
        deltas[version] = {
            key: metrics[key] - baseline[key]
            if metrics[key] is not None and baseline[key] is not None
            else None
            for key in ("accuracy", "macro_f1", "errors", "evaluated")
        }
        deltas[version]["story_ties"] = [
            {
                "threshold": candidate["threshold"],
                **{
                    key: candidate[key] - base[key]
                    for key in ("tp", "fp", "tn", "fn", "errors", "precision", "recall", "f1")
                },
            }
            for candidate, base in zip(metrics["story_ties"], baseline["story_ties"], strict=True)
        ]
    return {
        "gold_fingerprint": hashlib.sha256(
            json.dumps(
                [case.model_dump(mode="json") for case in ordered],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "case_ids": [case.case_id for case in ordered],
        "baseline_version": baseline_version,
        "by_version": by_version,
        "delta_from_baseline": deltas,
        "changed_cases": [
            case.case_id
            for case in ordered
            if len(
                {
                    (indexed[case.case_id].relation, indexed[case.case_id].error_code)
                    for indexed in by_case.values()
                }
            )
            > 1
        ],
    }


class RelationBenchService:
    def __init__(
        self,
        session: Session,
        *,
        enabled: bool,
        clock: Callable[[], datetime],
        settings: Settings | None = None,
    ) -> None:
        self._session, self._enabled, self._clock = session, enabled, clock
        self.settings = settings

    def save(self, *, owner_id: UUID, command: RelationBenchGoldInput) -> SelectBenchAcceptedView:
        from analysis.evaluation_services import SelectBenchService, _hash

        imported = isinstance(command, RelationBenchImportInput)
        if not imported and not self._enabled:
            raise ApplicationError("selectbench_disabled")
        candidates = [
            case for case in command.cases if command.split is None or case.split == command.split
        ]
        rng = random.Random(command.seed)
        strata: dict[str, list[RelationGoldCaseInput]] = {}
        for case in sorted(candidates, key=lambda row: row.case_id):
            strata.setdefault(case.stratum or "unclassified", []).append(case)
        for group in strata.values():
            rng.shuffle(group)
        chosen: list[RelationGoldCaseInput] = []
        while len(chosen) < min(command.sample_size, len(candidates)):
            for key in sorted(strata):
                if strata[key] and len(chosen) < command.sample_size:
                    chosen.append(strata[key].pop())
        if imported:
            chosen = candidates
        gold = [
            case.model_dump(mode="json") for case in sorted(chosen, key=lambda row: row.case_id)
        ]
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            audit, replay = accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="selectbench.relation.import" if imported else "selectbench.relation.run",
                target_ref=command.label,
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
            )
            previous = self._session.scalar(
                select(SelectBenchRun).where(
                    SelectBenchRun.owner_id == owner_id,
                    SelectBenchRun.operation_id == command.operation_id,
                )
            )
            if previous is not None:
                return SelectBenchAcceptedView(
                    run=SelectBenchService._run_view(previous, replayed=True),
                    job_ids=[
                        UUID(str(value))
                        for value in cast(list[str], audit.after_state.get("job_ids", []))
                    ],
                    replayed=True,
                )
            if replay:
                raise ApplicationError("evaluation_input_conflict")
            model_snapshot = (
                None
                if imported
                else freeze_ai_benchmark_in_transaction(
                    self._session, owner_id=owner_id, models=command.models, settings=self.settings
                )
            )
            run = SelectBenchRun(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                input_fingerprint=_hash(command.model_dump(mode="json")),
                gold_fingerprint=_hash(gold),
                label=command.label,
                prompt_version=relation_prompt_version(),
                split=command.split,
                seed=command.seed,
                sample_size=len(gold),
                models=command.models,
                summary={},
                imported_by=owner_id,
                created_at=now,
            )
            self._session.add(run)
            self._session.flush()
            tasks, job_ids = {}, []
            for model in command.models:
                predictions = (
                    {
                        case.case_id: case
                        for case in cast(RelationBenchImportInput, command).predictions[model]
                    }
                    if imported
                    else {}
                )
                for case in chosen:
                    predicted = predictions.get(case.case_id)
                    row = SelectBenchResult(
                        id=uuid4(),
                        owner_id=owner_id,
                        run_id=run.id,
                        model=model,
                        case_id=case.case_id,
                        title=(case.a.title + " / " + case.b.title)[:500],
                        stratum=case.stratum,
                        gold="select" if case.gold_relation in POSITIVE else "reject",
                        relevance=case.gold_relation,
                        category=predicted.relation if predicted else None,
                        decision=(
                            "select"
                            if predicted.relation in POSITIVE
                            and predicted.confidence is not None
                            and predicted.confidence >= 0.8
                            else "reject"
                        )
                        if predicted and predicted.relation
                        else None,
                        score=predicted.confidence * 100
                        if predicted and predicted.confidence is not None
                        else None,
                        reason=predicted.difference if predicted else None,
                        error_code=predicted.error_code if predicted else "pending",
                        ai_call_id=None,
                        created_at=now,
                    )
                    self._session.add(row)
                    if not imported:
                        assert model_snapshot is not None
                        job = JobService(self._session, clock=self._clock).accept_in_transaction(
                            owner_id=owner_id,
                            command=JobAcceptanceInput(
                                operation_id=uuid5(
                                    command.operation_id, f"case:{model}:{case.case_id}"
                                ),
                                kind="analysis.selectbench",
                                scope={
                                    "ai_benchmark_models": model_snapshot.model_dump_json(),
                                    "ai_benchmark_hash": model_snapshot.sha256,
                                    "benchmark_model_ref": model,
                                    "run_id": str(run.id),
                                    "result_id": str(row.id),
                                    "gold_fingerprint": run.gold_fingerprint.hex(),
                                },
                                observation=JobObservationContext(
                                    configuration_ref=f"selectbench:{run.id.hex}",
                                    configuration_version=1,
                                ),
                            ),
                        )
                        job_ids.append(job.id)
                        tasks[str(row.id)] = {
                            "case": case.model_dump(mode="json"),
                            "model": model,
                            "job_id": str(job.id),
                            "outputs": {},
                            "calls": {},
                            "pending_stage": None,
                        }
            run.summary = {
                "_evaluation": {
                    "model_snapshots": model_snapshot.model_dump(mode="json")
                    if model_snapshot
                    else None,
                    "model_snapshot_hash": model_snapshot.sha256 if model_snapshot else None,
                    "kind": "relation",
                    "gold": gold,
                    "tasks": tasks,
                    "job_ids": [str(value) for value in job_ids],
                    "status": "completed" if imported else "pending",
                }
            }
            self._session.flush()
            self._summaries(run)
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state={"run_id": str(run.id), "job_ids": [str(value) for value in job_ids]},
                now=now,
            )
            return SelectBenchAcceptedView(run=SelectBenchService._run_view(run), job_ids=job_ids)

    def _summaries(self, run: SelectBenchRun) -> None:
        results = list(
            self._session.scalars(
                select(SelectBenchResult).where(
                    SelectBenchResult.owner_id == run.owner_id, SelectBenchResult.run_id == run.id
                )
            )
        )
        run.summary = {
            **run.summary,
            **{
                model: relation_metrics(
                    [
                        {
                            "gold": row.relevance,
                            "relation": row.category,
                            "confidence": row.score / 100 if row.score is not None else None,
                        }
                        for row in results
                        if row.model == model
                    ]
                )
                for model in run.models
            },
        }

    def get_cases(
        self,
        *,
        owner_id: UUID,
        run_id: UUID,
        cursor: str | None = None,
        limit: int = 100,
        disagree: bool = False,
        errors: bool = False,
    ) -> RelationBenchCasesView:
        from analysis.evaluation_services import SelectBenchService

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
            state = cast(dict[str, Any], run.summary.get("_evaluation", {}))
            if state.get("kind") != "relation":
                raise ApplicationError("invalid_evaluation_input")
            results: dict[str, dict[str, RelationPredictionInput]] = {}
            for row in self._session.scalars(
                select(SelectBenchResult).where(
                    SelectBenchResult.owner_id == owner_id, SelectBenchResult.run_id == run_id
                )
            ):
                results.setdefault(row.case_id, {})[row.model] = RelationPredictionInput(
                    case_id=row.case_id,
                    relation=row.category,
                    confidence=row.score / 100 if row.score is not None else None,
                    difference=row.reason,
                    error_code=row.error_code,
                )
            items: list[RelationBenchCaseView] = []
            strata: dict[str, int] = {}
            for raw in state["gold"]:
                case = RelationGoldCaseInput.model_validate(raw)
                strata[case.stratum or "unclassified"] = (
                    strata.get(case.stratum or "unclassified", 0) + 1
                )
                predictions = results[case.case_id]
                if cursor is not None and case.case_id <= cursor:
                    continue
                if (
                    disagree
                    and len({p.relation for p in predictions.values() if p.relation is not None})
                    <= 1
                ):
                    continue
                if errors and not any(p.error_code is not None for p in predictions.values()):
                    continue
                items.append(RelationBenchCaseView(case=case, by_model=predictions))
            return RelationBenchCasesView(
                run=SelectBenchService._run_view(run),
                items=items[:limit],
                next_cursor=items[limit - 1].case.case_id if len(items) > limit else None,
                strata=strata,
            )
