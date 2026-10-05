from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from itertools import combinations
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analysis.prompts import editorial_prompt_version, render_editorial_prompt
from events.fact_schemas import (
    FactRelationCandidate,
    FactRelationChoice,
    FactVerdict,
    VerdictRelation,
)
from events.schemas import EventDecision, EventFactDecision, EventInput

_RELATIONS = {"SAME_OCCURRENCE", "SAME_STORY", "UNRELATED", "ROUNDUP"}
_FRAME_KEYS = ("subject", "action", "object", "occurredAt")


def relation_frame(frame: dict[str, object] | None) -> dict[str, str | None] | None:
    """Pair identity uses only scalar fields, never the stored quote/condition arrays."""
    if frame is None:
        return None
    return {key: value if isinstance(value := frame.get(key), str) else None for key in _FRAME_KEYS}


def frames_conflict(
    first: Mapping[str, object] | None,
    second: Mapping[str, object] | None,
    *,
    independent_updates_only: bool = False,
) -> bool:
    if not first or not second:
        return False
    if independent_updates_only:
        actions = (first.get("action"), second.get("action"))
        if not all(
            isinstance(action, str)
            and any(
                token in action.lower()
                for token in ("发布", "推出", "更新", "launch", "release", "update", "publish")
            )
            for action in actions
        ):
            return False
    return any(
        isinstance(a := first.get(key), str)
        and isinstance(b := second.get(key), str)
        and bool(a.strip())
        and bool(b.strip())
        and a.strip().casefold() != b.strip().casefold()
        for key in _FRAME_KEYS
    )


def constrain_event_decision(
    decision: EventDecision,
    inputs: Sequence[EventInput],
    *,
    root_fact_id: UUID | None = None,
) -> EventDecision:
    """Reject unsupported identities and turn composite positives into existing mentions.

    A same_occurrence DTO here names a storage target only. The fact writer independently
    checks scope and stores composite members as mention, never primary/report.
    """
    if any(item.editorial_scope == "unknown" for item in inputs):
        raise ValueError("scope_unknown")
    if not decision.same_event:
        return decision
    singles = [item for item in inputs if item.editorial_scope != "composite"]
    for first, second in combinations(singles, 2):
        if frames_conflict(
            first.editorial_frame, second.editorial_frame, independent_updates_only=True
        ):
            raise ValueError("independent_updates")
    by_version = {item.content_version_id: item for item in singles}
    occurrence_groups = (
        [
            group.member_version_ids
            for group in decision.facts
            if group.relation in {"root", "same_occurrence"}
        ]
        if decision.facts
        else [list(by_version)]
    )
    for versions in occurrence_groups:
        frames = [
            by_version[identity].editorial_frame for identity in versions if identity in by_version
        ]
        if any(frames_conflict(a, b) for a, b in combinations(frames, 2)):
            raise ValueError("conflicting_occurrence")
    composites = [item for item in inputs if item.editorial_scope == "composite"]
    if not composites:
        return decision
    if root_fact_id is None:
        raise ValueError("composite_without_fact")
    composite_ids = {item.content_version_id for item in composites}
    groups = []
    for group in decision.facts:
        remaining = [
            identity for identity in group.member_version_ids if identity not in composite_ids
        ]
        if remaining:
            groups.append(group.model_copy(update={"member_version_ids": remaining}))
    if not decision.facts and singles:
        groups.append(
            EventFactDecision(
                member_version_ids=list(by_version),
                title=decision.title or "已有事实",
                summary=decision.summary or "已有事实",
                relation="same_occurrence",
                existing_fact_id=root_fact_id,
            )
        )
    groups.append(
        EventFactDecision(
            member_version_ids=sorted(composite_ids, key=str),
            title="综合资料提及",
            summary="综合资料仅挂靠已有事实,不提供发生身份。",
            relation="same_occurrence",
            existing_fact_id=root_fact_id,
        )
    )
    return EventDecision(**{**decision.model_dump(), "facts": groups})


class RelationReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=200)
    first_party: bool = False
    published_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=4000)
    frame: dict[str, str | None] | None = None

    @field_validator("published_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("report time must be aware")
        return value

    @field_validator("frame")
    @classmethod
    def bounded_frame(cls, value: dict[str, str | None] | None) -> dict[str, str | None] | None:
        if value is not None and (
            set(value) - {"subject", "action", "object", "occurredAt"}
            or any(item is not None and len(item) > 500 for item in value.values())
        ):
            raise ValueError("invalid report frame")
        return value


class RelationPairOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    a: str = Field(max_length=400)
    b: str = Field(max_length=400)
    relation: VerdictRelation
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    difference: str = Field(max_length=400)


def relation_pair_request(
    first: RelationReportInput, second: RelationReportInput
) -> tuple[str, str, str]:
    """Shared production and benchmark prompt; supplied evidence is never template code."""
    prompt = (
        json.dumps(
            {"A": first.model_dump(mode="json"), "B": second.model_dump(mode="json")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return editorial_prompt_version("group-pair"), render_editorial_prompt("group-pair"), prompt


def normalize_verdicts(
    candidates: Sequence[FactRelationCandidate], raw_decisions: Sequence[object]
) -> tuple[FactVerdict, ...]:
    """Preserve malformed/missing model evidence, rather than manufacturing unrelated."""
    decisions: dict[int, object] = {}
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            continue
        identity = raw.get("id")
        if not isinstance(identity, str):
            continue
        try:
            number = int(identity.strip().removeprefix("C").removeprefix("c")) - 1
        except ValueError:
            continue
        if 0 <= number < len(candidates) and number not in decisions:
            decisions[number] = raw
    result = []
    for number, candidate in enumerate(candidates):
        raw = decisions.get(number)
        if not isinstance(raw, dict):
            result.append(FactVerdict(candidate.fact_id, None, None, "", "missing"))
            continue
        relation, confidence, note = raw.get("relation"), raw.get("confidence"), raw.get("note", "")
        valid = (
            isinstance(relation, str)
            and relation in _RELATIONS
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and math.isfinite(confidence)
            and 0 <= confidence <= 1
            and isinstance(note, str)
            and len(note) <= 400
        )
        result.append(
            FactVerdict(
                candidate.fact_id,
                cast(VerdictRelation, relation) if valid else None,
                float(cast(int | float, confidence)) if valid else None,
                note if isinstance(note, str) else "",
                "valid" if valid else "invalid",
            )
        )
    return tuple(result)


def choose_relation(
    candidates: Sequence[FactRelationCandidate],
    verdicts: Sequence[FactVerdict],
    *,
    signal_only: bool = False,
    query_scope: Literal["single", "composite", "unknown"] | None = None,
) -> FactRelationChoice:
    if query_scope == "unknown":
        return FactRelationChoice("unreviewed")
    by_fact: dict[UUID, FactVerdict] = {verdict.fact_id: verdict for verdict in verdicts}
    if query_scope == "composite":
        mentions = [
            candidate
            for candidate in candidates
            if candidate.fact_id in by_fact
            and by_fact[candidate.fact_id].state == "valid"
            and by_fact[candidate.fact_id].relation in {"SAME_OCCURRENCE", "SAME_STORY", "ROUNDUP"}
            and (by_fact[candidate.fact_id].confidence or 0) >= 0.8
        ]
        mentions.sort(key=lambda candidate: (-candidate.recall_score, candidate.fact_id.hex))
        if not mentions:
            return FactRelationChoice("unreviewed")
        return FactRelationChoice("mention", mentions[0].fact_id, mentions[0].event_id)
    same = [
        candidate
        for candidate in candidates
        if candidate.fact_id in by_fact
        and by_fact[candidate.fact_id].relation == "SAME_OCCURRENCE"
        and (not signal_only or (by_fact[candidate.fact_id].confidence or 0) >= 0.8)
    ]
    same.sort(
        key=lambda candidate: (
            -(by_fact[candidate.fact_id].confidence or 0),
            -candidate.recall_score,
            candidate.fact_id.hex,
        )
    )
    if same:
        target = same[0]
        return FactRelationChoice(
            "signal" if signal_only else "same_occurrence", target.fact_id, target.event_id
        )
    developments = [
        candidate
        for candidate in candidates
        if candidate.fact_id in by_fact
        and by_fact[candidate.fact_id].relation == "SAME_STORY"
        and (signal_only or candidate.story_root)
        and (not signal_only or (by_fact[candidate.fact_id].confidence or 0) >= 0.8)
    ]
    developments.sort(key=lambda candidate: (-candidate.recall_score, candidate.fact_id.hex))
    if developments:
        target = developments[0]
        return FactRelationChoice(
            "signal" if signal_only else "development", target.fact_id, target.event_id
        )
    if signal_only:
        return FactRelationChoice("signal_unmatched")
    if candidates and all(
        candidate.fact_id in by_fact and by_fact[candidate.fact_id].relation == "ROUNDUP"
        for candidate in candidates
    ):
        return FactRelationChoice("roundup")
    if any(
        candidate.fact_id not in by_fact or by_fact[candidate.fact_id].state != "valid"
        for candidate in candidates
    ):
        return FactRelationChoice("unreviewed")
    return FactRelationChoice("new_story")
