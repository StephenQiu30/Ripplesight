from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_event_reading import (
    _fixed_member_fields,
    _seed_reading,
)
from tests.integration.test_event_reading import (
    event_read_client as event_read_client,
)
from tests.integration.test_event_reading_boundaries import _other_content

from ai.models import AiCall
from ai.schemas import AiCompletion, AiTokenUsage
from content.schemas import RecordContentVisibilityInput
from content.services import ContentService
from events.consolidation import EventConsolidationExecutor, EventConsolidationService
from events.fact_models import EventFactAssignment, EventGroupingOverride
from events.facts import ensure_legacy_facts_in_transaction
from events.heat import EventHeatService
from events.heat_schemas import AttentionSourceInput
from events.models import Event, EventMember
from events.reads import EventReadService
from events.story_models import EventStoryLink
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job


class ControlledStoryClient:
    provider = "fake"
    model = "controlled-story"

    def __init__(self, confidences=(0.8, 0.75), relation="SAME_STORY"):
        self.calls, self.confidences, self.relation = [], confidences, relation

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={
                "a": "A",
                "b": "B",
                "relation": self.relation,
                "confidence": self.confidences[len(self.calls) - 1],
                "difference": "直接联系",
            },
            usage=AiTokenUsage(input_tokens=20, output_tokens=10),
            duration_ms=1,
        )

    def close(self):
        pass


def _controlled_factory(monkeypatch, controlled):
    def create(settings, model):
        controlled.provider, controlled.model = model.provider, model.model
        controlled.frozen_model = model
        controlled.capability_settings = settings
        controlled.component_key = model.component_key
        return controlled

    monkeypatch.setattr("events.ai_execution.create_ai_client_for_frozen_model", create)


def _pair(client):
    owner, topic, first_id, fixed, _ = _seed_reading(client)
    other = _other_content(client, owner)
    factory = client.app.state.session_factory
    second_id, now = uuid4(), datetime.now(UTC)
    with factory() as session, session.begin():
        first = session.get(Event, first_id)
        first.title = "Acme model release event"
        first.updated_at = now
        session.add(
            Event(
                id=second_id,
                owner_id=owner,
                topic_id=topic,
                revision=1,
                title="Acme model release event",
                summary="第二份报道",
                first_seen_at=now,
                first_seen_basis="discovered",
                status="active",
                merged_into_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            EventMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=topic,
                event_id=second_id,
                content_id=other.id,
                content_version_id=other.latest_observation.content_version.id,
                **_fixed_member_fields(session, owner, other),
                source_key="x",
                representative_comment_id=None,
                added_revision=1,
                removed_revision=None,
                assignment_origin="model",
                created_at=now,
            )
        )
        session.flush()
        for identity, author in ((fixed.id, "alpha"), (other.id, "beta")):
            session.execute(
                text(
                    "UPDATE content_observations SET author_external_id=:author "
                    "WHERE content_id=:id"
                ),
                {"author": author, "id": identity},
            )
        for identity in (first_id, second_id):
            ensure_legacy_facts_in_transaction(session, event=session.get(Event, identity), now=now)
    with factory() as session:
        for author in ("alpha", "beta"):
            EventHeatService(session).upsert_source(
                owner_id=owner,
                command=AttentionSourceInput(
                    source_key="x",
                    selector_kind="author",
                    selector_ref=author,
                    name=author,
                    mode="editorial",
                    scheduled=False,
                ),
            )
    _enable_ai_budget(factory.kw["bind"], owner)
    settings = client.app.state.settings.model_copy(
        update={"events_cluster_enabled": True, "ai_enabled": True, "ai_model": "controlled-story"}
    )
    with factory() as session, session.begin():
        service = EventConsolidationService(session, settings)
        assert service.enqueue_due_in_transaction(now=now, ai_enabled=True) == 1
        assert service.enqueue_due_in_transaction(now=now, ai_enabled=True) == 0
        job = session.scalar(select(Job).where(Job.kind == "events.consolidate"))
        message = SimpleNamespace(
            kind=job.kind,
            job_id=job.id,
            owner_id=owner,
            operation_id=job.operation_id,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=300).acquire(
            job_id=message.job_id, worker_id="controlled-story"
        )
    return owner, factory, first_id, second_id, message, lease, settings


def test_two_round_consolidation_merges_into_earliest_and_preserves_model_history(
    event_read_client, monkeypatch
):
    owner, factory, first, second, message, lease, settings = _pair(event_read_client)
    controlled = ControlledStoryClient()
    _controlled_factory(monkeypatch, controlled)
    executor = EventConsolidationExecutor(factory, settings)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(controlled.calls) == 2
    assert '"A":{"first_party"' in controlled.calls[0]["prompt"]
    with factory() as session:
        assert session.get(Event, second).merged_into_id == first
        assert session.get(Event, first).revision == 2
        assert len(session.scalars(select(AiCall)).all()) == 2
        assert session.scalar(select(EventGroupingOverride)) is None
        current = session.scalars(
            select(EventMember).where(EventMember.removed_revision.is_(None))
        ).all()
        assert len(current) == 2 and all(row.assignment_origin == "model" for row in current)
        facts = session.scalars(
            select(EventFactAssignment).where(EventFactAssignment.removed_revision.is_(None))
        ).all()
        assert {row.relation for row in facts} == {"root", "development"}
        assert EventReadService(session).get_event(owner_id=owner, event_id=second).id == first


