"""M3 exact comparable heat snapshots, with every historical input rechecked."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.alert_reading import freeze_alert_content_inputs_in_transaction
from content.report_reading import report_inputs_readable_in_transaction
from content.version_inputs import observations_readable_in_transaction
from events.heat_models import EventAttentionSnapshot, EventAttentionSource
from events.heat_schemas import ATTENTION_FORMULA_VERSION
from events.models import Event


@dataclass(frozen=True)
class HeatAlertFacts:
    value: float | None
    reason: str | None
    manifest: dict[str, object]


def event_alert_candidate_in_transaction(
    session: Session, *, owner_id: UUID, topic_id: UUID, event_id: UUID
) -> bool:
    if not session.in_transaction():
        raise RuntimeError("event identity read requires caller transaction")
    return (
        session.scalar(
            select(Event.id).where(
                Event.owner_id == owner_id,
                Event.topic_id == topic_id,
                Event.id == event_id,
                Event.status == "active",
            )
        )
        is not None
    )


def _readable(
    session: Session, *, owner_id: UUID, snapshot: EventAttentionSnapshot, now: datetime
) -> bool:
    raw = snapshot.input_manifest.get("inputs")
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) > 1000
        or not snapshot.complete
        or snapshot.result.get("eligible") is not True
    ):
        return False
    versions = []
    try:
        for item in raw:
            if not isinstance(item, dict):
                return False
            source = session.scalar(
                select(EventAttentionSource).where(
                    EventAttentionSource.owner_id == owner_id,
                    EventAttentionSource.id == UUID(str(item["source_id"])),
                )
            )
            if (
                source is None
                or not source.enabled
                or source.mode == "isolated"
                or source.revision != item["source_revision"]
            ):
                return False
            versions.append(UUID(str(item["version_id"])))
            if item.get("representative_comment_id"):
                # Old heat manifests freeze only comment identity, not its version.
                # Such a sample cannot prove an immutable ALL alert input.
                return False
        original_inputs = freeze_alert_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            version_ids=tuple(set(versions)),
            as_of=snapshot.window_end,
            now=now,
        )
        if set(original_inputs) != set(versions):
            return False
        return report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=tuple(versions),
            observation_ids=(),
            now=now,
        )
    except (KeyError, ValueError, TypeError):
        return False


def load_heat_alert_facts_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    event_id: UUID,
    end: datetime,
    now: datetime,
) -> HeatAlertFacts:
    event = session.scalar(
        select(Event).where(
            Event.owner_id == owner_id,
            Event.topic_id == topic_id,
            Event.id == event_id,
            Event.status == "active",
        )
    )
    if event is None:
        return HeatAlertFacts(None, "alert_event_unavailable", {})
    current = session.scalar(
        select(EventAttentionSnapshot)
        .where(
            EventAttentionSnapshot.owner_id == owner_id,
            EventAttentionSnapshot.event_id == event_id,
            EventAttentionSnapshot.event_revision == event.revision,
            EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
            EventAttentionSnapshot.window_end <= end,
            EventAttentionSnapshot.window_end >= end - timedelta(minutes=5),
            EventAttentionSnapshot.computed_at <= now,
        )
        .order_by(
            EventAttentionSnapshot.window_end.desc(), EventAttentionSnapshot.computed_at.desc()
        )
        .limit(1)
    )
    if current is None:
        return HeatAlertFacts(None, "alert_heat_missing", {})
    baseline = session.scalar(
        select(EventAttentionSnapshot)
        .where(
            EventAttentionSnapshot.owner_id == owner_id,
            EventAttentionSnapshot.event_id == event_id,
            EventAttentionSnapshot.event_revision == event.revision,
            EventAttentionSnapshot.formula_version == current.formula_version,
            EventAttentionSnapshot.window_end == current.window_end - timedelta(hours=1),
            EventAttentionSnapshot.computed_at <= now,
        )
        .order_by(EventAttentionSnapshot.computed_at.desc())
        .limit(1)
    )
    if baseline is None:
        return HeatAlertFacts(None, "alert_heat_baseline_missing", {})

    def participants(row: EventAttentionSnapshot) -> set[str]:
        roster = row.result.get("roster")
        if not isinstance(roster, list) or not roster:
            return set()
        values = [item.get("participant_key") for item in roster if isinstance(item, dict)]
        if len(values) != len(roster) or any(not isinstance(key, str) or not key for key in values):
            return set()
        return {cast(str, key) for key in values}

    if (
        not participants(current)
        or participants(current) != participants(baseline)
        or not _readable(session, owner_id=owner_id, snapshot=current, now=now)
        or not _readable(session, owner_id=owner_id, snapshot=baseline, now=now)
    ):
        return HeatAlertFacts(None, "alert_heat_not_comparable", {})
    current_value, baseline_value = current.result.get("heat"), baseline.result.get("heat")
    if (
        not isinstance(current_value, (float, int))
        or not isinstance(baseline_value, (float, int))
        or not isfinite(current_value)
        or not isfinite(baseline_value)
    ):
        return HeatAlertFacts(None, "alert_heat_invalid", {})
    version_ids = tuple(
        {
            UUID(str(item["version_id"]))
            for row in (baseline, current)
            for item in cast(list[dict[str, object]], row.input_manifest["inputs"])
        }
    )
    originals = freeze_alert_content_inputs_in_transaction(
        session, owner_id=owner_id, version_ids=version_ids, as_of=end, now=now
    )
    if set(originals) != set(version_ids):
        return HeatAlertFacts(None, "alert_input_unavailable", {})
    observation_ids = tuple({obs for item in originals.values() for obs in item.observation_ids})
    manifest: dict[str, object] = {
        "metric": "heat_increment",
        "event_id": str(event_id),
        "event_revision": event.revision,
        "topic_id": str(topic_id),
        "formula_version": current.formula_version,
        "snapshot_ids": [str(baseline.id), str(current.id)],
        "snapshot_hashes": [baseline.input_fingerprint.hex(), current.input_fingerprint.hex()],
        "content_version_ids": [str(i) for i in sorted(version_ids, key=str)],
        "observation_ids": [str(i) for i in sorted(observation_ids, key=str)],
    }
    return HeatAlertFacts(float(current_value - baseline_value), None, manifest)


def heat_alert_inputs_readable_in_transaction(
    session: Session, *, owner_id: UUID, manifest: dict[str, object], now: datetime
) -> bool:
    try:
        event = session.scalar(
            select(Event).where(
                Event.owner_id == owner_id,
                Event.id == UUID(str(manifest["event_id"])),
                Event.status == "active",
            )
        )
        ids = manifest["snapshot_ids"]
        hashes = manifest["snapshot_hashes"]
        if (
            event is None
            or event.revision != manifest["event_revision"]
            or not isinstance(ids, list)
            or len(ids) != 2
            or not isinstance(hashes, list)
            or len(hashes) != 2
        ):
            return False
        for identity, expected_hash in zip(ids, hashes, strict=True):
            row = session.scalar(
                select(EventAttentionSnapshot).where(
                    EventAttentionSnapshot.owner_id == owner_id,
                    EventAttentionSnapshot.id == UUID(str(identity)),
                )
            )
            if (
                row is None
                or row.event_id != event.id
                or row.formula_version != manifest["formula_version"]
                or row.input_fingerprint.hex() != expected_hash
                or not _readable(session, owner_id=owner_id, snapshot=row, now=now)
            ):
                return False
        raw_observations, raw_versions = (
            manifest["observation_ids"],
            manifest["content_version_ids"],
        )
        if not isinstance(raw_observations, list) or not isinstance(raw_versions, list):
            return False
        observations = tuple(UUID(str(i)) for i in raw_observations)
        versions = tuple(UUID(str(i)) for i in raw_versions)
        return observations_readable_in_transaction(
            session, owner_id=owner_id, observation_ids=observations, now=now
        ) and report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=versions,
            observation_ids=observations,
            now=now,
        )
    except (KeyError, ValueError, TypeError):
        return False
