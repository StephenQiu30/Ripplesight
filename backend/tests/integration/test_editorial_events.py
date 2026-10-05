# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _request_run,
    _run,
    _source,
    editorial_client,  # noqa: F401
)

from ai.schemas import AiCompletion, AiTokenUsage
from analysis.event_reading import list_editorial_event_inputs_in_transaction
from content.schemas import RecordContentVisibilityInput
from content.services import ContentService
from core.errors import ApplicationError
from events.fact_models import EventFact, EventFactAssignment, EventFactMember
from events.facts import EventFactReadService
from events.models import Event, EventCandidate
from events.services import EventCandidateService, EventClusterExecutor
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job
from jobs.schemas import JobAcceptedMessage
from monitors.editorial_events import editorial_event_topic_id
from monitors.schemas import MonitorTopicUpdateInput
from monitors.services import MonitorTopicService

AT = NOW + timedelta(minutes=1)


class EditorialComposite(ControlledClient):
    def complete(self, **kwargs):
        result = super().complete(**kwargs)
        if kwargs["output_schema"]["title"] == "StructureOutput":
            result.output["scope"] = "composite"
        return result


class EditorialWithFact(ControlledClient):
    def complete(self, **kwargs):
        result = super().complete(**kwargs)
        if kwargs["output_schema"]["title"] == "StructureOutput":
            result.output["scope"] = "single"
            result.output["fact"] = {
                "title": "OpenAI 新模型发布",
                "subject": "openai",
                "action": "发布",
                "object": "新模型",
                "occurredAt": NOW.date().isoformat(),
                "evidence": "OpenAI 发布新模型,公开 API。",
                "conditions": [{"quote": "OpenAI 发布新模型,公开 API。"}],
            }
        return result


class ClusterClient:
    provider, model = "controlled", "controlled-events"

    def __init__(self, version):
        self.version, self.calls = version, []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={
                "same_event": True,
                "member_version_ids": [str(self.version)],
                "title": "OpenAI 新模型发布",
                "summary": "受控固定发布证据。",
                "facts": [
                    {
                        "member_version_ids": [str(self.version)],
                        "title": "新模型发布",
                        "summary": "同一次发生的发布事实。",
                        "relation": "root",
                    }
                ],
            },
            usage=AiTokenUsage(input_tokens=10, output_tokens=10),
            duration_ms=1,
        )

    def close(self):
        pass


