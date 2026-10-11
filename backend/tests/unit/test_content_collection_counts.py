"""Exercise identity accounting without a database or upstream requests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from content.collection_counts import classify_collection_identities
from content.models import ContentObservation


def _observation(
    job: UUID, content: UUID, version: UUID | None, index: int, **metrics: int | None
) -> ContentObservation:
    return ContentObservation(
        id=UUID(int=index + 1),
        job_id=job,
        content_id=content,
        content_version_id=version,
        received_at=datetime(2026, 10, 11, tzinfo=UTC) + timedelta(seconds=index),
        **metrics,
    )


def test_two_rounds_partition_unique_identities_without_counting_repeated_observations() -> None:
    first, second, empty = uuid4(), uuid4(), uuid4()
    changed, duplicate, unknown, added = (uuid4() for _ in range(4))
    v1, v2 = uuid4(), uuid4()
    history = [
        _observation(first, changed, v1, 0),
        _observation(first, duplicate, v1, 1),
        _observation(first, unknown, None, 2),
        _observation(second, changed, v2, 3),
        _observation(second, changed, v2, 4),
        _observation(second, duplicate, v1, 5),
        _observation(second, duplicate, v1, 6),
        _observation(second, unknown, None, 7),
        _observation(second, added, v1, 8),
        _observation(second, added, v2, 9),
    ]
    counts = classify_collection_identities(list(reversed(history)), job_ids=(first, second, empty))
    assert counts[first].new == 3
    assert (counts[second].new, counts[second].updated) == (1, 1)
    assert (counts[second].unchanged, counts[second].unclassified) == (1, 1)
    assert counts[empty].new == counts[empty].updated == 0
    assert counts[empty].unchanged == counts[empty].unclassified == 0
    # Historical Jobs not requested must still provide the comparison baseline.
    assert classify_collection_identities(history, job_ids=(second,))[second] == counts[second]


@pytest.mark.parametrize(
    "field",
    ("like_count", "comment_count", "repost_count", "view_count", "play_count", "danmaku_count"),
)
@pytest.mark.parametrize(
    ("before", "after", "updated", "unchanged", "unclassified"),
    (
        (0, 1, 1, 0, 0),
        (1, 0, 1, 0, 0),
        (0, 0, 0, 1, 0),
        (None, 0, 0, 0, 1),
        (0, None, 0, 0, 1),
        (None, None, 0, 1, 0),
    ),
)
def test_metrics_preserve_zero_unknown_and_changes(
    field: str,
    before: int | None,
    after: int | None,
    updated: int,
    unchanged: int,
    unclassified: int,
) -> None:
    first, second, content, version = (uuid4() for _ in range(4))
    counts = classify_collection_identities(
        [
            _observation(first, content, version, 0, **{field: before}),
            _observation(second, content, version, 1, **{field: after}),
        ],
        job_ids=(second,),
    )[second]
    assert counts.new == 0
    assert (counts.updated, counts.unchanged, counts.unclassified) == (
        updated,
        unchanged,
        unclassified,
    )


def test_known_change_takes_precedence_over_missing_evidence_and_counts_once() -> None:
    first, second, content, v1, v2 = (uuid4() for _ in range(5))
    counts = classify_collection_identities(
        [
            _observation(first, content, None, 0, like_count=0),
            _observation(second, content, v1, 1, like_count=1),
            _observation(second, content, v2, 2, like_count=None),
            _observation(second, content, None, 3),
        ],
        job_ids=(second,),
    )[second]
    assert counts.updated == 1
    assert counts.new == counts.unchanged == counts.unclassified == 0


def test_distinct_native_identities_are_not_deduplicated_by_identical_text_version() -> None:
    job, first_content, other_platform_content, version = (uuid4() for _ in range(4))
    counts = classify_collection_identities(
        [
            _observation(job, first_content, version, 0),
            _observation(job, other_platform_content, version, 1),
        ],
        job_ids=(job,),
    )[job]
    assert counts.new == 2


def test_equal_received_times_use_stable_id_and_ignore_source_publication_order() -> None:
    first, second, content, version = (uuid4() for _ in range(4))
    old = _observation(first, content, version, 0)
    later = _observation(second, content, version, 1)
    later.received_at = old.received_at
    later.observed_at = datetime(2000, 1, 1, tzinfo=UTC)
    counts = classify_collection_identities([later, old], job_ids=(second, first))
    assert counts[first].new == counts[second].unchanged == 1
