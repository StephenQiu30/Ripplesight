"""One occurrence, one representative; grounded developments must add information.

Adapted from AIHOT 9acad0c selection step 6 (MIT; THIRD_PARTY_NOTICES.md).
Relations and structure are existing evidence, not new model calls or title similarity.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from analysis.editorial_schemas import EditorialPublicationInputView, FactOutput
from analysis.editorial_structure import normalize_structure
from events.fact_schemas import EventPublicationGrouping


@dataclass(frozen=True, slots=True)
class EditorialSelectionCandidate:
    snapshot: EditorialPublicationInputView
    grouping: EventPublicationGrouping | None
    eligible: bool
    grouping_enabled: bool = True
    grouping_in_scope: bool = True


@dataclass(frozen=True, slots=True)
class EditorialSelectionGate:
    state: Literal["selected", "duplicate", "redundant", "requires_review", "ineligible"]
    reason: str
    representative_id: UUID | None = None

    @property
    def selected(self) -> bool:
        return self.state == "selected"


def representative_order(
    *, first_party: bool, body_complete: bool, score: int | None, at: datetime, identity: UUID
) -> tuple[bool, bool, int, datetime, str]:
    return not first_party, not body_complete, -(score or 0), at, str(identity)


def _order(item: EditorialSelectionCandidate) -> tuple[bool, bool, int, datetime, str]:
    snapshot = item.snapshot
    result = snapshot.run.result if snapshot.run else None
    return representative_order(
        first_party=snapshot.source.first_party,
        body_complete=snapshot.material.body_complete and not snapshot.material.body_pending,
        score=result.score if result else None,
        at=snapshot.timeline_at,
        identity=snapshot.material.content_id,
    )


def _manual(item: EditorialSelectionCandidate) -> bool:
    result = item.snapshot.run.result if item.snapshot.run else None
    return bool(
        result
        and (
            result.manual_overrides.get("selected") is True
            or (result.manual and not result.manual_overrides and result.selected)
            or (item.grouping and item.grouping.assignment_origin == "manual")
        )
    )


def _fact(item: EditorialSelectionCandidate) -> FactOutput | None:
    result = item.snapshot.run.result if item.snapshot.run else None
    structure = result.structure if result else None
    fact = structure.fact if structure else None
    if (
        structure is None
        or structure.scope != "single"
        or fact is None
        or not fact.evidence
        or not all(value and value.strip() for value in (fact.subject, fact.action, fact.object))
    ):
        return None
    # Stored structure is normally normalized at the original stage. Recheck old fixtures
    # and historical results rather than accepting ungrounded stored strings.
    grounded = normalize_structure(structure, item.snapshot.material).fact
    if grounded is None or grounded != fact:
        return None
    return fact


def _normalized(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _fact_identity(fact: FactOutput) -> tuple[str, ...]:
    return tuple(_normalized(getattr(fact, key)) for key in ("subject", "action", "object"))


def _decide_ungrouped(
    candidates: list[EditorialSelectionCandidate],
) -> dict[UUID, EditorialSelectionGate]:
    """Use only exact grounded identities; never infer an event from title similarity."""
    decisions: dict[UUID, EditorialSelectionGate] = {}
    occurrences: dict[tuple[str, ...], list[EditorialSelectionCandidate]] = {}
    for item in candidates:
        identity = item.snapshot.material.content_id
        fact = _fact(item)
        reason = "grouping_disabled" if not item.grouping_enabled else "grouping_out_of_scope"
        if fact is None:
            # Turning off clustering must preserve the original model selection contract.
            decisions[identity] = EditorialSelectionGate("selected", reason, identity)
            continue
        published = item.snapshot.material.published_at
        occurrence = (
            ("occurred", fact.occurred_at)
            if fact.occurred_at
            else ("published", published.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat())
            if published
            else ("material", str(identity))
        )
        occurrences.setdefault((*_fact_identity(fact), *occurrence), []).append(item)
    covered: dict[tuple[str, ...], list[FactOutput]] = {}
    for key, members in sorted(
        occurrences.items(),
        key=lambda pair: (min(item.snapshot.timeline_at for item in pair[1]), pair[0]),
    ):
        representative = min(members, key=_order)
        identity = representative.snapshot.material.content_id
        fact = _fact(representative)
        assert fact is not None
        previous = covered.get(key[:3], [])
        reason = (
            "grouping_disabled" if not representative.grouping_enabled else "grouping_out_of_scope"
        )
        gate = (
            EditorialSelectionGate("redundant", "no_new_information")
            if previous
            and not any(_manual(item) for item in members)
            and not _adds_information(fact, previous)
            else EditorialSelectionGate("selected", reason, identity)
        )
        decisions[identity] = gate
        for item in members:
            other = item.snapshot.material.content_id
            if other != identity:
                decisions[other] = EditorialSelectionGate(
                    "duplicate" if gate.selected else gate.state,
                    "same_occurrence" if gate.selected else gate.reason,
                    identity if gate.selected else None,
                )
        if gate.selected:
            covered.setdefault(key[:3], []).append(fact)
    return decisions


def _numbers(fact: FactOutput) -> set[tuple[Decimal, str]]:
    text = " ".join([fact.evidence or "", *(condition.quote for condition in fact.conditions)])
    text = re.sub(r"\d{4}-\d{2}-\d{2}", "", text)
    values = re.findall(
        r"(?<!\d)([+-]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(%|万|亿|美元|元|倍|gb\b|mb\b|ms\b|毫秒|秒|tokens?\b)?",
        text.casefold(),
    )
    return {(Decimal(number.replace(",", "")), unit) for number, unit in values}


def _adds_information(fact: FactOutput, covered: list[FactOutput]) -> bool:
    # A differently worded evidence quote alone is never incremental information.
    identities = {
        tuple(_normalized(getattr(previous, key)) for key in ("subject", "action", "object"))
        for previous in covered
    }
    if (
        tuple(_normalized(getattr(fact, key)) for key in ("subject", "action", "object"))
        not in identities
    ):
        return True
    if fact.occurred_at and all(previous.occurred_at != fact.occurred_at for previous in covered):
        return True
    numbers = set().union(*(_numbers(previous) for previous in covered))
    if _numbers(fact) - numbers:
        return True
    conditions = {
        _normalized(condition.quote) for previous in covered for condition in previous.conditions
    }
    return any(_normalized(condition.quote) not in conditions for condition in fact.conditions)


def decide_editorial_selection(
    candidates: Iterable[EditorialSelectionCandidate],
) -> dict[UUID, EditorialSelectionGate]:
    """Decide on the full permitted story before source filters, pagination or outlet limits."""
    decisions: dict[UUID, EditorialSelectionGate] = {}
    occurrences: dict[UUID, list[EditorialSelectionCandidate]] = {}
    ungrouped: list[EditorialSelectionCandidate] = []
    for item in candidates:
        identity = item.snapshot.material.content_id
        if not item.eligible:
            decisions[identity] = EditorialSelectionGate("ineligible", "not_a_candidate")
        elif not item.grouping_enabled or not item.grouping_in_scope:
            ungrouped.append(item)
        elif _manual(item) and item.grouping is None:
            decisions[identity] = EditorialSelectionGate("selected", "manual_standalone", identity)
        elif item.grouping is None:
            decisions[identity] = EditorialSelectionGate("requires_review", "grouping_unresolved")
        elif not _manual(item) and _fact(item) is None:
            decisions[identity] = EditorialSelectionGate(
                "requires_review", "fact_evidence_incomplete"
            )
        else:
            occurrences.setdefault(item.grouping.fact_id, []).append(item)
    covered: dict[UUID, list[FactOutput]] = {}
    incomplete_coverage: set[UUID] = set()
    # Process occurrences chronologically; representative authority does not reorder progress.
    for _, members in sorted(
        occurrences.items(),
        key=lambda pair: (
            min(item.snapshot.timeline_at for item in pair[1]),
            str(pair[0]),
        ),
    ):
        representative = min(members, key=_order)
        grouping = representative.grouping
        assert grouping is not None
        identity = representative.snapshot.material.content_id
        fact = _fact(representative)
        previous = covered.get(grouping.event_id, [])
        if any(_manual(item) for item in members):
            gate = EditorialSelectionGate("selected", "manual_confirmed", identity)
        elif grouping.relation == "background":
            gate = EditorialSelectionGate("redundant", "background_only")
        elif grouping.relation not in {"root", "development"}:
            gate = EditorialSelectionGate("requires_review", "relation_unreviewed")
        elif grouping.event_id in incomplete_coverage:
            gate = EditorialSelectionGate("requires_review", "selected_evidence_incomplete")
        elif previous and fact is not None and not _adds_information(fact, previous):
            gate = EditorialSelectionGate("redundant", "no_new_information")
        else:
            gate = EditorialSelectionGate("selected", "new_information", identity)
        decisions[identity] = gate
        for item in members:
            other = item.snapshot.material.content_id
            if other != identity:
                decisions[other] = EditorialSelectionGate(
                    "duplicate" if gate.selected else gate.state,
                    "same_occurrence" if gate.selected else gate.reason,
                    identity if gate.selected else None,
                )
        if gate.selected:
            # Only the selected representative has supplied information in selection.
            # A losing report cannot silently expand what selected readers have received.
            if fact is not None:
                covered.setdefault(grouping.event_id, []).append(fact)
            else:
                incomplete_coverage.add(grouping.event_id)
    return {**decisions, **_decide_ungrouped(ungrouped)}
