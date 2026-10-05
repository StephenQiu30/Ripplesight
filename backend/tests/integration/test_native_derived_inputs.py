"""Approved source Jobs and fixed observations in real PostgreSQL; no source/model HTTP."""

import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_content_native_identity import collect, configured
from tests.integration.test_editorial_execution import ControlledClient
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from ai.services import AiService
from analysis.editorial_schemas import EditorialRunInput, EditorialSourceInput
from analysis.editorial_services import EditorialExecutor, EditorialService
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentObservation, ContentVersion
from core.config import Settings
from core.errors import ApplicationError
from events.clustering import candidate_fingerprint
from events.consolidation import _automatic_merge, load_story_roots_in_transaction
from events.fact_models import EventFact, EventFactAssignment
from events.facts import (
    ensure_legacy_facts_in_transaction,
    load_publication_groupings_in_transaction,
)
from events.heat_models import EventAttentionSource
from events.models import Event, EventMember
from events.observation_inputs import (
    event_member_input_manifest,
    freeze_event_inputs_in_transaction,
    load_fact_observation_inputs_in_transaction,
    load_frozen_event_inputs_in_transaction,
)
from events.reads import EventReadService
from events.schemas import EventInput
from events.signals import _fact_reports
from jobs.execution import JobExecutionService
from jobs.schemas import JobAcceptanceInput, JobAcceptedMessage, JobObservationContext
from jobs.services import JobService
from monitors.editorial_events import ensure_editorial_event_topic_in_transaction
from publication.media_mirror_models import PublicationMediaRun
from publication.media_mirror_services import require_media_run_source_in_transaction
from publication.publication_models import PublicationRecord, PublicationRevision
from publication.reading import PublicationReadingService
from publication.schemas import FrozenPublicationReference, SourcePolicyInput
from publication.services import PublicationService
from publication.stories import public_stories_in_transaction


def source_input(s, owner, topic, profile, frozen, *, inputs=()):
    version = s.get(ContentVersion, frozen[1])
    return EventInput(
        owner_id=owner,
        topic_id=topic,
        content_id=frozen[0],
        content_version_id=frozen[1],
        source_key=profile.source_key,
        title=version.title or "",
        body=version.body,
        first_seen_at=NOW,
        first_seen_basis="discovered",
        matched_keywords=frozenset({"editorial-input"}),
        observation_id=frozen[2],
        input_observation_ids=inputs,
    )


