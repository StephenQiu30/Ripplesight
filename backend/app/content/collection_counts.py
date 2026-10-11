"""Classify retained collection observations without new persistence or requests."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from uuid import UUID

from content.models import ContentObservation


class _IdentityState(IntEnum):
    UNCHANGED = 0
    UNCLASSIFIED = 1
    UPDATED = 2
    NEW = 3


@dataclass(frozen=True, slots=True)
class CollectionIdentityCounts:
    """Mutually exclusive counts whose sum is the Job's unique content count."""

    new: int
    updated: int
    unchanged: int
    unclassified: int


def classify_collection_identities(
    history: Sequence[ContentObservation], *, job_ids: tuple[UUID, ...]
) -> dict[UUID, CollectionIdentityCounts]:
    """Compare adjacent retained receipts and classify each Job/content pair once.

    Args:
        history: Owner-scoped history for the selected Jobs' content identities.
        job_ids: Jobs to project, including Jobs with no retained observations.

    Returns:
        Counts for every requested Job. New identity takes precedence over update,
        update over insufficient comparison evidence, and unchanged comes last.
        Results reflect retained history, not an immutable ingestion ledger.
    """
    states: dict[UUID, dict[UUID, _IdentityState]] = {job_id: {} for job_id in job_ids}
    previous_by_content: dict[UUID, ContentObservation] = {}
    for current in sorted(history, key=lambda item: (item.received_at, item.id)):
        previous = previous_by_content.get(current.content_id)
        previous_by_content[current.content_id] = current
        if current.job_id not in states:
            continue
        state = _compare_observations(previous, current)
        job_states = states[current.job_id]
        job_states[current.content_id] = max(
            state, job_states.get(current.content_id, _IdentityState.UNCHANGED)
        )
    return {
        job_id: CollectionIdentityCounts(
            new=sum(state == _IdentityState.NEW for state in values.values()),
            updated=sum(state == _IdentityState.UPDATED for state in values.values()),
            unchanged=sum(state == _IdentityState.UNCHANGED for state in values.values()),
            unclassified=sum(state == _IdentityState.UNCLASSIFIED for state in values.values()),
        )
        for job_id, values in states.items()
    }


def _compare_observations(
    previous: ContentObservation | None, current: ContentObservation
) -> _IdentityState:
    if previous is None:
        return _IdentityState.NEW
    missing = previous.content_version_id is None or current.content_version_id is None
    if not missing and previous.content_version_id != current.content_version_id:
        return _IdentityState.UPDATED
    for before, after in (
        (previous.like_count, current.like_count),
        (previous.comment_count, current.comment_count),
        (previous.repost_count, current.repost_count),
        (previous.view_count, current.view_count),
        (previous.play_count, current.play_count),
        (previous.danmaku_count, current.danmaku_count),
    ):
        if before is not None and after is not None and before != after:
            return _IdentityState.UPDATED
        if (before is None) != (after is None):
            missing = True
    return _IdentityState.UNCLASSIFIED if missing else _IdentityState.UNCHANGED
