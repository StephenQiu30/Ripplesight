"""Real isolated PostgreSQL: fixed approved source Jobs and independent alias inputs."""

from datetime import datetime, timedelta
from email.utils import format_datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_editorial_rsshub import approval, enable
from tests.integration.test_editorial_source_profiles import begin, job, setup
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW, config, feed

from connections.editorial_models import EditorialSourceMaterialReceipt
from connections.editorial_services import EditorialSourceService
from content.event_reading import load_event_member_content_in_transaction
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import (
    ContentNativeIdentity,
    ContentObservation,
    ContentRecord,
    ContentVersion,
)
from content.observation_inputs import freeze_observation_inputs_in_transaction
from content.schemas import EventContentReadReference
from content.services import ContentService
from core.errors import ApplicationError
from sources.adapters.editorial_rss import parse_feed
from sources.editorial_schemas import EditorialCursor, EditorialPage


def configured(
    session, *, owner_id=None, route="/threads/sample", mode="author_stream", grant=True
):
    _, owner, p, cmd = setup(session, owner_id=owner_id)
    service = EditorialSourceService(session, clock=lambda: NOW)
    configuration = config(route=route, query_mode=mode)
    cmd = cmd.model_copy(
        update={
            "operation_id": uuid4(),
            "expected_revision": p.revision,
            "enabled": False,
            "interval_minutes": 60,
            "configuration": configuration,
        }
    )
    p = service.save_profile(owner_id=owner, profile_id=p.id, command=cmd)
    service.approve_rsshub(owner_id=owner, profile_id=p.id, command=approval(p))
    p = enable(service, owner, p, cmd)
    if grant:
        with session.begin():
            session.execute(
                text(
                    "UPDATE source_access_policies SET field_purposes=field_purposes || "
                    "CAST(:native AS jsonb) WHERE owner_id=:owner AND source_key=:key"
                ),
                {
                    "owner": owner,
                    "key": p.source_key,
                    "native": '{"native_identity":"hotkey:native-object-dedup:v1"}',
                },
            )
    return service, owner, p


def collect(
    session,
    service,
    owner,
    p,
    *,
    body="Observed original text",
    url="https://www.threads.com/t/AbC_012-",
    weak=False,
    barrier=None,
    published_at: datetime | None = None,
):
    accepted, op = job(session, owner, p)
    # Real original Job row authority. No worker/source requests in this controlled test.
    with session.begin():
        session.execute(
            text("UPDATE jobs SET status='running',started_at=:now WHERE id=:id"),
            {"id": accepted.id, "now": NOW},
        )
    prepared = begin(service, owner, p, accepted, op)
    description = f"<p><strong>@sample</strong>:</p><p>{body}</p>"
    material = parse_feed(
        feed(
            url=url,
            description=description,
            extra_item=f"<pubDate>{format_datetime(published_at)}</pubDate>"
            if published_at
            else "",
        ),
        p.configuration.feed_url,
        p.configuration,
    )[0]
    if weak:
        material = material.model_copy(update={"native_identity": None})
    page = EditorialPage(
        status="complete",
        materials=(material,),
        cursor=EditorialCursor(initialized_at=NOW, last_ok_at=NOW),
        observed_at=NOW,
    )
    service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page)
    if barrier is not None:
        barrier.wait(timeout=10)
    result = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
    with session.begin():
        receipt = session.get(EditorialSourceMaterialReceipt, (owner, p.id, material.identity_key))
        observation = session.get(ContentObservation, receipt.observation_id)
        frozen = (observation.content_id, observation.content_version_id, observation.id)
    return result, frozen