def event(s, owner, topic, item):
    row = Event(
        id=uuid4(),
        owner_id=owner,
        topic_id=topic,
        revision=1,
        title="Fixed event",
        summary="Narrative from selected fixed input",
        first_seen_at=NOW,
        first_seen_basis="discovered",
        status="active",
        merged_into_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    s.add(row)
    s.flush()
    member = EventMember(
        id=uuid4(),
        owner_id=owner,
        topic_id=topic,
        event_id=row.id,
        content_id=item.content_id,
        content_version_id=item.content_version_id,
        source_key=item.source_key,
        observation_id=item.observation_id,
        observation_source_key=item.observation_source_key,
        input_manifest=event_member_input_manifest(item),
        representative_comment_id=None,
        representative_comment_observation_id=None,
        added_revision=1,
        removed_revision=None,
        assignment_origin="model",
        created_at=NOW,
    )
    s.add(member)
    s.flush()
    return row.id, member.id


def source_policy(s, owner, p):
    PublicationService(s).save_source_policy_in_transaction(
        owner_id=owner,
        actor_id=owner,
        source_key=p.source_key,
        command=SourcePolicyInput(
            operation_id=uuid4(),
            expected_revision=0,
            participation_mode="editorial",
            license_name="Controlled public metadata",
            reason="Selected source permission",
            release_delay_seconds=0,
        ),
        now=NOW,
    )


def revoke(s, owner, p):
    s.execute(
        text(
            "UPDATE source_access_policies SET enabled=false "
            "WHERE owner_id=:owner AND source_key=:key"
        ),
        {"owner": owner, "key": p.source_key},
    )


def aliases(s):
    a, owner, pa = configured(s)
    b, _, pb = configured(
        s, owner_id=owner, route="/threads/search/sample/serpType=recent", mode="platform_keyword"
    )
    _, fa = collect(s, a, owner, pa)
    _, fb = collect(s, b, owner, pb)
    assert fa[:2] == fb[:2]
    return owner, pa, pb, fa, fb


def attention_source(s, owner, p):
    s.add(
        EventAttentionSource(
            id=uuid4(),
            owner_id=owner,
            source_key=p.source_key,
            selector_kind="source",
            selector_ref=p.source_key,
            name=p.name,
            revision=1,
            mode="editorial",
            group_key=None,
            owner_entity_key=None,
            first_party=False,
            tier="T1",
            scheduled=False,
            enabled=True,
            interval_seconds=300,
            last_successful_fetch_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def complete_editorial(engine, s, owner, p, frozen):
    """Run the actual editorial Job with a local controlled model; no model HTTP."""
    with s.begin():
        current = EditorialService(s, clock=lambda: NOW).get_source_in_transaction(
            owner_id=owner, source_key=p.source_key
        )
    EditorialService(s, clock=lambda: NOW).save_source(
        owner_id=owner,
        source_key=p.source_key,
        command=EditorialSourceInput(
            operation_id=uuid4(),
            expected_revision=current.revision if current is not None else 0,
            tier="T1",
            source_kind="rss",
            name=p.name,
            enabled=True,
        ),
    )
    _enable_ai_budget(engine, owner)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE resource_budget_policies SET window_anchor_at=:now, "
                "limit_units=50 WHERE owner_id=:owner"
            ),
            {"now": NOW, "owner": owner},
        )
    run = EditorialService(s, clock=lambda: NOW).request_run(
        owner_id=owner,
        content_id=frozen[0],
        source_key=p.source_key,
        command=EditorialRunInput(operation_id=uuid4(), content_version_id=frozen[1]),
    )
    with s.begin():
        outbox = s.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
    lease = JobExecutionService(s, lease_seconds=30, clock=lambda: NOW).acquire(
        job_id=run.job_id, worker_id="native-publication-contract"
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(environment="test", database_url=os.environ["HOTKEY_TEST_DATABASE_URL"])
    with sessions() as ai_session:
        completion = EditorialExecutor(sessions, settings, clock=lambda: NOW).execute(
            message, lease, ai=AiService(ai_session, ControlledClient(), clock=lambda: NOW)
        )
    assert completion.status.value == "succeeded"


def test_historical_private_narrative_requires_removed_a_public_permission(engine):
    with Session(engine, expire_on_commit=False) as s:
        a, owner, pa = configured(s)
        b, _, pb = configured(
            s,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        # This scenario later selects B publicly and publishes the whole story.
        # Both fixed members need source RSS dates so permission is the only blocker.
        _, fa = collect(s, a, owner, pa, published_at=NOW)
        _, fb = collect(
            s,
            b,
            owner,
            pb,
            url="https://www.threads.com/t/CbC_012-",
            body="OpenAI independent B model release",
            published_at=NOW,
        )
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            fixed, _ = freeze_event_inputs_in_transaction(
                s,
                owner_id=owner,
                inputs=(
                    source_input(s, owner, topic, pa, fa),
                    source_input(s, owner, topic, pb, fb),
                ),
                now=NOW,
            )
            ea, ma = event(s, owner, topic, fixed[0])
            _, mb = event(s, owner, topic, fixed[1])
            s.get(EventMember, ma).removed_revision = 2
            s.get(EventMember, mb).event_id = ea
            row = s.get(Event, ea)
            row.revision = 2
            row.title = "Historical A framing remains in compatibility narrative"
            row.summary = "This old narrative used A before A was moved away."
            s.flush()
            ensure_legacy_facts_in_transaction(s, event=row, now=NOW)
            source_policy(s, owner, pb)
            PublicationService(s).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key=pa.source_key,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=0,
                    participation_mode="isolated",
                    reason="Private A framing",
                    license_name="Private metadata",
                    release_delay_seconds=0,
                ),
                now=NOW,
            )
        # This is the supported historical no-Derived branch, not a fresh correction;
        # real corrections create stale Derived and already block this old narrative.
        complete_editorial(engine, s, owner, pb, fb)
        assert (
            EventReadService(s, clock=lambda: NOW)
            .get_event(owner_id=owner, event_id=ea)
            .derived_text_available
        )
        with s.begin():
            reader = PublicationReadingService(s)
            own = reader.projection_in_transaction(owner_id=owner, content_id=fb[0], now=NOW)
            assert own and own.event_id == ea and own.selected and own.visibility == "public"
            assert not public_stories_in_transaction(
                reader, owner_id=owner, event_ids=(ea,), now=NOW
            )
            # Public uses of B's original item still pass independently of A's narrative.
            assert reader.detail_in_transaction(owner_id=owner, content_id=fb[0], now=NOW)
            PublicationService(s).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key=pa.source_key,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=1,
                    participation_mode="editorial",
                    reason="Public historical A use approved",
                    license_name="Controlled public metadata",
                    release_delay_seconds=0,
                ),
                now=NOW,
            )
            assert public_stories_in_transaction(reader, owner_id=owner, event_ids=(ea,), now=NOW)


