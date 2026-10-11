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
    *,
    like_count: int | None = None,
) -> None:
    session.execute(
        text(
            "INSERT INTO content_observations "
            "(id, owner_id, content_id, job_id, source_operation_id, "
            "content_version_id, observed_at, received_at, like_count) VALUES "
            "(:id, :owner_id, :content_id, :job_id, :operation_id, "
            ":version_id, :observed_at, :observed_at, :like_count)"
        ),
        {
            "id": uuid4(),
            "owner_id": owner_id,
            "content_id": content_id,
            "job_id": job_id,
            "operation_id": uuid4(),
            "version_id": version_id,
            "observed_at": observed_at,
            "like_count": like_count,
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

            assert len(select_statements) == 1
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
            assert facts[0].updated_count == 0
            assert facts[0].unchanged_count == 0
            assert facts[0].unclassified_count == 1
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
            assert facts[2].updated_count == facts[2].unchanged_count == 0
            assert facts[2].unclassified_count == 0
            assert facts[2].content_ids == (shared_content,)
            assert facts[2].content_version_ids == tuple(sorted((shared_v1, shared_v2), key=str))
            assert facts[3].observation_count == 0
            assert facts[3].content_ids == facts[3].content_version_ids == ()

            other_owner_facts = ContentService(session).collection_facts_in_transaction(
                owner_id=other_owner_id, job_ids=(first_job, second_job)
            )
            assert all(item.observation_count == 0 for item in other_owner_facts)
            assert all(item.content_ids == () for item in other_owner_facts)
            assert all(
                item.updated_count == item.unchanged_count == 0 for item in other_owner_facts
            )
            assert all(item.unclassified_count == 0 for item in other_owner_facts)

            old_counts = ContentService(session).collection_counts_in_transaction(
                owner_id=owner_id, job_ids=(first_job, second_job)
            )
            assert old_counts[0].first_ingested_count == 1
            assert old_counts[1].deduplicated_count == 2
            assert old_counts[1].unclassified_count == 1
            assert "content_ids" not in old_counts[0].model_dump()
        finally:
            session.rollback()


def test_collection_identity_counts_partition_updates_duplicates_and_unknowns(
    content_fact_sessions: sessionmaker[Session],
) -> None:
    owner, first_job, second_job = uuid4(), uuid4(), uuid4()
    changed, metric_changed, duplicate, unknown, added = (uuid4() for _ in range(5))
    versions = {
        content: (uuid4(), uuid4())
        for content in (changed, metric_changed, duplicate, unknown, added)
    }
    now = datetime(2026, 10, 11, tzinfo=UTC)
    with content_fact_sessions() as session, session.begin():
        try:
            for job in (first_job, second_job):
                _seed_job(session, owner, job, now)
            for content, version_ids in versions.items():
                _seed_content(session, owner, content, version_ids, now)
            for index, content in enumerate((changed, metric_changed, duplicate, unknown)):
                _seed_observation(
                    session,
                    owner,
                    first_job,
                    content,
                    versions[content][0],
                    now + timedelta(seconds=index),
                    like_count=0,
                )
            for index, (content, version, likes) in enumerate(
                (
                    (changed, versions[changed][1], 1),
                    (metric_changed, versions[metric_changed][0], 1),
                    (duplicate, versions[duplicate][0], 0),
                    (duplicate, versions[duplicate][0], 0),
                    (unknown, None, None),
                    (added, versions[added][0], 0),
                    (added, versions[added][1], 1),
                ),
                start=10,
            ):
                _seed_observation(
                    session,
                    owner,
                    second_job,
                    content,
                    version,
                    now + timedelta(seconds=index),
                    like_count=likes,
                )
            service = ContentService(session)
            facts = service.collection_facts_in_transaction(owner_id=owner, job_ids=(second_job,))
            fact = facts[0]
            assert fact.observation_count == 7
            assert fact.ingested_count == 5
            assert (fact.first_ingested_count, fact.updated_count) == (1, 2)
            assert (fact.unchanged_count, fact.unclassified_count) == (1, 1)
            assert (
                fact.first_ingested_count
                + fact.updated_count
                + fact.unchanged_count
                + fact.unclassified_count
            ) == fact.ingested_count
            assert fact.deduplicated_count == 6  # Legacy observation denominator is different.
            # Read-only replay preserves accounting and does not create more observations.
            assert (
                service.collection_facts_in_transaction(owner_id=owner, job_ids=(second_job,))
                == facts
            )
        finally:
            session.rollback()


def test_collection_identity_denominator_stays_consistent_while_running_job_appends(
    content_fact_sessions: sessionmaker[Session],
) -> None:
    owner, running_job, baseline_job, content, v1, v2 = (uuid4() for _ in range(6))
    now = datetime(2026, 10, 11, tzinfo=UTC)
    with content_fact_sessions() as session, session.begin():
        for job in (running_job, baseline_job):
            _seed_job(session, owner, job, now)
        _seed_content(session, owner, content, (v1, v2), now)
        _seed_observation(session, owner, baseline_job, content, v1, now)

    appended = False
    reads = 0

    def append_after_snapshot(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal appended, reads
        if not statement.lstrip().lower().startswith("select"):
            return
        reads += 1
        if appended:
            return
        appended = True
        with content_fact_sessions() as writer, writer.begin():
            _seed_observation(writer, owner, running_job, content, v2, now + timedelta(seconds=1))

    with content_fact_sessions() as session, session.begin():
        engine = session.get_bind()
        event.listen(engine, "after_cursor_execute", append_after_snapshot)
        try:
            facts = ContentService(session).collection_facts_in_transaction(
                owner_id=owner, job_ids=(running_job, baseline_job)
            )
        finally:
            event.remove(engine, "after_cursor_execute", append_after_snapshot)
        assert appended and reads == 1
        assert facts[0].ingested_count == facts[0].updated_count == 0
        assert facts[0].content_ids == ()
        assert facts[1].ingested_count == facts[1].first_ingested_count == 1
        latest = ContentService(session).collection_facts_in_transaction(
            owner_id=owner, job_ids=(running_job,)
        )[0]
        assert latest.ingested_count == latest.updated_count == 1
        assert (
            latest.first_ingested_count == latest.unchanged_count == latest.unclassified_count == 0
        )


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


def test_execution_denominators_use_one_snapshot_while_new_receipt_arrives(
    content_fact_sessions: sessionmaker[Session],
) -> None:
    owner, job, baseline, content, version = (uuid4() for _ in range(5))
    now = datetime(2026, 10, 12, tzinfo=UTC)
    with content_fact_sessions() as session, session.begin():
        for identifier in (job, baseline):
            _seed_job(session, owner, identifier, now)
        _seed_content(session, owner, content, (version,), now)
        _seed_observation(session, owner, baseline, content, version, now)
        session.execute(
            text(
                "INSERT INTO job_attempts (id,job_id,lease_epoch,collection_cycle_no,worker_id,"
                "queued_at,started_at,lease_expires_at,collection_counts_tracked) "
                "VALUES (:id,:job,1,1,'test',:now,:now,:expires,true)"
            ),
            {"id": uuid4(), "job": job, "now": now, "expires": now + timedelta(seconds=60)},
        )
    reads = 0

    def append_after_snapshot(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal reads
        if not statement.lstrip().lower().startswith("select"):
            return
        reads += 1
        if reads > 1:
            return
        with content_fact_sessions() as writer, writer.begin():
            _seed_observation(writer, owner, job, content, version, now + timedelta(seconds=1))
            writer.execute(
                text("UPDATE content_observations SET execution_epoch=1 WHERE job_id=:job"),
                {"job": job},
            )

    with content_fact_sessions() as session, session.begin():
        engine = session.get_bind()
        event.listen(engine, "after_cursor_execute", append_after_snapshot)
        try:
            counts = ContentService(session).collection_execution_counts_in_transaction(
                owner_id=owner, job_id=job, epochs=(1, 2)
            )
        finally:
            event.remove(engine, "after_cursor_execute", append_after_snapshot)
        assert reads == 1
        assert all(item.ingested_count == item.observation_count == 0 for item in counts)
        latest = ContentService(session).collection_execution_counts_in_transaction(
            owner_id=owner, job_id=job, epochs=(1, 2)
        )
        assert latest[0].ingested_count == latest[0].unchanged_count == 1
        assert latest[0].content_version_ids == (version,)
        assert latest[1].ingested_count == 0
        denied = ContentService(session).collection_execution_counts_in_transaction(
            owner_id=uuid4(), job_id=job, epochs=(1,)
        )
        assert denied[0].ingested_count == 0
