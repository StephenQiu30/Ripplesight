from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, Engine, Table, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from core.errors import DependencyUnavailableError
from db.demo import DEFAULT_DEMO_SCOPE_ID, resolve_demo_scope
from db.metadata import metadata


@pytest.fixture
def demo_engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def _topic(engine: Engine, scope_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO monitor_topics (id, owner_id, name, created_at, updated_at) "
                "VALUES (:id, :scope, 'Demo scope test', now(), now())"
            ),
            {"id": uuid4(), "scope": scope_id},
        )


def test_empty_demo_resolves_without_creating_an_account_or_starting_a_transaction(
    demo_engine: Engine,
) -> None:
    with Session(demo_engine) as session:
        assert resolve_demo_scope(session) == DEFAULT_DEMO_SCOPE_ID
        assert not session.in_transaction()
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM monitor_topics")) == 0
    tables = inspect(demo_engine).get_table_names()
    assert "identity_users" not in tables and "identity_sessions" not in tables
    for table in tables:
        assert not any(
            fk["referred_table"] in {"identity_users", "identity_sessions"}
            for fk in inspect(demo_engine).get_foreign_keys(table)
        )


def test_existing_unique_partition_is_reused_without_selecting_a_user(demo_engine: Engine) -> None:
    scope_id = uuid4()
    _topic(demo_engine, scope_id)
    with Session(demo_engine) as session:
        assert resolve_demo_scope(session) == scope_id
        assert not session.in_transaction()


def test_multiple_historical_partitions_are_rejected(demo_engine: Engine) -> None:
    _topic(demo_engine, uuid4())
    _topic(demo_engine, uuid4())
    with (
        Session(demo_engine) as session,
        pytest.raises(DependencyUnavailableError, match="demo_scope_conflict"),
    ):
        resolve_demo_scope(session)


def test_newly_registered_business_tables_participate_in_partition_resolution(
    demo_engine: Engine,
) -> None:
    scope_id = uuid4()
    table = Table(
        "demo_scope_registered_test",
        metadata,
        Column("id", PG_UUID, primary_key=True),
        Column("owner_id", PG_UUID, nullable=False),
    )
    try:
        table.create(demo_engine)
        with demo_engine.begin() as connection:
            connection.execute(table.insert(), {"id": uuid4(), "owner_id": scope_id})
        with Session(demo_engine) as session:
            assert resolve_demo_scope(session) == scope_id
        _topic(demo_engine, uuid4())
        with (
            Session(demo_engine) as session,
            pytest.raises(DependencyUnavailableError, match="demo_scope_conflict"),
        ):
            resolve_demo_scope(session)
    finally:
        table.drop(demo_engine, checkfirst=True)
        metadata.remove(table)


@pytest.mark.parametrize("legacy_row", (False, True))
def test_empty_legacy_identity_schema_cannot_enable_anonymous_writes(
    demo_engine: Engine, legacy_row: bool
) -> None:
    try:
        with demo_engine.begin() as connection:
            connection.execute(text("CREATE TABLE identity_users (id uuid PRIMARY KEY)"))
            if legacy_row:
                connection.execute(
                    text("INSERT INTO identity_users (id) VALUES (:id)"), {"id": uuid4()}
                )
        with (
            Session(demo_engine) as session,
            pytest.raises(DependencyUnavailableError, match="demo_scope_conflict"),
        ):
            resolve_demo_scope(session)
    finally:
        with demo_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS identity_users"))
