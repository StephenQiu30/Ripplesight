"""Construct reproducible v15 inputs from immutable stored evidence, without IO."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from leaderboard.configuration import cloaked_model
from leaderboard.method.constants import (
    ANCHORS,
    BOARD_KEYS,
    CARRY_FORWARD_DAYS,
    CATEGORY_MIN_MODELS,
    CONFIGURATION_POLICY,
    OVERALL_POLICY,
    RELEASE_WINDOW_MONTHS,
    SCORING_SOURCES,
    category_policy,
)
from leaderboard.method.types import (
    BoardInput,
    CategoryAvailability,
    EvidenceMeta,
    Policy,
    QualificationScenario,
    RegistryEntry,
    RunInputs,
    ScoreRow,
    ScoringSource,
    Signal,
    SignalRow,
    Snapshot,
    SourceUse,
)


def _js_string(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def protocol_of(source_key: str, metadata: dict[str, object]) -> str:
    if "intelligenceIndexVersion" in metadata:
        tag = "intelligenceIndexVersion=" + _js_string(metadata["intelligenceIndexVersion"])
    elif "editionId" in metadata:
        tag = "editionId=" + _js_string(metadata["editionId"])
        if "datasetVersion" in metadata:
            tag += ";datasetVersion=" + _js_string(metadata["datasetVersion"])
    elif "release" in metadata and source_key.startswith("livebench"):
        tag = "release=" + _js_string(metadata["release"])
    elif "benchmarkVersion" in metadata:
        tag = "benchmarkVersion=" + _js_string(metadata["benchmarkVersion"])
    else:
        tag = "published-schema"
    return f"{source_key}:registered-v13:{tag}"


def _date(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    return None


def _iso(value: object) -> str | None:
    parsed = _date(value)
    return (
        parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if parsed
        else None
    )


def release_cutoff(at: datetime) -> datetime:
    """Match JS setUTCMonth overflow (31st can roll into the following month)."""
    utc = at.astimezone(UTC)
    ordinal = utc.year * 12 + utc.month - 1 - RELEASE_WINDOW_MONTHS
    year, month_zero = divmod(ordinal, 12)
    return utc.replace(year=year, month=month_zero + 1, day=1) + timedelta(days=utc.day - 1)


def qualify_models(
    units: Sequence[str],
    registry: dict[str, RegistryEntry],
    unit_rows: dict[str, dict[str, SignalRow]],
    policy: Policy,
    released: dict[str, datetime | None],
    cutoff: datetime,
    *,
    sources: Sequence[ScoringSource] = SCORING_SOURCES,
    anchors: Sequence[str] = ANCHORS,
) -> tuple[str, ...]:
    active = tuple(u for u in units if u in registry and registry[u].weight > 0)
    budgets = {source.unit: source.budget for source in sources}
    candidates = {slug for unit in active for slug in unit_rows.get(unit, {})}
    out: list[str] = []
    for slug in sorted(candidates):
        release = released.get(slug)
        if release and release < cutoff:
            continue
        present = tuple(unit for unit in active if slug in unit_rows.get(unit, {}))
        if len(present) < policy.sources:
            continue
        if len({registry[unit].family for unit in present}) < policy.families:
            continue
        if len({registry[unit].operator for unit in present}) < policy.operators:
            continue
        specialised = {
            budgets[unit]
            for unit in present
            if unit in budgets and budgets[unit] not in ("broad", "preference")
        }
        if len(specialised) < policy.categories:
            continue
        direct = sum(
            anchor != slug and any(anchor in unit_rows.get(unit, {}) for unit in present)
            for anchor in anchors
        )
        if direct < policy.direct_anchors:
            continue
        out.append(slug)
    return tuple(out)


def build_run_inputs(
    snapshots: Sequence[Snapshot],
    scores: Sequence[ScoreRow],
    *,
    at: datetime,
    snapshot_ids: Sequence[str] | None = None,
    sources: Sequence[ScoringSource] = SCORING_SOURCES,
    anchors: Sequence[str] = ANCHORS,
    overall_policy: Policy = OVERALL_POLICY,
) -> RunInputs:
    if at.tzinfo is None:
        raise ValueError("Run time must be timezone aware")
    keys = {source.key for source in sources}
    by_source: dict[str, Snapshot] = {}
    if snapshot_ids is not None:
        requested = set(snapshot_ids)
        chosen = tuple(s for s in snapshots if s.id in requested)
        if {s.id for s in chosen} != requested:
            raise ValueError("A requested reproduction snapshot is missing")
        if len({s.source_key for s in chosen}) != len(chosen):
            raise ValueError("Reproduction accepts one selected snapshot per source")
        by_source = {s.source_key: s for s in chosen}
        history = chosen
    else:
        for snapshot in sorted(snapshots, key=lambda s: (s.fetched_at, s.id), reverse=True):
            if snapshot.source_key in keys and snapshot.fetched_at <= at:
                by_source.setdefault(snapshot.source_key, snapshot)
        chosen = tuple(by_source[key] for key in sorted(by_source))
        older = tuple(
            s
            for s in sorted(snapshots, key=lambda s: (s.fetched_at, s.id), reverse=True)
            if s.source_key in by_source
            and s.fetched_at < by_source[s.source_key].fetched_at
            and (_date(s.metadata.get("lastSeenAt")) or s.fetched_at)
            >= at - timedelta(days=CARRY_FORWARD_DAYS)
            and protocol_of(s.source_key, s.metadata)
            == protocol_of(s.source_key, by_source[s.source_key].metadata)
        )
        history = (*chosen, *older)
    rows_by_snapshot: dict[str, list[ScoreRow]] = {}
    for row in sorted(scores, key=lambda r: not r.selected_for_product):
        rows_by_snapshot.setdefault(row.snapshot_id, []).append(row)
    source_of = {s.unit: s for s in sources}
    unit_rows: dict[str, dict[str, SignalRow]] = {}
    names: dict[str, str] = {}
    released: dict[str, datetime | None] = {}
    evidence: dict[str, EvidenceMeta] = {}
    present: set[tuple[str, str, str]] = set()
    for snapshot in history:
        for row in rows_by_snapshot.get(snapshot.id, ()):
            key = (snapshot.source_key, row.metric_key, row.slug)
            if key in present:
                continue
            present.add(key)  # Explicit exclusion consumes history too: never revive an old score.
            source = source_of.get(row.metric_key)
            if (
                source is None
                or source.key != snapshot.source_key
                or not row.selected_for_product
                or row.raw_score is None
                or cloaked_model(row.slug, row.name)
            ):
                continue
            unit_rows.setdefault(row.metric_key, {})[row.slug] = SignalRow(
                row.raw_score,
                row.slug,
                row.configuration_key,
                row.lower_bound,
                row.upper_bound,
            )
            names[row.slug], released[row.slug] = row.name, row.released_at
            evidence[f"{row.metric_key}:{row.slug}"] = EvidenceMeta(
                row.metric_key,
                source.operator,
                protocol_of(snapshot.source_key, snapshot.metadata),
                snapshot.id,
                _iso(snapshot.metadata.get("lastSeenAt")) or _iso(snapshot.fetched_at),
                _iso(row.metadata.get("measuredAt")),
                _iso(snapshot.published_at),
                row.configuration_key,
                snapshot.id != by_source[snapshot.source_key].id,
                CONFIGURATION_POLICY,
            )
    boards: list[BoardInput] = []
    categories: list[CategoryAvailability] = []

    def with_data(source: ScoringSource) -> bool:
        return source.scoring and bool(unit_rows.get(source.unit))

    for board in BOARD_KEYS:
        members = (
            tuple(sources)
            if board == "overall"
            else tuple(s for s in sources if s.category == board)
        )
        budget = sum(source.weight for source in members)
        active = tuple(source for source in members if with_data(source))
        if not active:
            continue
        registry = {
            source.unit: RegistryEntry(
                source.family,
                source.weight if board == "overall" else source.weight / budget,
                source.operator,
                protocol_of(source.key, by_source[source.key].metadata),
                source.direction,
                source.interval_sd,
            )
            for source in active
        }
        units = tuple(source.unit for source in active)
        policy = (
            overall_policy
            if board == "overall"
            else category_policy(len(units), len({s.operator for s in active}))
        )

        def qualify(
            use_units: Sequence[str],
            use_registry: dict[str, RegistryEntry] = registry,
            use_policy: Policy = policy,
        ) -> tuple[str, ...]:
            return qualify_models(
                use_units,
                use_registry,
                unit_rows,
                use_policy,
                released,
                release_cutoff(at),
                sources=sources,
                anchors=anchors,
            )

        models = qualify(units)
        scenarios: dict[str, QualificationScenario] = {}
        for operator in dict.fromkeys(source.operator for source in active):
            remaining = tuple(unit for unit in units if registry[unit].operator != operator)
            qualified = qualify(remaining)
            scenarios[f"operator:{operator}"] = QualificationScenario(
                remaining if qualified else (), qualified
            )
        for unit in units:
            remaining = tuple(other for other in units if other != unit)
            qualified = qualify(remaining)
            scenarios[f"unit:{unit}"] = QualificationScenario(
                remaining if qualified else (), qualified
            )
        signals = tuple(
            Signal(
                unit,
                tuple(unit_rows[unit][slug] for slug in sorted(unit_rows[unit]) if slug in models),
            )
            for unit in units
        )
        boards.append(
            BoardInput(
                board,
                {slug: names.get(slug, slug) for slug in models},
                models,
                policy,
                tuple(anchors),
                signals,
                registry,
                scenarios,
            )
        )
        if board != "overall":
            categories.append(
                CategoryAvailability(
                    board,
                    "READY" if len(models) >= CATEGORY_MIN_MODELS else "INSUFFICIENT",
                    len(models),
                    len(units),
                    len(active),
                    tuple(by_source[source.key].id for source in active),
                )
            )
    uses = tuple(
        SourceUse(
            source.key,
            source.weight,
            source.family,
            source.category,
            with_data(source),
            bool(source.category) and with_data(source),
            source.budget,
        )
        for source in sources
    )
    return RunInputs(
        at,
        tuple(snapshot.id for snapshot in chosen),
        tuple(boards),
        evidence,
        uses,
        tuple(categories),
    )
