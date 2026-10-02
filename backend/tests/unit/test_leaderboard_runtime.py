from datetime import UTC, datetime, timedelta
from uuid import uuid4

from leaderboard.schedule import leaderboard_operation_id, leaderboard_window


def test_six_hour_window_identity_is_stable_and_changes_with_method_or_owner() -> None:
    owner = uuid4()
    now = datetime(2026, 10, 2, 8, 10, tzinfo=UTC)
    assert leaderboard_window(now) == datetime(2026, 10, 2, 6, 5, tzinfo=UTC)
    assert leaderboard_operation_id(owner, now) == leaderboard_operation_id(
        owner, now + timedelta(hours=2)
    )
    assert leaderboard_operation_id(owner, now) != leaderboard_operation_id(
        owner, now + timedelta(hours=4)
    )
    assert leaderboard_operation_id(owner, now) != leaderboard_operation_id(uuid4(), now)


def test_upstream_four_shanghai_run_times_do_not_admit_a_new_window_five_minutes_early():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Asia/Shanghai")
    for hour in (2, 8, 14, 20):
        due = datetime(2026, 10, 2, hour, 5, tzinfo=zone)
        assert leaderboard_window(due) == due.astimezone(UTC)
        assert leaderboard_window(due - timedelta(microseconds=1)) == (
            due - timedelta(hours=6)
        ).astimezone(UTC)
