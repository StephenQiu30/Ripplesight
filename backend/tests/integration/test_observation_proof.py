"""Explicit source and ALL-input proofs in real isolated PostgreSQL, no providers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.integration.test_analysis_observation_inputs import aliases, freeze
from tests.integration.test_content_records import (
    _command,
    _comment_command,
    _seed_comment_context,
    _seed_context,
    _user_scope,
)
from tests.integration.test_content_records import content_client as content_client
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from content.analysis_inputs import analysis_observation_manifests_readable_in_transaction
from content.models import ContentObservation, ContentObservationInput, ContentVersionInput
from content.observation_inputs import (
    freeze_observation_inputs_in_transaction,
    observation_input_closures_in_transaction,
    save_observation_inputs_in_transaction,
)
from content.observation_reading import readable_observation_groups_in_transaction
from content.report_reading import report_inputs_readable_in_transaction
from content.services import ContentObservationCleanup, ContentService
from core.errors import ApplicationError

_UNKNOWN = (
    "UPDATE content_observations SET input_basis=NULL,source_key=NULL,"
    "source_native_scope=NULL,source_external_id=NULL,source_identity_basis=NULL,"
    "editorial_profile_id=NULL,native_identity_proof=NULL WHERE id=:id"
)


@pytest.mark.parametrize("kind", ["post", "comment", "metrics"])
def test_actual_social_persistence_freezes_source_and_keeps_new_material_readable(
    content_client, kind
):
    owner = _user_scope(content_client)
    now = datetime.now(UTC)
    connection, policy, retention, job, _ = _seed_context(content_client, owner, now=now)
    if kind == "comment":
        policy, retention, job = _seed_comment_context(content_client, owner, connection)
        command = _comment_command(
            owner_id=owner,
            connection_id=connection,
            policy_id=policy,
            retention_id=retention,
            job_id=job,
            external_id="proof-comment",
            post_external_id="proof-post",
        )
    else:
        command = _command(
            owner_id=owner,
            connection_id=connection,
            policy_id=policy,
            retention_id=retention,
            job_id=job,
            operation_id=uuid4(),
            observed_at=now,
            extra_fields={
                "body": "Exact new source text",
                "text_scope": "full",
                "text_origin": "source",
            }
            if kind == "post"
            else {},
        )
    read_at = now + timedelta(seconds=1)
    with content_client.app.state.session_factory() as session:
        service = ContentService(session, clock=lambda: read_at)
        persist = service.persist_comment if kind == "comment" else service.persist_post
        first = persist(owner_id=owner, command=command)
        replay = persist(owner_id=owner, command=command)
        assert first.latest_observation.id == replay.latest_observation.id
        identifier = first.latest_observation.id
        with session.begin():
            row = session.get(ContentObservation, identifier)
            assert (row.input_basis, row.source_key, row.source_external_id) == (
                "source_v1",
                "x",
                command.admission.fields["external_id"],
            )
            assert row.source_identity_basis is None and row.editorial_profile_id is None
            groups = {"new": (identifier,)}
            assert readable_observation_groups_in_transaction(
                session,
                owner_id=owner,
                observation_groups=groups,
                now=read_at,
                include_metadata=kind == "metrics",
            ) == {"new": (identifier,)}
            if kind == "metrics":
                assert readable_observation_groups_in_transaction(
                    session, owner_id=owner, observation_groups=groups, now=read_at
                ) == {"new": None}
            session.execute(text(_UNKNOWN), {"id": identifier})
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            persist(owner_id=owner, command=command)
        session.rollback()
        with session.begin():
            assert (
                session.scalar(
                    select(ContentObservation.input_basis).where(
                        ContentObservation.id == identifier
                    )
                )
                is None
            )
            assert len(tuple(session.scalars(select(ContentObservation.id)))) == 1


@pytest.mark.parametrize("version_edges", [False, True])
def test_unknown_original_never_borrows_same_version_or_version_witness_permission(
    engine, version_edges
):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            held = session.get(ContentObservation, a[2])
            assert held.input_basis == "source_v1"
            session.execute(text(_UNKNOWN), {"id": a[2]})
            if version_edges:
                session.add(
                    ContentVersionInput(
                        owner_id=owner, content_version_id=a[1], observation_id=b[2]
                    )
                )
                session.flush()
            assert analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=(manifest_a, manifest_b), now=NOW
            ) == {manifest_a.signature: False, manifest_b.signature: True}
            assert not report_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(a[1],),
                observation_ids=(a[2],),
                now=NOW,
            )
            assert not report_inputs_readable_in_transaction(
                session, owner_id=owner, content_version_ids=(a[1],), observation_ids=(), now=NOW
            )
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                freeze_observation_inputs_in_transaction(
                    session, owner_id=owner, observation_ids=(a[2],), now=NOW
                )
            assert held.input_basis is None
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(b[2],), now=NOW
            ) == (b[2],)


def _node_values(original, identifier, basis):
    values = {
        column.name: getattr(original, column.name)
        for column in ContentObservation.__table__.columns
    }
    values.update(id=identifier, source_operation_id=uuid4(), input_basis=basis)
    return values


@pytest.mark.parametrize("shape", ["leaf_edge", "derived_empty", "cycle", "missing", "cross_owner"])
def test_invalid_explicit_graph_rejects_only_its_own_output(engine, shape):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            original = session.get(ContentObservation, a[2])
            left, right = uuid4(), uuid4()
            session.execute(
                insert(ContentObservation),
                [
                    _node_values(
                        original, left, "source_v1" if shape == "leaf_edge" else "observations_v1"
                    ),
                    _node_values(
                        original, right, "observations_v1" if shape == "cycle" else "source_v1"
                    ),
                ],
            )
            if shape in {"leaf_edge", "cycle"}:
                session.add(
                    ContentObservationInput(
                        owner_id=owner, output_observation_id=left, input_observation_id=right
                    )
                )
            if shape == "cycle":
                session.add(
                    ContentObservationInput(
                        owner_id=owner, output_observation_id=right, input_observation_id=left
                    )
                )
            session.flush()
            roots = (uuid4(),) if shape == "missing" else (left,)
            if shape == "cross_owner":
                assert observation_input_closures_in_transaction(
                    session, owner_id=uuid4(), observation_groups={"wrong": (a[2],)}
                ) == {"wrong": None}
            result = observation_input_closures_in_transaction(
                session, owner_id=owner, observation_groups={"invalid": roots, "valid": (b[2],)}
            )
            assert result == {"invalid": None, "valid": (b[2],)}


def test_all_closure_limit_and_bulk_final_group_never_truncate_or_infect_other_output(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            original = session.get(ContentObservation, a[2])
            root = uuid4()
            leaves = tuple(uuid4() for _ in range(2000))
            session.execute(
                insert(ContentObservation),
                [
                    _node_values(original, root, "observations_v1"),
                    *(_node_values(original, identifier, "source_v1") for identifier in leaves),
                ],
            )
            session.execute(
                insert(ContentObservationInput),
                [
                    {"owner_id": owner, "output_observation_id": root, "input_observation_id": item}
                    for item in leaves[:1999]
                ],
            )
            within = observation_input_closures_in_transaction(
                session, owner_id=owner, observation_groups={"bounded": (root,)}
            )["bounded"]
            assert len(within) == 2000 and set(within) == {root, *leaves[:1999]}
            session.add(
                ContentObservationInput(
                    owner_id=owner, output_observation_id=root, input_observation_id=leaves[-1]
                )
            )
            session.flush()
            groups = {str(i): (b[2],) for i in range(1000)}
            groups["last"] = (root,)
            result = observation_input_closures_in_transaction(
                session, owner_id=owner, observation_groups=groups
            )
            assert result.pop("last") is None
            assert len(result) == 1000 and all(value == (b[2],) for value in result.values())


@pytest.mark.parametrize(
    "correction",
    [
        "input_basis='invalid'",
        "source_key=NULL",
        "source_external_id=''",
        "source_identity_basis='fake'",
        "source_identity_basis=NULL",
    ],
)
def test_schema_rejects_invalid_modern_provenance_and_editorial_null_basis(engine, correction):
    with Session(engine) as session:
        _, _, _, a, _ = aliases(session)
        with pytest.raises(IntegrityError), session.begin():
            session.execute(
                text(f"UPDATE content_observations SET {correction} WHERE id=:id"), {"id": a[2]}
            )


def test_unknown_output_cannot_acquire_explicit_inputs_by_replay(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            held = session.get(ContentObservation, a[2])
            held.input_basis = "observations_v1"
            session.flush()
            session.execute(text(_UNKNOWN), {"id": a[2]})
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                save_observation_inputs_in_transaction(
                    session,
                    owner_id=owner,
                    output_observation_id=a[2],
                    input_observation_ids=(b[2],),
                )
            assert not tuple(
                session.scalars(
                    select(ContentObservationInput.input_observation_id).where(
                        ContentObservationInput.output_observation_id == a[2]
                    )
                )
            )
            assert held.input_basis is None


def test_concurrent_same_operation_keeps_one_original_derived_observation_and_graph(content_client):
    owner = _user_scope(content_client)
    now = datetime.now(UTC)
    connection, policy, retention, job, _ = _seed_context(content_client, owner, now=now)
    command = _command(
        owner_id=owner,
        connection_id=connection,
        policy_id=policy,
        retention_id=retention,
        job_id=job,
        operation_id=uuid4(),
        observed_at=now,
        extra_fields={"body": "Actual input", "text_scope": "full", "text_origin": "source"},
    )
    sessions = content_client.app.state.session_factory
    with sessions() as session:
        source = ContentService(session, clock=lambda: now).persist_post(
            owner_id=owner, command=command
        )
    derived = command.model_copy(update={"source_operation_id": uuid4()})
    barrier = Barrier(2)

    def persist():
        with sessions.begin() as session:
            barrier.wait(timeout=10)
            return (
                ContentService(session, clock=lambda: now)
                .persist_post_in_transaction(
                    owner_id=owner,
                    command=derived,
                    input_observation_ids=(source.latest_observation.id,),
                )
                .latest_observation.id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: persist(), range(2)))
    assert results[0] == results[1]
    with sessions.begin() as session:
        output = session.get(ContentObservation, results[0])
        assert output.input_basis == "observations_v1"
        assert set(session.scalars(select(ContentObservation.id))) == {
            source.latest_observation.id,
            output.id,
        }
        assert tuple(
            session.scalars(
                select(ContentObservationInput.input_observation_id).where(
                    ContentObservationInput.output_observation_id == output.id
                )
            )
        ) == (source.latest_observation.id,)


def test_another_transaction_cleanup_invalidates_held_reader_without_alias_substitution(engine):
    from sqlalchemy.orm import sessionmaker

    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            first, second = freeze(session, owner, a), freeze(session, owner, b)
            held = session.get(ContentObservation, a[2])
            assert held is not None
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(a[2],), now=NOW
            ) == (a[2],)
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(
                    ContentObservationCleanup(sessions, clock=lambda: NOW), str(a[2])
                ).result(timeout=15)
            assert analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=(first, second), now=NOW
            ) == {first.signature: False, second.signature: True}
