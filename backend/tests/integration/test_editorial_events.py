# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
    editorial_client,  # noqa: F401
)

from ai.schemas import AiCompletion, AiTokenUsage
from analysis.event_reading import list_editorial_event_inputs_in_transaction
from content.schemas import RecordContentVisibilityInput
from content.services import ContentService
from core.errors import ApplicationError
from events.fact_models import EventFact, EventFactMember
from events.models import Event, EventCandidate
from events.services import EventCandidateService, EventClusterExecutor
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job
from jobs.schemas import JobAcceptedMessage
from monitors.editorial_events import editorial_event_topic_id
from monitors.schemas import MonitorTopicUpdateInput
from monitors.services import MonitorTopicService

AT = NOW + timedelta(minutes=1)


class EditorialWithFact(ControlledClient):
    def complete(self, **kwargs):
        result = super().complete(**kwargs)
        if kwargs["output_schema"]["title"] == "StructureOutput":
            result.output["fact"] = {
                "title": "OpenAI 新模型发布",
                "subject": "openai",
                "action": "发布",
                "object": "新模型",
                "occurredAt": NOW.date().isoformat(),
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
        fact = session.scalar(select(EventFact))
        member = session.scalar(select(EventFactMember))
        assert event.topic_id == editorial_event_topic_id(owner)
        assert fact.frame == {
            "subject": "openai",
            "action": "发布",
            "object": "新模型",
            "occurredAt": NOW.date().isoformat(),
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
    assert _candidate(factory, owner)[0] == 0


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
