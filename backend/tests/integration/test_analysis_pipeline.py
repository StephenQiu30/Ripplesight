from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from confluent_kafka import Consumer, KafkaError, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import create_test_account

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.schemas import AnnotationResultState, AnnotationStatus, AnnotationWrite
from analysis.services import (
    AnalysisAnnotateExecutor,
    AnalysisService,
    analysis_operation_id,
    resolve_annotation_results,
)
from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from core.config import Settings
from evidence.schemas import DataClass, DeletionReason
from evidence.services import LifecycleService, SourceAccessPolicyService
from jobs.execution import JobExecutionFailure
from jobs.schemas import JobAcceptedMessage
from jobs.services import OutboxEnvelope
from sources.contracts import SourceCapability
from worker.app import create_job_message_handler
from worker.messaging import process_message, publish_outbox


@dataclass(frozen=True)
class AnalysisCase:
    sessions: sessionmaker[Session]
    owner_id: UUID
    topic_id: UUID
    content_id: UUID
    version_id: UUID
    comment_id: UUID
    now: datetime


@pytest.fixture
def analysis_case() -> Iterator[AnalysisCase]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    owner_id, topic_id, content_id, version_id, comment_id, source_job_id = (
        uuid4() for _ in range(6)
    )
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    old = now - timedelta(days=4)
    with sessions() as session, session.begin():
        create_test_account(session, owner_id=owner_id)
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner, 'HotKey', 'active', 'ready', 1, :now, :now)"
            ),
            {"id": topic_id, "owner": owner_id, "now": old},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, "
                "source_keys, created_at) "
                "VALUES (:topic, 1, :owner, '[\"HotKey\"]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, '[\"hackernews\"]'::jsonb, :now)"
            ),
            {"topic": topic_id, "owner": owner_id, "now": old},
        )
        session.execute(
            text(
                "INSERT INTO jobs "
                "(id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, created_at, updated_at) VALUES "
                "(:id, :owner, :operation, 'keyword.search', 'topic:seed', "
                "1, 'hackernews', 'search', '{}'::jsonb, :fingerprint, :now, :now)"
            ),
            {
                "id": source_job_id,
                "owner": owner_id,
                "operation": uuid4(),
                "fingerprint": source_job_id.bytes * 2,
                "now": old,
            },
        )
        for record_id, kind in ((content_id, "post"), (comment_id, "comment")):
            session.execute(
                text(
                    "INSERT INTO content_records "
                    "(id, owner_id, source_key, object_type, external_id, created_at) "
                    "VALUES (:id, :owner, 'hackernews', :kind, :external_id, :now)"
                ),
                {
                    "id": record_id,
                    "owner": owner_id,
                    "kind": kind,
                    "external_id": record_id.hex,
                    "now": old,
                },
            )
        session.execute(
            text(
                "INSERT INTO content_versions "
                "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                "title, body, created_at) VALUES "
                "(:id, :owner, :content, :fingerprint, 'full', 'source', "
                "'HotKey 产品讨论', '原正文', :now)"
            ),
            {
                "id": version_id,
                "owner": owner_id,
                "content": content_id,
                "fingerprint": version_id.bytes * 2,
                "now": old,
            },
        )
        _seed_comment_version(session, owner_id, comment_id, "原评论", old)
        session.execute(
            text(
                "INSERT INTO content_threads "
                "(owner_id, content_id, post_content_id, root_content_id, "
                "parent_relation_status, created_at) "
                "VALUES (:owner, :comment, :post, :comment, 'root', :now)"
            ),
            {"owner": owner_id, "comment": comment_id, "post": content_id, "now": old},
        )
        session.execute(
            text(
                "INSERT INTO content_observations "
                "(id, owner_id, content_id, job_id, source_operation_id, "
                "content_version_id, observed_at, received_at) VALUES "
                "(:id, :owner, :content, :job, :operation, :version, :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "content": content_id,
                "job": source_job_id,
                "operation": uuid4(),
                "version": version_id,
                "now": old,
            },
        )
        _track_analysis_observations(session, owner_id)
    case = AnalysisCase(sessions, owner_id, topic_id, content_id, version_id, comment_id, now)
    try:
        yield case
    finally:
        engine.dispose()