def test_composite_positive_grouping_persists_only_a_mention_of_existing_fact(
    editorial_client, monkeypatch
):
    now = datetime.now(UTC)
    owner, _, posts = _seed_posts(
        editorial_client,
        [
            ("OpenAI 发布新模型", "OpenAI 发布新模型,公开 API。"),
            (
                "OpenAI 发布新模型大会回顾",
                "OpenAI 发布新模型。另有独立芯片发布与多位演讲者。",
            ),
        ],
        dated=True,
        now=now,
    )
    _source(editorial_client, owner, now=now)
    _budget(editorial_client, owner, now=now)
    _, single, message, lease = _request_run(editorial_client, owner, posts[0], now=now)
    _execute(editorial_client, owner, message, lease, EditorialWithFact(), now=now)
    factory = editorial_client.app.state.session_factory
    at = now + timedelta(seconds=10)
    _, candidate = _candidate(factory, owner, at=at)
    monkeypatch.setattr(
        "events.services.create_ai_client", lambda _: ClusterClient(single.content_version_id)
    )
    settings = editorial_client.app.state.settings.model_copy(
        update={"events_cluster_enabled": True, "ai_enabled": True}
    )
    cluster_message, cluster_lease = _cluster_message(factory, candidate)
    EventClusterExecutor(factory, settings, clock=lambda: at).execute(
        cluster_message, cluster_lease
    )
    with factory() as session:
        event = session.scalar(select(Event))
        event_id = event.id
        fact = session.scalar(select(EventFact))
        fact_id, original_frame = fact.id, fact.frame
    _, composite, message, lease = _request_run(
        editorial_client, owner, posts[1], now=now + timedelta(seconds=20)
    )
    _execute(
        editorial_client,
        owner,
        message,
        lease,
        EditorialComposite(),
        now=now + timedelta(seconds=20),
    )
    at = now + timedelta(seconds=30)
    with factory() as session, session.begin():
        assert (
            EventCandidateService(session).enqueue_due_in_transaction(now=at, ai_enabled=True) == 1
        )
        append = session.scalar(select(EventCandidate).where(EventCandidate.status == "pending"))
        assert append.expected_event_revisions == {str(event_id): 1}
        assert {item["editorial_scope"] for item in append.input_manifest["items"]} == {
            "single",
            "composite",
        }

    class WrongCompositeRoot(ClusterClient):
        def complete(self, **kwargs):
            result = super().complete(**kwargs)
            result.output["member_version_ids"] = [
                str(single.content_version_id),
                str(composite.content_version_id),
            ]
            result.output["facts"] = [
                {
                    "member_version_ids": [str(single.content_version_id)],
                    "title": "已有事实",
                    "summary": "已有发布",
                    "relation": "same_occurrence",
                    "existing_fact_id": str(fact_id),
                },
                {
                    "member_version_ids": [str(composite.content_version_id)],
                    "title": "错误综合根",
                    "summary": "错误的根事实",
                    "relation": "root",
                },
            ]
            return result

    provider = WrongCompositeRoot(composite.content_version_id)
    monkeypatch.setattr("events.services.create_ai_client", lambda _: provider)
    cluster_message, cluster_lease = _cluster_message(factory, append)
    executor = EventClusterExecutor(factory, settings, clock=lambda: at)
    executor.execute(cluster_message, cluster_lease)
    executor.execute(cluster_message, cluster_lease)
    assert len(provider.calls) == 1
    with factory() as session:
        assert len(session.scalars(select(Event)).all()) == 1
        assert len(session.scalars(select(EventFact)).all()) == 1
        assert session.get(EventFact, fact_id).frame == original_frame
        assert session.get(Event, event_id).revision == 2
        assert session.scalar(select(EventFactAssignment)).relation == "root"
        members = list(session.scalars(select(EventFactMember)))
        assert {member.role for member in members} == {"primary", "mention"}
        assert (
            next(
                member
                for member in members
                if member.content_version_id == composite.content_version_id
            ).role
            == "mention"
        )
    assert _candidate(factory, owner, at=at + timedelta(seconds=1))[0] == 0


def _selected(client):
    owner, run, message, lease = _run(client)
    _budget(client, owner)
    _execute(client, owner, message, lease, EditorialWithFact())
    return owner, run, client.app.state.session_factory


def _candidate(factory, owner, *, at=None):
    at = at or datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session, session.begin():
        count = EventCandidateService(session, clock=lambda: at).enqueue_due_in_transaction(
            now=at, ai_enabled=True
        )
        candidate = session.scalar(select(EventCandidate))
    return count, candidate


def _cluster_message(factory, candidate):
    with factory() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": candidate.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        lease = JobExecutionService(
            session, lease_seconds=300, clock=lambda: candidate.created_at
        ).acquire(job_id=candidate.job_id, worker_id="editorial-events-controlled")
    return message, lease


