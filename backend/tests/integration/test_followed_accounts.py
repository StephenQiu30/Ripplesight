from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.errors import ApplicationError
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


def _identity(
    *,
    external_id: str,
    alias_value: str,
    display_name: str = "相同展示名",
) -> FollowedAccountIdentityInput:
    return FollowedAccountIdentityInput(
        source_key="x",
        external_id=external_id,
        alias_value=alias_value,
        display_name=display_name,
    )


def test_stable_identity_survives_rename_and_keeps_alias_observations(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    observed_at = datetime(2026, 9, 25, tzinfo=UTC)
    service = FollowedAccountService(session, clock=lambda: observed_at)

    first = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )
    observed_at += timedelta(hours=1)
    renamed = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(
            external_id="1001",
            alias_value="small_new",
            display_name="新展示名",
        ),
    )

    assert renamed.id == first.id
    assert renamed.external_id == "1001"
    assert renamed.display_name == "新展示名"
    assert renamed.latest_observed_alias == "small_new"
    assert [
        (
            item.alias_value,
            item.first_seen_at,
            item.last_seen_at,
        )
        for item in renamed.aliases
    ] == [
        ("small", datetime(2026, 9, 25, tzinfo=UTC), datetime(2026, 9, 25, tzinfo=UTC)),
        ("small_new", datetime(2026, 9, 25, 1, tzinfo=UTC), datetime(2026, 9, 25, 1, tzinfo=UTC)),
    ]


def test_reused_alias_keeps_multiple_stable_identity_candidates(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    service = FollowedAccountService(session)

    first = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )
    second = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="2002", alias_value="small"),
    )
    candidates = service.find_by_alias(owner_id=owner_id, source_key="x", alias_value="small")

    assert first.id != second.id
    assert {candidate.external_id for candidate in candidates} == {"1001", "2002"}
    assert all(candidate.latest_observed_alias == "small" for candidate in candidates)


def test_reobserving_same_alias_updates_last_seen_without_duplicate_history(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    observed_at = datetime(2026, 9, 25, tzinfo=UTC)
    service = FollowedAccountService(session, clock=lambda: observed_at)

    service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )
    observed_at += timedelta(minutes=5)
    result = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )

    assert len(result.aliases) == 1
    assert result.aliases[0].first_seen_at == datetime(2026, 9, 25, tzinfo=UTC)
    assert result.aliases[0].last_seen_at == datetime(2026, 9, 25, 0, 5, tzinfo=UTC)


def test_account_and_alias_observation_timestamps_do_not_regress_with_clock(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    observed_at = datetime(2026, 9, 25, tzinfo=UTC)
    service = FollowedAccountService(session, clock=lambda: observed_at)

    service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )
    observed_at += timedelta(minutes=5)
    latest = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )

    observed_at -= timedelta(minutes=3)
    regressed = service.record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )

    assert regressed.id == latest.id
    assert regressed.updated_at == datetime(2026, 9, 25, 0, 5, tzinfo=UTC)
    assert regressed.aliases[0].first_seen_at == datetime(2026, 9, 25, tzinfo=UTC)
    assert regressed.aliases[0].last_seen_at == datetime(2026, 9, 25, 0, 5, tzinfo=UTC)


def test_account_read_hides_records_outside_owner_scope(
    followed_account_session: tuple[Session, UUID],
) -> None:
    session, owner_id = followed_account_session
    account = FollowedAccountService(session).record_confirmed_identity(
        owner_id=owner_id,
        identity=_identity(external_id="1001", alias_value="small"),
    )
    service = FollowedAccountService(session)

    with pytest.raises(ApplicationError, match="resource_not_found"):
        service.get_account(owner_id=uuid4(), account_id=account.id)

    assert (
        service.find_by_alias(
            owner_id=uuid4(),
            source_key="x",
            alias_value="small",
        )
        == []
    )
