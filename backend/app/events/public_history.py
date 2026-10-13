"""Read fixed heat calculations without recomputing history or widening public inputs."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from content.version_inputs import observations_readable_in_transaction
from events.heat_models import EventAttentionSnapshot
from events.heat_schemas import ATTENTION_FORMULA_VERSION, AttentionSourceView, EventAttentionView
from events.public_history_schemas import (
    HistoryReason,
    HistoryState,
    PublicHeatHistory,
    PublicHeatPoint,
    PublicHeatReference,
    PublicHeatTrend,
)


@dataclass(frozen=True, slots=True)
class HeatRecord:
    """Fixed storage row for deterministic validation outside the SQL reader."""

    window_end: datetime
    computed_at: datetime
    fingerprint: bytes
    manifest: dict[str, object]
    result: dict[str, object]
    complete: bool


class _Input(BaseModel):
    content_id: UUID
    version_id: UUID
    observation_id: UUID
    representative_comment_observation_id: UUID | None = None
    source_id: UUID
    source_revision: int = Field(ge=1)
    source_time: datetime
    source: AttentionSourceView


class _Manifest(BaseModel):
    input_basis: Literal["observations_v1"]
    event_id: UUID
    event_revision: int = Field(ge=1)
    formula_version: str
    measurement_kind: Literal["recorded", "recomputed"]
    observation_ids: list[UUID] = Field(min_length=1, max_length=20000)
    inputs: list[_Input] = Field(min_length=1, max_length=2000)


def _state(reason: HistoryReason) -> HistoryState:
    return (
        "unavailable"
        if reason in {"invalid", "not_public", "provenance_unknown", "capacity"}
        else "insufficient_data"
    )


def _point(
    record: HeatRecord,
    *,
    event_id: UUID,
    revision: int,
    now: datetime,
    references: frozenset[PublicHeatReference],
) -> PublicHeatPoint:
    point = PublicHeatPoint(window_end=record.window_end)
    if record.manifest.get("measurement_kind") is None:
        return point.model_copy(update={"reason": "provenance_unknown"})
    try:
        manifest = _Manifest.model_validate_json(json.dumps(record.manifest), strict=True)
        result = EventAttentionView.model_validate_json(json.dumps(record.result), strict=True)
        if (
            record.window_end.utcoffset() is None
            or record.computed_at.utcoffset() is None
            or record.window_end > record.computed_at
            or record.computed_at > now
            or manifest.event_id != event_id
            or result.event_id != event_id
            or manifest.event_revision != revision
            or result.event_revision != revision
            or manifest.formula_version != ATTENTION_FORMULA_VERSION
            or result.formula_version != ATTENTION_FORMULA_VERSION
            or result.window_end != record.window_end
            or result.complete != record.complete
            or not math.isfinite(result.heat)
            or result.heat < 0
            or any(
                count < 0
                for count in (
                    result.participant_count,
                    result.editorial_participant_count,
                    result.signal_participant_count,
                    result.comparable_participant_count,
                    result.uncomparable_participant_count,
                )
            )
            or hashlib.sha256(
                json.dumps(record.manifest, sort_keys=True, separators=(",", ":")).encode()
            ).digest()
            != record.fingerprint
        ):
            raise ValueError("invalid fixed heat record")
        allowed = {reference.observation_id for reference in references}
        if not set(manifest.observation_ids) <= allowed:
            return point.model_copy(update={"reason": "not_public"})
        cohort = set()
        for item in manifest.inputs:
            source = item.source
            if (
                item.source_id != source.id
                or item.source_revision != source.revision
                or item.source_time.utcoffset() is None
                or item.source_time > record.computed_at
                or any(
                    value.utcoffset() is None or value > record.computed_at
                    for value in (
                        source.created_at,
                        source.updated_at,
                        *(
                            [source.last_successful_fetch_at]
                            if source.last_successful_fetch_at
                            else []
                        ),
                    )
                )
            ):
                raise ValueError("invalid source provenance")
            if (
                PublicHeatReference(item.content_id, item.version_id, item.observation_id)
                not in references
                or item.observation_id not in manifest.observation_ids
                or item.representative_comment_observation_id is not None
            ):
                return point.model_copy(update={"reason": "not_public"})
            cohort.add(
                (
                    str(source.id),
                    source.revision,
                    source.mode,
                    source.group_key,
                    source.owner_entity_key,
                )
            )
        point.computed_at = record.computed_at
        if manifest.measurement_kind == "recomputed":
            point.reason = "recomputed"
        elif record.computed_at - record.window_end >= timedelta(hours=1):
            point.reason = "invalid"
        elif not result.complete or not result.eligible:
            point.reason = "incomplete"
        else:
            point.value = result.heat
            point.participant_count = result.participant_count
            point.segment_key = hashlib.sha256(
                json.dumps(
                    [ATTENTION_FORMULA_VERSION, revision, sorted(cohort)], separators=(",", ":")
                ).encode()
            ).hexdigest()
        return point
    except (ValidationError, ValueError, TypeError, OverflowError):
        return point.model_copy(update={"reason": "invalid"})


def history_from_records(
    records: dict[datetime, HeatRecord],
    *,
    event_id: UUID,
    revision: int,
    now: datetime,
    references: frozenset[PublicHeatReference],
    capacity: bool = False,
) -> PublicHeatHistory:
    """Validate 48 UTC hourly slots and require an unbroken six-hour baseline."""
    if now.utcoffset() is None:
        raise ValueError("history requires an aware snapshot")
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    points = []
    for index in range(47, -1, -1):
        at = end - timedelta(hours=index)
        record = records.get(at)
        points.append(
            PublicHeatPoint(window_end=at, reason="capacity" if capacity else "missing")
            if capacity or record is None
            else _point(
                record, event_id=event_id, revision=revision, now=now, references=references
            )
        )
    connected = any(
        a.value is not None and b.value is not None and a.segment_key == b.segment_key
        for a, b in pairwise(points)
    )
    unavailable = next(
        (
            point.reason
            for point in reversed(points)
            if point.reason and _state(point.reason) == "unavailable"
        ),
        None,
    )
    changed = any(
        a.value is not None and b.value is not None and a.segment_key != b.segment_key
        for a, b in pairwise(points)
    )
    reason = (
        None
        if connected
        else unavailable
        or ("source_changed" if changed else None)
        or next((point.reason for point in reversed(points) if point.reason), "missing")
    )
    recent = points[-7:]
    trend_reason = next((point.reason for point in reversed(recent) if point.reason), None)
    if trend_reason is None and len({point.segment_key for point in recent}) != 1:
        trend_reason = "source_changed"
    baseline = recent[0].value
    latest = recent[-1].value
    if trend_reason is None and (baseline is None or baseline <= 0):
        trend_reason = "zero_baseline"
    if trend_reason:
        trend = PublicHeatTrend(state=_state(trend_reason), reason=trend_reason)
    elif baseline is not None and latest is not None:
        percent = (latest - baseline) / baseline * 100
        trend = (
            PublicHeatTrend(
                state="available",
                direction="up" if percent > 0 else "down" if percent < 0 else "flat",
                percent=percent,
            )
            if math.isfinite(percent)
            else PublicHeatTrend(state="unavailable", reason="invalid")
        )
    else:
        trend = PublicHeatTrend(state="insufficient_data", reason="missing")
    return PublicHeatHistory(
        state="available" if connected else _state(reason or "missing"),
        reason=reason,
        event_revision=revision,
        snapshot_at=now,
        points=points,
        trend=trend,
    )


def read_public_history_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    event_id: UUID,
    revision: int,
    now: datetime,
    references: frozenset[PublicHeatReference],
) -> PublicHeatHistory:
    """Read newest rows first, then validate; never fall back after a bad latest row."""
    if not session.in_transaction():
        raise RuntimeError("public history requires caller transaction")
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    rows = list(
        session.scalars(
            select(EventAttentionSnapshot)
            .where(
                EventAttentionSnapshot.owner_id == owner_id,
                EventAttentionSnapshot.event_id == event_id,
                EventAttentionSnapshot.event_revision == revision,
                EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
                EventAttentionSnapshot.window_end >= end - timedelta(hours=47),
                EventAttentionSnapshot.window_end <= end,
            )
            .order_by(EventAttentionSnapshot.computed_at.desc(), EventAttentionSnapshot.id.desc())
            .limit(2001)
        )
    )
    records = {}
    for row in rows:
        if row.window_end not in records:
            records[row.window_end] = HeatRecord(
                row.window_end,
                row.computed_at,
                row.input_fingerprint,
                row.input_manifest,
                row.result,
                row.complete,
            )
    readable = not references or observations_readable_in_transaction(
        session,
        owner_id=owner_id,
        observation_ids=tuple(ref.observation_id for ref in references),
        now=now,
    )
    view = history_from_records(
        records,
        event_id=event_id,
        revision=revision,
        now=now,
        references=references if readable else frozenset(),
        capacity=len(rows) > 2000,
    )
    return view
