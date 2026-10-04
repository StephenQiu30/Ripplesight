"""Real PostgreSQL concurrent source admission and immutable actual-input boundaries."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_content_native_identity import collect, configured
from tests.integration.test_editorial_body import approval as body_approval
from tests.integration.test_editorial_body import response
from tests.integration.test_editorial_rsshub import approval, enable
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from connections.editorial_schemas import EditorialProfileInput
from connections.editorial_services import EditorialSourceService
from content.export_reading import (
    FrozenContentExportInput,
    freeze_export_content_in_transaction,
    restore_export_content_in_transaction,
)
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentNativeIdentity, ContentObservation, ContentRecord, ContentVersion
from content.observation_inputs import freeze_observation_inputs_in_transaction
from core.errors import ApplicationError
from sources.editorial_body_review import EditorialBodyReview
from sources.editorial_schemas import EditorialBodyConfiguration


def test_concurrent_initial_aliases_share_identity_version_then_replay_keeps_observations(engine):
    with Session(engine, expire_on_commit=False) as session:
        _, owner, pa = configured(session)
        _, _, pb = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
    barrier = Barrier(2)

    def worker(profile):
        with Session(engine, expire_on_commit=False) as session:
            service = EditorialSourceService(session, clock=lambda: NOW)
            return collect(session, service, owner, profile, barrier=barrier)[1]

    with ThreadPoolExecutor(max_workers=2) as executor:
        a, b = tuple(executor.map(worker, (pa, pb)))
    assert a[:2] == b[:2] and a[2] != b[2]
    with Session(engine, expire_on_commit=False) as session:
        service = EditorialSourceService(session, clock=lambda: NOW)
        _, replay = collect(session, service, owner, pa)
        assert replay == a
        with session.begin():
            assert len(session.scalars(select(ContentRecord)).all()) == 1
            assert len(session.scalars(select(ContentVersion)).all()) == 1
            assert len(session.scalars(select(ContentNativeIdentity)).all()) == 1
            assert len(session.scalars(select(ContentObservation)).all()) == 2


def test_owner_and_weak_existing_identity_do_not_merge_by_url(engine):
    with Session(engine, expire_on_commit=False) as session:
        a, owner, pa = configured(session)
        b, other, pb = configured(session)
        _, fa = collect(session, a, owner, pa)
        _, fb = collect(session, b, other, pb)
        assert fa[0] != fb[0]
        c, _, pc = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, weak = collect(session, c, owner, pc, weak=True)
        assert weak[0] != fa[0]
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            collect(session, c, owner, pc)
        session.rollback()
        with session.begin():
            assert len(session.scalars(select(ContentRecord)).all()) == 3
            assert len(session.scalars(select(ContentNativeIdentity)).all()) == 2


def test_frozen_export_a_is_not_rescued_by_b_same_version_and_b_keeps_own_permission(engine):
    with Session(engine, expire_on_commit=False) as session:
        a, owner, pa = configured(session)
        b, _, pb = configured(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, fa = collect(session, a, owner, pa)
        _, fb = collect(session, b, owner, pb)
        purpose = "hotkey:personal-file-export:v1"
        with session.begin():
            session.execute(
                text(
                    "UPDATE source_access_policies SET processing_purpose=:purpose, "
                    "field_purposes=field_purposes || CAST(:fields AS jsonb) WHERE owner_id=:owner"
                ),
                {
                    "purpose": purpose,
                    "owner": owner,
                    "fields": json.dumps(
                        {
                            key: purpose
                            for key in (
                                "object_type",
                                "text_scope",
                                "title",
                                "body",
                                "author_name",
                                "published_at",
                                "canonical_url",
                                "final_url",
                            )
                        }
                    ),
                },
            )
            item = freeze_export_content_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(fa[1],),
                observation_ids=(fa[2],),
                now=NOW,
            )[0]
            frozen = FrozenContentExportInput(
                version_id=item.version_id,
                observation_id=item.observation_id,
                input_observation_ids=item.input_observation_ids,
                discovered_at=item.discovered_at,
            )
            assert item.source_key == pa.source_key and item.input_observation_ids == (fa[2],)
            session.execute(
                text(
                    "UPDATE source_access_policies SET enabled=false "
                    "WHERE owner_id=:owner AND source_key=:key"
                ),
                {"owner": owner, "key": pa.source_key},
            )
        with (
            session.begin(),
            pytest.raises(ApplicationError, match="editorial_material_unavailable"),
        ):
            restore_export_content_in_transaction(
                session, owner_id=owner, frozen_inputs=(frozen,), now=NOW
            )
        with session.begin():
            independent = freeze_export_content_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(fb[1],),
                now=NOW,
            )[0]
            assert independent.source_key == pb.source_key
            assert independent.input_observation_ids == (fb[2],)
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert session.get(ContentVersion, fb[1]) is not None


def body_profile(session, *, owner_id=None, route="/threads/sample", mode="author_stream"):
    service, owner, profile = configured(session, owner_id=owner_id, route=route, mode=mode)
    review = EditorialBodyReview(
        read_reference="controlled-read",
        save_reference="controlled-save",
        fee_reference="controlled-zero",
        egress_reference="controlled-egress",
        request_bound_reference="controlled-request-bound",
        deployment_reference="controlled-local-runtime",
        reviewed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    configuration = profile.configuration.model_copy(
        update={
            "body_extraction": EditorialBodyConfiguration(
                enabled=True,
                allowed_hosts=("www.threads.com",),
                review=review,
                max_fetches=1,
            )
        }
    )
    command = EditorialProfileInput(
        operation_id=uuid4(),
        name=profile.name,
        reason="Controlled same original body inputs",
        expected_revision=profile.revision,
        policy_version=1,
        enabled=False,
        interval_minutes=60,
        configuration=configuration,
    )
    profile = service.save_profile(owner_id=owner, profile_id=profile.id, command=command)
    service.approve_rsshub(owner_id=owner, profile_id=profile.id, command=approval(profile))
    profile = enable(service, owner, profile, command)
    service.approve_body(owner_id=owner, profile_id=profile.id, command=body_approval(profile))
    with session.begin():
        session.execute(
            text(
                "UPDATE source_access_policies SET field_purposes=field_purposes "
                "|| CAST(:fields AS jsonb) "
                "WHERE owner_id=:owner AND source_key=:key"
            ),
            {
                "owner": owner,
                "key": profile.source_key,
                "fields": (
                    '{"text_origin_ref":"controlled origin","truncation_reason":"controlled limit"}'
                ),
            },
        )
    return service, owner, service.get_profile(owner_id=owner, profile_id=profile.id)


def test_two_alias_body_outputs_share_representation_but_keep_separate_actual_feed_inputs(engine):
    with Session(engine, expire_on_commit=False) as session:
        a, owner, pa = body_profile(session)
        b, _, pb = body_profile(
            session,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, fa = collect(session, a, owner, pa)
        _, fb = collect(session, b, owner, pb)
        outputs = []
        for service, profile in ((a, pa), (b, pb)):
            with session.begin():
                from connections.editorial_models import EditorialSourceRun

                run = session.scalar(
                    select(EditorialSourceRun).where(
                        EditorialSourceRun.owner_id == owner,
                        EditorialSourceRun.profile_id == profile.id,
                    )
                )
                run_id = run.id
            target = service.begin_body_request(owner_id=owner, run_id=run_id)
            service.apply_body_response(owner_id=owner, run_id=run_id, response=response(target))
            service.finish_body_phase(owner_id=owner, run_id=run_id)
            with session.begin():
                output = session.scalar(
                    select(ContentObservation).where(
                        ContentObservation.owner_id == owner,
                        ContentObservation.editorial_profile_id == profile.id,
                        ContentObservation.input_basis == "observations_v1",
                    )
                )
                outputs.append((output.id, output.content_version_id))
        assert outputs[0][1] == outputs[1][1] and outputs[0][0] != outputs[1][0]
        with session.begin():
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(outputs[0][0],), now=NOW
            ) == tuple(sorted((fa[2], outputs[0][0]), key=str))
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(outputs[1][0],), now=NOW
            ) == tuple(sorted((fb[2], outputs[1][0]), key=str))
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert session.get(ContentObservation, outputs[0][0]) is None
            assert session.get(ContentObservation, outputs[1][0]) is not None
            assert session.get(ContentVersion, outputs[1][1]) is not None
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(outputs[1][0],), now=NOW
            ) == tuple(sorted((fb[2], outputs[1][0]), key=str))


def test_legacy_leaf_without_original_evidence_is_unreadable_even_with_text_version(engine):
    from content.report_reading import report_inputs_readable_in_transaction
    from content.version_inputs import legacy_content_versions_readable_in_transaction

    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile = configured(session)
        _, frozen = collect(session, service, owner, profile)
        with session.begin():
            source = session.get(ContentVersion, frozen[1])
            values = {
                column.name: getattr(source, column.name)
                for column in ContentVersion.__table__.columns
            }
            identifier = uuid4()
            values.update(id=identifier, fingerprint=identifier.bytes * 2)
            session.add(ContentVersion(**values))
            session.flush()
            assert not legacy_content_versions_readable_in_transaction(
                session, owner_id=owner, content_version_ids=(identifier,), now=NOW
            )
            assert not report_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                content_version_ids=(identifier,),
                observation_ids=(),
                now=NOW,
            )