def test_same_occurrence_consolidates_fact_identity_in_the_same_transaction(
    event_read_client, monkeypatch
):
    _, factory, first, _, message, lease, settings = _pair(event_read_client)
    controlled = ControlledStoryClient(relation="SAME_OCCURRENCE")
    _controlled_factory(monkeypatch, controlled)
    EventConsolidationExecutor(factory, settings).execute(message, lease)
    with factory() as session:
        current = session.scalars(
            select(EventFactAssignment).where(EventFactAssignment.removed_revision.is_(None))
        ).all()
        assert len(current) == 1 and current[0].relation == "root"
        assert session.get(Event, first).revision == 3


def test_failed_second_review_keeps_stories_and_requires_two_independent_contact_reports(
    event_read_client, monkeypatch
):
    owner, factory, first, second, message, lease, settings = _pair(event_read_client)
    controlled = ControlledStoryClient((0.8, 0.74, 0.9, 0.9))
    _controlled_factory(monkeypatch, controlled)
    EventConsolidationExecutor(factory, settings).execute(message, lease)
    assert len(controlled.calls) == 4
    with factory() as session:
        assert session.get(Event, second).status == "active"
        link = session.scalar(select(EventStoryLink))
        assert len(link.evidence) == 2
        view = EventReadService(session).list_related(owner_id=owner, event_id=first)
        assert [row.event.id for row in view.items] == [second]
        assert view.items[0].supporting_report_count == 2
        reverse = EventReadService(session).list_related(owner_id=owner, event_id=second)
        assert [row.event.id for row in reverse.items] == [first]
    with factory() as session:
        job_id = session.scalar(select(Job.id).where(Job.source_key == "x").limit(1))
        ContentService(session).record_visibility(
            owner_id=owner,
            command=RecordContentVisibilityInput(
                content_id=link.evidence[0]["content_id"],
                job_id=job_id,
                source_operation_id=uuid4(),
                observed_at=datetime.now(UTC),
                status="deleted",
                basis="source_tombstone",
            ),
        )
    with factory() as session:
        assert EventReadService(session).list_related(owner_id=owner, event_id=first).items == []


def test_saved_story_judge_recovers_without_repeating_paid_round(event_read_client, monkeypatch):
    _, factory, _, _, message, lease, settings = _pair(event_read_client)
    controlled = ControlledStoryClient()
    _controlled_factory(monkeypatch, controlled)
    executor = EventConsolidationExecutor(factory, settings)
    save = executor._save_response

    def crash(*args, **kwargs):
        save(*args, **kwargs)
        raise SystemExit("saved judge")

    monkeypatch.setattr(executor, "_save_response", crash)
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    EventConsolidationExecutor(factory, settings).execute(message, lease)
    assert len(controlled.calls) == 2


def test_unsaved_story_response_is_unknown_and_is_never_rebought(event_read_client, monkeypatch):
    _, factory, _, _, message, lease, settings = _pair(event_read_client)
    controlled = ControlledStoryClient()
    _controlled_factory(monkeypatch, controlled)
    executor = EventConsolidationExecutor(factory, settings)
    monkeypatch.setattr(executor, "_save_response", lambda *_: (_ for _ in ()).throw(SystemExit()))
    with pytest.raises(SystemExit):
        executor.execute(message, lease)
    with pytest.raises(JobExecutionFailure, match="event_consolidation_result_unknown"):
        EventConsolidationExecutor(factory, settings).execute(message, lease)
    assert len(controlled.calls) == 1


def test_consolidation_scan_passes_admitted_first_page_without_starving_later_pairs(
    event_read_client,
):
    owner, topic, original_event, _, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    event_ids = [original_event]
    for _ in range(16):
        material = _other_content(event_read_client, owner)
        identity = uuid4()
        with factory() as session, session.begin():
            session.add(
                Event(
                    id=identity,
                    owner_id=owner,
                    topic_id=topic,
                    revision=1,
                    title="Controlled shared release story",
                    summary="Controlled independent root",
                    first_seen_at=now,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                EventMember(
                    id=uuid4(),
                    owner_id=owner,
                    topic_id=topic,
                    event_id=identity,
                    content_id=material.id,
                    content_version_id=material.latest_observation.content_version.id,
                    **_fixed_member_fields(session, owner, material),
                    source_key="x",
                    representative_comment_id=None,
                    added_revision=1,
                    removed_revision=None,
                    assignment_origin="model",
                    created_at=now,
                )
            )
        event_ids.append(identity)
    with factory() as session, session.begin():
        session.execute(
            text("UPDATE content_observations SET author_external_id='candidate-author'"),
        )
        for identity in event_ids:
            event = session.get(Event, identity)
            event.title, event.updated_at = "Controlled shared release story", now
            ensure_legacy_facts_in_transaction(session, event=event, now=now)
    with factory() as session:
        EventHeatService(session).upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="author",
                selector_ref="candidate-author",
                name="Controlled source",
                mode="editorial",
                scheduled=False,
            ),
        )
    settings = event_read_client.app.state.settings.model_copy(
        update={"events_cluster_enabled": True, "ai_enabled": True}
    )
    # Seventeen active roots form 136 pairs. Admitted pairs must not hide later pairs,
    # including once over 100 pairs have already entered the original Job/Outbox.
    accepted = []
    for _ in range(8):
        with factory() as session, session.begin():
            accepted.append(
                EventConsolidationService(session, settings).enqueue_due_in_transaction(
                    now=now, ai_enabled=True
                )
            )
    assert accepted == [20, 20, 20, 20, 20, 20, 16, 0]
    with factory() as session:
        jobs = session.scalars(select(Job).where(Job.kind == "events.consolidate")).all()
        assert len(jobs) == 136 and len({job.operation_id for job in jobs}) == 136
        assert session.scalar(select(AiCall)) is None
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
