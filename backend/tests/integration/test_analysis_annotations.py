from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import create_test_account
from tests.integration.test_analysis_pipeline import _track_analysis_observations

from analysis.models import ContentAnnotation
from analysis.reads import load_content_annotations_in_transaction
from analysis.schemas import (
    AnalysisJobScope,
    AnalysisPromptItem,
    AnnotationResultState,
    AnnotationStatus,
    AnnotationWrite,
)
from analysis.services import AnalysisService, analysis_operation_id
from content.schemas import AnalysisPostContentView
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService, load_job_execution_configuration


def _seed_legacy_analysis_job(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    posts: tuple[AnalysisPostContentView, ...],
    now: datetime,
    rule_version: int = 1,
    prompt_version: str = "v1",
    failed: bool = False,
) -> UUID:
    """Persist an original complete historical Job, without invoking a provider."""
    scope = AnalysisJobScope(
        topic_id=topic_id,
        topic_rule_version=rule_version,
        prompt_version=prompt_version,
        content_version_ids=tuple(post.content_version_id for post in posts),
        prompt_items=tuple(
            AnalysisPromptItem(
                content_id=post.content_id,
                content_version_id=post.content_version_id,
                title=post.title,
                body=post.body,
                comments=(),
                comment_version_ids=(),
            )
            for post in posts
        ),
        retry_index=int(failed),
    )
    accepted = JobService(session, clock=lambda: now).accept_in_transaction(
        owner_id=owner_id,
        command=JobAcceptanceInput(
            operation_id=analysis_operation_id(
                topic_id=topic_id,
                topic_rule_version=rule_version,
                content_version_ids=scope.content_version_ids,
                prompt_version=prompt_version,
                retry_index=scope.retry_index,
            ),
            kind="analysis.annotate",
            observation=JobObservationContext(
                configuration_ref=f"topic:{topic_id}",
                configuration_version=rule_version,
            ),
            scope=scope.to_job_scope(),
        ),
    )
    if failed:
        # A controlled recorded failure, not a successful AI call or readable summary.
        session.execute(
            text(
                "UPDATE jobs SET status='failed', last_error_code='analysis_timeout', "
                "last_error_category='transient', last_error_at=:now, "
                "next_action='retry later', updated_at=:now WHERE id=:id AND owner_id=:owner"
            ),
            {"id": accepted.id, "owner": owner_id, "now": now},
        )
    return accepted.id


def _bind_original_call(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    post: AnalysisPostContentView,
    result: AnnotationWrite,
    rule_version: int,
    now: datetime,
) -> AnnotationWrite:
    call = session.execute(
        text("SELECT job_id, status FROM ai_calls WHERE owner_id=:owner AND id=:id"),
        {"owner": owner_id, "id": result.ai_call_id},
    ).one_or_none()
    if call is None:
        return result  # Existing storage test deliberately records an unavailable diagnostic call.
    if call.job_id is not None:
        configuration = load_job_execution_configuration(session, job_id=call.job_id)
        assert configuration is not None
        original = AnalysisJobScope.from_job_scope(configuration.scope)
        if original.topic_rule_version == rule_version:
            return result
        # Another rule is another controlled model invocation; preserve the old call's Job.
        replacement = uuid4()
        session.execute(
            text(
                "INSERT INTO ai_calls (id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, output_tokens, "
                "reasoning_output_tokens, duration_ms, created_at) "
                "SELECT :replacement, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, output_tokens, "
                "reasoning_output_tokens, duration_ms, :now FROM ai_calls "
                "WHERE owner_id=:owner AND id=:id"
            ),
            {"replacement": replacement, "now": now, "owner": owner_id, "id": result.ai_call_id},
        )
        result = result.model_copy(update={"ai_call_id": replacement})
    job_id = _seed_legacy_analysis_job(
        session,
        owner_id=owner_id,
        topic_id=topic_id,
        posts=(post,),
        rule_version=rule_version,
        now=now,
        failed=call.status == "failed",
    )
    session.execute(
        text("UPDATE ai_calls SET job_id=:job WHERE owner_id=:owner AND id=:id"),
        {"job": job_id, "owner": owner_id, "id": result.ai_call_id},
    )
    return result


