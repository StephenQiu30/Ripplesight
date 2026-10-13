"""Fixed history provenance and conservative trend boundaries."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from events.heat_schemas import ATTENTION_FORMULA_VERSION, EventAttentionView
from events.public_history import HeatRecord, PublicHeatReference, history_from_records

NOW = datetime(2026, 10, 13, 12, 30, tzinfo=UTC)
EVENT = uuid4()
REF = PublicHeatReference(uuid4(), uuid4(), uuid4())
SOURCE = uuid4()
END = NOW.replace(minute=0)


def record(at, *, value=10, kind="recorded", revision=1, complete=True):
    manifest = {
        "input_basis": "observations_v1",
        "event_id": str(EVENT),
        "event_revision": 1,
        "formula_version": ATTENTION_FORMULA_VERSION,
        "measurement_kind": kind,
        "observation_ids": [str(REF.observation_id)],
        "inputs": [
            {
                "content_id": str(REF.content_id),
                "version_id": str(REF.version_id),
                "observation_id": str(REF.observation_id),
                "source_id": str(SOURCE),
                "source_revision": revision,
                "source_time": (END - timedelta(days=2)).isoformat(),
                "source": {
                    "id": str(SOURCE),
                    "source_key": "x",
                    "selector_kind": "source",
                    "selector_ref": "x",
                    "name": "private source name",
                    "revision": revision,
                    "mode": "editorial",
                    "group_key": "private group",
                    "owner_entity_key": None,
                    "first_party": False,
                    "tier": "T1",
                    "scheduled": False,
                    "enabled": True,
                    "interval_seconds": 1800,
                    "last_successful_fetch_at": None,
                    "created_at": (END - timedelta(days=3)).isoformat(),
                    "updated_at": (END - timedelta(days=3)).isoformat(),
                },
            }
        ],
    }
    result = EventAttentionView(
        event_id=EVENT,
        event_revision=1,
        window_end=at,
        heat=value,
        eligible=True,
        participant_count=2,
        editorial_participant_count=1,
        signal_participant_count=1,
        comparable_participant_count=2,
        uncomparable_participant_count=0,
        previous_heat=1,
        comparable_heat=value,
        comparable_previous_heat=1,
        trend="up",
        trend_pct=1,
        complete=complete,
        badges=[],
        source_names=[],
        roster=[],
        representative=None,
    ).model_dump(mode="json")
    return HeatRecord(
        at, at + timedelta(minutes=10), fingerprint(manifest), manifest, result, complete
    )


def fingerprint(manifest):
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).digest()


def history(records, **kw):
    return history_from_records(
        records, event_id=EVENT, revision=1, now=NOW, references=frozenset({REF}), **kw
    )


def series():
    return {
        END - timedelta(hours=n): record(END - timedelta(hours=n), value=20 - n) for n in range(7)
    }


@pytest.mark.parametrize(
    ("latest", "direction", "percent"), [(28, "up", 100), (7, "down", -50), (14, "flat", 0)]
)
def test_seven_continuous_records_compare_exactly(latest, direction, percent):
    rows = series()
    rows[END] = record(END, value=latest)
    view = history(rows)
    assert len(view.points) == 48 and view.state == "available"
    assert view.trend.state == "available" and view.trend.direction == direction
    assert view.trend.percent == percent
    assert "private" not in view.model_dump_json()


@pytest.mark.parametrize(
    ("change", "reason", "state"),
    [
        ("missing", "missing", "insufficient_data"),
        ("kind", "recomputed", "insufficient_data"),
        ("source", "source_changed", "insufficient_data"),
        ("old", "provenance_unknown", "unavailable"),
        ("hash", "invalid", "unavailable"),
        ("complete", "incomplete", "insufficient_data"),
        ("result", "invalid", "unavailable"),
        ("closure", "not_public", "unavailable"),
        ("triple", "not_public", "unavailable"),
        ("future", "invalid", "unavailable"),
        ("count", "invalid", "unavailable"),
    ],
)
def test_latest_bad_record_never_becomes_healthy_trend(change, reason, state):
    rows = series()
    current = rows[END]
    if change == "missing":
        del rows[END]
    elif change == "kind":
        rows[END] = record(END, kind="recomputed")
    elif change == "source":
        rows[END] = record(END, revision=2)
    elif change == "hash":
        rows[END] = replace(current, fingerprint=b"x" * 32)
    elif change == "complete":
        rows[END] = record(END, complete=False)
    elif change == "future":
        rows[END] = replace(current, computed_at=NOW + timedelta(minutes=1))
    elif change in {"result", "count"}:
        rows[END] = replace(
            current,
            result={**current.result, "heat" if change == "result" else "participant_count": -1},
        )
    else:
        manifest = json.loads(json.dumps(current.manifest))
        if change == "old":
            manifest.pop("measurement_kind")
        elif change == "closure":
            manifest["observation_ids"].append(str(uuid4()))
        elif change == "triple":
            manifest["inputs"][0]["version_id"] = str(uuid4())
        rows[END] = replace(current, manifest=manifest, fingerprint=fingerprint(manifest))
    view = history(rows)
    assert view.trend.state == state and view.trend.reason == reason
    if change not in {"missing", "source"}:
        assert view.points[-1].value is None


def test_zero_baseline_not_infinity_and_missing_not_zero():
    rows = series()
    at = END - timedelta(hours=6)
    rows[at] = record(at, value=0)
    assert history(rows).trend.reason == "zero_baseline"
    empty = history({})
    assert empty.state == "insufficient_data"
    assert all(point.value is None and point.reason == "missing" for point in empty.points)
    assert all(point.reason == "capacity" for point in history(rows, capacity=True).points)


def test_single_points_and_changed_cohort_are_not_connected():
    view = history(
        {END: record(END), END - timedelta(hours=1): record(END - timedelta(hours=1), revision=2)}
    )
    assert view.state == "insufficient_data" and view.reason == "source_changed"
    assert view.points[-1].segment_key != view.points[-2].segment_key


def test_fully_populated_but_changing_sources_are_not_reported_missing():
    rows = {
        END - timedelta(hours=index): record(END - timedelta(hours=index), revision=index + 1)
        for index in range(48)
    }
    view = history(rows)
    assert view.state == "insufficient_data" and view.reason == "source_changed"
    assert all(point.value is not None for point in view.points)
    assert view.trend.reason == "source_changed"


def test_delayed_calculation_may_contain_a_noncontributing_later_material():
    current = record(END)
    manifest = json.loads(json.dumps(current.manifest))
    manifest["inputs"][0]["source_time"] = (END + timedelta(minutes=5)).isoformat()
    view = history({END: replace(current, manifest=manifest, fingerprint=fingerprint(manifest))})
    assert view.points[-1].value == 10 and view.points[-1].reason is None
