from datetime import UTC, datetime, timedelta
from uuid import uuid4

from analysis.runtime import PromptRuntimeWindow, project_prompt_runtime_origin


def _at(minutes: int) -> datetime:
    return datetime(2026, 9, 28, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _window(
    start: int, end: int, *, enabled: bool, prompt_version: str = "current"
) -> PromptRuntimeWindow:
    return PromptRuntimeWindow(
        run_id=uuid4(),
        prompt_version=prompt_version,
        ai_enabled=enabled,
        starts_at=_at(start),
        ends_at=_at(end),
    )


def test_disabled_then_enabled_starts_at_reenable_and_keeps_run_ids() -> None:
    disabled = _window(0, 30, enabled=False)
    enabled = _window(30, 120, enabled=True)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(90)),),
        runtime_windows=(disabled, enabled),
    )
    assert result.status == "candidate"
    assert result.started_at == _at(30)
    assert result.runtime_ids == (disabled.run_id, enabled.run_id)


def test_gap_before_first_known_candidate_is_unknown() -> None:
    disabled = _window(0, 20, enabled=False)
    enabled = _window(30, 90, enabled=True)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(60)),),
        runtime_windows=(disabled, enabled),
    )
    assert result.status == "unknown"
    assert result.reason == "prompt_runtime_history_gap"
    assert result.runtime_ids == (disabled.run_id,)


def test_conflicting_scheduler_config_is_unknown() -> None:
    enabled = _window(0, 90, enabled=True)
    conflicting = _window(0, 90, enabled=False)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(60)),),
        runtime_windows=(enabled, conflicting),
    )
    assert result.status == "unknown"
    assert result.reason == "prompt_runtime_conflict"
    assert set(result.runtime_ids) == {enabled.run_id, conflicting.run_id}


def test_other_prompt_and_disabled_sessions_do_not_create_current_candidate() -> None:
    other = _window(0, 30, enabled=True, prompt_version="previous")
    disabled = _window(30, 90, enabled=False)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(60)),),
        runtime_windows=(other, disabled),
    )
    assert result.status == "not_required"
    assert result.started_at is None


def test_gap_after_first_candidate_does_not_erase_known_origin() -> None:
    enabled = _window(0, 30, enabled=True)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(60)),),
        runtime_windows=(enabled,),
    )
    assert result.status == "candidate"
    assert result.started_at == _at(10)


def test_zero_length_session_and_end_boundary_do_not_cover_time() -> None:
    zero = _window(10, 10, enabled=True)
    enabled = _window(20, 30, enabled=True)
    result = project_prompt_runtime_origin(
        prompt_version="current",
        eligible_spans=((_at(10), _at(20)),),
        runtime_windows=(zero, enabled),
    )
    assert result.status == "unknown"
    assert result.reason == "prompt_runtime_history_gap"


def test_no_eligible_span_is_not_required_even_without_runtime_history() -> None:
    result = project_prompt_runtime_origin(
        prompt_version="current", eligible_spans=(), runtime_windows=()
    )
    assert result.status == "not_required"
