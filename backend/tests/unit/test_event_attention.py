from datetime import UTC, datetime, timedelta
from uuid import UUID

from events.attention import compute_attention
from events.heat_schemas import AttentionEvidence, AttentionSource

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def _source(number, *, mode="editorial", group=None, entity=None, age=100, last_ok=NOW):
    return AttentionSource(
        id=UUID(int=number),
        name=f"来源{number}",
        mode=mode,
        group_key=group,
        owner_entity_key=entity,
        tier=None,
        first_party=False,
        created_at=NOW - timedelta(hours=age),
        scheduled=True,
        interval_seconds=1800,
        last_successful_fetch_at=last_ok,
    )


def _evidence(source, number, *, age=0):
    return AttentionEvidence(
        id=UUID(int=number),
        source=source,
        content_id=UUID(int=number + 100),
        content_version_id=UUID(int=number + 200),
        source_time=NOW - timedelta(hours=age),
        kind="editorial",
    )


def test_one_owner_or_group_counts_once_and_repeat_collection_does_not_refresh_source_time():
    first = _source(1, group="group", entity="different")
    second = _source(2, group="group", entity="other")
    third = _source(3, mode="signal")
    result = compute_attention(
        (
            _evidence(first, 1, age=24),
            _evidence(first, 2, age=24),
            _evidence(second, 3, age=30),
            _evidence(third, 4, age=24),
        ),
        at=NOW,
    )
    assert result.participant_count == 2
    assert result.heat == 10.0
    assert result.eligible and result.editorial_participant_count == 1


def test_48h_boundary_is_open_and_future_signals_are_excluded():
    result = compute_attention(
        (_evidence(_source(1), 1, age=48), _evidence(_source(2), 2, age=-1)), at=NOW
    )
    assert result.participant_count == 0 and not result.eligible


def test_new_or_behind_source_is_removed_from_entire_participant_comparison():
    old = _source(1, group="owner", last_ok=NOW - timedelta(hours=5))
    recent = _source(2, group="owner", age=1)
    other = _source(3, last_ok=NOW - timedelta(hours=5))
    result = compute_attention(
        (_evidence(old, 1, age=8), _evidence(recent, 2), _evidence(other, 3, age=7)), at=NOW
    )
    assert result.eligible and result.trend == "unknown"
    assert result.trend_pct is None and result.uncomparable_participant_count == 2
    assert not result.complete


def test_source_clocks_repair_past_hour_after_success_and_preserve_current_grace():
    source = _source(1, last_ok=NOW - timedelta(hours=1))
    other = _source(2, last_ok=NOW - timedelta(hours=1))
    evidence = (_evidence(source, 1, age=8), _evidence(other, 2, age=8))
    assert compute_attention(evidence, at=NOW).complete
    assert not compute_attention(evidence, at=NOW, historical=True).complete
    assert compute_attention(evidence, at=NOW - timedelta(hours=2), historical=True).complete


def test_surge_uses_new_participants_and_signal_only_cannot_enter_ranking():
    editorial = _source(1)
    signals = (_source(2, mode="signal"), _source(3, mode="signal"))
    result = compute_attention(
        tuple(
            _evidence(source, index + 1, age=1)
            for index, source in enumerate((editorial, *signals))
        ),
        at=NOW,
        first_report_at=NOW - timedelta(hours=1),
    )
    assert result.badges == ["surge", "new"] and result.trend == "new"
    signal_only = compute_attention(
        tuple(_evidence(source, index + 1) for index, source in enumerate(signals)), at=NOW
    )
    assert not signal_only.eligible