def test_same_occurrence_fact_frame_requires_all_original_reports(engine):
    with Session(engine, expire_on_commit=False) as s:
        a, owner, pa = configured(s)
        b, _, pb = configured(
            s,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, fa = collect(s, a, owner, pa)
        _, fb = collect(
            s, b, owner, pb, url="https://www.threads.com/t/BbC_012-", body="Independent B report"
        )
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            frozen, _ = freeze_event_inputs_in_transaction(
                s,
                owner_id=owner,
                inputs=(
                    source_input(s, owner, topic, pa, fa),
                    source_input(s, owner, topic, pb, fb),
                ),
                now=NOW,
            )
            ea, _ = event(s, owner, topic, frozen[0])
            eb, _ = event(s, owner, topic, frozen[1])
            for identity, p in ((ea, pa), (eb, pb)):
                ensure_legacy_facts_in_transaction(s, event=s.get(Event, identity), now=NOW)
                attention_source(s, owner, p)
            fact_a = s.scalar(
                select(EventFactAssignment.fact_id).where(
                    EventFactAssignment.event_id == ea, EventFactAssignment.relation == "root"
                )
            )
            s.get(EventFact, fact_a).frame = {"subject": "Sensitive A framing"}
            s.flush()
            roots = load_story_roots_in_transaction(s, owner_id=owner, event_ids=(ea, eb), now=NOW)
            assert len(roots) == 2
            _automatic_merge(
                s,
                owner_id=owner,
                roots=(roots[ea], roots[eb]),
                operation_id=uuid4(),
                same_occurrence=True,
                now=NOW,
            )
            expected = {fa[2], fb[2]}
            assert (
                set(
                    load_fact_observation_inputs_in_transaction(
                        s, owner_id=owner, fact_ids=(fact_a,), now=NOW
                    )[fact_a]
                )
                == expected
            )
            merged = load_story_roots_in_transaction(s, owner_id=owner, event_ids=(ea,), now=NOW)
            assert merged and all(
                set(r.input_observation_ids) == expected for r in merged[ea].reports
            )
            signals = _fact_reports(s, owner_id=owner, now=NOW)
            assert signals and all(set(r.input_observation_ids) == expected for r in signals)
            revoke(s, owner, pa)
        with s.begin():
            assert not load_story_roots_in_transaction(s, owner_id=owner, event_ids=(ea,), now=NOW)
            assert not _fact_reports(s, owner_id=owner, now=NOW)
            assert not load_publication_groupings_in_transaction(
                s,
                owner_id=owner,
                content_versions={fb[0]: fb[1]},
                selected_observations={fb[0]: fb[2]},
                now=NOW,
            )
            # B keeps its own independent original text despite the unavailable A frame.
            from content.event_reading import load_event_member_content_in_transaction
            from content.schemas import EventContentReadReference

            ref = EventContentReadReference(fb[0], fb[1], observation_id=fb[2])
            assert (
                load_event_member_content_in_transaction(
                    s, owner_id=owner, references=(ref,), now=NOW
                )[ref].source_key
                == pb.source_key
            )


def test_public_b_alias_does_not_publish_private_a_event_frame(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, pa, pb, fa, fb = aliases(s)
        later = NOW + timedelta(seconds=1)
        with s.begin():
            # Raw discovery intentionally selects the latest permitted observation.
            # Give B an explicit later receipt; equal timestamps must not make the
            # fixture depend on random UUID ordering between private A and public B.
            s.get(ContentObservation, fb[2]).received_at = later
            s.flush()
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            frozen, _ = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pa, fa),), now=NOW
            )
            ea, _ = event(s, owner, topic, frozen[0])
            ensure_legacy_facts_in_transaction(s, event=s.get(Event, ea), now=NOW)
            source_policy(s, owner, pb)
            PublicationService(s).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key=pa.source_key,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=0,
                    participation_mode="isolated",
                    reason="Private A framing",
                    license_name="Private metadata",
                    release_delay_seconds=0,
                ),
                now=NOW,
            )
            assert load_publication_groupings_in_transaction(
                s,
                owner_id=owner,
                content_versions={fa[0]: fa[1]},
                selected_observations={fa[0]: fa[2]},
                now=NOW,
            )
            assert not load_publication_groupings_in_transaction(
                s,
                owner_id=owner,
                content_versions={fb[0]: fb[1]},
                selected_observations={fb[0]: fb[2]},
                now=NOW,
            )
            published = PublicationService(s).publish_in_transaction(
                owner_id=owner, content_id=fb[0], now=later
            )
            assert published is not None and published.visibility == "public"
            reader = PublicationReadingService(s)
            own = reader.projection_in_transaction(owner_id=owner, content_id=fb[0], now=later)
            assert own and own.observation_id == fb[2] and own.source_key == pb.source_key
            assert own.event_id is None
            assert reader.detail_in_transaction(owner_id=owner, content_id=fb[0], now=later)
            assert not public_stories_in_transaction(
                reader, owner_id=owner, event_ids=(ea,), now=later
            )