def _seed_comment_version(
    session: Session, owner_id: UUID, comment_id: UUID, body: str, at: datetime
) -> None:
    version_id = uuid4()
    session.execute(
        text(
            "INSERT INTO content_versions "
            "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
            "body, created_at) VALUES "
            "(:id, :owner, :content, :fingerprint, 'full', 'source', :body, :now)"
        ),
        {
            "id": version_id,
            "owner": owner_id,
            "content": comment_id,
            "fingerprint": version_id.bytes * 2,
            "body": body,
            "now": at,
        },
    )
    session.execute(
        text(
            "INSERT INTO content_observations "
            "(id, owner_id, content_id, job_id, source_operation_id, "
            "content_version_id, observed_at, received_at) "
            "SELECT :id, :owner, :content, id, :operation, :version, :at, :at FROM jobs "
            "WHERE owner_id=:owner AND source_key='hackernews' AND kind='keyword.search' LIMIT 1"
        ),
        {
            "id": uuid4(),
            "owner": owner_id,
            "content": comment_id,
            "operation": uuid4(),
            "version": version_id,
            "at": at,
        },
    )
    _track_analysis_observations(session, owner_id)


def _track_analysis_observations(session: Session, owner_id: UUID) -> None:
    rows = session.execute(
        text(
            "SELECT o.id, o.observed_at, j.source_key, j.source_capability "
            "FROM content_observations o "
            "JOIN jobs j ON j.id=o.job_id AND j.owner_id=o.owner_id WHERE o.owner_id=:owner "
            "AND NOT EXISTS (SELECT 1 FROM evidence_resources r WHERE r.owner_id=o.owner_id "
            "AND r.resource_type='content_observation' AND r.resource_id=o.id) "
            "ORDER BY o.observed_at"
        ),
        {"owner": owner_id},
    ).all()
    for row in rows:
        at = max(row.observed_at, SOURCE_PRESETS[row.source_key].reviewed_at)
        SourcePresetService(session, clock=lambda at=at: at).apply_in_transaction(
            owner_id=owner_id,
            preset=SOURCE_PRESETS[row.source_key],
        )
        admission = SourceAccessPolicyService(
            session, clock=lambda at=at: at
        ).admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=row.source_key,
            capability=SourceCapability(row.source_capability),
            data_class=DataClass.STRUCTURED,
            collected_at=row.observed_at,
            payload={"title": "HotKey fixture"},
        )
        LifecycleService(session, clock=lambda at=at: at).track_resource_in_transaction(
            owner_id=owner_id,
            resource_type="content_observation",
            resource_id=row.id,
            admission=admission,
            cleanup_targets=[],
        )


def _scan(case: AnalysisCase) -> tuple[UUID, ...]:
    with case.sessions() as session, session.begin():
        return tuple(
            job.id
            for job in AnalysisService(session).enqueue_due_batches_in_transaction(
                owner_id=case.owner_id, topic_id=case.topic_id, now=case.now
            )
        )


def _make_unreadable(case: AnalysisCase, content_id: UUID, mode: str) -> None:
    with case.sessions() as session:
        observation_id = session.scalar(
            text(
                "SELECT id FROM content_observations WHERE owner_id=:owner AND content_id=:content"
            ),
            {"owner": case.owner_id, "content": content_id},
        )
        assert observation_id is not None
        session.rollback()
        if mode == "deleted":
            LifecycleService(session, clock=lambda: case.now).request_deletion(
                owner_id=case.owner_id,
                operation_id=uuid4(),
                resource_type="content_observation",
                resource_id=observation_id,
                reason=DeletionReason.USER_REQUEST,
            )
        else:
            with session.begin():
                if mode == "untracked":
                    session.execute(
                        text(
                            "DELETE FROM evidence_resources "
                            "WHERE owner_id=:owner AND resource_id=:id"
                        ),
                        {"owner": case.owner_id, "id": observation_id},
                    )
                    return
                session.execute(
                    text(
                        "UPDATE evidence_resources SET expires_at=:now "
                        "WHERE owner_id=:owner AND resource_id=:id"
                    ),
                    {"now": case.now, "owner": case.owner_id, "id": observation_id},
                )


@pytest.mark.parametrize("mode", ["expired", "deleted", "untracked"])
@pytest.mark.parametrize("target", ["post", "comment"])
def test_analysis_scan_obeys_lifecycle(analysis_case: AnalysisCase, mode: str, target: str) -> None:
    case = analysis_case
    _make_unreadable(case, case.content_id if target == "post" else case.comment_id, mode)
    jobs = _scan(case)
    if target == "post":
        assert jobs == ()
    else:
        assert len(jobs) == 1
        with case.sessions() as session:
            scope = session.scalar(text("SELECT scope FROM jobs WHERE id=:id"), {"id": jobs[0]})
        assert json.loads(scope["prompt_items"])[0]["comments"] == []


