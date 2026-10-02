from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from tests.conftest import TEST_DATABASE_TRUNCATE, authenticate_test_client, authenticated_owner_id

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from connections.schemas import SourceEntryPoint
from connections.services import SourceConnectionService
from content.schemas import (
    ContentSamplePreviewInput,
    ContentVisibilityBasis,
    ContentVisibilityStatus,
    PersistContentPostInput,
    RecordContentVisibilityInput,
)
from content.services import ContentObservationCleanup, ContentService
from core.config import Settings
from core.errors import ApplicationError
from evidence.schemas import (
    AdmittedSourcePayload,
    CleanupTargetKind,
    DataClass,
    DeletionReason,
    DeletionStatus,
)
from evidence.services import CleanupProcessor, LifecycleService
from main import create_app
from sources.contracts import SourceCapability

_TRUNCATE = TEST_DATABASE_TRUNCATE


@pytest.fixture
def content_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(_TRUNCATE))
    try:
        with TestClient(create_app(settings)) as client:
            authenticate_test_client(client)
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def _user_scope(client: TestClient) -> UUID:
    with client.app.state.session_factory() as session:
        return authenticated_owner_id(session)


def _seed_context(client: TestClient, owner_id: UUID) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    connection_id = uuid4()
    policy_id = uuid4()
    retention_id = uuid4()
    job_ids = (uuid4(), uuid4())
    now = datetime.now(UTC)
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        session.execute(
            text(
                "INSERT INTO source_connections "
                "(id, owner_id, source_key, status, current_version, created_at, updated_at) "
                "VALUES (:id, :owner_id, 'x', 'active', 1, :now, :now)"
            ),
            {"id": connection_id, "owner_id": owner_id, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO source_connection_versions "
                "(connection_id, version, owner_id, secret_ref, created_by, created_at) "
                "VALUES (:id, 1, :owner_id, 'env:HOTKEY_X_TOKEN', :owner_id, :now)"
            ),
            {"id": connection_id, "owner_id": owner_id, "now": now},
        )
        fields = {
            "object_type": "作品类型",
            "external_id": "作品身份",
            "canonical_url": "原文入口",
            "author_external_id": "公开作者身份",
            "published_at": "发布时间",
            "like_count": "点赞观察",
            "comment_count": "评论观察",
            "repost_count": "转发观察",
            "view_count": "浏览观察",
            "play_count": "播放观察",
            "danmaku_count": "弹幕观察",
            "text_scope": "正文完整度",
            "text_origin": "正文来源",
            "text_origin_ref": "机器提取依据",
            "title": "作品标题",
            "body": "作品正文",
            "truncation_reason": "截断原因",
            "quote_target_external_id": "引用目标身份",
            "quote_target_native_scope": "引用目标作用域",
            "quote_target_author_external_id": "引用目标作者",
            "repost_target_external_id": "转帖目标身份",
            "repost_target_native_scope": "转帖目标作用域",
            "repost_target_author_external_id": "转帖目标作者",
        }
        session.execute(
            text(
                "INSERT INTO source_access_policies "
                "(id, owner_id, source_key, capability, status, enabled, access_basis, "
                "terms_reference, processing_purpose, component_name, component_version, "
                "component_license, field_purposes, reviewed_at, review_expires_at, "
                "policy_version, created_at, updated_at) VALUES "
                "(:id, :owner_id, 'x', 'search', 'approved', true, 'official_api', "
                "'https://developer.x.com/terms', '受控作品资料验证', 'controlled-collector', "
                "'1', 'MIT', CAST(:fields AS jsonb), :now, NULL, 1, :now, :now)"
            ),
            {
                "id": policy_id,
                "owner_id": owner_id,
                "fields": json.dumps(fields, ensure_ascii=False),
                "now": now,
            },
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies "
                "(id, owner_id, source_policy_id, source_policy_version, data_class, "
                "requested_days, source_max_days, effective_days, policy_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner_id, :policy_id, 1, 'structured', 30, NULL, 30, 1, :now, :now)"
            ),
            {
                "id": retention_id,
                "owner_id": owner_id,
                "policy_id": policy_id,
                "now": now,
            },
        )
        for index, job_id in enumerate(job_ids, start=1):
            session.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, owner_id, operation_id, kind, configuration_ref, "
                    "configuration_version, source_key, source_capability, scope, "
                    "request_fingerprint, status, created_at, updated_at) VALUES "
                    "(:id, :owner_id, :operation_id, 'monitor.collect', :configuration_ref, "
                    "1, 'x', 'search', '{}'::jsonb, :fingerprint, 'queued', :now, :now)"
                ),
                {
                    "id": job_id,
                    "owner_id": owner_id,
                    "operation_id": uuid4(),
                    "configuration_ref": f"topic:controlled-{index}",
                    "fingerprint": bytes([index]) * 32,
                    "now": now,
                },
            )
    return connection_id, policy_id, retention_id, *job_ids


def _command(
    *,
    owner_id: UUID,
    connection_id: UUID,
    policy_id: UUID,
    retention_id: UUID,
    job_id: UUID,
    operation_id: UUID,
    observed_at: datetime,
    like_count: int = 0,
    external_id: str = "post-001",
    extra_fields: dict[str, object] | None = None,
) -> PersistContentPostInput:
    return PersistContentPostInput(
        job_id=job_id,
        source_operation_id=operation_id,
        connection_id=connection_id,
        connection_version=1,
        entry_point=SourceEntryPoint.MANUAL,
        component_name="controlled-collector",
        component_version="1",
        native_scope=None,
        admission=AdmittedSourcePayload(
            policy_id=policy_id,
            policy_version=1,
            owner_id=owner_id,
            source_key="x",
            capability=SourceCapability.SEARCH,
            retention_policy_id=retention_id,
            retention_policy_version=1,
            data_class=DataClass.STRUCTURED,
            collected_at=observed_at,
            expires_at=observed_at + timedelta(days=30),
            fields={
                "object_type": "post",
                "external_id": external_id,
                "canonical_url": f"https://example.invalid/posts/{external_id}",
                "author_external_id": "author-1",
                "published_at": "2026-09-22T07:00:00Z",
                "like_count": like_count,
                "comment_count": None,
                "repost_count": 0,
                "view_count": None,
                "play_count": None,
                "danmaku_count": None,
                **(extra_fields or {}),
            },
        ),
    )


