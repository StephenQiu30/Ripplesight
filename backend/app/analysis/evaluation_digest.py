"""Offline story-digest comparison, using controlled outputs and existing bench scoring.

Adapted from AIHOT 9acad0c story-digest-evaluation and eval-story-digests-core.
Copyright (c) 2026 数字生命卡兹克. MIT: root LICENSE.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from analysis.evaluation_services import score_model_report
from events.digest_prompts import (
    LEGACY_DIGEST_PROMPT_VERSION,
    event_digest_metrics,
    event_digest_prompt_version,
    render_event_digest_prompt,
    serialize_event_digest_data,
)


class DigestEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str = Field(min_length=1, max_length=200, pattern=r"\S")
    members: list[dict[str, Any]] = Field(min_length=1, max_length=2000)
    facts: list[dict[str, Any]] = Field(max_length=2000)
    # Null explicitly represents a missing/failed controlled response.
    old_summary: str | None = Field(max_length=10000)
    new_summary: str | None = Field(max_length=10000)


def parse_digest_evaluation_jsonl(value: str) -> list[DigestEvaluationCase]:
    if len(value) > 20_000_000:
        raise ValueError("digest cases exceed 20 million characters")
    rows: list[DigestEvaluationCase] = []
    seen: set[str] = set()
    for line, raw in enumerate(value.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("//"):
            continue
        try:
            row = DigestEvaluationCase.model_validate(json.loads(raw))
        except ValueError:
            raise ValueError(f"line {line}: invalid digest case") from None
        if row.case_id in seen:
            raise ValueError(f"line {line}: duplicate case identity")
        seen.add(row.case_id)
        rows.append(row)
        if len(rows) > 100:
            raise ValueError(f"line {line}: more than 100 cases")
    if not rows:
        raise ValueError("digest evaluation contains no cases")
    return rows


def evaluate_event_digests(cases: Sequence[DigestEvaluationCase]) -> dict[str, Any]:
    """Render both prompts over identical inputs; no clients, calls or persistence."""
    if not 1 <= len(cases) <= 100 or len({row.case_id for row in cases}) != len(cases):
        raise ValueError("digest evaluation needs 1..100 unique cases")
    versions = {"old": LEGACY_DIGEST_PROMPT_VERSION, "new": event_digest_prompt_version()}
    rows: list[dict[str, Any]] = []
    scores: dict[str, list[dict[str, object]]] = {"old": [], "new": []}
    for case in cases:
        data = serialize_event_digest_data(case.members, case.facts)
        row: dict[str, Any] = {"case_id": case.case_id, "input": json.loads(data)}
        for name, output in (("old", case.old_summary), ("new", case.new_summary)):
            metrics = event_digest_metrics(output or "")
            row[name] = {
                "prompt_version": versions[name],
                "prompt": render_event_digest_prompt(data, legacy=name == "old"),
                "summary": output,
                "metrics": {**asdict(metrics), "compliant": metrics.compliant},
            }
            scores[name].append(
                {
                    "gold": "select",
                    "decision": None
                    if output is None
                    else "select"
                    if metrics.compliant
                    else "reject",
                }
            )
        rows.append(row)
    summary = {}
    for name in versions:
        summary[name] = {
            "bench": score_model_report(scores[name]),
            **{
                key + "_rate": sum(row[name]["metrics"][key] for row in rows) / len(rows)
                for key in (
                    "length_compliant",
                    "paragraphs_compliant",
                    "first_sentence_compliant",
                    "compliant",
                )
            },
        }
    return {
        "mode": "controlled_offline",
        "model_calls": 0,
        "sample_size": len(rows),
        "prompt_versions": versions,
        "summary": summary,
        "cases": rows,
    }