@pytest.mark.parametrize("mode", ["expired", "deleted", "untracked"])
@pytest.mark.parametrize("target", ["post", "comment"])
def test_queued_analysis_rechecks_frozen_evidence(
    analysis_case: AnalysisCase, mode: str, target: str
) -> None:
    case = analysis_case
    (job_id,) = _scan(case)
    with case.sessions() as session:
        operation_id = session.scalar(
            text("SELECT operation_id FROM jobs WHERE id=:id"), {"id": job_id}
        )
    _make_unreadable(case, case.content_id if target == "post" else case.comment_id, mode)
    executor = AnalysisAnnotateExecutor(
        case.sessions,
        Settings(database_url=os.environ["HOTKEY_TEST_DATABASE_URL"]),
        clock=lambda: case.now,
    )
    message = JobAcceptedMessage(
        schema_version=2,
        message_id=uuid4(),
        event_type="job.accepted.v2",
        job_id=job_id,
        owner_id=case.owner_id,
        operation_id=operation_id,
        kind="analysis.annotate",
        configuration_ref=f"topic:{case.topic_id}",
        configuration_version=1,
    )
    with pytest.raises(JobExecutionFailure) as failure:
        executor._load_execution(message)
    assert failure.value.error_code == (
        "analysis_content_missing" if target == "post" else "analysis_comment_missing"
    )
    with case.sessions() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM ai_calls WHERE owner_id=:owner"),
                {"owner": case.owner_id},
            )
            == 0
        )


