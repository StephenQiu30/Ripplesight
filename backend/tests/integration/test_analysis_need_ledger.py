from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from tests.integration.test_analysis_need_origin import _activate_prompt, _event, _runtime_session
from tests.integration.test_analysis_need_origin import origin_case as origin_case
from tests.integration.test_analysis_pipeline import AnalysisCase, _post, _seed_ai_call
from tests.integration.test_analysis_pipeline import analysis_case as analysis_case

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.schemas import AnnotationResultState, AnnotationStatus, AnnotationWrite
from analysis.services import AnalysisService, build_analysis_need_ledger_in_transaction


def test_ledger_enumerates_unqueued_old_and_new_versions_without_claiming_ratio(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", case.now - timedelta(minutes=50))
    start = case.now - timedelta(hours=1)
    cutoff = case.now + timedelta(minutes=20)

    with case.sessions() as session, session.begin():
        unknown = build_analysis_need_ledger_in_transaction(
            session, owner_id=case.owner_id, start=start, end=case.now, cutoff_at=cutoff
        )
    assert (unknown.candidate_count, unknown.unknown_count) == (0, 1)
    assert unknown.analysis_status == "not_computable"

    _activate_prompt(case, case.now - timedelta(hours=2))
    newer_version, future_version = uuid4(), uuid4()
    with case.sessions() as session, session.begin():
        source_job = session.execute(
            text("SELECT id FROM jobs WHERE owner_id = :owner"),
            {"owner": case.owner_id},
        ).scalar_one()
        for version_id, observed_at in (
            (newer_version, case.now - timedelta(minutes=10)),
            (future_version, case.now + timedelta(minutes=1)),
        ):
            session.execute(
                text(
                    "INSERT INTO content_versions "
                    "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                    "title, body, created_at) VALUES "
                    "(:id, :owner, :content, :fingerprint, 'full', 'source', "
                    "'HotKey 新版本', '正文', :at)"
                ),
                {
                    "id": version_id,
                    "owner": case.owner_id,
                    "content": case.content_id,
                    "fingerprint": version_id.bytes * 2,
                    "at": observed_at,
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
                    "job": source_job,
                    "operation": uuid4(),
                    "version": version_id,
                    "at": observed_at,
                },
            )

    with case.sessions() as session, session.begin():
        ledger = build_analysis_need_ledger_in_transaction(
            session, owner_id=case.owner_id, start=start, end=case.now, cutoff_at=cutoff
        )
    assert ledger.analysis_status == "not_computable"
    assert ledger.metric_version == "analysis-candidate-v2"
    assert (ledger.candidate_count, ledger.unknown_count) == (2, 0)
    assert (ledger.matured_count, ledger.pending_observation_count) == (1, 1)
    assert (ledger.timely_valid_count, ledger.late_or_missing_count) == (0, 1)
    assert {row.content_version_id for row in ledger.rows} == {case.version_id, newer_version}
    assert {row.source_key for row in ledger.rows} == {"hackernews"}
    assert all(row.prompt_runtime_ids for row in ledger.rows)
    assert {row.started_at for row in ledger.rows} == {
        case.now - timedelta(minutes=50),
        case.now - timedelta(minutes=10),
    }

    backend_root = Path(__file__).resolve().parents[2]
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli",
            "jobs",
            "analysis-need-ledger",
            "--owner-id",
            str(case.owner_id),
            "--start",
            start.isoformat(),
            "--end",
            case.now.isoformat(),
            "--cutoff",
            cutoff.isoformat(),
        ],
        cwd=backend_root,
        env={
            **os.environ,
            "HOTKEY_DATABASE_URL": os.environ["HOTKEY_TEST_DATABASE_URL"],
            "PYTHONPATH": str(backend_root / "app"),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    exported = json.loads(process.stdout)
    assert exported["candidate_count"] == 2
    assert exported["metric_version"] == "analysis-candidate-v2"
    assert all(item["prompt_runtime_ids"] for item in exported["rows"])
    assert {item["content_version_id"] for item in exported["rows"]} == {
        str(case.version_id),
        str(newer_version),
    }

    call_id = uuid4()
    _seed_ai_call(case, call_id)
    with case.sessions() as session, session.begin():
        AnalysisService(session).persist_results_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            posts={case.version_id: _post(case)},
            results=(
                AnnotationWrite(
                    content_version_id=case.version_id,
                    relevant=False,
                    relevance_reason="受控测试: 不相关",
                    summary="受控测试",
                    ai_call_id=call_id,
                    status=AnnotationStatus.ANNOTATED,
                    result_state=AnnotationResultState.VALID,
                ),
            ),
            created_at=case.now,
        )
    with case.sessions() as session, session.begin():
        annotated = build_analysis_need_ledger_in_transaction(
            session, owner_id=case.owner_id, start=start, end=case.now, cutoff_at=cutoff
        )
    assert (annotated.matured_count, annotated.timely_valid_count) == (1, 1)
    assert annotated.late_or_missing_count == 0
    assert (
        next(
            row for row in annotated.rows if row.content_version_id == case.version_id
        ).first_valid_at
        == case.now
    )


