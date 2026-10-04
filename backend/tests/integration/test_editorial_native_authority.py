"""Real original Job leases and staged RSS materials; no platform or collector requests."""

import os
from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from tests.integration.test_content_native_identity import collect, configured
from tests.integration.test_editorial_rsshub import approval, configure, enable
from tests.integration.test_editorial_source_profiles import job
from tests.unit.test_editorial_native_identity import feed
from tests.unit.test_editorial_rsshub import NOW

from connections.editorial_identity import (
    load_editorial_native_identity_source_material_in_transaction,
    require_editorial_native_identity_authority_in_transaction,
)
from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceRun
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentObservation, ContentVersion
from core.errors import ApplicationError
from jobs.execution import JobExecutionService, StaleExecutionLeaseError
from sources.adapters.editorial_rss import parse_feed
from sources.editorial_schemas import (
    EditorialBodyCheckpoint,
    EditorialBodyTarget,
    EditorialCursor,
    EditorialPage,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL is required")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def prepared_source(session):
    service, owner, profile, command = configure(session)
    service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=approval(profile))
    profile = enable(service, owner, profile, command)
    accepted, operation = job(session, owner, profile)
    lease = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).acquire(
        job_id=accepted.id, worker_id="native-authority-test"
    )

    def guard(current, guard_owner, guard_job):
        assert guard_owner == owner and guard_job == accepted.id
        JobExecutionService(
            current, lease_seconds=30, clock=lambda: NOW
        ).require_current_lease_in_transaction(lease)
        return True

    run = service.begin_run(
        owner_id=owner,
        profile_id=profile.id,
        configuration_version=profile.configuration_version,
        revision=profile.revision,
        job_id=accepted.id,
        operation_id=operation,
        guard=guard,
    ).result
    material = parse_feed(feed(), profile.configuration.feed_url, profile.configuration)[0]
    assert material.native_identity is not None
    page = EditorialPage(
        status="partial",
        reason="rsshub_limited_snapshot",
        materials=(material,),
        cursor=EditorialCursor(),
        observed_at=NOW,
    )
    service.stage_page(owner_id=owner, run_id=run.run_id, page=page, guard=guard)
    return service, owner, profile, accepted, run, material, lease, guard


def authority(session, owner, profile, accepted, material, **changes):
    arguments = {
        "owner_id": owner,
        "profile_id": profile.id,
        "configuration_version": profile.configuration_version,
        "job_id": accepted.id,
        "material": material,
        "proof": material.native_identity,
        "now": NOW,
        **changes,
    }
    require_editorial_native_identity_authority_in_transaction(session, **arguments)


def test_current_approved_source_job_and_original_staged_material_authorize_without_writes(engine):
    with Session(engine) as session:
        _, owner, profile, accepted, run, material, _, guard = prepared_source(session)
        with session.begin():
            assert guard(session, owner, accepted.id)
            authority(session, owner, profile, accepted, material)
            target_material = material.model_copy(
                update={"metadata": {}, "excerpt": None, "body_text": None, "body_html": None}
            )
            original = load_editorial_native_identity_source_material_in_transaction(
                session,
                owner_id=owner,
                profile_id=profile.id,
                configuration_version=profile.configuration_version,
                job_id=accepted.id,
                material=target_material,
                proof=material.native_identity,
                now=NOW,
            )
            assert original == material
            assert (
                session.scalar(
                    text("SELECT status FROM editorial_source_runs WHERE id=:id"),
                    {"id": run.run_id},
                )
                == "staged"
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_observations WHERE owner_id=:owner"),
                    {"owner": owner},
                )
                == 0
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM jobs WHERE owner_id=:owner"), {"owner": owner}
                )
                == 1
            )