@pytest.fixture
def annotation_context() -> Iterator[
    tuple[sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime]
]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    owner_id, topic_id, content_id, version_id, source_job_id, observation_id = (
        uuid4() for _ in range(6)
    )
    invalid_call_id, valid_call_id = uuid4(), uuid4()
    now = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
    with sessions() as connection, connection.begin():
        create_test_account(connection, owner_id=owner_id)
        connection.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner_id, 'annotation topic', 'paused', "
                "'pending_source_selection', 2, :now, :now)"
            ),
            {"id": topic_id, "owner_id": owner_id, "now": now},
        )
        for rule_version in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:topic_id, :version, :owner_id, '[\"title\"]'::jsonb, '[]'::jsonb, "
                    "'[]'::jsonb, :now)"
                ),
                {
                    "topic_id": topic_id,
                    "version": rule_version,
                    "owner_id": owner_id,
                    "now": now,
                },
            )
        connection.execute(
            text(
                "INSERT INTO content_records "
                "(id, owner_id, source_key, object_type, external_id, created_at) "
                "VALUES (:id, :owner_id, 'hackernews', 'post', :external_id, :now)"
            ),
            {
                "id": content_id,
                "owner_id": owner_id,
                "external_id": str(content_id),
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO content_versions "
                "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                "title, created_at) VALUES "
                "(:id, :owner_id, :content_id, :fingerprint, 'full', 'source', 'title', :now)"
            ),
            {
                "id": version_id,
                "owner_id": owner_id,
                "content_id": content_id,
                "fingerprint": version_id.bytes * 2,
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO jobs (id,owner_id,operation_id,kind,configuration_ref,"
                "configuration_version,source_key,source_capability,scope,request_fingerprint,"
                "created_at,updated_at) VALUES (:id,:owner,:operation,'keyword.search',"
                "'topic:seed',1,'hackernews','search','{}'::jsonb,:fingerprint,:now,:now)"
            ),
            {
                "id": source_job_id,
                "owner": owner_id,
                "operation": uuid4(),
                "fingerprint": source_job_id.bytes * 2,
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO content_observations (id,owner_id,content_id,content_version_id,"
                "job_id,source_operation_id,observed_at,received_at) "
                "VALUES (:id,:owner,:content,:version,:job,:operation,:now,:now)"
            ),
            {
                "id": observation_id,
                "owner": owner_id,
                "content": content_id,
                "version": version_id,
                "job": source_job_id,
                "operation": uuid4(),
                "now": now,
            },
        )
        _track_analysis_observations(connection, owner_id)
        for call_id in (invalid_call_id, valid_call_id):
            connection.execute(
                text(
                    "INSERT INTO ai_calls "
                    "(id, owner_id, purpose, provider, model, prompt_version, "
                    "input_fingerprint, status, input_tokens, cached_input_tokens, "
                    "output_tokens, reasoning_output_tokens, duration_ms, created_at) VALUES "
                    "(:id, :owner_id, 'analysis.annotate', 'test', 'test-model', 'v1', "
                    ":fingerprint, 'succeeded', 0, 0, 0, 0, 0, :now)"
                ),
                {"id": call_id, "owner_id": owner_id, "fingerprint": b"a" * 32, "now": now},
            )
    post = AnalysisPostContentView(
        content_id=content_id,
        content_version_id=version_id,
        observation_id=observation_id,
        title="title",
        body=None,
    )
    try:
        yield sessions, owner_id, topic_id, post, invalid_call_id, valid_call_id, now
    finally:
        engine.dispose()


def _persist(
    context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
    result: AnnotationWrite,
    *,
    rule_version: int = 1,
    at: datetime | None = None,
) -> None:
    sessions, owner_id, topic_id, post, _, _, now = context
    with sessions() as session, session.begin():
        result = _bind_original_call(
            session,
            owner_id=owner_id,
            topic_id=topic_id,
            post=post,
            result=result,
            rule_version=rule_version,
            now=at or now,
        )
        AnalysisService(session).persist_results_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=rule_version,
            prompt_version="v1",
            posts={post.content_version_id: post},
            results=(result,),
            created_at=at or now,
        )