def test_content_versions_preserve_scope_provenance_relations_and_snapshot_time(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, first_job_id, second_job_id = _seed_context(
        content_client, owner_id
    )
    base_time = datetime.now(UTC) - timedelta(minutes=3)
    factory = content_client.app.state.session_factory

    target_command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=first_job_id,
        operation_id=uuid4(),
        observed_at=base_time,
        external_id="post-target",
        extra_fields={
            "text_scope": "full",
            "text_origin": "source",
            "title": "目标作品",
            "body": "目标正文",
            "published_at": "2026-09-22T06:59:59.123456Z",
        },
    )
    subject_fields = {
        "author_external_id": "author-subject",
        "published_at": "2026-09-22T07:00:00.123Z",
        "text_scope": "summary",
        "text_origin": "source",
        "title": "摘要标题",
        "body": "<b>来源摘要</b>",
        "quote_target_external_id": "post-missing",
        "quote_target_author_external_id": "author-quote",
        "repost_target_external_id": "post-target",
        "repost_target_author_external_id": "author-target",
    }
    first_operation = uuid4()
    subject = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=first_job_id,
        operation_id=first_operation,
        observed_at=base_time + timedelta(minutes=1),
        external_id="post-subject",
        extra_fields=subject_fields,
    )
    later = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=second_job_id,
        operation_id=uuid4(),
        observed_at=base_time + timedelta(minutes=2),
        external_id="post-subject",
        extra_fields=subject_fields,
    )

    with factory() as session:
        service = ContentService(session)
        target = service.persist_post(owner_id=owner_id, command=target_command)
        created = service.persist_post(owner_id=owner_id, command=subject)
        replayed = service.persist_post(owner_id=owner_id, command=subject)
        updated = service.persist_post(owner_id=owner_id, command=later)

    assert created.latest_observation.id == replayed.latest_observation.id
    assert created.latest_observation.content_version is not None
    assert updated.latest_observation.content_version is not None
    assert (
        created.latest_observation.content_version.id
        == updated.latest_observation.content_version.id
    )
    detail = content_client.get(f"/api/contents/{created.id}")
    assert detail.status_code == 200, detail.json()
    observation = detail.json()["latest_observation"]
    assert observation["observed_at"] != created.latest_observation.observed_at.isoformat()
    assert observation["published_at_fractional_digits"] == 3
    assert observation["author_external_id"] == "author-subject"
    assert observation["content_version"] == {
        "id": str(created.latest_observation.content_version.id),
        "text_scope": "summary",
        "text_origin": "source",
        "text_origin_ref": None,
        "title": "摘要标题",
        "body": "<b>来源摘要</b>",
        "truncation_reason": None,
        "relations": [
            {
                "relation_type": "quote",
                "target_native_scope": None,
                "target_external_id": "post-missing",
                "target_author_external_id": "author-quote",
                "target_content_id": None,
            },
            {
                "relation_type": "repost",
                "target_native_scope": None,
                "target_external_id": "post-target",
                "target_author_external_id": "author-target",
                "target_content_id": str(target.id),
            },
        ],
    }
    with factory() as session:
        counts = session.execute(
            text(
                "SELECT (SELECT count(*) FROM content_records), "
                "(SELECT count(*) FROM content_versions), "
                "(SELECT count(*) FROM content_version_relations), "
                "(SELECT count(*) FROM content_observations)"
            )
        ).one()
    assert tuple(counts) == (2, 2, 2, 3)


def test_edit_and_visibility_history_keep_last_success_across_failures_and_late_data(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    base_time = datetime.now(UTC) - timedelta(minutes=10)
    factory = content_client.app.state.session_factory
    first = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=base_time,
        extra_fields={
            "text_scope": "full",
            "text_origin": "source",
            "body": "第一版正文",
        },
    )
    second = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=base_time + timedelta(minutes=2),
        extra_fields={
            "text_scope": "full",
            "text_origin": "source",
            "body": "第二版正文",
        },
    )

    with factory() as session:
        created = ContentService(
            session, clock=lambda: base_time + timedelta(seconds=30)
        ).persist_post(owner_id=owner_id, command=first)
        updated = ContentService(
            session, clock=lambda: base_time + timedelta(minutes=2, seconds=30)
        ).persist_post(owner_id=owner_id, command=second)
        service = ContentService(session, clock=lambda: base_time + timedelta(minutes=6))
        service.record_visibility(
            owner_id=owner_id,
            command=RecordContentVisibilityInput(
                content_id=created.id,
                job_id=job_id,
                source_operation_id=uuid4(),
                observed_at=base_time + timedelta(minutes=1),
                status=ContentVisibilityStatus.DELETED,
                basis=ContentVisibilityBasis.HTTP_GONE,
            ),
        )
        after_late_delete = service.get_content(owner_id=owner_id, content_id=created.id)
        service.record_visibility(
            owner_id=owner_id,
            command=RecordContentVisibilityInput(
                content_id=created.id,
                job_id=job_id,
                source_operation_id=uuid4(),
                observed_at=base_time + timedelta(minutes=3),
                status=ContentVisibilityStatus.TRANSIENT_FAILURE,
                basis=ContentVisibilityBasis.TIMEOUT,
            ),
        )
        after_timeout = service.get_content(owner_id=owner_id, content_id=created.id)
        service.record_visibility(
            owner_id=owner_id,
            command=RecordContentVisibilityInput(
                content_id=created.id,
                job_id=job_id,
                source_operation_id=uuid4(),
                observed_at=base_time + timedelta(minutes=4),
                status=ContentVisibilityStatus.UNKNOWN,
                basis=ContentVisibilityBasis.NOT_FOUND,
            ),
        )
        service.record_visibility(
            owner_id=owner_id,
            command=RecordContentVisibilityInput(
                content_id=created.id,
                job_id=job_id,
                source_operation_id=uuid4(),
                observed_at=base_time + timedelta(minutes=5),
                status=ContentVisibilityStatus.DELETED,
                basis=ContentVisibilityBasis.SOURCE_TOMBSTONE,
            ),
        )

    assert created.id == updated.id
    assert after_late_delete.current_visibility is not None
    assert after_late_delete.current_visibility.status is ContentVisibilityStatus.VISIBLE
    assert after_timeout.current_visibility is not None
    assert after_timeout.current_visibility.status is ContentVisibilityStatus.TRANSIENT_FAILURE
    assert after_timeout.latest_observation.content_version is not None
    assert after_timeout.latest_observation.content_version.body == "第二版正文"

    response = content_client.get(f"/api/contents/{created.id}")
    assert response.status_code == 200, response.json()
    detail = response.json()
    assert detail["current_visibility"]["status"] == "deleted"
    assert detail["current_visibility"]["basis"] == "source_tombstone"
    assert detail["latest_observation"]["content_version"]["body"] == "第二版正文"
    assert [item["content_version"]["body"] for item in detail["version_history"]] == [
        "第二版正文",
        "第一版正文",
    ]
    assert [item["status"] for item in detail["visibility_history"]] == [
        "deleted",
        "unknown",
        "transient_failure",
        "visible",
        "deleted",
        "visible",
    ]


