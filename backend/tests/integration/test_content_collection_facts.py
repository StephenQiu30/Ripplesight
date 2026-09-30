from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from content.services import ContentService


@pytest.fixture
def content_fact_sessions() -> Iterator[sessionmaker[Session]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _seed_job(session: Session, owner_id: UUID, job_id: UUID, now: datetime) -> None:
    session.execute(
        text(
            "INSERT INTO jobs "
            "(id, owner_id, operation_id, kind, configuration_ref, "
            "configuration_version, source_key, source_capability, scope, "
            "request_fingerprint, created_at, updated_at) VALUES "
            "(:id, :owner_id, :operation_id, 'keyword.search', 'content-facts:test', "
            "1, 'hackernews', 'search', '{}'::jsonb, :fingerprint, :now, :now)"
        ),
        {
            "id": job_id,
            "owner_id": owner_id,
            "operation_id": uuid4(),
            "fingerprint": job_id.bytes * 2,
            "now": now,
        },
    )


def _seed_content(
    session: Session, owner_id: UUID, content_id: UUID, version_ids: tuple[UUID, ...], now: datetime
) -> None:
    session.execute(
        text(
            "INSERT INTO content_records "
            "(id, owner_id, source_key, object_type, external_id, created_at) "
            "VALUES (:id, :owner_id, 'hackernews', 'post', :external_id, :now)"
        ),
        {"id": content_id, "owner_id": owner_id, "external_id": content_id.hex, "now": now},
    )
    for index, version_id in enumerate(version_ids):
        session.execute(
            text(
                "INSERT INTO content_versions "
                "(id, owner_id, content_id, fingerprint, text_scope, text_origin, "
                "title, created_at) VALUES "
                "(:id, :owner_id, :content_id, :fingerprint, 'full', 'source', :title, :now)"
            ),
            {
                "id": version_id,
                "owner_id": owner_id,
                "content_id": content_id,
                "fingerprint": version_id.bytes * 2,
                "title": f"Content version {index}",
                "now": now,
            },
        )


def _seed_observation(
    session: Session,
    owner_id: UUID,
    job_id: UUID,
    content_id: UUID,
    version_id: UUID | None,
    observed_at: datetime,
) -> None:
    session.execute(
        text(
            "INSERT INTO content_observations "
            "(id, owner_id, content_id, job_id, source_operation_id, "
            "content_version_id, observed_at, received_at) VALUES "
            "(:id, :owner_id, :content_id, :job_id, :operation_id, "
            ":version_id, :observed_at, :observed_at)"
        ),
        {
            "id": uuid4(),
            "owner_id": owner_id,
            "content_id": content_id,
            "job_id": job_id,
            "operation_id": uuid4(),
            "version_id": version_id,
            "observed_at": observed_at,
        },
    )


def test_collection_facts_batch_preserves_job_identity_and_first_ingestion(
    content_fact_sessions: sessionmaker[Session],
) -> None:
    owner_id, other_owner_id = uuid4(), uuid4()
    first_job, second_job, empty_job, unknown_job = (uuid4() for _ in range(4))
    shared_content, new_content = uuid4(), uuid4()
    shared_v1, shared_v2, new_v = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)

    with content_fact_sessions() as session:
        session.begin()
        try:
            for job_id in (first_job, second_job, empty_job):
                _seed_job(session, owner_id, job_id, now)
            _seed_content(session, owner_id, shared_content, (shared_v1, shared_v2), now)
            _seed_content(session, owner_id, new_content, (new_v,), now)
            for index, (job, content, version) in enumerate(
                (
                    (first_job, shared_content, shared_v1),
                    (first_job, shared_content, shared_v2),
                    (second_job, shared_content, shared_v2),
                    (second_job, new_content, new_v),
                    (second_job, shared_content, None),
                )
            ):
                _seed_observation(
                    session, owner_id, job, content, version, now + timedelta(seconds=index)
                )

            select_statements: list[str] = []

            def count_selects(
                _connection: object,
                _cursor: object,
                statement: str,
                _parameters: object,
                _context: object,
                _executemany: bool,
            ) -> None:
                if statement.lstrip().lower().startswith("select"):
                    select_statements.append(statement)

            engine = session.get_bind()
            event.listen(engine, "before_cursor_execute", count_selects)
            try:
                facts = ContentService(session).collection_facts_in_transaction(
                    owner_id=owner_id,
                    job_ids=(second_job, empty_job, first_job, unknown_job),
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_selects)

            assert len(select_statements) == 2
            assert [item.job_id for item in facts] == [
                second_job,
                empty_job,
                first_job,
                unknown_job,
            ]
            assert facts[0].observation_count == 3
            assert facts[0].ingested_count == 2
            assert facts[0].first_ingested_count == 1
            assert facts[0].deduplicated_count == 2
            assert facts[0].content_ids == tuple(sorted((shared_content, new_content), key=str))
            assert facts[0].analysis_targets_complete is False
            assert facts[1].analysis_targets_complete is True
            assert facts[0].content_version_ids == tuple(sorted((shared_v2, new_v), key=str))
            assert facts[1].observation_count == 0
            assert facts[1].content_ids == facts[1].content_version_ids == ()
            assert facts[2].observation_count == 2
            assert facts[2].ingested_count == 1
            assert facts[2].first_ingested_count == 1
            assert facts[2].deduplicated_count == 1
            assert facts[2].content_ids == (shared_content,)
            assert facts[2].content_version_ids == tuple(sorted((shared_v1, shared_v2), key=str))
            assert facts[3].observation_count == 0
            assert facts[3].content_ids == facts[3].content_version_ids == ()

            other_owner_facts = ContentService(session).collection_facts_in_transaction(
                owner_id=other_owner_id, job_ids=(first_job, second_job)
            )
            assert all(item.observation_count == 0 for item in other_owner_facts)
            assert all(item.content_ids == () for item in other_owner_facts)

            old_counts = ContentService(session).collection_counts_in_transaction(
                owner_id=owner_id, job_ids=(first_job, second_job)
            )
            assert old_counts[0].first_ingested_count == 1
            assert old_counts[1].deduplicated_count == 2
            assert "content_ids" not in old_counts[0].model_dump()
        finally:
            session.rollback()


