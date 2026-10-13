"""Explainable public-report changes; no population inference or notification writes."""

from collections import Counter
from datetime import datetime
from fractions import Fraction

from core.publication_config import PublicNegativeSurgePolicy
from publication.report_sentiment import public_report_sentiment
from publication.schemas import (
    NegativeSurgeReason,
    PublicNegativeSurgeEvent,
    PublicNegativeSurgeRule,
    PublicNegativeSurgeView,
    PublicSentimentWindow,
    PublicStoryView,
)


def _coverage(window: PublicSentimentWindow) -> Fraction:
    return Fraction(window.valid_count, window.sample_count) if window.sample_count else Fraction(0)


def _increase(current: PublicSentimentWindow, previous: PublicSentimentWindow) -> Fraction:
    return Fraction(current.negative, current.valid_count) - Fraction(
        previous.negative, previous.valid_count
    )


def evaluate_negative_surge(
    story: PublicStoryView, *, now: datetime, policy: PublicNegativeSurgePolicy | None
) -> PublicNegativeSurgeEvent:
    """Evaluate one fully public event, with explicit precedence and exact thresholds.

    Samples must come from publication's complete permission-checked report DTO,
    never from the bounded home story selection or a private analysis query.
    """
    sentiment = (
        public_report_sentiment(story.sentiment.samples, now=now) if story.sentiment else None
    )
    result = PublicNegativeSurgeEvent(
        event_id=story.id,
        title=story.title,
        reading_url=f"/discover/stories/{story.id}",
        state="not_configured" if policy is None else "unavailable",
        reasons=[],
        current=sentiment.current if sentiment else None,
        previous=sentiment.previous if sentiment else None,
    )
    reasons: list[NegativeSurgeReason] = []
    if policy is None:
        reasons.append("rule_not_configured")
    if sentiment is None:
        result.reasons = [*reasons, "analysis_unavailable"]
        return result
    current, previous = sentiment.current, sentiment.previous
    if sentiment.time_unknown_count:
        reasons.append("time_unknown")
    in_windows = [
        sample
        for sample in sentiment.samples
        if sample.discovered_at is not None
        and sample.discovered_at.utcoffset() is not None
        and previous.start < sample.discovered_at <= current.end
    ]
    if any(sample.state == "conflict" for sample in in_windows):
        reasons.append("evidence_conflict")
    if any(sample.state == "unavailable" or sample.backfill is None for sample in in_windows):
        reasons.append("analysis_unavailable")
    unavailable = bool(reasons and policy is not None)
    if not current.sample_count:
        reasons.append("current_empty")
    if not previous.sample_count:
        reasons.append("previous_empty")
    if policy is None:
        if not current.valid_count:
            reasons.append("current_samples_insufficient")
        if not previous.valid_count:
            reasons.append("previous_samples_insufficient")
        result.reasons = reasons
        return result
    if current.valid_count < policy.min_valid_samples:
        reasons.append("current_samples_insufficient")
    if previous.valid_count < policy.min_valid_samples:
        reasons.append("previous_samples_insufficient")
    coverage = Fraction(policy.min_analysis_coverage)
    if _coverage(current) < coverage:
        reasons.append("current_coverage_low")
    if _coverage(previous) < coverage:
        reasons.append("previous_coverage_low")
    if any(not sample.source_key for sample in in_windows):
        reasons.append("source_identity_missing")
    if current.source_keys != previous.source_keys:
        reasons.append("sources_changed")
    if min(len(current.source_keys), len(previous.source_keys)) < policy.min_sources:
        reasons.append("sources_insufficient")
    source_windows = []
    for source in sorted(set(current.source_keys) | set(previous.source_keys)):
        grouped = public_report_sentiment(
            [sample for sample in in_windows if sample.source_key == source], now=now
        )
        source_windows.append((grouped.current, grouped.previous))
        if (
            min(grouped.current.valid_count, grouped.previous.valid_count)
            < policy.min_valid_samples
        ):
            reasons.append("source_samples_insufficient")
        if min(_coverage(grouped.current), _coverage(grouped.previous)) < coverage:
            reasons.append("source_coverage_low")
    if reasons:
        result.state = "unavailable" if unavailable else "insufficient_data"
        result.reasons = list(dict.fromkeys(reasons))
        return result
    increase = _increase(current, previous)
    count_increase = current.negative - previous.negative
    threshold = Fraction(policy.min_ratio_increase)
    if current.negative < policy.min_negative_count:
        reasons.append("negative_count_below_threshold")
    if count_increase < policy.min_negative_count_increase:
        reasons.append("count_increase_below_threshold")
    if increase < threshold:
        reasons.append("ratio_increase_below_threshold")
    if any(_increase(at, before) < threshold for at, before in source_windows):
        reasons.append("source_ratio_increase_below_threshold")
    result.state = "not_triggered" if reasons else "triggered"
    result.reasons = reasons
    result.ratio_increase = float(increase)
    result.negative_count_increase = count_increase
    return result


def negative_surge_summary(
    events: list[PublicNegativeSurgeEvent],
    *,
    now: datetime,
    policy: PublicNegativeSurgePolicy | None,
) -> PublicNegativeSurgeView:
    """Count the entire public set before bounding the stable, trigger-first list."""
    counts = Counter(event.state for event in events)
    state = (
        "not_configured"
        if policy is None
        else "empty"
        if not events
        else "triggered"
        if counts["triggered"]
        else "unavailable"
        if counts["unavailable"]
        else "insufficient_data"
        if counts["insufficient_data"]
        else "not_triggered"
    )
    priority = {
        "triggered": 0,
        "unavailable": 1,
        "insufficient_data": 2,
        "not_configured": 3,
        "not_triggered": 4,
    }
    ordered = sorted(
        events,
        key=lambda event: (
            priority[event.state],
            -(event.ratio_increase or 0),
            -(event.negative_count_increase or 0),
            str(event.event_id),
        ),
    )
    return PublicNegativeSurgeView(
        snapshot_at=now,
        state=state,
        rule=PublicNegativeSurgeRule.model_validate(
            policy.model_dump(exclude={"calibration_reference"})
        )
        if policy
        else None,
        total_events=len(events),
        evaluated_events=counts["triggered"] + counts["not_triggered"],
        triggered_count=counts["triggered"],
        not_triggered_count=counts["not_triggered"],
        insufficient_count=counts["insufficient_data"],
        unavailable_count=counts["unavailable"],
        not_configured_count=counts["not_configured"],
        events=ordered[:20],
    )