def test_analysis_scan_uses_selected_source_or_exact_hotlist_topic_version(
    analysis_case: AnalysisCase,
) -> None:
    case = analysis_case
    old = case.now - timedelta(days=4)
    with case.sessions() as session, session.begin():

        def seed_job(
            source_key: str, kind: str, capability: str, at: datetime
        ) -> tuple[UUID, UUID]:
            job_id, operation_id = uuid4(), uuid4()
            session.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, owner_id, operation_id, kind, configuration_ref, "
                    "configuration_version, source_key, source_capability, scope, "
                    "request_fingerprint, created_at, updated_at) VALUES "
                    "(:id, :owner, :operation, :kind, 'topic:seed', 1, :source, "
                    ":capability, '{}'::jsonb, :fingerprint, :at, :at)"
                ),
                {
                    "id": job_id,
                    "owner": case.owner_id,
                    "operation": operation_id,
                    "kind": kind,
                    "source": source_key,
                    "capability": capability,
                    "fingerprint": job_id.bytes * 2,
                    "at": at,
                },
            )
            return job_id, operation_id

        def seed_post(
            source_key: str,
            job_id: UUID,
            at: datetime,
            *,
            content_id: UUID | None = None,
            existing: bool = False,
        ) -> tuple[UUID, UUID]:
            content_id = content_id or uuid4()
            version_id = uuid4()
            if not existing:
                session.execute(
                    text(
                        "INSERT INTO content_records "
                        "(id, owner_id, source_key, object_type, external_id, created_at) "
                        "VALUES (:id, :owner, :source, 'post', :external_id, :at)"
                    ),
                    {
                        "id": content_id,
                        "owner": case.owner_id,
                        "source": source_key,
                        "external_id": content_id.hex,
                        "at": at,
                    },
                )
            session.execute(
                text(
                    "INSERT INTO content_versions "
                    "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                    "title, body, created_at) VALUES "
                    "(:id, :owner, :content, :fingerprint, 'full', 'source', "
                    "'HotKey 讨论', '待分析正文', :at)"
                ),
                {
                    "id": version_id,
                    "owner": case.owner_id,
                    "content": content_id,
                    "fingerprint": version_id.bytes * 2,
                    "at": at,
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
                    "content": content_id,
                    "job": job_id,
                    "operation": uuid4(),
                    "version": version_id,
                    "at": at,
                },
            )
            return content_id, version_id

        def seed_hotlist_snapshot(
            job_id: UUID,
            operation_id: UUID,
            at: datetime,
            entries: tuple[tuple[UUID, list[str]], ...],
        ) -> None:
            snapshot_id = uuid4()
            session.execute(
                text(
                    "INSERT INTO collection_due_windows "
                    "(id, owner_id, schedule_key, source_key, capability, due_at, "
                    "window_start, window_end, admission_state, operation_id, job_id, recorded_at) "
                    "VALUES (:id, :owner, :schedule, 'hotlist_36kr', 'hotlist', :at, "
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
                    "INSERT INTO hotlist_snapshots "
                    "(id, owner_id, source_key, job_id, operation_id, observed_at, entry_count) "
                    "VALUES (:id, :owner, 'hotlist_36kr', :job, :operation, :at, :count)"
                ),
                {
                    "id": snapshot_id,
                    "owner": case.owner_id,
                    "job": job_id,
                    "operation": operation_id,
                    "at": at,
                    "count": len(entries),
                },
            )
            session.execute(
                text(
                    "INSERT INTO hotlist_entries "
                    "(snapshot_id, owner_id, rank, title, url, content_id, matched_topic_ids) "
                    "VALUES (:snapshot, :owner, :rank, 'HotKey 讨论', :url, :content, "
                    "CAST(:matches AS jsonb))"
                ),
                [
                    {
                        "snapshot": snapshot_id,
                        "owner": case.owner_id,
                        "rank": rank,
                        "url": f"https://example.com/{content_id}",
                        "content": content_id,
                        "matches": json.dumps(matches),
                    }
                    for rank, (content_id, matches) in enumerate(entries, 1)
                ],
            )

        google_job_id, _ = seed_job("google_news", "keyword.search", "search", old)
        _, google_version_id = seed_post("google_news", google_job_id, old)

        matched_hotlist_content_id = uuid4()
        hotlist_job_id, hotlist_operation_id = seed_job(
            "hotlist_36kr", "source.hotlist", "hotlist", old
        )
        _, matched_version_id = seed_post(
            "hotlist_36kr", hotlist_job_id, old, content_id=matched_hotlist_content_id
        )
        unmatched_content_id, unmatched_version_id = seed_post("hotlist_36kr", hotlist_job_id, old)
        seed_hotlist_snapshot(
            hotlist_job_id,
            hotlist_operation_id,
            old,
            (
                (matched_hotlist_content_id, [str(case.topic_id)]),
                (unmatched_content_id, [str(uuid4())]),
            ),
        )
        later = old + timedelta(minutes=30)
        later_job_id, later_operation_id = seed_job(
            "hotlist_36kr", "source.hotlist", "hotlist", later
        )
        _, later_version_id = seed_post(
            "hotlist_36kr",
            later_job_id,
            later,
            content_id=matched_hotlist_content_id,
            existing=True,
        )
        seed_hotlist_snapshot(
            later_job_id, later_operation_id, later, ((matched_hotlist_content_id, []),)
        )
        _track_analysis_observations(session, case.owner_id)

    job_ids = _scan(case)
    assert len(job_ids) == 1
    with case.sessions() as session, session.begin():
        scope = session.execute(
            text("SELECT scope FROM jobs WHERE id = :id"), {"id": job_ids[0]}
        ).scalar_one()
    scoped_version_ids = set(json.loads(scope["content_version_ids"]))
    assert scoped_version_ids == {
        str(case.version_id),
        str(matched_version_id),
    }
    assert not {google_version_id, unmatched_version_id, later_version_id} & {
        UUID(item) for item in scoped_version_ids
    }


def _seed_ai_call(case: AnalysisCase, call_id: UUID) -> None:
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, "
                "output_tokens, reasoning_output_tokens, duration_ms, created_at) "
                "VALUES (:id, :owner, 'analysis.annotate', 'test', 'test-model', :prompt, "
                ":fingerprint, 'succeeded', 0, 0, 0, 0, 0, :now)"
            ),
            {
                "id": call_id,
                "owner": case.owner_id,
                "prompt": ANALYSIS_PROMPT_VERSION,
                "fingerprint": call_id.bytes * 2,
                "now": case.now,
            },
        )