def test_candidate_pins_original_observation_and_cannot_follow_or_rescue_alias(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, pa, pb, fa, fb = aliases(s)
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            frozen, manifest = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pa, fa),), now=NOW
            )
            pinned = load_frozen_event_inputs_in_transaction(
                s, owner_id=owner, topic_id=topic, manifest=manifest, now=NOW
            )
            assert pinned[0].observation_id == fa[2] and pinned[0].source_key == pa.source_key
            assert pinned[0].input_observation_ids == frozen[0].input_observation_ids
            assert candidate_fingerprint(topic_id=topic, members=pinned) == candidate_fingerprint(
                topic_id=topic, members=frozen
            )
            revoke(s, owner, pa)
        with s.begin():
            assert not load_frozen_event_inputs_in_transaction(
                s, owner_id=owner, topic_id=topic, manifest=manifest, now=NOW
            )
            independent, _ = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pb, fb),), now=NOW
            )
            assert independent[0].input_observation_ids == (fb[2],)


def test_actual_b_source_fk_and_complete_member_batch_permissions(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, pa, pb, fa, fb = aliases(s)
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            raw, _ = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pb, fb),), now=NOW
            )
            independent_event, independent_member = event(s, owner, topic, raw[0])
            batched, _ = freeze_event_inputs_in_transaction(
                s,
                owner_id=owner,
                inputs=(replace(raw[0], input_observation_ids=(fa[2], fb[2])),),
                now=NOW,
            )
            batch_topic = uuid4()
            s.execute(
                text(
                    "INSERT INTO monitor_topics (id,owner_id,name,status,readiness_status,"
                    "current_version,created_at,updated_at) "
                    "VALUES (:id,:owner,'Other partition','paused','ready',1,:now,:now)"
                ),
                {"id": batch_topic, "owner": owner, "now": NOW},
            )
            batch_event, batch_member = event(
                s, owner, batch_topic, replace(batched[0], topic_id=batch_topic)
            )
            revoke(s, owner, pa)
        reader = EventReadService(s, clock=lambda: NOW)
        assert reader.get_event(owner_id=owner, event_id=independent_event).derived_text_available
        with pytest.raises(ApplicationError, match="resource_not_found"):
            reader.get_event(owner_id=owner, event_id=batch_event)
        with s.begin():
            purge_observation_dependants_in_transaction(
                s, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert s.get(EventMember, independent_member) is not None
            assert s.get(EventMember, batch_member) is None
            assert (
                s.get(ContentObservation, fb[2]) is not None
                and s.get(ContentVersion, fb[1]) is not None
            )


def test_modern_event_null_source_shadow_is_unreadable_even_with_matching_null_manifest(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, _, pb, _, fb = aliases(s)
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            frozen, _ = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pb, fb),), now=NOW
            )
            assert frozen[0].observation_source_key == pb.source_key
            event_id, member_id = event(s, owner, topic, frozen[0])
            member = s.get(EventMember, member_id)
            member.observation_source_key = None
            member.input_manifest = {**member.input_manifest, "observation_source_key": None}
        with pytest.raises(ApplicationError, match="resource_not_found"):
            EventReadService(s, clock=lambda: NOW).get_event(owner_id=owner, event_id=event_id)
        with s.begin():
            member = s.get(EventMember, member_id)
            member.observation_source_key = pb.source_key
            member.input_manifest = {
                **member.input_manifest,
                "observation_source_key": pb.source_key,
            }
        assert EventReadService(s, clock=lambda: NOW).get_event(owner_id=owner, event_id=event_id)


