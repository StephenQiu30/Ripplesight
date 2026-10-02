"""Parsed source contract and deterministic representative selection (no IO)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from math import isfinite
from typing import Any

from leaderboard.configuration import REASONS, Configuration, cloaked_model, model_slug


@dataclass(frozen=True, slots=True)
class ParsedRow:
    source_model_name: str
    base_name: str
    configuration: Configuration
    metric_key: str
    metric_name: str
    raw_score: float
    key_name: str | None = None
    configuration_key: str | None = None
    alt_names: tuple[str, ...] = ()
    organization: str | None = None
    released_at: datetime | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    source_rank: int | None = None
    sample_size: int | None = None
    source_published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not self.source_model_name.strip()
            or not self.base_name.strip()
            or not self.metric_key.strip()
        ):
            raise ValueError("Source rows require a name, base model and metric")
        if not isfinite(self.raw_score):
            raise ValueError("Source score must be finite")
        if any(
            bound is not None and not isfinite(bound)
            for bound in (self.lower_bound, self.upper_bound)
        ):
            raise ValueError("Published error bounds must be finite")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("Published error bounds must be ordered")
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("Sample size cannot be negative")


@dataclass(frozen=True, slots=True)
class FetchResult:
    source_key: str
    source_name: str
    source_url: str
    license: str
    attribution_url: str
    published_at: datetime | None
    rows: tuple[ParsedRow, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedRow:
    row: ParsedRow
    model_id: str
    selected: bool
    selection_reason: str


def stored_configuration_key(row: ParsedRow) -> str:
    return (
        row.configuration_key or f"{row.configuration.key}@{row.key_name or row.source_model_name}"
    )


def prepare_rows(rows: Sequence[ParsedRow]) -> tuple[ParsedRow, ...]:
    seen: set[tuple[str, str]] = set()
    deduplicated: list[ParsedRow] = []
    for row in rows:
        key = (stored_configuration_key(row), row.metric_key)
        if key not in seen:
            seen.add(key)
            deduplicated.append(row)
    ranked: dict[str, list[ParsedRow]] = {}
    for row in deduplicated:
        ranked.setdefault(row.metric_key, []).append(row)
    needs_rank = {
        key for key, group in ranked.items() if all(row.source_rank is None for row in group)
    }
    return tuple(
        replace(
            row,
            source_rank=1
            + sum(other.raw_score > row.raw_score for other in ranked[row.metric_key]),
        )
        if row.metric_key in needs_rank
        else row
        for row in deduplicated
    )


def select_representatives(
    rows: Sequence[ParsedRow],
    model_ids: Sequence[str],
    model_slugs: dict[str, str] | None = None,
) -> tuple[ResolvedRow, ...]:
    if len(rows) != len(model_ids):
        raise ValueError("Every parsed row needs exactly one resolved model")
    slugs = model_slugs or {}
    groups: dict[tuple[str, str], list[tuple[ParsedRow, str]]] = {}
    for row, model_id in zip(rows, model_ids, strict=True):
        groups.setdefault((model_id, row.metric_key), []).append((row, model_id))
    output: list[ResolvedRow] = []
    for group in groups.values():
        eligible = [
            (row, mid)
            for row, mid in group
            if not row.configuration.ineligible
            and not cloaked_model(row.source_model_name, slugs.get(mid))
        ]

        def priority(item: tuple[ParsedRow, str]) -> tuple[int, int, int, int, int, str]:
            row, model_id = item
            slug_shaped = all(
                c.isascii() and (c.islower() or c.isdigit() or c == "-")
                for c in row.source_model_name
            )
            return (
                -row.configuration.rank,
                -int(row.configuration.kind == "FIRST_PARTY"),
                -int(slug_shaped),
                -int(model_slug(row.source_model_name) == slugs.get(model_id)),
                len(row.source_model_name),
                row.source_model_name,
            )

        best = min(eligible, key=priority)[0] if eligible else None
        for row, model_id in group:
            selected = row is best
            if row.configuration.ineligible:
                reason = row.configuration.ineligible
            elif cloaked_model(row.source_model_name, slugs.get(model_id)):
                reason = REASONS["cloaked"]
            elif row.configuration.kind == "SCAFFOLDED":
                reason = REASONS["scaffolded_selected" if selected else "scaffolded_lower"]
            elif selected:
                reason = REASONS[
                    "first_party" if row.configuration.kind == "FIRST_PARTY" else "source_default"
                ]
            else:
                reason = REASONS["lower_priority"]
            output.append(ResolvedRow(row, model_id, selected, reason))
    return tuple(output)
