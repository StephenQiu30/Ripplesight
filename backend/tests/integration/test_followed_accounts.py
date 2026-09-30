from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from monitors.schemas import FollowedAccountIdentityInput
from monitors.services import FollowedAccountService


@pytest.fixture
def followed_account_session() -> Iterator[tuple[Session, UUID]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    owner_id = uuid4()

    session = Session(engine)
    try:
        yield session, owner_id
    finally:
        session.close()
        engine.dispose()


def test_postgres_keeps_stable_identity_and_owner_scoped_alias_history(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    observed_at = datetime(2026, 9, 25, tzinfo=UTC)
    service = FollowedAccountService(session, clock=lambda: observed_at)

    first = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=FollowedAccountIdentityInput(
            source_key="x",
            external_id="1001",
            alias_value="small",
            display_name="相同展示名",
        ),
    )
    observed_at += timedelta(hours=1)
    renamed = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=FollowedAccountIdentityInput(
            source_key="x",
            external_id="1001",
            alias_value="small_new",
            display_name="新展示名",
        ),
    )
    reused = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=FollowedAccountIdentityInput(
            source_key="x",
            external_id="2002",
            alias_value="small",
            display_name="相同展示名",
        ),
    )

    assert renamed.id == first.id
    assert renamed.external_id == "1001"
    assert renamed.latest_observed_alias == "small_new"
    assert {
        candidate.external_id
        for candidate in service.find_by_alias(
            owner_id=owner_id,
            source_key="x",
            alias_value="small",
        )
    } == {"1001", "2002"}
    assert reused.id != first.id
    assert (
        service.find_by_alias(
            owner_id=uuid4(),
            source_key="x",
            alias_value="small",
        )
        == []
    )
