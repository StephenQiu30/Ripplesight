"""Versioned rule boundaries, source comparability, missing evidence and safe configuration."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.publication_config import PublicNegativeSurgePolicy
from publication.negative_surge import evaluate_negative_surge, negative_surge_summary
from publication.report_sentiment import public_report_sentiment
from publication.schemas import PublicSentimentSample, PublicStoryView

NOW = datetime(2026, 10, 13, tzinfo=UTC)
CONTROLLED_POLICY = {
    "policy_id": "controlled-test-only",
    "calibration_reference": "controlled-fixture-not-business-calibration",
    "min_valid_samples": 2,
    "min_analysis_coverage": 0.5,
    "min_sources": 1,
    "min_negative_count": 2,
    "min_negative_count_increase": 1,
    "min_ratio_increase": 0.5,
}


def policy(**changes):
    return PublicNegativeSurgePolicy.model_validate(CONTROLLED_POLICY | changes)


def sample(label="negative", *, hours=1, source="source", state="valid", **changes):
    return PublicSentimentSample(
        content_id=uuid4(),
        source_key=source,
        discovered_at=NOW - timedelta(hours=hours),
        backfill=False,
        state=state,
        label=label if state == "valid" else None,
    ).model_copy(update=changes)


def story(samples=None):
    if samples is None:
        samples = [sample(), sample(), sample(hours=25), sample("neutral", hours=25)]
    return PublicStoryView(
        id=uuid4(),
        revision=1,
        title="controlled event",
        summary="controlled",
        latest_progress=None,
        phase="active",
        first_seen_at=NOW,
        reports=[],
        sentiment=public_report_sentiment(samples, now=NOW),
    )


def evaluate(value=None, **changes):
    return evaluate_negative_surge(value or story(), now=NOW, policy=policy(**changes))


def test_exact_threshold_inclusive_and_public_rule_has_no_calibration_reference():
    result = evaluate()
    assert result.state == "triggered" and result.reasons == []
    assert result.ratio_increase == 0.5 and result.negative_count_increase == 1
    view = negative_surge_summary([result], now=NOW, policy=policy())
    assert view.state == "triggered" and view.triggered_count == view.evaluated_events == 1
    assert "calibration" not in view.model_dump_json()


def test_json_decimal_precision_is_preserved_before_exact_boundary_comparison(monkeypatch):
    raw = json.dumps(CONTROLLED_POLICY).replace(
        '"min_ratio_increase": 0.5', '"min_ratio_increase": 0.500000000000000001'
    )
    monkeypatch.setenv("HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY", raw)
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.public_negative_surge_policy.min_ratio_increase == Decimal(
        "0.500000000000000001"
    )
    result = evaluate_negative_surge(story(), now=NOW, policy=settings.public_negative_surge_policy)
    assert result.state == "not_triggered"
    public = negative_surge_summary([result], now=NOW, policy=settings.public_negative_surge_policy)
    assert '"min_ratio_increase":"0.500000000000000001"' in public.model_dump_json()


@pytest.mark.parametrize(
    "state,reason", [("unavailable", "analysis_unavailable"), ("conflict", "evidence_conflict")]
)
def test_backfill_cannot_mask_unavailable_or_conflicting_evidence(state, reason):
    value = story()
    value.sentiment.samples.append(sample(state=state, backfill=True))
    result = evaluate(value)
    assert result.state == "unavailable" and reason in result.reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"min_ratio_increase": 0.5000000001}, "ratio_increase_below_threshold"),
        ({"min_negative_count": 3}, "negative_count_below_threshold"),
        ({"min_negative_count_increase": 2}, "count_increase_below_threshold"),
    ],
)
def test_just_below_each_rule_is_not_triggered(changes, reason):
    result = evaluate(**changes)
    assert result.state == "not_triggered" and reason in result.reasons


def test_zero_negative_baseline_is_comparable_but_zero_valid_baseline_is_not():
    value = story([sample(), sample(), sample("neutral", hours=25), sample("neutral", hours=25)])
    assert evaluate(value).state == "triggered"
    value.sentiment = public_report_sentiment([sample(), sample()], now=NOW)
    result = evaluate(value)
    assert result.state == "insufficient_data" and "previous_empty" in result.reasons
    assert result.ratio_increase is result.negative_count_increase is None


@pytest.mark.parametrize("state", ["not_analyzed", "pending", "failed", "invalid", "not_relevant"])
def test_partial_analysis_is_coverage_not_neutral_or_unconditionally_unavailable(state):
    value = story()
    value.sentiment.samples.append(sample(state=state))
    assert evaluate(value).state == "triggered"
    result = evaluate(value, min_analysis_coverage=0.8)
    assert result.state == "insufficient_data" and "current_coverage_low" in result.reasons
    assert result.current.negative == 2 and result.current.valid_count == 2


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"backfill": True}, "current_coverage_low"),
        ({"source_key": "new-source"}, "sources_changed"),
    ],
)
def test_backfill_and_source_changes_do_not_create_surge(change, reason):
    value = story()
    value.sentiment.samples.append(sample(**change))
    result = evaluate(value, min_analysis_coverage=1.0)
    assert result.state == "insufficient_data" and reason in result.reasons


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"state": "unavailable", "label": None}, "analysis_unavailable"),
        ({"state": "conflict", "label": None}, "evidence_conflict"),
        ({"backfill": None}, "analysis_unavailable"),
        ({"discovered_at": None}, "time_unknown"),
        ({"discovered_at": NOW + timedelta(seconds=1)}, "time_unknown"),
        ({"discovered_at": NOW.replace(tzinfo=None)}, "time_unknown"),
    ],
)
def test_unavailable_evidence_precedes_sample_insufficiency(change, reason):
    value = story([sample(**change)])
    result = evaluate(value)
    assert result.state == "unavailable" and reason in result.reasons
    assert result.ratio_increase is None


def test_missing_dto_and_unconfigured_rule_keep_distinct_states_and_data_gaps():
    value = story([])
    result = evaluate_negative_surge(value, now=NOW, policy=None)
    assert result.state == "not_configured"
    assert {"rule_not_configured", "current_empty", "previous_empty"} <= set(result.reasons)
    value.sentiment = None
    assert evaluate(value).state == "unavailable"
    result = evaluate_negative_surge(value, now=NOW, policy=None)
    assert result.reasons == ["rule_not_configured", "analysis_unavailable"]


def test_source_strata_prevent_aggregate_mix_shift_from_becoming_surge():
    samples = []
    # A is always negative and B is always neutral: only their proportions change.
    for source, label, current, previous in [("a", "negative", 8, 2), ("b", "neutral", 2, 8)]:
        samples.extend(sample(label, source=source) for _ in range(current))
        samples.extend(sample(label, source=source, hours=25) for _ in range(previous))
    result = evaluate(story(samples))
    assert result.state == "not_triggered" and result.ratio_increase == 0.6
    assert result.reasons == ["source_ratio_increase_below_threshold"]


def test_discovery_window_endpoints_and_deduplication():
    samples = [sample(hours=0), sample(hours=24), sample("neutral", hours=48)]
    value = story([*samples, samples[0]])
    result = evaluate(value)
    assert result.current.sample_count == result.previous.sample_count == 1
    assert result.state == "insufficient_data"


def test_summary_counts_full_set_before_stable_truncation_and_empty_zero():
    values = [evaluate(story()) for _ in range(25)]
    values += [evaluate(story([])), evaluate(story().model_copy(update={"sentiment": None}))]
    summary = negative_surge_summary(values, now=NOW, policy=policy())
    assert summary.state == "triggered" and summary.total_events == 27
    assert summary.triggered_count == summary.evaluated_events == 25
    assert summary.insufficient_count == summary.unavailable_count == 1
    assert len(summary.events) == 20 and all(e.state == "triggered" for e in summary.events)
    reversed_view = negative_surge_summary(list(reversed(values)), now=NOW, policy=policy())
    assert summary == reversed_view
    assert negative_surge_summary([], now=NOW, policy=policy()).state == "empty"
    assert negative_surge_summary([], now=NOW, policy=None).state == "not_configured"


@pytest.mark.parametrize(
    "field",
    ["min_valid_samples", "min_sources", "min_negative_count", "min_negative_count_increase"],
)
@pytest.mark.parametrize("invalid", [True, "2", 0, -1, 2.5])
def test_strict_positive_integer_config(field, invalid):
    with pytest.raises(ValidationError):
        policy(**{field: invalid})


@pytest.mark.parametrize("field", ["min_analysis_coverage", "min_ratio_increase"])
@pytest.mark.parametrize("invalid", [True, "0.5", 0, -1, 1.01, float("nan"), float("inf")])
def test_strict_finite_proportions_config(field, invalid):
    with pytest.raises(ValidationError):
        policy(**{field: invalid})


def test_environment_config_missing_empty_null_valid_invalid_and_no_secret_exposure(monkeypatch):
    monkeypatch.setenv(
        "HOTKEY_DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1/hotkey_test"
    )
    monkeypatch.delenv("HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY", raising=False)
    assert Settings().public_negative_surge_policy is None
    for value in ["", "null"]:
        monkeypatch.setenv("HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY", value)
        assert Settings().public_negative_surge_policy is None
    monkeypatch.setenv("HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY", json.dumps(CONTROLLED_POLICY))
    configured = Settings().public_negative_surge_policy
    assert configured.policy_id == "controlled-test-only"
    assert CONTROLLED_POLICY["calibration_reference"] not in configured.model_dump_json()
    for value in [
        "{",
        "{}",
        json.dumps(CONTROLLED_POLICY | {"unknown": 1}),
        json.dumps(CONTROLLED_POLICY | {"calibration_reference": " "}),
    ]:
        monkeypatch.setenv("HOTKEY_PUBLIC_NEGATIVE_SURGE_POLICY", value)
        with pytest.raises(ValueError):
            Settings()


def test_home_evaluates_all_101_events_before_limit_and_partial_total_stays_unknown(monkeypatch):
    import publication.home as module
    from tests.unit.test_publication_groups import member

    values = [story() for _ in range(101)]
    values[-1].sentiment = None
    projection = member(at=NOW).projection
    monkeypatch.setattr(
        module,
        "iter_current_publications_in_transaction",
        lambda *a, **k: iter(
            [
                SimpleNamespace(projection=projection.model_copy(update={"event_id": value.id}))
                for value in values
            ]
        ),
    )
    by_id = {value.id: value for value in values}
    monkeypatch.setattr(
        module,
        "public_stories_in_transaction",
        lambda *a, event_ids, **k: [by_id[key] for key in event_ids],
    )
    reader = SimpleNamespace(
        session=SimpleNamespace(in_transaction=lambda: True, get=lambda *a, **k: None),
        indexing_enabled=False,
        public_categories=(),
    )
    view = module.home_in_transaction(
        reader, owner_id=UUID(int=1), now=NOW, limit=1, surge_policy=policy()
    )
    assert len(view.stories) == 1 and view.overview.total_events == 101
    assert view.negative_surge.triggered_count == 100 and len(view.negative_surge.events) == 20
    assert view.negative_surge.unavailable_count == 1
    assert view.overview.negative_surge_count is None

    assert len(view.platform_trends) == 6
    assert all(board.state == "not_configured" for board in view.platform_trends)