def test_old_backlog_concurrent_scans_freeze_comments_and_accept_once(
    analysis_case: AnalysisCase,
) -> None:
    case = analysis_case
    with ThreadPoolExecutor(max_workers=2) as pool:
        scans = tuple(pool.map(lambda _: _scan(case), range(2)))
    assert {job_id for scan in scans for job_id in scan}
    with case.sessions() as session, session.begin():
        rows = session.execute(
            text(
                "SELECT id, operation_id, scope FROM jobs "
                "WHERE owner_id = :owner AND kind = 'analysis.annotate'"
            ),
            {"owner": case.owner_id},
        ).all()
        assert len(rows) == 1
        assert (
            session.scalar(
                text("SELECT count(*) FROM outbox_messages WHERE aggregate_id = :job"),
                {"job": rows[0].id},
            )
            == 1
        )
        frozen = rows[0].scope["prompt_items"]
        assert "原评论" in frozen
    with case.sessions() as session, session.begin():
        _seed_comment_version(session, case.owner_id, case.comment_id, "后续更新评论", case.now)
    executor = AnalysisAnnotateExecutor(
        case.sessions,
        Settings(database_url=os.environ["HOTKEY_TEST_DATABASE_URL"]),
        clock=lambda: case.now,
    )
    message = JobAcceptedMessage(
        schema_version=2,
        message_id=uuid4(),
        event_type="job.accepted.v2",
        job_id=rows[0].id,
        owner_id=case.owner_id,
        operation_id=rows[0].operation_id,
        kind="analysis.annotate",
        configuration_ref=f"topic:{case.topic_id}",
        configuration_version=1,
    )
    _, _, _, items = executor._load_execution(message)
    assert items[0].comments == ("原评论",)
    assert _scan(case) == ()
    with case.sessions() as session, session.begin():
        legacy_scope = dict(rows[0].scope)
        legacy_items = json.loads(legacy_scope["prompt_items"])
        for item in legacy_items:
            item.pop("comment_version_ids")
        legacy_scope["prompt_items"] = json.dumps(legacy_items)
        session.execute(
            text("UPDATE jobs SET scope=CAST(:scope AS jsonb) WHERE id=:id"),
            {"scope": json.dumps(legacy_scope), "id": rows[0].id},
        )
    with pytest.raises(JobExecutionFailure) as legacy_failure:
        executor._load_execution(message)
    assert legacy_failure.value.error_code == "analysis_frozen_input_missing"
    with case.sessions() as session, session.begin():
        session.execute(text("UPDATE jobs SET status='failed' WHERE id=:id"), {"id": rows[0].id})
    assert len(_scan(case)) == 1


def test_invalid_annotation_gets_one_retry_then_queryable_failure(
    analysis_case: AnalysisCase,
) -> None:
    case = analysis_case
    initial = _scan(case)
    assert len(initial) == 1
    first_call = uuid4()
    _seed_ai_call(case, first_call)
    with case.sessions() as session, session.begin():
        session.execute(
            text("UPDATE jobs SET status = 'partially_succeeded' WHERE id = :job"),
            {"job": initial[0]},
        )
        post = _post(case)
        AnalysisService(session).persist_results_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            posts={case.version_id: post},
            results=(
                AnnotationWrite(
                    content_version_id=case.version_id,
                    ai_call_id=first_call,
                    status=AnnotationStatus.UNANALYZED,
                    result_state=AnnotationResultState.INVALID,
                    error_code="analysis_output_missing",
                ),
            ),
            created_at=case.now,
        )
    retry = _scan(case)
    assert len(retry) == 1 and retry != initial
    assert _scan(case) == ()

    second_call = uuid4()
    _seed_ai_call(case, second_call)
    result = resolve_annotation_results(
        expected_content_version_ids=(case.version_id,),
        raw_items=(),
        ai_call_id=second_call,
        retry_index=1,
    )[0]
    with case.sessions() as session, session.begin():
        AnalysisService(session).persist_results_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            posts={case.version_id: _post(case)},
            results=(result,),
            created_at=case.now + timedelta(seconds=1),
        )
    with case.sessions() as session, session.begin():
        state, error = session.execute(
            text(
                "SELECT result_state, error_code FROM content_annotations WHERE owner_id = :owner"
            ),
            {"owner": case.owner_id},
        ).one()
    assert (state, error) == ("failed", "analysis_invalid_exhausted")
    assert _scan(case) == ()


