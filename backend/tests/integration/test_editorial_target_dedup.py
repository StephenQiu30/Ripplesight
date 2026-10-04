from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from tests.unit.test_editorial_rsshub import NOW, rsshub_config

from connections.editorial_schemas import EditorialProfileInput
from connections.editorial_services import EditorialSourceService
from core.errors import ApplicationError
from sources.editorial_schemas import EditorialSourceConfiguration


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL is required")
    value = create_engine(url)
    try:
        yield value
    finally:
        value.dispose()


def command(target: str = "sample", **overrides: object) -> EditorialProfileInput:
    value = EditorialProfileInput(
        operation_id=uuid4(),
        name="Controlled RSSHub target",
        reason="Controlled exact target deduplication",
        policy_version=1,
        interval_minutes=60,
        configuration=rsshub_config(target=target, route=f"/threads/{target}"),
    )
    return value.model_copy(update=overrides)


def test_duplicate_target_is_rejected_atomically_but_operation_replay_and_self_edit_work(engine):
    owner = uuid4()
    with Session(engine) as session:
        service = EditorialSourceService(session, clock=lambda: NOW)
        first = command()
        existing = service.save_profile(owner_id=owner, command=first)
        assert service.save_profile(owner_id=owner, command=first) == existing
        duplicate = command(name="Another label")
        with pytest.raises(ApplicationError, match="editorial_target_conflict"):
            service.save_profile(owner_id=owner, command=duplicate)
        with session.begin():
            assert (
                session.scalar(
                    text("SELECT count(*) FROM editorial_source_profiles WHERE owner_id=:owner"),
                    {"owner": owner},
                )
                == 1
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM source_connections WHERE owner_id=:owner"),
                    {"owner": owner},
                )
                == 1
            )
        edited = service.save_profile(
            owner_id=owner,
            profile_id=existing.id,
            command=command(expected_revision=existing.revision, name="Edited existing target"),
        )
        assert edited.id == existing.id and edited.revision == existing.revision + 1


def test_target_change_conflict_rolls_back_revision_and_local_host_is_not_a_new_target(engine):
    owner = uuid4()
    with Session(engine) as session:
        service = EditorialSourceService(session, clock=lambda: NOW)
        first = service.save_profile(owner_id=owner, command=command())
        second_command = command("another")
        second = service.save_profile(owner_id=owner, command=second_command)
        with pytest.raises(ApplicationError, match="editorial_target_conflict"):
            service.save_profile(
                owner_id=owner,
                profile_id=second.id,
                command=command(expected_revision=second.revision),
            )
        assert service.get_profile(owner_id=owner, profile_id=second.id).revision == second.revision
        alternate_host = EditorialSourceConfiguration.model_validate(
            {
                **first.configuration.model_dump(mode="json"),
                "allowed_hosts": ["host.docker.internal"],
                "feed_url": "http://host.docker.internal:1200/threads/sample",
            }
        )
        with pytest.raises(ApplicationError, match="editorial_target_conflict"):
            service.save_profile(owner_id=owner, command=command(configuration=alternate_host))


def test_owner_and_distinct_routes_are_separate_and_generic_feeds_keep_existing_semantics(engine):
    with Session(engine) as session:
        service = EditorialSourceService(session, clock=lambda: NOW)
        owner = uuid4()
        service.save_profile(owner_id=owner, command=command())
        other = service.save_profile(owner_id=uuid4(), command=command())
        assert other.enabled is False
        search = rsshub_config(query_mode="tag_feed", route="/threads/search/sample")
        service.save_profile(owner_id=owner, command=command(configuration=search))
        generic = EditorialSourceConfiguration(
            kind="rss", feed_url="https://example.com/feed", allowed_hosts=("example.com",)
        )
        service.save_profile(owner_id=owner, command=command(configuration=generic))
        service.save_profile(owner_id=owner, command=command(configuration=generic))


def test_concurrent_creation_of_same_owner_target_commits_only_one_profile(engine):
    owner = uuid4()
    barrier = Barrier(2)

    def save(_index: int) -> UUID | str:
        with Session(engine) as session:
            barrier.wait(timeout=5)
            try:
                return (
                    EditorialSourceService(session, clock=lambda: NOW)
                    .save_profile(owner_id=owner, command=command())
                    .id
                )
            except ApplicationError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert sum(isinstance(result, UUID) for result in results) == 1
    assert results.count("editorial_target_conflict") == 1
    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM editorial_source_profiles WHERE owner_id=:owner"),
                {"owner": owner},
            )
            == 1
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM editorial_source_profile_versions WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
            == 1
        )
