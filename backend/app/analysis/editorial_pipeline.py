"""Deterministic editorial planning; all paid calls are made by the owning service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from analysis.editorial_rules import (
    CATEGORY_BY_ITEM_TYPE,
    ENTITIES,
    THRESHOLDS,
    decide_selection,
    finalize_copy,
    is_short_post,
    looks_zh,
    needs_short_post_translation,
    normalize_prefilter,
    normalize_tags,
    render_material,
    score_input,
    structure_instructions,
    summarize_prompt,
)
from analysis.editorial_schemas import (
    EditorialMaterial,
    PrefilterOutput,
    ScoreOutput,
    StructureOutput,
    SummarizeOutput,
    UnderstandOutput,
)
from analysis.prompts import editorial_prompt_version, render_editorial_prompt


@dataclass(frozen=True, slots=True)
class EditorialStep:
    key: str
    prompt_version: str
    instructions: str
    prompt: str
    output_type: type[BaseModel]


def next_editorial_step(
    material: EditorialMaterial,
    outputs: dict[str, dict[str, Any]],
    *,
    now: datetime,
    selection_only: bool = False,
) -> EditorialStep | dict[str, Any]:
    """Resume on immutable stage identities; score-1 and score-2 cannot share an answer."""
    if "prefilter" not in outputs:
        return EditorialStep(
            "prefilter",
            editorial_prompt_version("prefilter"),
            render_editorial_prompt("prefilter"),
            json.dumps(render_material(material), ensure_ascii=False),
            PrefilterOutput,
        )
    prefilter = PrefilterOutput.model_validate(outputs["prefilter"])
    label = normalize_prefilter(prefilter.label, material)
    base: dict[str, Any] = {
        "prefilter": {"label": label, "reason": prefilter.reason},
        "scores": [],
        "threshold": THRESHOLDS.get(material.tier),
        "score": None,
        "selected": False,
        "relevance": "block" if label == "BLOCK" else "unknown",
        "writing": None,
        "structure": None,
    }
    if label == "BLOCK":
        return base
    values: tuple[int, ...] = ()
    if material.tier in THRESHOLDS:
        for key in ("score-1", "score-2"):
            if key not in outputs:
                return EditorialStep(
                    key,
                    editorial_prompt_version("selection-score"),
                    render_editorial_prompt("selection-score"),
                    score_input(material),
                    ScoreOutput,
                )
            values += (ScoreOutput.model_validate(outputs[key]).attention_score,)
    decision = decide_selection(material.tier, values)
    base.update({"scores": list(values), "threshold": decision.threshold, "score": decision.score})
    if selection_only:
        base.update(
            {"selected": decision.selected, "relevance": "pass" if label == "PASS" else "unknown"}
        )
        return base
    if "structure" not in outputs:
        return EditorialStep(
            "structure",
            editorial_prompt_version("structure"),
            structure_instructions(),
            render_material(material),
            StructureOutput,
        )
    structure = StructureOutput.model_validate(outputs["structure"])
    structure.tags = normalize_tags(structure.tags)
    structure.subjects = list(
        dict.fromkeys(
            subject.strip().lower()
            for subject in structure.subjects
            if subject.strip().lower() in ENTITIES
        )
    )
    base["structure"] = structure.model_dump(mode="json", by_alias=True)
    writing: dict[str, Any]
    if decision.understand:
        if "understand" not in outputs:
            return EditorialStep(
                "understand",
                editorial_prompt_version("understand"),
                render_editorial_prompt("understand"),
                "请按系统规则理解以下单篇材料。\n\n" + render_material(material),
                UnderstandOutput,
            )
        answer = UnderstandOutput.model_validate(outputs["understand"])
        copy = finalize_copy(material, answer.title_zh, answer.summary_zh)
        writing = {
            "kind": "understand",
            **copy.model_dump(mode="json"),
            "reason_zh": answer.editorial_judgment or None,
            "item_type": answer.item_type,
            "author_role": answer.author_role,
            "tags": normalize_tags(answer.tags, CATEGORY_BY_ITEM_TYPE[answer.item_type]),
        }
    else:
        main = material.body or material.title
        if is_short_post(material) and not needs_short_post_translation(main):
            copy = finalize_copy(material, main, main)
            writing = {
                "kind": "verbatim",
                **copy.model_dump(mode="json"),
                "reason_zh": None,
                "tags": None,
            }
        elif not is_short_post(material) and len((material.body or material.excerpt).strip()) < 20:
            copy = finalize_copy(material, material.title if looks_zh(material.title) else "", "")
            writing = {
                "kind": "none",
                **copy.model_dump(mode="json"),
                "reason_zh": None,
                "tags": None,
            }
        else:
            if "summarize" not in outputs:
                names = (
                    "summarize-article",
                    "summarize-article-empty",
                    "summarize-short-post",
                    "summarize-short-post-quoted",
                    "summarize-long-post",
                    "summarize-long-post-quoted",
                    "identity-context",
                )
                # The full include version exceeds the ledger limit; record a compact hash.
                import hashlib

                version = (
                    "summarize@"
                    + hashlib.sha256(editorial_prompt_version(*names).encode()).hexdigest()[:20]
                )
                return EditorialStep(
                    "summarize",
                    version,
                    "只返回匹配提供JSON Schema的JSON对象, 不输出其他文字。",
                    summarize_prompt(material, now),
                    SummarizeOutput,
                )
            answer_summary = SummarizeOutput.model_validate(outputs["summarize"])
            summary = (
                answer_summary.body_zh or answer_summary.summary_zh
                if is_short_post(material)
                else answer_summary.summary_zh or answer_summary.body_zh
            )
            copy = finalize_copy(material, answer_summary.title_zh, summary)
            writing = {
                "kind": "summarize",
                **copy.model_dump(mode="json"),
                "reason_zh": None,
                "tags": None,
            }
    available = bool(writing["title_zh"] and writing["summary_zh"])
    base.update(
        {
            "selected": available and decision.selected,
            "relevance": "pass" if available else "unknown",
            "writing": writing,
            "body_complete": material.body_complete,
        }
    )
    return base