def test_lifecycle_cleanup_removes_postgres_content_and_blocks_exact_replay(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=observed_at,
        extra_fields={
            "text_scope": "full",
            "text_origin": "source",
            "body": "待清理正文",
        },
    )
    factory = content_client.app.state.session_factory
    with factory() as session:
        created = ContentService(session).persist_post(owner_id=owner_id, command=command)
        deletion = LifecycleService(session).request_deletion(
            owner_id=owner_id,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=created.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )

    assert deletion.status is DeletionStatus.PENDING
    assert deletion.target_count == 1
    result = CleanupProcessor(
        factory,
        handlers={
            CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(factory)
        },
    ).process_due(limit=1)
    assert result.succeeded == 1
    assert result.failed == 0

    with factory() as session:
        completed = LifecycleService(session).get_deletion(
            owner_id=owner_id, deletion_id=deletion.id
        )
        counts = session.execute(
            text(
                "SELECT (SELECT count(*) FROM content_records), "
                "(SELECT count(*) FROM content_discoveries), "
                "(SELECT count(*) FROM content_versions), "
                "(SELECT count(*) FROM content_observations), "
                "(SELECT count(*) FROM content_visibility_observations)"
            )
        ).one()
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            ContentService(session).persist_post(owner_id=owner_id, command=command)

    assert completed.status is DeletionStatus.COMPLETED
    assert tuple(counts) == (0, 0, 0, 0, 0)
    assert content_client.get(f"/api/contents/{created.id}").status_code == 404


@pytest.mark.parametrize(
    ("extra_fields", "message"),
    [
        ({"text_scope": "summary", "text_origin": "source"}, "requires a title or body"),
        (
            {"text_scope": "truncated", "text_origin": "source", "body": "部分正文"},
            "requires truncation_reason",
        ),
        (
            {"text_scope": "media_only", "text_origin": "source", "body": "伪造媒体文本"},
            "cannot contain invented",
        ),
        (
            {"text_scope": "full", "text_origin": "machine_extracted", "body": "提取文本"},
            "requires text_origin_ref",
        ),
        (
            {
                "text_scope": "full",
                "text_origin": "source",
                "text_origin_ref": "media_extraction:1",
                "body": "来源原文",
            },
            "cannot declare a machine extraction reference",
        ),
        (
            {
                "text_scope": "full",
                "text_origin": "source",
                "body": "来源原文",
                "quote_target_author_external_id": "author-only",
            },
            "target identity requires an external_id",
        ),
        (
            {
                "published_at": "2026-09-22T07:00:00.1234567Z",
                "text_scope": "full",
                "text_origin": "source",
                "body": "来源原文",
            },
            "at most 6 fractional digits",
        ),
    ],
)
def test_content_version_contract_rejects_false_or_untraceable_text(
    content_client: TestClient,
    extra_fields: dict[str, object],
    message: str,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
        extra_fields=extra_fields,
    )

    with (
        content_client.app.state.session_factory() as session,
        pytest.raises(ValueError, match=message),
    ):
        ContentService(session).persist_post(owner_id=owner_id, command=command)


def test_content_versions_keep_truncated_media_and_machine_extracted_semantics(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    cases = (
        (
            "post-truncated",
            {
                "text_scope": "truncated",
                "text_origin": "source",
                "body": "来源只返回的前半段",
                "truncation_reason": "source_limit",
            },
        ),
        ("post-media", {"text_scope": "media_only", "text_origin": "source"}),
        (
            "post-extracted",
            {
                "text_scope": "full",
                "text_origin": "machine_extracted",
                "text_origin_ref": "media_extraction:controlled-001",
                "body": "受控提取文本",
            },
        ),
    )
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    created = []
    with content_client.app.state.session_factory() as session:
        service = ContentService(session)
        for index, (external_id, fields) in enumerate(cases):
            created.append(
                service.persist_post(
                    owner_id=owner_id,
                    command=_command(
                        owner_id=owner_id,
                        connection_id=connection_id,
                        policy_id=policy_id,
                        retention_id=retention_id,
                        job_id=job_id,
                        operation_id=uuid4(),
                        observed_at=observed_at + timedelta(seconds=index),
                        external_id=external_id,
                        extra_fields=fields,
                    ),
                )
            )

    versions = [item.latest_observation.content_version for item in created]
    assert [version.text_scope if version else None for version in versions] == [
        "truncated",
        "media_only",
        "full",
    ]
    assert versions[0] is not None
    assert versions[0].truncation_reason == "source_limit"
    assert versions[1] is not None
    assert versions[1].title is None and versions[1].body is None
    assert versions[2] is not None
    assert versions[2].text_origin == "machine_extracted"
    assert versions[2].text_origin_ref == "media_extraction:controlled-001"


def test_same_post_keeps_two_discoveries_zero_unknown_and_idempotent_observations(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, first_job_id, second_job_id = _seed_context(
        content_client, owner_id
    )
    observed_at = datetime.now(UTC) - timedelta(minutes=2)
    first_operation = uuid4()
    second_operation = uuid4()
    first = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=first_job_id,
        operation_id=first_operation,
        observed_at=observed_at,
    )
    second = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=second_job_id,
        operation_id=second_operation,
        observed_at=observed_at + timedelta(minutes=1),
    )
    factory = content_client.app.state.session_factory

    with factory() as session:
        service = ContentService(session)
        created = service.persist_post(owner_id=owner_id, command=first)
        replayed = service.persist_post(owner_id=owner_id, command=first)
        updated = service.persist_post(owner_id=owner_id, command=second)
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.persist_post(
                owner_id=owner_id,
                command=first.model_copy(
                    update={
                        "admission": first.admission.model_copy(
                            update={"fields": {**first.admission.fields, "like_count": 1}}
                        )
                    }
                ),
            )

    assert created.id == replayed.id == updated.id
    assert created.latest_observation.id == replayed.latest_observation.id
    listed = content_client.get("/api/contents")
    detail = content_client.get(f"/api/contents/{created.id}")

    assert listed.status_code == 200, listed.json()
    assert listed.headers["cache-control"] == "no-store"
    assert len(listed.json()["items"]) == 1
    item = listed.json()["items"][0]
    assert item["discovery_count"] == 2
    assert item["latest_observation"]["metrics"]["like_count"] == 0
    assert item["latest_observation"]["metrics"]["view_count"] is None
    assert detail.status_code == 200
    assert {entry["job_id"] for entry in detail.json()["discoveries"]} == {
        str(first_job_id),
        str(second_job_id),
    }
    with factory() as session:
        counts = session.execute(
            text(
                "SELECT (SELECT count(*) FROM content_records), "
                "(SELECT count(*) FROM content_discoveries), "
                "(SELECT count(*) FROM content_observations), "
                "(SELECT count(*) FROM evidence_resources), "
                "(SELECT count(*) FROM source_capability_evidence)"
            )
        ).one()
    assert tuple(counts) == (1, 2, 2, 2, 2)


