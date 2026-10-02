"""Caller-transaction source health; inspection never refreshes or writes a poll."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobs.operator_maintenance import first_job_admitted_at_in_transaction
from leaderboard.fetch import SOURCE_KEYS
from leaderboard.models import LeaderboardSourceState
from leaderboard.schemas import LeaderboardSourceHealthView

SOURCE_STALE_AFTER = timedelta(hours=26)


def load_source_health_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    now: datetime,
    enabled: bool = False,
    external_requests_enabled: bool = False,
) -> tuple[LeaderboardSourceHealthView, ...]:
    """Use actual success, or the owner's original admitted job when never successful.

    Collection switches belong to the caller's Settings. Both must be enabled to
    expect new upstream evidence: a stored-only round must not cause stale alerts.
    The admission anchor is an observed business fact, not a fabricated first
    network-enable timestamp. No existing source-state timestamps are rewritten.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("leaderboard health requires an aware caller transaction")
    expected = enabled and external_requests_enabled
    admitted_at = first_job_admitted_at_in_transaction(
        session, owner_id=owner_id, kind="leaderboard.refresh"
    )
    states = {row.source_key: row for row in session.scalars(select(LeaderboardSourceState))}
    views: list[LeaderboardSourceHealthView] = []
    for key in (key for keys in SOURCE_KEYS.values() for key in keys):
        state = states.get(key)
        success = state.last_ok_at if state else None
        checked = state.checked_at if state else None
        anchor = success or admitted_at or checked
        views.append(
            LeaderboardSourceHealthView(
                source_key=key,
                enabled=expected,
                checked_at=checked,
                last_successful_poll_at=success,
                anchor_at=anchor,
                failing=state is not None and not state.ok,
                stale=expected and anchor is not None and now - anchor > SOURCE_STALE_AFTER,
            )
        )
    return tuple(views)