def test_collection_analysis_batch_uses_persisted_prompt_and_rejects_ambiguity(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    sessions, owner_id, topic_id, post, _, valid_call_id, now = annotation_context
    collection_job_id = uuid4()
    with sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, status, created_at, updated_at) VALUES "
                "(:id, :owner, :operation, 'keyword.search', :ref, 1, 'bilibili', "
                "'search', '{}'::jsonb, :fingerprint, 'queued', :now, :now)"
            ),
            {
                "id": collection_job_id,
                "owner": owner_id,
                "operation": uuid4(),
                "ref": f"topic:{topic_id}",
                "fingerprint": b"c" * 32,
                "now": now,
            },
        )
    _persist(
        annotation_context,
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=valid_call_id,
            status=AnnotationStatus.ANNOTATED,
            result_state=AnnotationResultState.VALID,
            relevant=False,
            relevance_reason="不同主题",
            summary="内容讨论另一主题",
        ),
    )
    targets = {collection_job_id: (topic_id, 1, (post.content_version_id,))}
    with sessions() as session, session.begin():
        counts = AnalysisService(session).collection_analysis_counts_in_transaction(
            owner_id=owner_id, targets_by_job=targets
        )
        foreign = AnalysisService(session).collection_analysis_counts_in_transaction(
            owner_id=uuid4(), targets_by_job=targets
        )
    count = counts[collection_job_id]
    assert count is not None
    assert count.annotated_count == 1
    assert foreign[collection_job_id] is None

    with sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO jobs (id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, scope, request_fingerprint, status, created_at, "
                "updated_at) VALUES (:id, :owner, :operation, 'analysis.annotate', :ref, "
                "1, CAST(:scope AS jsonb), :fingerprint, 'queued', :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner": owner_id,
                "operation": uuid4(),
                "ref": f"topic:{topic_id}",
                "scope": json.dumps(
                    {
                        "topic_id": str(topic_id),
                        "topic_rule_version": 1,
                        "prompt_version": "v2",
                        "content_version_ids": json.dumps([str(post.content_version_id)]),
                    }
                ),
                "fingerprint": b"d" * 32,
                "now": now,
            },
        )
    with sessions() as session, session.begin():
        ambiguous = AnalysisService(session).collection_analysis_counts_in_transaction(
            owner_id=owner_id, targets_by_job=targets
        )
    assert ambiguous[collection_job_id] is None