@pytest.mark.parametrize("change", ["replace", "disable"])
def test_connection_changes_preserve_historical_content_and_replay(
    content_client: TestClient, change: str
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
        extra_fields={"body": "historical body", "text_scope": "full", "text_origin": "source"},
    )
    factory = content_client.app.state.session_factory
    with factory() as session:
        original = ContentService(session).persist_post(owner_id=owner_id, command=command)
        with session.begin():
            if change == "replace":
                session.execute(
                    text(
                        "INSERT INTO source_connection_versions "
                        "(connection_id, version, owner_id, secret_ref, created_by, created_at) "
                        "SELECT connection_id, 2, owner_id, secret_ref, created_by, now() "
                        "FROM source_connection_versions WHERE connection_id = :id AND version = 1"
                    ),
                    {"id": connection_id},
                )
                session.execute(
                    text("UPDATE source_connections SET current_version = 2 WHERE id = :id"),
                    {"id": connection_id},
                )
            else:
                session.execute(
                    text("UPDATE source_connections SET status = 'disabled' WHERE id = :id"),
                    {"id": connection_id},
                )
        replayed = ContentService(session).persist_post(owner_id=owner_id, command=command)
        assert replayed == original
        assert session.execute(
            text("SELECT connection_version FROM source_capability_evidence")
        ).all() == [(1,)]
        assert session.scalar(text("SELECT count(*) FROM content_observations")) == 1
    response = content_client.get(f"/api/contents/{original.id}")
    assert response.status_code == 200
    assert "historical body" in response.text


def test_content_reads_enforce_owner_and_lifecycle_boundary(content_client: TestClient) -> None:
    assert content_client.get("/api/contents").status_code == 200
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    factory = content_client.app.state.session_factory
    with factory() as session:
        created = ContentService(session).persist_post(owner_id=owner_id, command=command)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session).get_content(owner_id=uuid4(), content_id=created.id)
        LifecycleService(session).request_deletion(
            owner_id=owner_id,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=created.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )

    hidden = content_client.get(f"/api/contents/{created.id}")
    listed = content_client.get("/api/contents")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "resource_not_found"
    assert listed.status_code == 200
    assert listed.json() == {"items": [], "next_cursor": None}


