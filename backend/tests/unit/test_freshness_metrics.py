from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from jobs.metrics import (
    AnalysisTimingSample,
    CollectionTimingSample,
    expected_hotlist_buckets,
    summarize_analysis_timing,
    summarize_collection_timing,
)
from jobs.schemas import (
    FreshnessTimelineInput,
    SourceTimePrecision,
    SourceTimeStatus,
)
from jobs.services import measure_freshness_timeline

BASE = datetime(2026, 9, 21, 12, tzinfo=UTC)


def _timeline(**changes: object) -> FreshnessTimelineInput:
    values: dict[str, object] = {
        "scheduled_for_at": BASE,
        "accepted_at": BASE + timedelta(seconds=2),
        "started_at": BASE + timedelta(seconds=5),
        "request_started_at": BASE + timedelta(seconds=7),
        "source_published_at": BASE - timedelta(minutes=10),
        "source_time_precision": SourceTimePrecision.SECOND,
        "source_observed_at": BASE + timedelta(seconds=11),
        "persisted_at": BASE + timedelta(seconds=14),
        "queryable_at": BASE + timedelta(seconds=15),
    }
    values.update(changes)
    return FreshnessTimelineInput(**values)


def test_complete_timeline_separates_each_non_negative_duration() -> None:
    source_time = datetime(2026, 9, 21, 19, 50, tzinfo=timezone(timedelta(hours=8)))

    measured = measure_freshness_timeline(_timeline(source_published_at=source_time))

    assert measured.source_time_status is SourceTimeStatus.VALID
    assert measured.schedule_wait_us == 5_000_000
    assert measured.queue_wait_us == 3_000_000
    assert measured.internal_prepare_us == 2_000_000
    assert measured.source_wait_us == 4_000_000
    assert measured.processing_us == 3_000_000
    assert measured.visibility_us == 1_000_000
    assert measured.end_to_end_us == 15_000_000
    assert measured.publication_to_observation_us == 611_000_000


def test_missing_stages_remain_unknown_instead_of_becoming_zero() -> None:
    measured = measure_freshness_timeline(
        _timeline(
            scheduled_for_at=None,
            started_at=None,
            request_started_at=None,
            source_published_at=None,
            source_time_precision=SourceTimePrecision.UNKNOWN,
            source_observed_at=None,
            persisted_at=None,
            queryable_at=None,
        )
    )

    assert measured.source_time_status is SourceTimeStatus.UNKNOWN
    assert measured.schedule_wait_us is None
    assert measured.queue_wait_us is None
    assert measured.source_wait_us is None
    assert measured.publication_to_observation_us is None


def test_source_time_anomalies_never_produce_negative_discovery_delay() -> None:
    missing_timezone = measure_freshness_timeline(
        _timeline(source_published_at=datetime(2026, 9, 21, 12))
    )
    future = measure_freshness_timeline(_timeline(source_published_at=BASE + timedelta(minutes=1)))

    assert missing_timezone.source_time_status is SourceTimeStatus.MISSING_TIMEZONE
    assert missing_timezone.publication_to_observation_us is None
    assert future.source_time_status is SourceTimeStatus.FUTURE_SKEW
    assert future.publication_to_observation_us is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accepted_at", datetime(2026, 9, 21, 12)),
        ("started_at", BASE + timedelta(seconds=1)),
        ("request_started_at", None),
        ("persisted_at", BASE + timedelta(seconds=10)),
        ("queryable_at", BASE + timedelta(seconds=13)),
    ],
)
def test_invalid_internal_time_chains_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _timeline(**{field: value})


