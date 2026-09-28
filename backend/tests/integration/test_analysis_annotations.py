from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from analysis.models import ContentAnnotation
from analysis.schemas import AnnotationResultState, AnnotationStatus, AnnotationWrite
from analysis.services import AnalysisService
from content.schemas import AnalysisPostContentView


@pytest.fixture
def annotation_context() -> tuple[
    sessionmaker[Session], UUID, UUID, AnalysisPostContentView, UUID, UUID, datetime
]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    owner_id, topic_id, content_id, version_id = (uuid4() for _ in range(4))
    invalid_call_id, valid_call_id = uuid4(), uuid4()
    now = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO identity_users "
                "(id, username, password_hash, credential_version, created_at, updated_at) "
                "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
            ),
            {"id": owner_id, "username": f"annotation-{owner_id.hex}", "now": now},
        )
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
                    "VALUES (:topic_id, :version, :owner_id, '[]'::jsonb, '[]'::jsonb, "
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
                "VALUES (:id, :owner_id, 'bilibili', 'post', :external_id, :now)"
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
        content_id=content_id, content_version_id=version_id, title="title", body=None
    )
    try:
        yield sessions, owner_id, topic_id, post, invalid_call_id, valid_call_id, now
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM content_records WHERE owner_id = :id"), {"id": owner_id}
            )
            connection.execute(text("DELETE FROM ai_calls WHERE owner_id = :id"), {"id": owner_id})
            connection.execute(
                text("DELETE FROM monitor_topic_versions WHERE created_by = :id"),
                {"id": owner_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topics WHERE owner_id = :id"), {"id": owner_id}
            )
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
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
        AnalysisService(session).persist_results_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=rule_version,
            prompt_version="v1",
            posts={post.content_version_id: post},
            results=(result,),
            created_at=at or now,
        )


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