def test_legacy_raw_version_member_cleanup_does_not_remove_independent_modern_b(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, pa, pb, fa, fb = aliases(s)
        with s.begin():
            topic = ensure_editorial_event_topic_in_transaction(s, owner_id=owner, now=NOW)
            b, _ = freeze_event_inputs_in_transaction(
                s, owner_id=owner, inputs=(source_input(s, owner, topic, pb, fb),), now=NOW
            )
            independent_event, independent_member = event(s, owner, topic, b[0])
            legacy_topic = uuid4()
            s.execute(
                text(
                    "INSERT INTO monitor_topics (id,owner_id,name,status,readiness_status,"
                    "current_version,created_at,updated_at) "
                    "VALUES (:id,:owner,'Legacy partition','paused','ready',1,:now,:now)"
                ),
                {"id": legacy_topic, "owner": owner, "now": NOW},
            )
            legacy_event, legacy_member = event(
                s,
                owner,
                legacy_topic,
                replace(source_input(s, owner, legacy_topic, pa, fa), observation_id=None),
            )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            EventReadService(s, clock=lambda: NOW).get_event(owner_id=owner, event_id=legacy_event)
        with s.begin():
            purge_observation_dependants_in_transaction(
                s, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert s.get(EventMember, legacy_member) is None
            assert s.get(EventMember, independent_member) is not None
            assert s.get(ContentObservation, fb[2]) is not None
            assert s.get(ContentVersion, fb[1]) is not None
        assert EventReadService(s, clock=lambda: NOW).get_event(
            owner_id=owner, event_id=independent_event
        )


def test_publication_explicit_b_republish_and_a_cleanup_preserve_b_without_read_mutation(engine):
    with Session(engine, expire_on_commit=False) as s:
        a, owner, pa = configured(s)
        _, fa = collect(s, a, owner, pa)
        with s.begin():
            source_policy(s, owner, pa)
            PublicationService(s).publish_in_transaction(owner_id=owner, content_id=fa[0], now=NOW)
            a_projection = dict(s.get(PublicationRecord, (owner, fa[0])).data)
            assert a_projection["observation_id"] == str(fa[2])
        b, _, pb = configured(
            s,
            owner_id=owner,
            route="/threads/search/sample/serpType=recent",
            mode="platform_keyword",
        )
        _, fb = collect(s, b, owner, pb)
        with s.begin():
            source_policy(s, owner, pb)
            reader = PublicationReadingService(s)
            assert (
                reader.projection_in_transaction(
                    owner_id=owner, content_id=fa[0], now=NOW
                ).observation_id
                == fa[2]
            )
            revoke(s, owner, pa)
        with s.begin():
            reader = PublicationReadingService(s)
            assert reader.detail_in_transaction(owner_id=owner, content_id=fa[0], now=NOW) is None
            assert s.get(PublicationRecord, (owner, fa[0])).data == a_projection
            PublicationService(s).publish_in_transaction(owner_id=owner, content_id=fb[0], now=NOW)
            b_projection = s.get(PublicationRecord, (owner, fb[0])).data
            assert (
                b_projection["observation_id"] == str(fb[2])
                and b_projection["source_key"] == pb.source_key
            )
            assert b_projection["input_fingerprint"] != a_projection["input_fingerprint"]
        with s.begin():
            purge_observation_dependants_in_transaction(
                s, owner_id=owner, observation_id=fa[2], now=NOW
            )
            row = s.get(PublicationRecord, (owner, fb[0]))
            assert row.data["observation_id"] == str(fb[2]) and row.visibility == "public"
            revisions = s.scalars(select(PublicationRevision)).all()
            assert revisions and all(r.data["observation_id"] == str(fb[2]) for r in revisions)
            assert PublicationReadingService(s).detail_in_transaction(
                owner_id=owner, content_id=fb[0], now=NOW
            )


def test_same_version_media_run_fk_and_cleanup_are_independent_without_network_grant(engine):
    with Session(engine, expire_on_commit=False) as s:
        owner, pa, pb, fa, fb = aliases(s)
        runs = []
        with s.begin():
            for p, frozen in ((pa, fa), (pb, fb)):
                op, run_id = uuid4(), uuid4()
                accepted = JobService(s, clock=lambda: NOW).accept_in_transaction(
                    owner_id=owner,
                    command=JobAcceptanceInput(
                        operation_id=op,
                        kind="publication.media_mirror",
                        observation=JobObservationContext(
                            configuration_ref="publication-media-mirror", configuration_version=1
                        ),
                        scope={"media_run_id": str(run_id)},
                    ),
                )
                # FK/cleanup fixture only: a queued row cannot grant public bytes or HTTP.
                s.add(
                    PublicationMediaRun(
                        owner_id=owner,
                        id=run_id,
                        operation_id=op,
                        job_id=accepted.id,
                        content_id=frozen[0],
                        content_version_id=frozen[1],
                        observation_id=frozen[2],
                        observation_source_key=p.source_key,
                        source_key=p.source_key,
                        policy_revision=1,
                        fixed_reference=FrozenPublicationReference(
                            content_id=frozen[0],
                            content_version_id=frozen[1],
                            observation_id=frozen[2],
                            input_observation_ids=(frozen[2],),
                            editorial_run_id=None,
                            manual_version=0,
                            source_profile_revision=1,
                            policy_revision=1,
                            publication_revision=1,
                        ).model_dump(mode="json"),
                        input_fingerprint="f" * 64,
                        status="queued",
                        reason=None,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
                runs.append(run_id)
            s.flush()
            assert len(s.scalars(select(PublicationMediaRun)).all()) == 2
            for run in s.scalars(select(PublicationMediaRun)):
                require_media_run_source_in_transaction(s, run, now=NOW)
                shadow = run.observation_source_key
                run.observation_source_key = None
                s.flush()
                with pytest.raises(ApplicationError, match="publication_revision_conflict"):
                    require_media_run_source_in_transaction(s, run, now=NOW)
                run.observation_source_key = shadow
                s.flush()
            revoke(s, owner, pa)
        with s.begin():
            purge_observation_dependants_in_transaction(
                s, owner_id=owner, observation_id=fa[2], now=NOW
            )
            assert s.get(PublicationMediaRun, (owner, runs[0])) is None
            assert s.get(PublicationMediaRun, (owner, runs[1])) is not None
            assert s.get(ContentObservation, fb[2]) is not None
