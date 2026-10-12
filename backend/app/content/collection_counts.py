"""Classify identities only from frozen first-identity and exact predecessor evidence."""

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
    history: Sequence[ContentObservation],
    *,
    job_ids: tuple[UUID, ...],
    readable_ids: set[UUID] | None = None,
) -> dict[UUID, CollectionIdentityCounts]:
    """Use each receipt's exact frozen predecessor and classify each Job/content pair once.

    Args:
        history: Owner-scoped history for the selected Jobs' content identities.
        job_ids: Jobs to project, including Jobs with no retained observations.
        readable_ids: Currently readable receipt IDs; None is for pure classification callers.

    Returns:
        Counts for every requested Job. New identity takes precedence over update,
        update over insufficient comparison evidence, and unchanged comes last.
        Missing or withdrawn exact baselines remain unclassified; older history
        is never substituted.
    """
    states: dict[UUID, dict[UUID, _IdentityState]] = {job_id: {} for job_id in job_ids}
    by_id = {item.id: item for item in history}
    for current in history:
        if current.job_id not in states:
            continue
        state = _classify_receipt(by_id, current, readable_ids)
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


def _classify_receipt(
    by_id: dict[UUID, ContentObservation],
    current: ContentObservation,
    readable_ids: set[UUID] | None,
) -> _IdentityState:
    if current.count_provenance_version != 1 or (
        readable_ids is not None and current.id not in readable_ids
    ):
        return _IdentityState.UNCLASSIFIED
    if (
        current.first_identity_state == "confirmed_first"
        and current.comparison_predecessor_id is None
    ):
        return _IdentityState.NEW
    if current.first_identity_state != "confirmed_existing":
        return _IdentityState.UNCLASSIFIED
    previous = (
        by_id.get(current.comparison_predecessor_id) if current.comparison_predecessor_id else None
    )
    if previous is None or (
        previous.owner_id != current.owner_id
        or previous.content_id != current.content_id
        or previous.id == current.id
        or previous.count_provenance_version != 1
        or (readable_ids is not None and previous.id not in readable_ids)
    ):
        return _IdentityState.UNCLASSIFIED
    return _compare_observations(previous, current)


def _compare_observations(
    previous: ContentObservation, current: ContentObservation
) -> _IdentityState:
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


def classify_collection_execution_identities(
    history: Sequence[ContentObservation],
    *,
    job_id: UUID,
    epochs: tuple[int, ...],
    readable_ids: set[UUID] | None = None,
) -> dict[int, CollectionIdentityCounts]:
    """Partition explicitly attributed identities using frozen comparison evidence.

    Args:
        history: Owner-scoped history for identities observed in the selected rounds.
        job_id: Task whose explicit execution provenance is selected.
        epochs: Actual lease epochs, distinct from shared collection budget cycles.
        readable_ids: Currently readable receipt IDs; None is for pure classification callers.

    Returns:
        One mutually exclusive identity partition per requested epoch. Unattributed
        receipts remain comparison context but never count in a guessed round.
        Deleting an exact baseline yields unknown, never a guessed first identity.
    """
    states: dict[int, dict[UUID, _IdentityState]] = {epoch: {} for epoch in epochs}
    by_id = {item.id: item for item in history}
    for current in history:
        if current.job_id != job_id or current.execution_epoch not in states:
            continue
        values = states[current.execution_epoch]
        values[current.content_id] = max(
            _classify_receipt(by_id, current, readable_ids),
            values.get(current.content_id, _IdentityState.UNCHANGED),
        )
    return {
        epoch: CollectionIdentityCounts(
            new=sum(state == _IdentityState.NEW for state in values.values()),
            updated=sum(state == _IdentityState.UPDATED for state in values.values()),
            unchanged=sum(state == _IdentityState.UNCHANGED for state in values.values()),
            unclassified=sum(state == _IdentityState.UNCLASSIFIED for state in values.values()),
        )
        for epoch, values in states.items()
    }