def test_collection_timing_uses_exact_odd_and_even_medians_at_threshold() -> None:
    samples = tuple(
        CollectionTimingSample(due_at=BASE, finished_at=BASE + timedelta(seconds=s))
        for s in (100, 300, 500)
    )
    odd = summarize_collection_timing(
        samples, cutoff_at=BASE + timedelta(hours=1), target_seconds=300
    )
    assert (odd.median_seconds, odd.median_lower_bound_seconds, odd.result) == (300, 300, "passed")
    even = summarize_collection_timing(
        samples[:2], cutoff_at=BASE + timedelta(hours=1), target_seconds=300
    )
    assert (even.median_seconds, even.result) == (200, "passed")
    late = summarize_collection_timing(
        (CollectionTimingSample(due_at=BASE, finished_at=BASE + timedelta(seconds=301)),),
        cutoff_at=BASE + timedelta(hours=1),
        target_seconds=300,
    )
    assert (late.median_seconds, late.result) == (301, "failed")


def test_unfinished_windows_keep_censored_median_and_lower_bound() -> None:
    cutoff = BASE + timedelta(seconds=301)
    pending = CollectionTimingSample(due_at=BASE, finished_at=None)
    uncertain = summarize_collection_timing(
        (pending,), cutoff_at=BASE + timedelta(seconds=300), target_seconds=300
    )
    assert (
        uncertain.median_seconds,
        uncertain.median_lower_bound_seconds,
        uncertain.timeout_count,
        uncertain.result,
    ) == (None, 300, 1, "indeterminate")
    failed = summarize_collection_timing((pending,), cutoff_at=cutoff, target_seconds=300)
    assert (
        failed.median_seconds,
        failed.median_lower_bound_seconds,
        failed.timeout_count,
        failed.result,
    ) == (None, 301, 1, "failed")
    certain = summarize_collection_timing(
        (
            CollectionTimingSample(BASE, BASE + timedelta(seconds=100)),
            CollectionTimingSample(BASE, BASE + timedelta(seconds=200)),
            pending,
        ),
        cutoff_at=BASE + timedelta(hours=1),
        target_seconds=300,
    )
    assert (certain.median_seconds, certain.timeout_count, certain.result) == (200, 1, "passed")
    empty = summarize_collection_timing((), cutoff_at=cutoff, target_seconds=300)
    assert (empty.sample_count, empty.median_seconds, empty.result) == (0, None, "no_samples")


def test_hotlist_expected_buckets_count_missing_rows_across_utc_day() -> None:
    start = datetime(2026, 9, 27, 23, 30, tzinfo=UTC)
    end = start + timedelta(hours=72)
    assert len(expected_hotlist_buckets(start=start, end=end, interval_seconds=1800)) == 144
    assert (
        len(
            expected_hotlist_buckets(
                start=start, end=end - timedelta(minutes=30), interval_seconds=1800
            )
        )
        == 143
    )


def test_analysis_timing_keeps_matured_failures_and_pending_samples() -> None:
    start = datetime(2026, 9, 27, 23, 30, tzinfo=UTC)
    cutoff = start + timedelta(hours=2)
    result = summarize_analysis_timing(
        (
            AnalysisTimingSample(start, start + timedelta(seconds=3600)),
            AnalysisTimingSample(start, start + timedelta(seconds=3601)),
            AnalysisTimingSample(start, None),
            AnalysisTimingSample(start + timedelta(minutes=90), None),
        ),
        cutoff_at=cutoff,
    )
    assert (result.matured_count, result.timely_valid_count) == (3, 1)
    assert (result.late_or_missing_count, result.pending_observation_count) == (2, 1)


def test_analysis_timing_zero_and_exact_maturity_boundary() -> None:
    assert summarize_analysis_timing((), cutoff_at=BASE).matured_count == 0
    pending = summarize_analysis_timing(
        (AnalysisTimingSample(BASE, None),),
        cutoff_at=BASE + timedelta(seconds=3599),
    )
    mature = summarize_analysis_timing(
        (AnalysisTimingSample(BASE, None),),
        cutoff_at=BASE + timedelta(seconds=3600),
    )
    assert (pending.pending_observation_count, pending.matured_count) == (1, 0)
    assert (mature.pending_observation_count, mature.late_or_missing_count) == (0, 1)