def test_detail_reads_annotation_status_by_readable_version_and_current_topic_rule(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, first_job_id, second_job_id = _seed_context(
        content_client, owner_id
    )
    now = datetime.now(UTC)
    factory = content_client.app.state.session_factory
    with factory() as session:
        first = ContentService(session).persist_post(
            owner_id=owner_id,
            command=_command(
                owner_id=owner_id,
                connection_id=connection_id,
                policy_id=policy_id,
                retention_id=retention_id,
                job_id=first_job_id,
                operation_id=uuid4(),
                observed_at=now - timedelta(minutes=2),
                extra_fields={"text_scope": "full", "text_origin": "source", "body": "旧正文"},
            ),
        )
        second = ContentService(session).persist_post(
            owner_id=owner_id,
            command=_command(
                owner_id=owner_id,
                connection_id=connection_id,
                policy_id=policy_id,
                retention_id=retention_id,
                job_id=second_job_id,
                operation_id=uuid4(),
                observed_at=now - timedelta(minutes=1),
                extra_fields={"text_scope": "full", "text_origin": "source", "body": "新正文"},
            ),
        )
    old_version = first.latest_observation.content_version
    current_version = second.latest_observation.content_version
    assert old_version is not None and current_version is not None
    topic_id, call_id = uuid4(), uuid4()
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, current_version, "
                "created_at, updated_at) "
                "VALUES (:topic, :owner, '品牌召回', 'active', 'ready', 2, :now, :now)"
            ),
            {"topic": topic_id, "owner": owner_id, "now": now},
        )
        for rule in (1, 2):
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:topic, :rule, :owner, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"topic": topic_id, "rule": rule, "owner": owner_id, "now": now},
            )
        session.execute(
            text("UPDATE jobs SET configuration_ref = :ref WHERE id IN (:first, :second)"),
            {"ref": f"topic:{topic_id}", "first": first_job_id, "second": second_job_id},
        )
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id, owner_id, purpose, provider, model, prompt_version, input_fingerprint, "
                "status, input_tokens, cached_input_tokens, output_tokens, "
                "reasoning_output_tokens, "
                "duration_ms, created_at) VALUES "
                "(:id, :owner, 'analysis.annotate', 'test', 'test-model', :prompt, :fingerprint, "
                "'succeeded', 0, 0, 0, 0, 0, :now)"
            ),
            {
                "id": call_id,
                "owner": owner_id,
                "prompt": ANALYSIS_PROMPT_VERSION,
                "fingerprint": call_id.bytes * 2,
                "now": now,
            },
        )
        for version_id, rule, state in (
            (old_version.id, 1, "valid"),
            (current_version.id, 1, "valid"),
            (current_version.id, 2, "pending"),
        ):
            valid = state == "valid"
            session.execute(
                text(
                    "INSERT INTO content_annotations "
                    "(id, owner_id, content_id, content_version_id, topic_id, topic_rule_version, "
                    "prompt_version, relevant, relevance_reason, sentiment, summary, ai_call_id, "
                    "status, result_state, first_valid_at, created_at, updated_at) VALUES "
                    "(:id, :owner, :content, :version, :topic, :rule, :prompt, :relevant, "
                    ":reason, :sentiment, :summary, :call, :status, :state, :first_valid_at, "
                    ":now, :now)"
                ),
                {
                    "id": uuid4(),
                    "owner": owner_id,
                    "content": second.id,
                    "version": version_id,
                    "topic": topic_id,
                    "rule": rule,
                    "prompt": ANALYSIS_PROMPT_VERSION,
                    "relevant": True if valid else None,
                    "reason": "受控理由" if valid else None,
                    "sentiment": "neutral" if valid else None,
                    "summary": "受控摘要" if valid else None,
                    "call": call_id if valid else None,
                    "status": "annotated" if valid else "unanalyzed",
                    "state": state,
                    "first_valid_at": now if valid else None,
                    "now": now,
                },
            )

    detail = content_client.get(f"/api/contents/{second.id}")
    assert detail.status_code == 200, detail.json()
    body = detail.json()
    assert body["analysis_topics"] == [
        {
            "topic_id": str(topic_id),
            "topic_name": "品牌召回",
            "current_rule_version": 2,
        }
    ]
    assert {
        (item["content_version_id"], item["topic_rule_version"], item["result_state"])
        for item in body["annotations"]
    } == {
        (str(old_version.id), 1, "valid"),
        (str(current_version.id), 1, "valid"),
        (str(current_version.id), 2, "pending"),
    }
    assert (
        next(item["relevant"] for item in body["annotations"] if item["topic_rule_version"] == 2)
        is None
    )
    current = content_client.get(
        "/api/contents", params={"topic_id": str(topic_id), "analysis_state": "pending"}
    )
    assert current.status_code == 200, current.json()
    assert [item["id"] for item in current.json()["items"]] == [str(second.id)]
    assert current.json()["items"][0]["analysis_state"] == "pending"
    assert (
        content_client.get(
            "/api/contents", params={"topic_id": str(topic_id), "analysis_state": "valid"}
        ).json()["items"]
        == []
    )
    with factory() as session:
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session).get_content(owner_id=uuid4(), content_id=second.id)
        LifecycleService(session).request_deletion(
            owner_id=owner_id,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=first.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    refreshed = content_client.get(f"/api/contents/{second.id}")
    assert refreshed.status_code == 200
    assert {item["content_version_id"] for item in refreshed.json()["annotations"]} == {
        str(current_version.id)
    }


def test_content_list_filters_bind_cursor_and_label_discovery_time(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, first_job_id, second_job_id = _seed_context(
        content_client, owner_id
    )
    now = datetime.now(UTC).replace(microsecond=0)
    topic_id = uuid4()
    factory = content_client.app.state.session_factory
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO monitor_topics "
                "(id, owner_id, name, status, readiness_status, "
                "current_version, created_at, updated_at) "
                "VALUES (:topic, :owner, '列表主题', 'active', 'ready', 1, :now, :now)"
            ),
            {"topic": topic_id, "owner": owner_id, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO monitor_topic_versions "
                "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                "VALUES (:topic, 1, :owner, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
            ),
            {"topic": topic_id, "owner": owner_id, "now": now},
        )
        session.execute(
            text("UPDATE jobs SET configuration_ref = :ref WHERE id IN (:first, :second)"),
            {"ref": f"topic:{topic_id}", "first": first_job_id, "second": second_job_id},
        )
    with factory() as session:
        service = ContentService(session)
        dated = service.persist_post(
            owner_id=owner_id,
            command=_command(
                owner_id=owner_id,
                connection_id=connection_id,
                policy_id=policy_id,
                retention_id=retention_id,
                job_id=first_job_id,
                operation_id=uuid4(),
                observed_at=now - timedelta(minutes=2),
                external_id="dated",
            ),
        )
        discovered = service.persist_post(
            owner_id=owner_id,
            command=_command(
                owner_id=owner_id,
                connection_id=connection_id,
                policy_id=policy_id,
                retention_id=retention_id,
                job_id=second_job_id,
                operation_id=uuid4(),
                observed_at=now - timedelta(minutes=1),
                external_id="discovered",
                extra_fields={"published_at": None},
            ),
        )

    page = content_client.get(
        "/api/contents", params={"topic_id": str(topic_id), "source_key": "x", "limit": 1}
    )
    assert page.status_code == 200, page.json()
    assert len(page.json()["items"]) == 1
    assert page.json()["next_cursor"]
    second = content_client.get(
        "/api/contents",
        params={
            "topic_id": str(topic_id),
            "source_key": "x",
            "limit": 1,
            "cursor": page.json()["next_cursor"],
        },
    )
    assert second.status_code == 200, second.json()
    assert {item["id"] for item in page.json()["items"] + second.json()["items"]} == {
        str(dated.id),
        str(discovered.id),
    }
    assert second.json()["next_cursor"] is None
    assert (
        content_client.get(
            "/api/contents",
            params={"source_key": "x", "cursor": page.json()["next_cursor"]},
        ).status_code
        == 422
    )
    with factory() as session, pytest.raises(ApplicationError, match="invalid_content_cursor"):
        ContentService(session).list_contents(
            owner_id=uuid4(), cursor=page.json()["next_cursor"], limit=20
        )
    with factory() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        ContentService(session).list_contents(
            owner_id=uuid4(), cursor=None, limit=20, topic_id=topic_id
        )

    window = content_client.get(
        "/api/contents",
        params={
            "topic_id": str(topic_id),
            "starts_at": (now - timedelta(minutes=3)).isoformat(),
            "ends_at": now.isoformat(),
        },
    )
    assert window.status_code == 200, window.json()
    assert [item["id"] for item in window.json()["items"]] == [str(discovered.id)]
    assert window.json()["items"][0]["timeline_basis"] == "first_observed_at"
    assert window.json()["items"][0]["latest_observation"]["metrics"]["comment_count"] is None
    assert (
        content_client.get("/api/contents", params={"source_key": "bilibili"}).json()["items"] == []
    )
    assert (
        content_client.get(
            "/api/contents", params={"topic_id": str(topic_id), "analysis_state": "missing"}
        ).status_code
        == 200
    )
    assert (
        content_client.get("/api/contents", params={"analysis_state": "missing"}).status_code == 422
    )
    assert (
        content_client.get("/api/contents", params={"starts_at": now.isoformat()}).status_code
        == 422
    )
    assert (
        content_client.get(
            "/api/contents",
            params={
                "starts_at": (now - timedelta(days=32)).isoformat(),
                "ends_at": now.isoformat(),
            },
        ).status_code
        == 422
    )
    assert content_client.get("/api/contents", params={"topic_id": str(uuid4())}).status_code == 404


@pytest.mark.parametrize(
    ("reference", "code"),
    [
        ("job_id", "resource_not_found"),
        ("connection_id", "resource_not_found"),
        ("connection_version", "connection_version_conflict"),
        ("disabled_connection", "connection_disabled"),
    ],
)
def test_unavailable_relation_rolls_back_entire_content_write(
    content_client: TestClient, reference: str, code: str
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    command = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
        extra_fields={"body": "private body", "text_scope": "full", "text_origin": "source"},
    )
    factory = content_client.app.state.session_factory
    with factory() as session:
        if reference == "disabled_connection":
            with session.begin():
                session.execute(
                    text("UPDATE source_connections SET status = 'disabled' WHERE id = :id"),
                    {"id": connection_id},
                )
            rejected = command
        else:
            value = 2 if reference == "connection_version" else uuid4()
            rejected = command.model_copy(update={reference: value})
        with pytest.raises(ApplicationError, match=code):
            ContentService(session).persist_post(owner_id=owner_id, command=rejected)
        for table in (
            "content_records",
            "content_versions",
            "content_observations",
            "content_discoveries",
            "content_visibility_observations",
            "evidence_resources",
            "source_capability_evidence",
        ):
            assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        if reference == "disabled_connection":
            session.execute(
                text("UPDATE source_connections SET status = 'active' WHERE id = :id"),
                {"id": connection_id},
            )
            session.commit()
        saved = ContentService(session).persist_post(owner_id=owner_id, command=command)
        outsider = uuid4()
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session).get_content(owner_id=outsider, content_id=saved.id)
        assert ContentService(session).list_contents(owner_id=outsider, cursor=None, limit=20) == (
            [],
            None,
        )
        platforms = SourceConnectionService(session).list_platforms(owner_id=outsider)
        for platform in platforms:
            assert platform.connection_version is None and not platform.has_credentials
            for capability in platform.capabilities:
                assert capability.manual.last_checked_at is None
                assert capability.manual.last_persisted_success_at is None
    response = content_client.get(f"/api/contents/{saved.id}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_reference_expansion_rechecks_target_readability(content_client: TestClient) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, job_id, _ = _seed_context(content_client, owner_id)
    base = _command(
        owner_id=owner_id,
        connection_id=connection_id,
        policy_id=policy_id,
        retention_id=retention_id,
        job_id=job_id,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
        external_id="target",
        extra_fields={"body": "private target", "text_scope": "full", "text_origin": "source"},
    )
    subject = base.model_copy(
        update={
            "source_operation_id": uuid4(),
            "admission": base.admission.model_copy(
                update={
                    "fields": {
                        **base.admission.fields,
                        "external_id": "subject",
                        "body": "subject only",
                        "quote_target_external_id": "target",
                    }
                }
            ),
        }
    )
    with content_client.app.state.session_factory() as session:
        service = ContentService(session)
        target = service.persist_post(owner_id=owner_id, command=base)
        saved = service.persist_post(owner_id=owner_id, command=subject)
        assert saved.latest_observation.content_version.relations[0].target_content_id == target.id
        LifecycleService(session).request_deletion(
            owner_id=owner_id,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=target.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
        current = service.get_content(owner_id=owner_id, content_id=saved.id)
        assert current.latest_observation.content_version.relations[0].target_content_id is None
        assert "private target" not in current.model_dump_json()


def test_concurrent_writes_reuse_the_same_native_content_identity(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, first_job_id, second_job_id = _seed_context(
        content_client, owner_id
    )
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    commands = (
        _command(
            owner_id=owner_id,
            connection_id=connection_id,
            policy_id=policy_id,
            retention_id=retention_id,
            job_id=first_job_id,
            operation_id=uuid4(),
            observed_at=observed_at,
        ),
        _command(
            owner_id=owner_id,
            connection_id=connection_id,
            policy_id=policy_id,
            retention_id=retention_id,
            job_id=second_job_id,
            operation_id=uuid4(),
            observed_at=observed_at + timedelta(seconds=1),
        ),
    )
    factory = content_client.app.state.session_factory

    def persist(command: PersistContentPostInput) -> UUID:
        with factory() as session:
            return (
                ContentService(session)
                .persist_post(
                    owner_id=owner_id,
                    command=command,
                )
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        content_ids = list(executor.map(persist, commands))

    assert content_ids[0] == content_ids[1]
    with factory() as session:
        counts = session.execute(
            text(
                "SELECT (SELECT count(*) FROM content_records), "
                "(SELECT count(*) FROM content_discoveries), "
                "(SELECT count(*) FROM content_observations)"
            )
        ).one()
    assert tuple(counts) == (1, 2, 2)


def _seed_comment_context(
    client: TestClient, owner_id: UUID, connection_id: UUID
) -> tuple[UUID, UUID, UUID]:
    policy_id = uuid4()
    retention_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)
    fields = {
        "object_type": "评论类型",
        "external_id": "评论身份",
        "post_external_id": "所属作品",
        "parent_comment_external_id": "父评论",
        "root_comment_external_id": "线程根",
        "reply_target_comment_external_id": "回复目标",
        "parent_relation_status": "父节点可用状态",
        "canonical_url": "评论入口",
        "author_external_id": "公开作者身份",
        "author_name": "公开作者昵称",
        "published_at": "发布时间",
        "like_count": "点赞观察",
        "text_scope": "正文完整度",
        "text_origin": "正文来源",
        "body": "评论正文",
    }
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO source_access_policies "
                "(id, owner_id, source_key, capability, status, enabled, access_basis, "
                "terms_reference, processing_purpose, component_name, component_version, "
                "component_license, field_purposes, reviewed_at, review_expires_at, "
                "policy_version, created_at, updated_at) VALUES "
                "(:id, :owner_id, 'x', 'comments', 'approved', true, 'official_api', "
                "'https://developer.x.com/terms', '受控评论资料验证', 'controlled-collector', "
                "'1', 'MIT', CAST(:fields AS jsonb), :now, NULL, 1, :now, :now)"
            ),
            {
                "id": policy_id,
                "owner_id": owner_id,
                "fields": json.dumps(fields, ensure_ascii=False),
                "now": now,
            },
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies "
                "(id, owner_id, source_policy_id, source_policy_version, data_class, "
                "requested_days, source_max_days, effective_days, policy_version, "
                "created_at, updated_at) VALUES "
                "(:id, :owner_id, :policy_id, 1, 'structured', 30, NULL, 30, 1, :now, :now)"
            ),
            {"id": retention_id, "owner_id": owner_id, "policy_id": policy_id, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO jobs "
                "(id, owner_id, operation_id, kind, configuration_ref, "
                "configuration_version, source_key, source_capability, scope, "
                "request_fingerprint, status, created_at, updated_at) VALUES "
                "(:id, :owner_id, :operation_id, 'source.comments', 'topic:controlled-comments', "
                "1, 'x', 'comments', '{}'::jsonb, :fingerprint, 'queued', :now, :now)"
            ),
            {
                "id": job_id,
                "owner_id": owner_id,
                "operation_id": uuid4(),
                "fingerprint": bytes([9]) * 32,
                "now": now,
            },
        )
    del connection_id
    return policy_id, retention_id, job_id