def test_two_approved_routes_share_identity_version_but_not_observation_or_permissions(engine):
    with Session(engine, expire_on_commit=False) as s:
        a, owner, pa = configured(s)
        b, _, pb = configured(
            s,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, fa = collect(s, a, owner, pa)
        _, fb = collect(s, b, owner, pb)
        assert fa[:2] == fb[:2] and fa[2] != fb[2]
        with s.begin():
            assert len(s.scalars(select(ContentRecord)).all()) == 1
            assert len(s.scalars(select(ContentVersion)).all()) == 1
            assert len(s.scalars(select(ContentNativeIdentity)).all()) == 1
            oa, ob = (s.get(ContentObservation, x[2]) for x in (fa, fb))
            assert oa.source_key == pa.source_key and ob.source_key == pb.source_key
            assert oa.input_basis == ob.input_basis == "source_v1"
            assert freeze_observation_inputs_in_transaction(
                s, owner_id=owner, observation_ids=(oa.id,), now=NOW
            ) == (oa.id,)
            s.execute(
                text(
                    "UPDATE source_access_policies SET enabled=false "
                    "WHERE owner_id=:owner AND source_key=:key"
                ),
                {"owner": owner, "key": pa.source_key},
            )
        with s.begin():
            ra = EventContentReadReference(fa[0], fa[1], observation_id=fa[2])
            rb = EventContentReadReference(fb[0], fb[1], observation_id=fb[2])
            readings = load_event_member_content_in_transaction(
                s, owner_id=owner, references=(ra, rb), now=NOW
            )
            assert ra not in readings and readings[rb].source_key == pb.source_key
        detail = ContentService(s, clock=lambda: NOW).get_content(owner_id=owner, content_id=fb[0])
        assert detail.source_key == pb.source_key
        assert detail.native_scope == f"editorial-profile:{pb.id}"
        assert [x.observation_id for x in detail.readable_sources] == [fb[2]]
        with s.begin():
            purge_observation_dependants_in_transaction(
                s, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert s.get(ContentObservation, fa[2]) is None
            assert s.get(ContentObservation, fb[2]) is not None
            assert s.get(ContentVersion, fb[1]) is not None
            assert (
                s.get(
                    EditorialSourceMaterialReceipt,
                    (owner, pb.id, "url:https://www.threads.com/t/AbC_012-"),
                )
                is not None
            )
        assert (
            ContentService(s, clock=lambda: NOW)
            .get_content(owner_id=owner, content_id=fb[0])
            .latest_observation.id
            == fb[2]
        )


@pytest.mark.parametrize("grant,weak", [(False, False), (True, True)])
def test_missing_exact_native_purpose_or_proof_keeps_profile_identity(engine, grant, weak):
    with Session(engine, expire_on_commit=False) as s:
        a, owner, pa = configured(s, grant=grant)
        b, _, pb = configured(
            s,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
            grant=grant,
        )
        _, fa = collect(s, a, owner, pa, weak=weak)
        _, fb = collect(s, b, owner, pb, weak=weak)
        assert fa[0] != fb[0]
        with s.begin():
            assert not s.scalars(select(ContentNativeIdentity)).all()


def test_real_revision_keeps_identity_and_original_input_not_replaced(engine):
    with Session(engine, expire_on_commit=False) as s:
        service, owner, p = configured(s)
        _, first = collect(s, service, owner, p)
        _, second = collect(s, service, owner, p, body="Actual edited source text")
        assert first[0] == second[0] and first[1] != second[1]
        with s.begin():
            ref = EventContentReadReference(first[0], first[1], observation_id=first[2])
            assert (
                load_event_member_content_in_transaction(
                    s, owner_id=owner, references=(ref,), now=NOW
                )[ref].observation.id
                == first[2]
            )
            s.execute(
                text(
                    "UPDATE evidence_resources SET expires_at=:now "
                    "WHERE owner_id=:owner AND resource_id=:id"
                ),
                {"now": NOW, "owner": owner, "id": first[2]},
            )
        with s.begin(), pytest.raises(ApplicationError, match="editorial_material_unavailable"):
            freeze_observation_inputs_in_transaction(
                s, owner_id=owner, observation_ids=(first[2],), now=NOW + timedelta(seconds=1)
            )