def test_concurrent_invalid_to_valid_keeps_audit_and_rejects_old_failure(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    context = annotation_context
    sessions, owner_id, topic_id, post, invalid_call_id, valid_call_id, now = context
    invalid = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=invalid_call_id,
        status=AnnotationStatus.UNANALYZED,
        result_state=AnnotationResultState.INVALID,
        error_code="analysis_output_missing",
    )
    valid = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=valid_call_id,
        status=AnnotationStatus.ANNOTATED,
        result_state=AnnotationResultState.VALID,
        relevant=False,
        relevance_reason="不同主题",
        summary="内容讨论另一主题",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: _persist(context, invalid), range(2)))
    with sessions() as session, session.begin():
        counts = AnalysisService(session).window_annotation_counts_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=1,
            prompt_version="v1",
            content_version_ids=(post.content_version_id,),
        )
    assert (counts.annotated_count, counts.abnormal_count) == (0, 1)

    _persist(context, valid, at=now + timedelta(minutes=1))
    _persist(context, invalid, at=now)
    _persist(context, invalid, rule_version=2, at=now + timedelta(minutes=2))
    with sessions() as session, session.begin():
        rows = session.scalars(
            select(ContentAnnotation)
            .where(ContentAnnotation.owner_id == owner_id)
            .order_by(ContentAnnotation.topic_rule_version)
        ).all()
        counts = AnalysisService(session).window_annotation_counts_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=1,
            prompt_version="v1",
            content_version_ids=(post.content_version_id,),
        )
    assert len(rows) == 2
    assert rows[0].result_state == "valid"
    assert rows[0].relevant is False
    assert rows[0].ai_call_id == valid_call_id
    assert [
        (entry["result_state"], entry["error_code"]) for entry in rows[0].diagnostic_history
    ] == [("invalid", "analysis_output_missing")]
    assert rows[1].result_state == "invalid"
    assert (counts.annotated_count, counts.abnormal_count, counts.failed_count) == (1, 0, 0)


def test_postgresql_rejects_fake_valid_annotation(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    sessions, owner_id, topic_id, post, _, valid_call_id, now = annotation_context
    with sessions() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(
            text(
                "INSERT INTO content_annotations "
                "(id, owner_id, content_id, content_version_id, topic_id, "
                "topic_rule_version, prompt_version, ai_call_id, status, result_state, "
                "relevant, viewpoints, created_at, updated_at) VALUES "
                "(:id, :owner_id, :content_id, :version_id, :topic_id, 1, 'v1', "
                ":call_id, 'annotated', 'valid', TRUE, '[]'::jsonb, :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner_id": owner_id,
                "content_id": post.content_id,
                "version_id": post.content_version_id,
                "topic_id": topic_id,
                "call_id": valid_call_id,
                "now": now,
            },
        )


def test_postgresql_rejects_valid_annotation_without_first_valid_time(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    sessions, owner_id, topic_id, post, _, valid_call_id, now = annotation_context
    with sessions() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(
            text(
                "INSERT INTO content_annotations "
                "(id, owner_id, content_id, content_version_id, topic_id, "
                "topic_rule_version, prompt_version, relevant, relevance_reason, "
                "summary, ai_call_id, status, result_state, created_at, updated_at) VALUES "
                "(:id, :owner_id, :content_id, :version_id, :topic_id, 1, 'v1', "
                "FALSE, '不同主题', '受控摘要', :call_id, 'annotated', 'valid', :now, :now)"
            ),
            {
                "id": uuid4(),
                "owner_id": owner_id,
                "content_id": post.content_id,
                "version_id": post.content_version_id,
                "topic_id": topic_id,
                "call_id": valid_call_id,
                "now": now,
            },
        )


def test_failed_call_upgrades_to_valid_and_old_failure_cannot_replace_it(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    context = annotation_context
    sessions, owner_id, topic_id, post, _, valid_call_id, now = context
    failed_call_id = uuid4()
    with sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, failure_code, input_tokens, "
                "cached_input_tokens, output_tokens, reasoning_output_tokens, "
                "duration_ms, created_at) VALUES "
                "(:id, :owner_id, 'analysis.annotate', 'test', 'test-model', 'v1', "
                ":fingerprint, 'failed', 'timeout', 0, 0, 0, 0, 0, :now)"
            ),
            {"id": failed_call_id, "owner_id": owner_id, "fingerprint": b"b" * 32, "now": now},
        )
    failed = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=failed_call_id,
        status=AnnotationStatus.UNANALYZED,
        result_state=AnnotationResultState.FAILED,
        error_code="analysis_timeout",
    )
    valid = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=valid_call_id,
        status=AnnotationStatus.ANNOTATED,
        result_state=AnnotationResultState.VALID,
        relevant=True,
        relevance_reason="正文直接讨论该主题",
        sentiment="neutral",
        summary="内容讨论该主题",
    )
    _persist(context, failed)
    with sessions() as session, session.begin():
        before = AnalysisService(session).window_annotation_counts_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=1,
            prompt_version="v1",
            content_version_ids=(post.content_version_id,),
        )
    assert (before.failed_count, before.annotated_count) == (1, 0)
    _persist(context, valid, at=now + timedelta(minutes=1))
    _persist(context, failed, at=now)
    with sessions() as session:
        row = session.scalar(
            select(ContentAnnotation).where(ContentAnnotation.owner_id == owner_id)
        )
    assert row is not None
    assert row.result_state == "valid"
    assert row.ai_call_id == valid_call_id
    assert row.diagnostic_history[0]["error_code"] == "analysis_timeout"
    assert len(row.diagnostic_history) == 1