def _comment_command(
    *,
    owner_id: UUID,
    connection_id: UUID,
    policy_id: UUID,
    retention_id: UUID,
    job_id: UUID,
    external_id: str,
    post_external_id: str | None,
    parent_comment_external_id: str | None = None,
    root_comment_external_id: str | None = None,
    reply_target_comment_external_id: str | None = None,
    parent_relation_status: str | None = None,
    author_name: str | None = "楼主",
) -> PersistContentPostInput:
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    fields: dict[str, object] = {
        "object_type": "comment",
        "external_id": external_id,
        "author_external_id": "commenter-1",
        "author_name": author_name,
        "published_at": "2026-09-22T08:00:00Z",
        "like_count": 3,
        "text_scope": "full",
        "text_origin": "source",
        "body": f"评论 {external_id}",
    }
    if post_external_id is not None:
        fields["post_external_id"] = post_external_id
    if parent_comment_external_id is not None:
        fields["parent_comment_external_id"] = parent_comment_external_id
    if root_comment_external_id is not None:
        fields["root_comment_external_id"] = root_comment_external_id
    if reply_target_comment_external_id is not None:
        fields["reply_target_comment_external_id"] = reply_target_comment_external_id
    if parent_relation_status is not None:
        fields["parent_relation_status"] = parent_relation_status
    return PersistContentPostInput(
        job_id=job_id,
        source_operation_id=uuid4(),
        connection_id=connection_id,
        connection_version=1,
        entry_point=SourceEntryPoint.MANUAL,
        component_name="controlled-collector",
        component_version="1",
        native_scope=None,
        admission=AdmittedSourcePayload(
            policy_id=policy_id,
            policy_version=1,
            owner_id=owner_id,
            source_key="x",
            capability=SourceCapability.COMMENTS,
            retention_policy_id=retention_id,
            retention_policy_version=1,
            data_class=DataClass.STRUCTURED,
            collected_at=observed_at,
            expires_at=observed_at + timedelta(days=30),
            fields=fields,
        ),
    )


