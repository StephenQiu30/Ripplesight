from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from tests.integration.test_analysis_pipeline import AnalysisCase
from tests.integration.test_analysis_pipeline import analysis_case as analysis_case

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.services import project_analysis_need_origin_in_transaction


@pytest.fixture
def origin_case(analysis_case: AnalysisCase) -> Iterator[AnalysisCase]:
    case = analysis_case
    with case.sessions() as session, session.begin():
        session.execute(text("DELETE FROM analysis_prompt_runtime_sessions"))
        session.execute(text("DELETE FROM analysis_prompt_activations"))
    yield case


def _event(
    case: AnalysisCase, sequence: int, status: str, reason: str, at: datetime, *, version: int = 1
) -> None:
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO monitor_topic_status_events "
                "(id, owner_id, topic_id, event_sequence, topic_rule_version, "
                "status, reason, occurred_at) VALUES "
                "(:id, :owner, :topic, :sequence, :version, :status, :reason, :at)"
            ),
            {
                "id": uuid4(),
                "owner": case.owner_id,
                "topic": case.topic_id,
                "sequence": sequence,
                "version": version,
                "status": status,
                "reason": reason,
                "at": at,
            },
        )


def _runtime_session(
    case: AnalysisCase,
    *,
    started_at: datetime,
    last_seen_at: datetime,
    ai_enabled: bool,
    prompt_version: str = ANALYSIS_PROMPT_VERSION,
) -> UUID:
    run_id = uuid4()
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO analysis_prompt_runtime_sessions "
                "(id, prompt_version, ai_enabled, started_at, last_seen_at, stopped_at) "
                "VALUES (:id, :version, :enabled, :started, :last_seen, NULL)"
            ),
            {
                "id": run_id,
                "version": prompt_version,
                "enabled": ai_enabled,
                "started": started_at,
                "last_seen": last_seen_at,
            },
        )
    return run_id


def _activate_prompt(case: AnalysisCase, at: datetime, *, runtime: bool = True) -> None:
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO analysis_prompt_activations "
                "(prompt_version, activated_at) VALUES (:version, :at)"
            ),
            {"version": ANALYSIS_PROMPT_VERSION, "at": at},
        )
    if runtime:
        _runtime_session(
            case,
            started_at=at,
            last_seen_at=case.now + timedelta(hours=2),
            ai_enabled=True,
        )


def _project(case: AnalysisCase, *, version: int = 1, at: datetime | None = None):
    with case.sessions() as session, session.begin():
        return project_analysis_need_origin_in_transaction(
            session,
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=version,
            content_version_id=case.version_id,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            as_of=at or case.now,
        )