def test_selected_editorial_material_creates_story_without_a_user_monitor(
    editorial_client, monkeypatch
):
    owner, run, factory = _selected(editorial_client)
    at = datetime.now(UTC) + timedelta(seconds=1)
    count, candidate = _candidate(factory, owner, at=at)
    assert count == 1 and candidate.topic_id == editorial_event_topic_id(owner)
    provider = ClusterClient(run.content_version_id)
    monkeypatch.setattr("events.services.create_ai_client", lambda _: provider)
    settings = editorial_client.app.state.settings.model_copy(
        update={
            "events_cluster_enabled": True,
            "ai_enabled": True,
        }
    )
    message, lease = _cluster_message(factory, candidate)
    executor = EventClusterExecutor(factory, settings, clock=lambda: at)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(provider.calls) == 1
    assert '"editorial_frame"' in provider.calls[0]["prompt"]
    with factory() as session:
        event = session.scalar(select(Event))
        event_id = event.id
        fact = session.scalar(select(EventFact))
        fact_id = fact.id
        member = session.scalar(select(EventFactMember))
        assert event.topic_id == editorial_event_topic_id(owner)
        assert fact.frame == {
            "subject": "openai",
            "action": "发布",
            "object": "新模型",
            "occurredAt": NOW.date().isoformat(),
            "evidence": "OpenAI 发布新模型,公开 API。",
            "conditions": [{"quote": "OpenAI 发布新模型,公开 API。"}],
        }
        assert member.fact_id == fact.id and member.role == "primary"
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM jobs WHERE configuration_ref=:ref "
                    "AND kind!='events.cluster'"
                ),
                {"ref": f"topic:{event.topic_id}"},
            ).scalar_one()
            == 0
        )
        topic_service = MonitorTopicService(session)
        listed, _ = topic_service.list_topics(
            owner_id=owner, include_archived=True, cursor=None, limit=100
        )
        assert event.topic_id not in {item.id for item in listed}
        for method in (
            topic_service.get_topic,
            topic_service.clone_topic,
            topic_service.resume_topic,
            topic_service.pause_topic,
            topic_service.archive_topic,
        ):
            with pytest.raises(ApplicationError, match="resource_not_found"):
                method(owner_id=owner, topic_id=event.topic_id)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            topic_service.update_topic(
                owner_id=owner,
                topic_id=event.topic_id,
                command=MonitorTopicUpdateInput(
                    name="恶意复用内部主题",
                    expected_version=1,
                    match_any=["OpenAI"],
                    match_all=[],
                    exclude=[],
                ),
            )
    with factory() as session:
        view = EventFactReadService(session).list_facts(owner_id=owner, event_id=event_id)
        assert view.facts[0].evidence == "OpenAI 发布新模型,公开 API。"
        assert [item.quote for item in view.facts[0].conditions] == ["OpenAI 发布新模型,公开 API。"]
    assert _candidate(factory, owner)[0] == 0
    with factory() as session, session.begin():
        stored_fact = session.get(EventFact, fact_id)
        stored_fact.status = "unreviewed"
    with factory() as session:
        hidden = EventFactReadService(session).list_facts(owner_id=owner, event_id=event_id)
        assert hidden.facts[0].evidence is None and hidden.facts[0].conditions == []
    with factory() as session, session.begin():
        stored_fact = session.get(EventFact, fact_id)
        stored_fact.status = "confirmed"
        stored_fact.frame = {"subject": "openai", "action": "发布", "object": "新模型"}
    with factory() as session:
        legacy = EventFactReadService(session).list_facts(owner_id=owner, event_id=event_id)
        assert legacy.facts[0].evidence is None and legacy.facts[0].conditions == []


def test_editorial_source_withdrawal_blocks_a_queued_story_before_another_paid_call(
    editorial_client, monkeypatch
):
    owner, run, factory = _selected(editorial_client)
    at = datetime.now(UTC) + timedelta(seconds=1)
    _, candidate = _candidate(factory, owner, at=at)
    with factory() as session:
        source_job = session.scalar(select(Job.id).where(Job.source_key == "x").limit(1))
        ContentService(session, clock=lambda: at + timedelta(seconds=1)).record_visibility(
            owner_id=owner,
            command=RecordContentVisibilityInput(
                content_id=run.content_id,
                job_id=source_job,
                source_operation_id=uuid4(),
                observed_at=at + timedelta(seconds=1),
                status="deleted",
                basis="source_tombstone",
            ),
        )
    provider = ClusterClient(run.content_version_id)
    monkeypatch.setattr("events.services.create_ai_client", lambda _: provider)
    message, lease = _cluster_message(factory, candidate)
    settings = editorial_client.app.state.settings.model_copy(
        update={"events_cluster_enabled": True}
    )
    with pytest.raises(JobExecutionFailure, match="event_input_changed"):
        EventClusterExecutor(factory, settings, clock=lambda: at + timedelta(seconds=2)).execute(
            message, lease
        )
    assert provider.calls == []
    with factory() as session, session.begin():
        assert (
            list_editorial_event_inputs_in_transaction(
                session, since=NOW - timedelta(hours=1), now=at + timedelta(seconds=2)
            ).items
            == ()
        )
        assert session.scalar(select(Event)) is None