def _thread_rows(client: TestClient, owner_id: UUID) -> dict[str, tuple[str, str | None]]:
    factory = client.app.state.session_factory
    with factory() as session:
        rows = session.execute(
            text(
                "SELECT c.external_id, p.external_id, pa.external_id "
                "FROM content_threads t "
                "JOIN content_records c ON c.owner_id = t.owner_id AND c.id = t.content_id "
                "JOIN content_records p ON p.owner_id = t.owner_id AND p.id = t.post_content_id "
                "LEFT JOIN content_records pa "
                "ON pa.owner_id = t.owner_id AND pa.id = t.parent_content_id "
                "WHERE t.owner_id = :owner_id"
            ),
            {"owner_id": owner_id},
        ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def test_comments_keep_post_and_parent_links_even_when_reply_arrives_first(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, *_ = _seed_context(content_client, owner_id)
    policy_id, retention_id, job_id = _seed_comment_context(content_client, owner_id, connection_id)
    factory = content_client.app.state.session_factory

    def persist(**kwargs: object) -> None:
        with factory() as session:
            ContentService(session).persist_comment(
                owner_id=owner_id,
                command=_comment_command(
                    owner_id=owner_id,
                    connection_id=connection_id,
                    policy_id=policy_id,
                    retention_id=retention_id,
                    job_id=job_id,
                    **kwargs,  # type: ignore[arg-type]
                ),
            )

    persist(external_id="reply-1", post_external_id="post-9", parent_comment_external_id="c-1")
    assert _thread_rows(content_client, owner_id) == {"reply-1": ("post-9", "c-1")}

    persist(external_id="c-1", post_external_id="post-9")
    persist(external_id="reply-1", post_external_id="post-9", parent_comment_external_id="c-1")
    assert _thread_rows(content_client, owner_id) == {
        "reply-1": ("post-9", "c-1"),
        "c-1": ("post-9", None),
    }

    with factory() as session:
        counts = dict(
            session.execute(
                text(
                    "SELECT object_type, count(*) FROM content_records "
                    "WHERE owner_id = :owner_id GROUP BY object_type"
                ),
                {"owner_id": owner_id},
            ).all()
        )
        author_names = set(
            session.scalars(
                text(
                    "SELECT author_name FROM content_observations "
                    "WHERE owner_id = :owner_id AND author_name IS NOT NULL"
                ),
                {"owner_id": owner_id},
            )
        )
    assert counts == {"post": 1, "comment": 2}
    assert author_names == {"楼主"}

    with pytest.raises(ValueError, match="thread"):
        persist(external_id="reply-1", post_external_id="post-other")
    with pytest.raises(ValueError, match="post_external_id"):
        persist(external_id="orphan", post_external_id=None)


def test_comments_keep_root_reply_target_and_unavailable_parent_gap(
    content_client: TestClient,
) -> None:
    owner_id = _user_scope(content_client)
    connection_id, *_ = _seed_context(content_client, owner_id)
    policy_id, retention_id, job_id = _seed_comment_context(content_client, owner_id, connection_id)
    factory = content_client.app.state.session_factory

    def persist(**kwargs: object) -> None:
        with factory() as session:
            ContentService(session).persist_comment(
                owner_id=owner_id,
                command=_comment_command(
                    owner_id=owner_id,
                    connection_id=connection_id,
                    policy_id=policy_id,
                    retention_id=retention_id,
                    job_id=job_id,
                    post_external_id="post-9",
                    **kwargs,  # type: ignore[arg-type]
                ),
            )

    persist(
        external_id="reply-1",
        parent_comment_external_id="deleted-parent",
        root_comment_external_id="root-1",
        reply_target_comment_external_id="deleted-parent",
        parent_relation_status="unavailable",
    )
    with factory() as session:
        assert session.execute(
            text(
                "SELECT root.external_id, parent.external_id, target.external_id, "
                "t.parent_relation_status FROM content_threads t "
                "JOIN content_records child ON child.id = t.content_id "
                "LEFT JOIN content_records root ON root.id = t.root_content_id "
                "LEFT JOIN content_records parent ON parent.id = t.parent_content_id "
                "LEFT JOIN content_records target ON target.id = t.reply_target_content_id "
                "WHERE child.external_id = 'reply-1'"
            )
        ).one() == ("root-1", "deleted-parent", "deleted-parent", "unavailable")

    persist(external_id="root-1", root_comment_external_id="root-1")
    persist(
        external_id="deleted-parent",
        parent_comment_external_id="root-1",
        root_comment_external_id="root-1",
        reply_target_comment_external_id="root-1",
        parent_relation_status="observed",
    )
    with factory() as session:
        assert session.execute(
            text(
                "SELECT child.external_id, root.external_id, t.parent_relation_status "
                "FROM content_threads t JOIN content_records child ON child.id = t.content_id "
                "LEFT JOIN content_records root ON root.id = t.root_content_id "
                "WHERE child.external_id IN ('root-1', 'reply-1') "
                "ORDER BY child.external_id"
            )
        ).all() == [
            ("reply-1", "root-1", "observed"),
            ("root-1", "root-1", "root"),
        ]

    with pytest.raises(ValueError, match="thread"):
        persist(
            external_id="reply-1",
            parent_comment_external_id="deleted-parent",
            root_comment_external_id="different-root",
            reply_target_comment_external_id="deleted-parent",
            parent_relation_status="observed",
        )

    with pytest.raises(IntegrityError), factory.begin() as session:
        session.execute(
            text(
                "UPDATE content_threads SET parent_relation_status = 'root' "
                "WHERE owner_id = :owner_id AND content_id = "
                "(SELECT id FROM content_records WHERE owner_id = :owner_id "
                "AND external_id = 'reply-1')"
            ),
            {"owner_id": owner_id},
        )


def test_comment_read_pages_keep_missing_root_and_parent_gap(
    content_client: TestClient,
) -> None:
    assert content_client.get(f"/api/contents/{uuid4()}/comments").status_code == 404
    owner_id = _user_scope(content_client)
    connection_id, policy_id, retention_id, post_job_id, _ = _seed_context(content_client, owner_id)
    comment_policy_id, comment_retention_id, comment_job_id = _seed_comment_context(
        content_client, owner_id, connection_id
    )
    factory = content_client.app.state.session_factory
    with factory() as session:
        post = ContentService(session).persist_post(
            owner_id=owner_id,
            command=_command(
                owner_id=owner_id,
                connection_id=connection_id,
                policy_id=policy_id,
                retention_id=retention_id,
                job_id=post_job_id,
                operation_id=uuid4(),
                observed_at=datetime.now(UTC) - timedelta(minutes=2),
                external_id="post-9",
                extra_fields={"text_scope": "full", "text_origin": "source", "title": "测试帖子"},
            ),
        )

    def persist(**kwargs: object) -> None:
        with factory() as session:
            ContentService(session).persist_comment(
                owner_id=owner_id,
                command=_comment_command(
                    owner_id=owner_id,
                    connection_id=connection_id,
                    policy_id=comment_policy_id,
                    retention_id=comment_retention_id,
                    job_id=comment_job_id,
                    post_external_id="post-9",
                    **kwargs,  # type: ignore[arg-type]
                ),
            )

    persist(
        external_id="reply-1",
        parent_comment_external_id="deleted-parent",
        root_comment_external_id="missing-root",
        reply_target_comment_external_id="deleted-parent",
        parent_relation_status="unavailable",
    )
    persist(external_id="root-2", root_comment_external_id="root-2")
    roots = content_client.get(f"/api/contents/{post.id}/comments", params={"limit": 1})
    assert roots.status_code == 200
    assert len(roots.json()["items"]) == 1
    assert roots.json()["next_cursor"] is not None
    second = content_client.get(
        f"/api/contents/{post.id}/comments",
        params={"limit": 1, "cursor": roots.json()["next_cursor"]},
    )
    assert second.status_code == 200
    all_roots = roots.json()["items"] + second.json()["items"]
    by_external = {item["external_id"]: item for item in all_roots}
    assert set(by_external) == {None, "root-2"}
    missing = by_external[None]
    assert missing["latest_observation"] is None
    assert missing["has_replies"] is True

    replies = content_client.get(
        f"/api/contents/{post.id}/comments", params={"root_id": missing["content_id"]}
    )
    assert replies.status_code == 200
    assert len(replies.json()["items"]) == 1
    reply = replies.json()["items"][0]
    assert reply["external_id"] == "reply-1"
    assert reply["root_content_id"] == missing["content_id"]
    assert reply["parent_relation_status"] == "unavailable"
    assert reply["parent_content_id"] != missing["content_id"]
    assert reply["reply_target_content_id"] == reply["parent_content_id"]
    assert reply["latest_observation"]["content_version"]["body"] == "评论 reply-1"
    assert (
        content_client.get(
            f"/api/contents/{post.id}/comments",
            params={
                "root_id": missing["content_id"],
                "cursor": by_external["root-2"]["content_id"],
            },
        ).status_code
        == 422
    )

    children = content_client.get(
        f"/api/contents/{post.id}/comments", params={"parent_id": reply["parent_content_id"]}
    )
    assert children.status_code == 200
    assert [item["content_id"] for item in children.json()["items"]] == [reply["content_id"]]
    assert (
        content_client.get(
            f"/api/contents/{post.id}/comments",
            params={"root_id": missing["content_id"], "parent_id": reply["parent_content_id"]},
        ).status_code
        == 422
    )
    assert (
        content_client.get(
            f"/api/contents/{post.id}/comments", params={"root_id": uuid4()}
        ).status_code
        == 404
    )
    assert content_client.get(f"/api/contents/{uuid4()}/comments").status_code == 404
    assert (
        content_client.get(f"/api/contents/{post.id}/comments", params={"limit": 0}).status_code
        == 422
    )
    with factory() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        ContentService(session).list_comments(
            owner_id=uuid4(),
            post_content_id=post.id,
            root_id=None,
            parent_id=None,
            cursor=None,
            limit=20,
        )


def test_persisted_rule_preview_is_bounded_local_and_owner_scoped(
    content_client: TestClient,
) -> None:
    owner = _user_scope(content_client)
    connection, policy, retention, first_job, second_job = _seed_context(content_client, owner)
    factory = content_client.app.state.session_factory
    now = datetime.now(UTC) - timedelta(minutes=2)
    with factory() as session:
        service = ContentService(session)
        for index in range(25):
            title = ["AI 发布", "daily update", "AI 招聘", "无关标题"][index % 4]
            recorder = (
                ContentService(session, clock=lambda: now + timedelta(days=2))
                if index == 24
                else service
            )
            saved = recorder.persist_post(
                owner_id=owner,
                command=_command(
                    owner_id=owner,
                    connection_id=connection,
                    policy_id=policy,
                    retention_id=retention,
                    job_id=first_job,
                    operation_id=uuid4(),
                    external_id=f"preview-{index}",
                    observed_at=(
                        now + timedelta(days=1)
                        if index == 24
                        else now + timedelta(seconds=2)
                        if index == 23
                        else now - timedelta(days=8)
                        if index == 22
                        else now - timedelta(seconds=index)
                    ),
                    extra_fields={
                        "title": title,
                        "body": "AI Agent " + "x" * 1500 if index % 4 == 3 else None,
                        "text_scope": "full",
                        "text_origin": "source",
                    },
                ),
            )
            if index == 23:
                LifecycleService(session).request_deletion(
                    owner_id=owner,
                    operation_id=uuid4(),
                    resource_type="content_observation",
                    resource_id=saved.latest_observation.id,
                    reason=DeletionReason.USER_REQUEST,
                )
        latest = service.persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=second_job,
                operation_id=uuid4(),
                external_id="preview-0",
                observed_at=now + timedelta(seconds=1),
                extra_fields={
                    "title": "AI 新版本",
                    "body": None,
                    "text_scope": "full",
                    "text_origin": "source",
                },
            ),
        )
    tables = ["jobs", "outbox_messages", "ai_calls", "monitor_topics", "resource_budget_windows"]
    with factory() as session:
        before = {
            t: session.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables
        }
    payload = {
        "match_any": [" AI ", "ai"],
        "match_all": [],
        "exclude": ["招聘"],
        "source_keys": ["x"],
    }
    headers = {"X-HotKey-CSRF": content_client.cookies["hotkey_csrf"]}
    response = content_client.post("/api/topics/sample-preview", json=payload, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert result["rule_basis"] == "draft" and result["rules"]["match_any"] == ["AI"]
    assert result["sample_status"] == "available" and result["truncated"]
    assert len(result["samples"]) == result["sample_limit"] == 20
    assert result["samples"][0]["content_version_id"] == str(
        latest.latest_observation.content_version.id
    )
    assert result["samples"][0]["title"] == "AI 新版本"
    assert all(not s["matched"] for s in result["samples"] if s["title"] == "daily update")
    assert all(
        s["excluded_by"] == ["招聘"] and not s["matched"]
        for s in result["samples"]
        if s["title"] == "AI 招聘"
    )
    assert all(
        s["matched"] and s["excerpt_truncated"] and len(s["body_excerpt"]) == 1200
        for s in result["samples"]
        if s["title"] == "无关标题"
    )
    assert all(s["source_key"] == "x" for s in result["samples"])
    with factory() as session:
        assert before == {
            t: session.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables
        }
    empty = content_client.post(
        "/api/topics/sample-preview",
        json={**payload, "source_keys": ["hackernews"]},
        headers=headers,
    )
    assert empty.json()["sample_status"] == "insufficient_samples" and not empty.json()["samples"]
    assert content_client.post("/api/topics/sample-preview", json=payload).status_code == 403
    assert (
        content_client.post(
            "/api/topics/sample-preview",
            json={**payload, "owner_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 422
    )
    command = ContentSamplePreviewInput.model_validate(payload)
    with factory() as session:
        foreign = ContentService(session).preview_rule_samples(owner_id=uuid4(), command=command)
        assert foreign.sample_status == "insufficient_samples" and not foreign.samples
        aged = ContentService(
            session, clock=lambda: datetime.now(UTC) + timedelta(days=8)
        ).preview_rule_samples(owner_id=owner, command=command)
        assert aged.sample_status == "insufficient_samples" and not aged.samples
    with factory() as session, session.begin():
        session.execute(
            text("UPDATE evidence_resources SET expires_at=collected_at + interval '1 second'")
        )
    empty = content_client.post("/api/topics/sample-preview", json=payload, headers=headers)
    assert empty.json()["sample_status"] == "insufficient_samples" and not empty.json()["samples"]
    content_client.cookies.clear()
    assert content_client.post("/api/topics/sample-preview", json=payload).status_code == 401
