from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from db.owners import list_owner_ids_in_transaction, require_owner_id
from identity.models import IdentityUser


@pytest.fixture
def owner_engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def _account(engine: Engine) -> UUID:
    owner = uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(
            IdentityUser(
                id=owner,
                username=f"user.{owner.hex}",
                email=None,
                github_user_id=None,
                password_hash=None,
                credential_version=1,
                created_at=now,
                updated_at=now,
            )
        )
    return owner


def test_empty_database_has_identity_schema_but_no_automatic_account(owner_engine: Engine) -> None:
    tables = inspect(owner_engine).get_table_names()
    assert {"identity_users", "identity_sessions"} <= set(tables)
    with Session(owner_engine) as session, session.begin():
        assert list_owner_ids_in_transaction(session) == ()
    for table in tables:
        if table.startswith("identity_"):
            continue
        assert not any(
            fk["referred_table"] in {"identity_users", "identity_sessions"}
            for fk in inspect(owner_engine).get_foreign_keys(table)
        )


def test_explicit_account_is_required_for_maintenance(owner_engine: Engine) -> None:
    owner = _account(owner_engine)
    with Session(owner_engine) as session:
        assert require_owner_id(session, owner) == owner
        assert not session.in_transaction()
        with pytest.raises(ApplicationError, match="resource_not_found"):
            require_owner_id(session, uuid4())


def test_multiple_valid_accounts_are_enumerated_without_selecting_the_first(
    owner_engine: Engine,
) -> None:
    first, second = _account(owner_engine), _account(owner_engine)
    with Session(owner_engine) as session, session.begin():
        assert set(list_owner_ids_in_transaction(session)) == {first, second}


def test_historical_partition_does_not_become_an_automatic_account(owner_engine: Engine) -> None:
    orphan = uuid4()
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO monitor_topics (id, owner_id, name, created_at, updated_at) "
                "VALUES (:id, :scope, 'Historical partition', now(), now())"
            ),
            {"id": uuid4(), "scope": orphan},
        )
    with Session(owner_engine) as session:
        with pytest.raises(ApplicationError, match="resource_not_found"):
            require_owner_id(session, orphan)
        with session.begin():
            assert list_owner_ids_in_transaction(session) == ()
