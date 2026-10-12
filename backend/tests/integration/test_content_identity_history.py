"""Verify reliable first identities and exact baselines against isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.integration.test_content_records import (
    _command,
    _seed_context,
    _user_scope,
)
from tests.integration.test_content_records import (
    content_client as content_client,
)

from content.identity_history import register_new_owner_history_in_transaction
from content.lifecycle import purge_observation_dependants_in_transaction
from content.services import ContentService


def _setup(client: TestClient):
    owner = _user_scope(client)
    connection, policy, retention, first, second = _seed_context(client, owner)
    command = _command(
        owner_id=owner,
        connection_id=connection,
        policy_id=policy,
        retention_id=retention,
        job_id=first,
        operation_id=uuid4(),
        observed_at=datetime.now(UTC) - timedelta(minutes=1),
        extra_fields={"text_scope": "full", "text_origin": "source", "body": "固定正文"},
    )
    return owner, first, second, command, client.app.state.session_factory


def _partition(factory, owner, job):
    with factory() as session, session.begin():
        facts = ContentService(session).collection_facts_in_transaction(
            owner_id=owner, job_ids=(job,)
        )[0]
    return (
        facts.first_ingested_count,
        facts.updated_count,
        facts.unchanged_count,
        facts.unclassified_count,
    )


def test_exact_baseline_gap_is_unknown_and_replay_keeps_original_proof(
    content_client: TestClient,
) -> None:
    owner, first, second, command, factory = _setup(content_client)
    later_command = command.model_copy(update={"job_id": second, "source_operation_id": uuid4()})
    with factory() as session:
        created = ContentService(session).persist_post(owner_id=owner, command=command)
        later = ContentService(session).persist_post(owner_id=owner, command=later_command)
    assert _partition(factory, owner, first) == (1, 0, 0, 0)
    assert _partition(factory, owner, second) == (0, 0, 1, 0)
    with factory() as session, session.begin():
        proof = session.execute(
            text(
                "SELECT first_identity_state, comparison_predecessor_id "
                "FROM content_observations WHERE id=:id"
            ),
            {"id": later.latest_observation.id},
        ).one()
        assert tuple(proof) == ("confirmed_existing", created.latest_observation.id)
        purge_observation_dependants_in_transaction(
            session,
            owner_id=owner,
            observation_id=created.latest_observation.id,
            now=datetime.now(UTC),
        )
    assert _partition(factory, owner, second) == (0, 0, 0, 1)
    with factory() as session:
        replay = ContentService(session).persist_post(owner_id=owner, command=later_command)
        assert replay.latest_observation.id == later.latest_observation.id
        assert (
            session.scalar(
                text("SELECT comparison_predecessor_id FROM content_observations WHERE id=:id"),
                {"id": replay.latest_observation.id},
            )
            == created.latest_observation.id
        )
    assert _partition(factory, owner, second) == (0, 0, 0, 1)


def test_complete_identity_cleanup_sticks_unknown_across_recollection_and_registration(
    content_client: TestClient,
) -> None:
    owner, _, second, command, factory = _setup(content_client)
    with factory() as session:
        saved = ContentService(session).persist_post(owner_id=owner, command=command)
    with factory() as session, session.begin():
        purge_observation_dependants_in_transaction(
            session,
            owner_id=owner,
            observation_id=saved.latest_observation.id,
            now=datetime.now(UTC),
        )
        register_new_owner_history_in_transaction(session, owner_id=owner, now=datetime.now(UTC))
        assert (
            session.scalar(
                text("SELECT state FROM content_identity_history WHERE owner_id=:id"), {"id": owner}
            )
            == "unknown"
        )
    fresh = command.model_copy(update={"job_id": second, "source_operation_id": uuid4()})
    with factory() as session:
        recollected = ContentService(session).persist_post(owner_id=owner, command=fresh)
        assert recollected.id != saved.id
        assert (
            session.scalar(
                text("SELECT first_identity_state FROM content_observations WHERE id=:id"),
                {"id": recollected.latest_observation.id},
            )
            == "unknown"
        )
    assert _partition(factory, owner, second) == (0, 0, 0, 1)


def test_missing_legacy_registration_is_never_assumed_clean(content_client: TestClient) -> None:
    owner, first, _, command, factory = _setup(content_client)
    with factory() as session, session.begin():
        session.execute(
            text("DELETE FROM content_identity_history WHERE owner_id=:id"), {"id": owner}
        )
    with factory() as session:
        ContentService(session).persist_post(owner_id=owner, command=command)
    assert _partition(factory, owner, first) == (0, 0, 0, 1)


def test_concurrent_first_receipts_freeze_one_first_identity(content_client: TestClient) -> None:
    owner, first, second, command, factory = _setup(content_client)
    barrier = Barrier(2)
    commands = (
        command,
        command.model_copy(update={"job_id": second, "source_operation_id": uuid4()}),
    )

    def collect(value):
        with factory() as session:
            barrier.wait(timeout=10)
            return ContentService(session).persist_post(owner_id=owner, command=value)

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(collect, commands))
    assert receipts[0].id == receipts[1].id
    partitions = [_partition(factory, owner, job) for job in (first, second)]
    assert sorted(partitions) == [(0, 0, 1, 0), (1, 0, 0, 0)]


@pytest.mark.parametrize(
    "values",
    [
        (None, "confirmed_first", None),
        (None, "confirmed_existing", uuid4()),
        (1, None, None),
        (1, "confirmed_existing", None),
        (1, "confirmed_first", uuid4()),
        (2, "confirmed_first", None),
        (1, "bogus", None),
    ],
)
def test_partial_or_invalid_count_proof_is_rejected_by_postgresql(
    content_client: TestClient, values
) -> None:
    owner, _, _, command, factory = _setup(content_client)
    with factory() as session:
        saved = ContentService(session).persist_post(owner_id=owner, command=command)
    with factory() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(
            text(
                "UPDATE content_observations SET count_provenance_version=:version, "
                "first_identity_state=:state, comparison_predecessor_id=:previous WHERE id=:id"
            ),
            {
                "version": values[0],
                "state": values[1],
                "previous": values[2],
                "id": saved.latest_observation.id,
            },
        )


@pytest.mark.parametrize("metadata_only", [False, True])
def test_withdrawn_source_baseline_is_unknown_even_for_metadata_only(
    content_client: TestClient, metadata_only: bool
) -> None:
    owner, _, second, command, factory = _setup(content_client)
    if metadata_only:
        fields = dict(command.admission.fields)
        for field in ("text_scope", "text_origin", "body"):
            fields.pop(field)
        command = command.model_copy(
            update={"admission": command.admission.model_copy(update={"fields": fields})}
        )
    with factory() as session:
        first = ContentService(session).persist_post(owner_id=owner, command=command)
        later_fields = dict(command.admission.fields, like_count=1)
        ContentService(session).persist_post(
            owner_id=owner,
            command=command.model_copy(
                update={
                    "job_id": second,
                    "source_operation_id": uuid4(),
                    "admission": command.admission.model_copy(update={"fields": later_fields}),
                }
            ),
        )
    assert (first.latest_observation.content_version is None) is metadata_only
    assert _partition(factory, owner, second) == (0, 1, 0, 0)
    with factory() as session, session.begin():
        session.execute(
            text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
            {"owner": owner},
        )
    assert _partition(factory, owner, second) == (0, 0, 0, 1)


def test_cleanup_waits_for_history_before_locking_an_observation(
    content_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    from content import services
    from content.identity_history import lock_owner_history_in_transaction

    owner, _, _, command, factory = _setup(content_client)
    with factory() as session:
        saved = ContentService(session).persist_post(owner_id=owner, command=command)
    entered = Event()
    original = services.lock_owner_history_in_transaction

    def observed_lock(session, *, owner_id):
        entered.set()
        return original(session, owner_id=owner_id)

    monkeypatch.setattr(services, "lock_owner_history_in_transaction", observed_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with factory() as session, session.begin():
            lock_owner_history_in_transaction(session, owner_id=owner)
            pending = executor.submit(
                services.ContentObservationCleanup(factory), str(saved.latest_observation.id)
            )
            assert entered.wait(timeout=10)
            # Cleanup is blocked on owner. It must not already hold this row's UPDATE lock.
            assert (
                session.scalar(
                    text("SELECT id FROM content_observations WHERE id=:id FOR UPDATE NOWAIT"),
                    {"id": saved.latest_observation.id},
                )
                == saved.latest_observation.id
            )
        pending.result(timeout=20)
    with factory() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM content_observations WHERE id=:id"),
                {"id": saved.latest_observation.id},
            )
            == 0
        )