def test_terminal_legacy_job_without_frozen_input_gets_new_frozen_job(
    analysis_case: AnalysisCase,
) -> None:
    case = analysis_case
    legacy_id = uuid4()
    operation_id = analysis_operation_id(
        topic_id=case.topic_id,
        topic_rule_version=1,
        content_version_ids=(case.version_id,),
        prompt_version=ANALYSIS_PROMPT_VERSION,
    )
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO jobs "
                "(id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, scope, request_fingerprint, status, "
                "created_at, updated_at) VALUES "
                "(:id, :owner, :operation, 'analysis.annotate', :ref, 1, "
                "CAST(:scope AS jsonb), :fingerprint, 'failed', :now, :now)"
            ),
            {
                "id": legacy_id,
                "owner": case.owner_id,
                "operation": operation_id,
                "ref": f"topic:{case.topic_id}",
                "scope": json.dumps(
                    {
                        "topic_id": str(case.topic_id),
                        "topic_rule_version": 1,
                        "prompt_version": ANALYSIS_PROMPT_VERSION,
                        "content_version_ids": f'["{case.version_id}"]',
                    }
                ),
                "fingerprint": legacy_id.bytes * 2,
                "now": case.now,
            },
        )

    executor = AnalysisAnnotateExecutor(
        case.sessions,
        Settings(database_url=os.environ["HOTKEY_TEST_DATABASE_URL"]),
        clock=lambda: case.now,
    )
    legacy_message = JobAcceptedMessage(
        schema_version=2,
        message_id=uuid4(),
        event_type="job.accepted.v2",
        job_id=legacy_id,
        owner_id=case.owner_id,
        operation_id=operation_id,
        kind="analysis.annotate",
        configuration_ref=f"topic:{case.topic_id}",
        configuration_version=1,
    )
    with pytest.raises(JobExecutionFailure) as missing_input:
        executor._load_execution(legacy_message)
    assert missing_input.value.error_code == "analysis_frozen_input_missing"

    replacement = _scan(case)

    assert len(replacement) == 1 and replacement[0] != legacy_id
    assert _scan(case) == ()


def test_analysis_outbox_crosses_kafka_and_worker_fails_closed_without_model(
    analysis_case: AnalysisCase,
) -> None:
    bootstrap = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if bootstrap is None:
        pytest.skip("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS is required")
    case = analysis_case
    job_ids = _scan(case)
    assert len(job_ids) == 1
    with case.sessions() as session:
        outbox = session.execute(
            text(
                "SELECT id, topic, message_key, event_type, payload "
                "FROM outbox_messages WHERE aggregate_id = :job"
            ),
            {"job": job_ids[0]},
        ).one()
    topic = f"hotkey.tests.plan040.{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    producer = Producer({"bootstrap.servers": bootstrap})
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"hotkey-tests-plan040-{uuid4().hex}",
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    try:
        admin.create_topics([NewTopic(topic, 1, 1)])[topic].result(10)
        consumer.subscribe([topic])
        envelope = OutboxEnvelope(
            message_id=outbox.id,
            topic=outbox.topic,
            message_key=outbox.message_key,
            event_type=outbox.event_type,
            schema_version=2,
            payload=outbox.payload,
        )
        publish_outbox(producer, replace(envelope, topic=topic), timeout_seconds=10)
        deadline = time.monotonic() + 15
        message = None
        while time.monotonic() < deadline and message is None:
            candidate = consumer.poll(1.0)
            if candidate is None:
                continue
            error = candidate.error()
            if error is not None:
                # Kafka may report a newly created topic as unknown until its
                # metadata reaches this consumer, even after AdminClient acks.
                if error.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    continue
                raise AssertionError(f"Kafka consumer error: {error.code()}")
            message = candidate
        assert message is not None
        executor = AnalysisAnnotateExecutor(
            case.sessions,
            Settings(database_url=os.environ["HOTKEY_TEST_DATABASE_URL"], ai_enabled=False),
            clock=lambda: case.now,
        )
        handler = create_job_message_handler(
            case.sessions,
            {"analysis.annotate": lambda context: executor.execute(context.message).completion},
            worker_id="plan040-kafka-test",
            lease_seconds=60,
            clock=lambda: case.now,
        )
        process_message(consumer, message, {topic: handler})
        handler(message)  # Replayed delivery must not generate another execution.
        with case.sessions() as session:
            status, error_code = session.execute(
                text("SELECT status, last_error_code FROM jobs WHERE id = :job"),
                {"job": job_ids[0]},
            ).one()
            call_count = session.scalar(
                text("SELECT count(*) FROM ai_calls WHERE owner_id = :owner"),
                {"owner": case.owner_id},
            )
        assert (status, error_code, call_count) == ("failed", "analysis_unavailable", 0)
    finally:
        consumer.close()
        admin.delete_topics([topic], operation_timeout=10)[topic].result(10)


def _post(case: AnalysisCase):
    from content.schemas import AnalysisPostContentView

    return AnalysisPostContentView(
        content_id=case.content_id,
        content_version_id=case.version_id,
        title="HotKey 产品讨论",
        body="原正文",
    )