@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "version",
        "material",
        "proof",
        "run_not_staged",
        "job_operation",
        "cancel",
        "approval",
    ],
)
def test_self_reported_proof_and_changed_current_authority_fail_closed(engine, change):
    with Session(engine) as session:
        _, owner, profile, accepted, run, material, _, _ = prepared_source(session)
        with session.begin():
            arguments = {}
            if change == "owner":
                arguments["owner_id"] = uuid4()
            elif change == "version":
                arguments["configuration_version"] = profile.configuration_version + 1
            elif change == "material":
                material = material.model_copy(update={"title": "Unstaged replacement"})
            elif change == "proof":
                arguments["proof"] = material.native_identity.model_copy(
                    update={"configuration_sha256": "f" * 64}
                )
            elif change == "run_not_staged":
                session.execute(
                    text("UPDATE editorial_source_runs SET status='running' WHERE id=:id"),
                    {"id": run.run_id},
                )
            elif change == "job_operation":
                session.execute(
                    text("UPDATE jobs SET operation_id=:operation WHERE id=:id"),
                    {"id": accepted.id, "operation": uuid4()},
                )
            elif change == "cancel":
                session.execute(
                    text("UPDATE jobs SET cancel_requested_at=:now WHERE id=:id"),
                    {"id": accepted.id, "now": NOW},
                )
            elif change == "approval":
                session.execute(
                    text(
                        "UPDATE resource_component_policies SET enabled_for_core=false "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            session.expire_all()
            with pytest.raises(ApplicationError):
                authority(session, owner, profile, accepted, material, **arguments)
            assert session.in_transaction()
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_observations WHERE owner_id=:owner"),
                    {"owner": owner},
                )
                == 0
            )


def test_stale_original_lease_cannot_apply_staged_native_candidates(engine):
    with Session(engine) as session:
        service, owner, _, accepted, run, _, old_lease, old_guard = prepared_source(session)
        new_lease = JobExecutionService(
            session, lease_seconds=30, clock=lambda: NOW + timedelta(seconds=31)
        ).acquire(job_id=accepted.id, worker_id="native-authority-new-epoch")
        assert new_lease.epoch > old_lease.epoch
        with pytest.raises(StaleExecutionLeaseError):
            service.apply_page(owner_id=owner, run_id=run.run_id, guard=old_guard)
        session.rollback()
        with session.begin():
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_observations WHERE owner_id=:owner"),
                    {"owner": owner},
                )
                == 0
            )


def test_other_original_job_kind_never_forwards_parser_proof_to_content_writer(engine):
    class CapturedCommandError(Exception):
        pass

    with Session(engine) as session:
        service, owner, _, accepted, run, _, _, guard = prepared_source(session)
        with session.begin():
            session.execute(
                text("UPDATE jobs SET kind='source.editorial.x_group' WHERE id=:id"),
                {"id": accepted.id},
            )

        def sink(_session, _owner, command):
            assert command.identity_proof is None
            assert command.material.native_identity is not None
            raise CapturedCommandError

        with pytest.raises(CapturedCommandError):
            service.apply_page(owner_id=owner, run_id=run.run_id, guard=guard, sink=sink)
        session.rollback()