def test_ledger_keeps_topic_and_rule_versions_as_distinct_identities(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    old = case.now - timedelta(days=4)
    _event(case, 1, "paused", "created", old)
    _event(case, 2, "active", "resumed", case.now - timedelta(minutes=90))
    _activate_prompt(case, case.now - timedelta(hours=2))
    other_topic = uuid4()
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, "
                "source_keys, created_at) VALUES "
                "(:topic, 2, :owner, '[\"HotKey\"]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, '[\"hackernews\"]'::jsonb, :at)"
            ),
            {
                "topic": case.topic_id,
                "owner": case.owner_id,
                "at": case.now - timedelta(minutes=45),
            },
        )
        session.execute(
            text("UPDATE monitor_topics SET current_version = 2 WHERE id = :topic"),
            {"topic": case.topic_id},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) VALUES "
                "(:topic, :owner, 'other', 'active', 'ready', 1, :old, :at)"
            ),
            {
                "topic": other_topic,
                "owner": case.owner_id,
                "old": old,
                "at": case.now - timedelta(minutes=30),
            },
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, "
                "source_keys, created_at) VALUES "
                "(:topic, 1, :owner, '[\"HotKey\"]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, '[\"hackernews\"]'::jsonb, :old)"
            ),
            {"topic": other_topic, "owner": case.owner_id, "old": old},
        )
        for sequence, status, at in (
            (1, "paused", old),
            (2, "active", case.now - timedelta(minutes=30)),
        ):
            session.execute(
                text(
                    "INSERT INTO monitor_topic_status_events "
                    "(id, owner_id, topic_id, event_sequence, topic_rule_version, "
                    "status, reason, occurred_at) VALUES "
                    "(:id, :owner, :topic, :sequence, 1, :status, :reason, :at)"
                ),
                {
                    "id": uuid4(),
                    "owner": case.owner_id,
                    "topic": other_topic,
                    "sequence": sequence,
                    "status": status,
                    "reason": "created" if sequence == 1 else "resumed",
                    "at": at,
                },
            )
    with case.sessions() as session, session.begin():
        ledger = build_analysis_need_ledger_in_transaction(
            session,
            owner_id=case.owner_id,
            start=case.now - timedelta(hours=1),
            end=case.now,
            cutoff_at=case.now + timedelta(hours=1),
        )
    assert ledger.unknown_count == 0
    assert ledger.candidate_count == 2
    assert {
        (row.content_version_id, row.topic_id, row.topic_rule_version) for row in ledger.rows
    } == {
        (case.version_id, case.topic_id, 2),
        (case.version_id, other_topic, 1),
    }


def test_ledger_distinguishes_known_disabled_window_from_runtime_gap(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    activation = case.now - timedelta(hours=2)
    resumed = case.now - timedelta(minutes=30)
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", case.now - timedelta(hours=1))
    _activate_prompt(case, activation, runtime=False)
    disabled_run = _runtime_session(
        case, started_at=activation, last_seen_at=resumed, ai_enabled=False
    )
    enabled_run = _runtime_session(
        case,
        started_at=resumed,
        last_seen_at=case.now + timedelta(hours=1),
        ai_enabled=True,
    )

    def ledger(end):
        with case.sessions() as session, session.begin():
            return build_analysis_need_ledger_in_transaction(
                session,
                owner_id=case.owner_id,
                start=case.now - timedelta(hours=1),
                end=end,
                cutoff_at=case.now + timedelta(hours=1),
            )

    off_window = ledger(resumed)
    assert (off_window.candidate_count, off_window.unknown_count) == (0, 0)
    assert off_window.rows == ()

    resumed_window = ledger(case.now)
    assert (resumed_window.candidate_count, resumed_window.unknown_count) == (1, 0)
    assert resumed_window.rows[0].started_at == resumed
    assert resumed_window.rows[0].prompt_runtime_ids == (disabled_run, enabled_run)

    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "UPDATE analysis_prompt_runtime_sessions SET last_seen_at = :seen "
                "WHERE id = :run_id"
            ),
            {"seen": case.now - timedelta(minutes=50), "run_id": disabled_run},
        )
    gap_window = ledger(case.now)
    assert (gap_window.candidate_count, gap_window.unknown_count) == (0, 1)
    assert gap_window.rows[0].reason == "prompt_runtime_history_gap"
    assert gap_window.rows[0].prompt_runtime_ids == (disabled_run,)


def test_ledger_marks_annotation_older_than_prompt_history_unknown(
    origin_case: AnalysisCase,
) -> None:
    case = origin_case
    _event(case, 1, "paused", "created", case.now - timedelta(days=4))
    _event(case, 2, "active", "resumed", case.now - timedelta(minutes=50))
    _activate_prompt(case, case.now - timedelta(minutes=30))
    call_id = uuid4()
    valid_at = case.now - timedelta(minutes=40)
    _seed_ai_call(case, call_id)
    with case.sessions() as session, session.begin():
        session.execute(
            text("UPDATE ai_calls SET created_at = :at WHERE id = :id"),
            {"at": valid_at, "id": call_id},
        )
        AnalysisService(session).persist_results_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            posts={case.version_id: _post(case)},
            results=(
                AnnotationWrite(
                    content_version_id=case.version_id,
                    relevant=False,
                    relevance_reason="受控测试: 不相关",
                    summary="受控测试",
                    ai_call_id=call_id,
                    status=AnnotationStatus.ANNOTATED,
                    result_state=AnnotationResultState.VALID,
                ),
            ),
            created_at=valid_at,
        )
    with case.sessions() as session, session.begin():
        ledger = build_analysis_need_ledger_in_transaction(
            session,
            owner_id=case.owner_id,
            start=case.now - timedelta(hours=1),
            end=case.now,
            cutoff_at=case.now + timedelta(hours=1),
        )
    assert (ledger.candidate_count, ledger.unknown_count) == (0, 1)
    assert ledger.rows[0].reason == "first_valid_precedes_need"
    assert ledger.rows[0].first_valid_at == valid_at