def test_old_post_origin_is_topic_activation_not_global_ingest(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    first_ingest = case.now - timedelta(days=4)
    topic_active = case.now - timedelta(minutes=70)
    _event(case, 1, "paused", "created", first_ingest)
    _event(case, 2, "active", "resumed", topic_active)
    assert _project(case).reason == "prompt_activation_unavailable"

    _activate_prompt(case, case.now - timedelta(hours=2))
    result = _project(case)
    assert result.status == "candidate"
    assert result.started_at == topic_active
    assert result.started_at != first_ingest
    assert _project(case, at=topic_active - timedelta(microseconds=1)).status == "not_required"


def test_prompt_disable_then_resume_moves_origin_to_reenabled_session(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    activation = case.now - timedelta(hours=2)
    topic_active = case.now - timedelta(hours=1)
    resumed = case.now - timedelta(minutes=30)
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", topic_active)
    _activate_prompt(case, activation, runtime=False)
    _runtime_session(case, started_at=activation, last_seen_at=resumed, ai_enabled=False)
    enabled_run = _runtime_session(
        case, started_at=resumed, last_seen_at=case.now + timedelta(hours=1), ai_enabled=True
    )

    origin = _project(case)
    assert origin.status == "candidate"
    assert origin.started_at == resumed
    assert enabled_run in origin.prompt_runtime_ids


def test_prompt_runtime_gap_before_first_enabled_session_is_unknown(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    activation = case.now - timedelta(hours=2)
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", case.now - timedelta(hours=1))
    _activate_prompt(case, activation, runtime=False)
    disabled_run = _runtime_session(
        case,
        started_at=activation,
        last_seen_at=case.now - timedelta(minutes=50),
        ai_enabled=False,
    )
    _runtime_session(
        case,
        started_at=case.now - timedelta(minutes=30),
        last_seen_at=case.now + timedelta(hours=1),
        ai_enabled=True,
    )
    result = _project(case)
    assert result.status == "unknown"
    assert result.reason == "prompt_runtime_history_gap"
    assert result.prompt_runtime_ids == (disabled_run,)


def test_missing_or_conflicting_prompt_runtime_is_unknown(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    activation = case.now - timedelta(hours=2)
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", case.now - timedelta(hours=1))
    _activate_prompt(case, activation, runtime=False)
    assert _project(case).reason == "prompt_runtime_history_gap"

    enabled_run = _runtime_session(
        case,
        started_at=activation,
        last_seen_at=case.now + timedelta(hours=1),
        ai_enabled=True,
    )
    disabled_run = _runtime_session(
        case,
        started_at=activation,
        last_seen_at=case.now + timedelta(hours=1),
        ai_enabled=False,
    )
    result = _project(case)
    assert result.status == "unknown"
    assert result.reason == "prompt_runtime_conflict"
    assert set(result.prompt_runtime_ids) == {enabled_run, disabled_run}


def test_rule_change_during_pause_starts_at_resume(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    old = case.now - timedelta(days=4)
    first_active = case.now - timedelta(minutes=90)
    paused = case.now - timedelta(minutes=60)
    rule_changed = case.now - timedelta(minutes=45)
    resumed = case.now - timedelta(minutes=30)
    _event(case, 1, "paused", "created", old)
    _event(case, 2, "active", "resumed", first_active)
    _event(case, 3, "paused", "paused", paused)
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, "
                "source_keys, created_at) VALUES "
                "(:topic, 2, :owner, '[\"HotKey\"]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, '[\"hackernews\"]'::jsonb, :at)"
            ),
            {"topic": case.topic_id, "owner": case.owner_id, "at": rule_changed},
        )
        session.execute(
            text("UPDATE monitor_topics SET current_version = 2 WHERE id = :topic"),
            {"topic": case.topic_id},
        )
    _event(case, 4, "active", "resumed", resumed, version=2)
    _activate_prompt(case, case.now - timedelta(hours=2))

    assert _project(case, version=1).started_at == first_active
    before_resume = _project(case, version=2, at=resumed - timedelta(microseconds=1))
    assert before_resume.status == "not_required"
    assert _project(case, version=2).started_at == resumed


def test_missing_topic_history_and_unselected_source_do_not_create_origin(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    _activate_prompt(case, case.now - timedelta(hours=2))
    assert _project(case).reason == "topic_history_unavailable"
    old = case.now - timedelta(days=4)
    _event(case, 1, "paused", "created", old)
    _event(case, 2, "active", "resumed", case.now - timedelta(hours=1))
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE monitor_topic_versions SET source_keys = '[]'::jsonb "
                "WHERE topic_id = :topic"
            ),
            {"topic": case.topic_id},
        )
    assert _project(case).status == "not_required"


def test_hotlist_origin_uses_first_matching_topic_and_exact_version(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    old = case.now - timedelta(days=4)
    _event(case, 1, "paused", "created", old)
    _event(case, 2, "active", "resumed", case.now - timedelta(hours=2))
    _activate_prompt(case, case.now - timedelta(hours=2))
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE monitor_topic_versions SET source_keys = '[]'::jsonb "
                "WHERE topic_id = :topic"
            ),
            {"topic": case.topic_id},
        )

    def observe_hotlist(at: datetime, *, matched: bool, version_id: UUID) -> None:
        job_id, operation_id, snapshot_id = uuid4(), uuid4(), uuid4()
        with case.sessions() as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, owner_id, operation_id, kind, configuration_ref, "
                    "configuration_version, source_key, source_capability, scope, "
                    "request_fingerprint, created_at, updated_at) VALUES "
                    "(:id, :owner, :operation, 'source.hotlist', 'topic:seed', 1, "
                    "'hackernews', 'hotlist', '{}'::jsonb, :fingerprint, :at, :at)"
                ),
                {
                    "id": job_id,
                    "owner": case.owner_id,
                    "operation": operation_id,
                    "fingerprint": job_id.bytes * 2,
                    "at": at,
                },
            )
            session.execute(
                text(
                    "INSERT INTO collection_due_windows "
                    "(id, owner_id, schedule_key, source_key, capability, due_at, "
                    "window_start, window_end, admission_state, operation_id, job_id, "
                    "recorded_at) VALUES "
                    "(:id, :owner, :schedule, 'hackernews', 'hotlist', :at, "
                    ":start, :at, 'accepted', :operation, :job, :at)"
                ),
                {
                    "id": uuid4(),
                    "owner": case.owner_id,
                    "schedule": uuid4(),
                    "at": at,
                    "start": at - timedelta(minutes=30),
                    "operation": operation_id,
                    "job": job_id,
                },
            )
            session.execute(
                text(
                    "INSERT INTO content_observations "
                    "(id, owner_id, content_id, job_id, source_operation_id, "
                    "content_version_id, observed_at, received_at) VALUES "
                    "(:id, :owner, :content, :job, :operation, :version, :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "owner": case.owner_id,
                    "content": case.content_id,
                    "job": job_id,
                    "operation": uuid4(),
                    "version": version_id,
                    "at": at,
                },
            )
            session.execute(
                text(
                    "INSERT INTO hotlist_snapshots "
                    "(id, owner_id, source_key, job_id, operation_id, observed_at, entry_count) "
                    "VALUES (:id, :owner, 'hackernews', :job, :operation, :at, 1)"
                ),
                {
                    "id": snapshot_id,
                    "owner": case.owner_id,
                    "job": job_id,
                    "operation": operation_id,
                    "at": at,
                },
            )
            session.execute(
                text(
                    "INSERT INTO hotlist_entries "
                    "(snapshot_id, owner_id, rank, title, url, content_id, "
                    "matched_topic_ids) VALUES "
                    "(:snapshot, :owner, 1, 'HotKey', 'https://example.com/hotkey', "
                    ":content, CAST(:matches AS jsonb))"
                ),
                {
                    "snapshot": snapshot_id,
                    "owner": case.owner_id,
                    "content": case.content_id,
                    "matches": f'["{case.topic_id}"]' if matched else "[]",
                },
            )

    unmatched_at = case.now - timedelta(minutes=90)
    matched_at = case.now - timedelta(minutes=60)
    observe_hotlist(unmatched_at, matched=False, version_id=case.version_id)
    assert _project(case).status == "not_required"
    observe_hotlist(matched_at, matched=True, version_id=case.version_id)
    assert _project(case).started_at == matched_at

    later_version = uuid4()
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO content_versions "
                "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                "title, body, created_at) VALUES "
                "(:id, :owner, :content, :fingerprint, 'full', 'source', "
                "'HotKey 后续', '新正文', :at)"
            ),
            {
                "id": later_version,
                "owner": case.owner_id,
                "content": case.content_id,
                "fingerprint": later_version.bytes * 2,
                "at": case.now - timedelta(minutes=30),
            },
        )
    observe_hotlist(case.now - timedelta(minutes=30), matched=True, version_id=later_version)
    assert _project(case).started_at == matched_at
