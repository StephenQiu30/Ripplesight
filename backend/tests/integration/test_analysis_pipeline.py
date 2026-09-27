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
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.schemas import AnnotationResultState, AnnotationStatus, AnnotationWrite
from analysis.services import (
    AnalysisAnnotateExecutor,
    AnalysisService,
    analysis_operation_id,
    resolve_annotation_results,
)
from core.config import Settings
from jobs.execution import JobExecutionFailure
from jobs.schemas import JobAcceptedMessage
from jobs.services import OutboxEnvelope
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
        session.execute(
            text(
                "INSERT INTO identity_users "
                "(id, username, password_hash, credential_version, created_at, updated_at) "
                "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
            ),
            {"id": owner_id, "username": f"analysis-pipeline-{owner_id.hex}", "now": old},
        )
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
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:topic, 1, :owner, '[\"HotKey\"]'::jsonb, '[]'::jsonb, "
                "'[]'::jsonb, :now)"
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
                "(owner_id, content_id, post_content_id, created_at) "
                "VALUES (:owner, :comment, :post, :now)"
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
    case = AnalysisCase(sessions, owner_id, topic_id, content_id, version_id, comment_id, now)
    try:
        yield case
    finally:
        with sessions() as session, session.begin():
            session.execute(
                text("DELETE FROM content_records WHERE owner_id = :owner"), {"owner": owner_id}
            )
            session.execute(text("DELETE FROM jobs WHERE owner_id = :owner"), {"owner": owner_id})
            session.execute(
                text("DELETE FROM ai_calls WHERE owner_id = :owner"), {"owner": owner_id}
            )
            session.execute(
                text("DELETE FROM monitor_topic_versions WHERE created_by = :owner"),
                {"owner": owner_id},
            )
            session.execute(
                text("DELETE FROM monitor_topics WHERE owner_id = :owner"), {"owner": owner_id}
            )
            session.execute(
                text("DELETE FROM identity_users WHERE id = :owner"), {"owner": owner_id}
            )
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


def _scan(case: AnalysisCase) -> tuple[UUID, ...]:
    with case.sessions() as session, session.begin():
        return tuple(
            job.id
            for job in AnalysisService(session).enqueue_due_batches_in_transaction(
                owner_id=case.owner_id, topic_id=case.topic_id, now=case.now
            )
        )


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
            message = consumer.poll(1.0)
        assert message is not None and message.error() is None
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