def test_collection_snapshot_facts_distinguish_empty_snapshot_from_absence(
    content_fact_sessions: sessionmaker[Session],
) -> None:
    owner_id, other_owner_id = uuid4(), uuid4()
    snapshot_job, no_snapshot_job, unrelated_job = (uuid4() for _ in range(3))
    operation_id, snapshot_id = uuid4(), uuid4()
    now = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
    with content_fact_sessions() as session:
        session.begin()
        try:
            for job_id in (snapshot_job, no_snapshot_job):
                session.execute(
                    text(
                        "INSERT INTO jobs "
                        "(id, owner_id, operation_id, kind, configuration_ref, "
                        "configuration_version, source_key, source_capability, scope, "
                        "request_fingerprint, created_at, updated_at) VALUES "
                        "(:id, :owner_id, :operation_id, 'source.hotlist', "
                        "'hotlist:hotlist_36kr', 1, 'hotlist_36kr', 'hotlist', "
                        "'{}'::jsonb, :fingerprint, :now, :now)"
                    ),
                    {
                        "id": job_id,
                        "owner_id": owner_id,
                        "operation_id": operation_id if job_id == snapshot_job else uuid4(),
                        "fingerprint": job_id.bytes * 2,
                        "now": now,
                    },
                )
            _seed_job(session, owner_id, unrelated_job, now)
            session.execute(
                text(
                    "INSERT INTO collection_due_windows "
                    "(id, owner_id, schedule_key, source_key, capability, due_at, "
                    "window_start, window_end, connection_version, policy_snapshot, "
                    "admission_state, operation_id, job_id, recorded_at) VALUES "
                    "(:id, :owner_id, :schedule_key, 'hotlist_36kr', 'hotlist', :now, "
                    ":window_start, :now, 1, '{}'::jsonb, 'accepted', "
                    ":operation_id, :job_id, :now)"
                ),
                {
                    "id": uuid4(),
                    "owner_id": owner_id,
                    "schedule_key": uuid4(),
                    "now": now,
                    "window_start": now - timedelta(minutes=30),
                    "operation_id": operation_id,
                    "job_id": snapshot_job,
                },
            )
            session.execute(
                text(
                    "INSERT INTO hotlist_snapshots "
                    "(id, owner_id, source_key, job_id, operation_id, observed_at, entry_count) "
                    "VALUES (:id, :owner_id, 'hotlist_36kr', :job_id, :operation_id, "
                    ":now, 0)"
                ),
                {
                    "id": snapshot_id,
                    "owner_id": owner_id,
                    "job_id": snapshot_job,
                    "operation_id": operation_id,
                    "now": now,
                },
            )
            selected_sql: list[str] = []

            def count_selects(
                _connection: object,
                _cursor: object,
                statement: str,
                _parameters: object,
                _context: object,
                _executemany: bool,
            ) -> None:
                if statement.lstrip().lower().startswith("select"):
                    selected_sql.append(statement)

            engine = session.get_bind()
            event.listen(engine, "before_cursor_execute", count_selects)
            try:
                facts = ContentService(session).collection_snapshot_facts_in_transaction(
                    owner_id=owner_id,
                    job_ids=(unrelated_job, snapshot_job, no_snapshot_job),
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_selects)

            assert len(selected_sql) == 1
            assert [item.job_id for item in facts] == [
                unrelated_job,
                snapshot_job,
                no_snapshot_job,
            ]
            assert facts[0].snapshot_id is None
            assert facts[0].entry_count is None
            assert facts[1].snapshot_id == snapshot_id
            assert facts[1].entry_count == 0
            assert facts[1].observed_at == now
            assert facts[2].snapshot_id is None
            assert facts[2].entry_count is None
            other_owner_facts = ContentService(session).collection_snapshot_facts_in_transaction(
                owner_id=other_owner_id, job_ids=(snapshot_job,)
            )
            assert other_owner_facts[0].snapshot_id is None
        finally:
            session.rollback()