def test_first_valid_time_survives_duplicate_and_later_diagnostic(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    context = annotation_context
    sessions, owner_id, _, post, invalid_call_id, valid_call_id, now = context
    invalid = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=invalid_call_id,
        status=AnnotationStatus.UNANALYZED,
        result_state=AnnotationResultState.INVALID,
        error_code="analysis_output_missing",
    )
    valid = AnnotationWrite(
        content_version_id=post.content_version_id,
        ai_call_id=valid_call_id,
        status=AnnotationStatus.ANNOTATED,
        result_state=AnnotationResultState.VALID,
        relevant=False,
        relevance_reason="不同主题",
        summary="内容讨论另一主题",
    )
    _persist(context, invalid)
    with sessions() as session:
        pending = session.scalar(
            select(ContentAnnotation).where(ContentAnnotation.owner_id == owner_id)
        )
        assert pending is not None
        assert pending.first_valid_at is None
    _persist(context, valid, at=now + timedelta(minutes=1))
    _persist(context, valid, at=now + timedelta(minutes=2))
    _persist(
        context,
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=uuid4(),
            status=AnnotationStatus.UNANALYZED,
            result_state=AnnotationResultState.FAILED,
            error_code="analysis_timeout",
        ),
        at=now + timedelta(minutes=3),
    )
    second_valid_call_id = uuid4()
    with sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, "
                "input_fingerprint, status, input_tokens, cached_input_tokens, "
                "output_tokens, reasoning_output_tokens, duration_ms, created_at) VALUES "
                "(:id, :owner_id, 'analysis.annotate', 'test', 'test-model', 'v1', "
                ":fingerprint, 'succeeded', 0, 0, 0, 0, 0, :now)"
            ),
            {
                "id": second_valid_call_id,
                "owner_id": owner_id,
                "fingerprint": b"c" * 32,
                "now": now + timedelta(minutes=4),
            },
        )
    _persist(
        context,
        valid.model_copy(update={"ai_call_id": second_valid_call_id}),
        at=now + timedelta(minutes=4),
    )
    with sessions() as session:
        row = session.execute(
            text(
                "SELECT first_valid_at, updated_at, result_state, ai_call_id "
                "FROM content_annotations WHERE owner_id = :owner"
            ),
            {"owner": owner_id},
        ).one()
    assert row.first_valid_at == now + timedelta(minutes=1)
    assert row.updated_at == now + timedelta(minutes=3)
    assert row.result_state == "valid"
    assert row.ai_call_id == valid_call_id
    separate_process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sys
from uuid import UUID
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
with engine.connect() as connection:
    first_valid_at = connection.scalar(
        text("SELECT first_valid_at FROM content_annotations WHERE owner_id = :owner"),
        {"owner": UUID(sys.argv[1])},
    )