@pytest.mark.parametrize("receipt_moved", [False, True])
def test_exact_withdrawal_clears_original_body_checkpoint_and_preserves_independent_run(
    engine, receipt_moved
):
    with Session(engine, expire_on_commit=False) as session:
        service_a, owner, profile_a = configured(session)
        service_b, _, profile_b = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        result_a, frozen_a = collect(session, service_a, owner, profile_a)
        result_b, frozen_b = collect(session, service_b, owner, profile_b)
        assert frozen_a[:2] == frozen_b[:2] and frozen_a[2] != frozen_b[2]
        if receipt_moved:
            _, replacement = collect(
                session, service_a, owner, profile_a, body="Later independently observed edit"
            )
        else:
            replacement = None
        material = parse_feed(
            feed(description="<p><strong>@sample</strong>:</p><p>Observed original text</p>"),
            profile_a.configuration.feed_url,
            profile_a.configuration,
        )[0]
        with session.begin():
            run_a = session.get(EditorialSourceRun, result_a.run_id)
            run_b = session.get(EditorialSourceRun, result_b.run_id)
            run_b_before = (
                run_b.status,
                run_b.prepared_page,
                run_b.failure_code,
                run_b.found,
                run_b.created,
                run_b.revised,
            )
            a_counts = (run_a.found, run_a.created, run_a.revised)
            target = EditorialBodyTarget(
                owner_id=owner,
                run_id=run_a.id,
                profile_id=profile_a.id,
                configuration_version=profile_a.configuration_version,
                profile_revision=profile_a.revision,
                job_id=run_a.job_id,
                operation_id=run_a.operation_id,
                content_id=frozen_a[0],
                expected_content_version_id=frozen_a[1],
                feed_observation_id=frozen_a[2],
                material=material,
            )
            run_a.status = "staged"
            run_a.prepared_page = {
                **EditorialPage(
                    status="complete", materials=(material,), observed_at=NOW
                ).model_dump(mode="json"),
                "_body_phase": EditorialBodyCheckpoint(targets=(target,)).model_dump(mode="json"),
            }
            session.flush()
            jobs_before = (
                session.execute(
                    text("SELECT to_jsonb(j) FROM jobs j WHERE owner_id=:owner ORDER BY id"),
                    {"owner": owner},
                )
                .scalars()
                .all()
            )
            attempts_before = session.scalar(
                text(
                    "SELECT count(*) FROM job_attempts a JOIN jobs j ON j.id=a.job_id "
                    "WHERE j.owner_id=:owner"
                ),
                {"owner": owner},
            )
            profiles_before = session.execute(
                text(
                    "SELECT id,cursor FROM editorial_source_profiles "
                    "WHERE owner_id=:owner ORDER BY id"
                ),
                {"owner": owner},
            ).all()
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=frozen_a[2], now=NOW
            )
            session.flush()
            assert run_a.prepared_page is None
            assert (run_a.status, run_a.failure_code) == (
                "failed",
                "editorial_material_unavailable",
            )
            assert (run_a.found, run_a.created, run_a.revised) == a_counts
            assert (
                run_b.status,
                run_b.prepared_page,
                run_b.failure_code,
                run_b.found,
                run_b.created,
                run_b.revised,
            ) == run_b_before
            assert session.get(ContentObservation, frozen_a[2]) is None
            assert session.get(ContentObservation, frozen_b[2]) is not None
            assert session.get(ContentVersion, frozen_b[1]) is not None
            receipt_b = session.get(
                EditorialSourceMaterialReceipt, (owner, profile_b.id, material.identity_key)
            )
            assert receipt_b.observation_id == frozen_b[2]
            receipt_a = session.get(
                EditorialSourceMaterialReceipt, (owner, profile_a.id, material.identity_key)
            )
            if replacement is None:
                assert receipt_a is None
            else:
                assert receipt_a.observation_id == replacement[2]
                assert session.get(ContentObservation, replacement[2]) is not None
            assert (
                session.execute(
                    text("SELECT to_jsonb(j) FROM jobs j WHERE owner_id=:owner ORDER BY id"),
                    {"owner": owner},
                )
                .scalars()
                .all()
                == jobs_before
            )
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM job_attempts a JOIN jobs j ON j.id=a.job_id "
                        "WHERE j.owner_id=:owner"
                    ),
                    {"owner": owner},
                )
                == attempts_before
            )
            assert (
                session.execute(
                    text(
                        "SELECT id,cursor FROM editorial_source_profiles "
                        "WHERE owner_id=:owner ORDER BY id"
                    ),
                    {"owner": owner},
                ).all()
                == profiles_before
            )
        assert service_a.body_checkpoint(owner_id=owner, run_id=result_a.run_id) is None
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service_a.begin_body_request(owner_id=owner, run_id=result_a.run_id)