print(first_valid_at.isoformat() if first_valid_at else "missing")
""",
            str(owner_id),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert datetime.fromisoformat(separate_process.stdout.strip()) == now + timedelta(minutes=1)


def test_annotation_batch_rolls_back_when_a_content_version_is_not_frozen(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    sessions, owner_id, topic_id, post, invalid_call_id, _, now = annotation_context
    results = (
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=invalid_call_id,
            status=AnnotationStatus.UNANALYZED,
            result_state=AnnotationResultState.INVALID,
            error_code="analysis_output_missing",
        ),
        AnnotationWrite(
            content_version_id=uuid4(),
            ai_call_id=invalid_call_id,
            status=AnnotationStatus.UNANALYZED,
            result_state=AnnotationResultState.INVALID,
            error_code="analysis_output_missing",
        ),
    )
    with (
        sessions() as session,
        pytest.raises(ValueError, match="unfrozen content version"),
        session.begin(),
    ):
        AnalysisService(session).persist_results_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=1,
            prompt_version="v1",
            posts={post.content_version_id: post},
            results=results,
            created_at=now,
        )
    with sessions() as session:
        assert (
            session.scalars(
                select(ContentAnnotation).where(ContentAnnotation.owner_id == owner_id)
            ).all()
            == []
        )


def test_late_arriving_valid_result_upgrades_newer_invalid_result(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
) -> None:
    context = annotation_context
    sessions, owner_id, _, post, invalid_call_id, valid_call_id, now = context
    _persist(
        context,
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=invalid_call_id,
            status=AnnotationStatus.UNANALYZED,
            result_state=AnnotationResultState.INVALID,
            error_code="analysis_output_missing",
        ),
        at=now + timedelta(minutes=2),
    )
    _persist(
        context,
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=valid_call_id,
            status=AnnotationStatus.ANNOTATED,
            result_state=AnnotationResultState.VALID,
            relevant=False,
            relevance_reason="不同主题",
            summary="内容讨论另一主题",
        ),
        at=now + timedelta(minutes=1),
    )
    with sessions() as session:
        row = session.scalar(
            select(ContentAnnotation).where(ContentAnnotation.owner_id == owner_id)
        )
    assert row is not None
    assert row.result_state == "valid"
    assert row.updated_at == now + timedelta(minutes=2)
    assert row.diagnostic_history[0]["result_state"] == "invalid"


@pytest.mark.parametrize("missing_proof", ("original_job", "leaf_permission"))
def test_unproven_legacy_result_stays_pending_and_unreadable(
    annotation_context: tuple[
        sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
    ],
    missing_proof: str,
) -> None:
    sessions, owner_id, topic_id, post, _, valid_call_id, now = annotation_context
    _persist(
        annotation_context,
        AnnotationWrite(
            content_version_id=post.content_version_id,
            ai_call_id=valid_call_id,
            status=AnnotationStatus.ANNOTATED,
            result_state=AnnotationResultState.VALID,
            relevant=False,
            relevance_reason="受控无关结果",
            summary="存在存储行不能证明结果仍可读",
        ),
    )
    with sessions() as session, session.begin():
        if missing_proof == "original_job":
            session.execute(
                text("UPDATE ai_calls SET job_id=NULL WHERE id=:id AND owner_id=:owner"),
                {"id": valid_call_id, "owner": owner_id},
            )
        else:
            session.execute(
                text(
                    "UPDATE evidence_resources SET expires_at=:expires WHERE owner_id=:owner "
                    "AND resource_type='content_observation' AND resource_id=:observation"
                ),
                {
                    "expires": now + timedelta(seconds=1),
                    "owner": owner_id,
                    "observation": post.observation_id,
                },
            )
        counts = AnalysisService(session).window_annotation_counts_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=1,
            prompt_version="v1",
            content_version_ids=(post.content_version_id,),
        )
        visible = load_content_annotations_in_transaction(
            session,
            owner_id=owner_id,
            content_id=post.content_id,
            readable_version_ids={post.content_version_id},
            now=now + timedelta(hours=1),
        )
    assert (counts.annotated_count, counts.pending_count) == (0, 1)
    assert visible == []
