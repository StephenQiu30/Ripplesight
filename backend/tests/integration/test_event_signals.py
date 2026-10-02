# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from tests.integration.test_content_records import _command
from tests.integration.test_event_consolidation import (
    ControlledStoryClient,
    _controlled_factory,
    _pair,
)
from tests.integration.test_event_embeddings import _embedding_budget
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from ai.adapters.embeddings import EmbeddingClient
from ai.embedding_contract import FrozenEmbeddingConfiguration
from ai.models import AiCall
from content.services import ContentService
from events.corrections import EventCorrectionService
from events.embedding_execution import EventEmbeddingExecutor, EventEmbeddingService
from events.fact_models import EventFact, EventFactAssignment, EventFactMember
from events.fact_schemas import EventCorrectionInput
from events.heat import EventHeatService
from events.heat_schemas import AttentionSourceInput
from events.models import Event, EventMember
from events.signals import EventSignalExecutor, EventSignalService
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job
from jobs.schemas import ComponentPolicyInput, CostClass
from jobs.services import ResourceBudgetService


def _post(factory, owner, external, *, author="gamma", quote=None):
    with factory() as session:
        connection = session.execute(text("SELECT id FROM source_connections")).scalar_one()
        policy = session.execute(text("SELECT id FROM source_access_policies")).scalar_one()
        retention = session.execute(text("SELECT id FROM evidence_retention_policies")).scalar_one()
        job = session.execute(text("SELECT id FROM jobs WHERE source_key='x' LIMIT 1")).scalar_one()
        fields = {
            "text_scope": "full",
            "text_origin": "source",
            "title": "讨论已发布的新模型",
            "body": "讨论证据。",
            "published_at": None,
            "author_external_id": author,
        }
        if quote:
            fields["quote_target_external_id"] = quote
        return ContentService(session).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                operation_id=uuid4(),
                observed_at=datetime.now(UTC),
                external_id=external,
                extra_fields=fields,
            ),
        )


def _source(factory, owner, author, mode):
    with factory() as session:
        EventHeatService(session).upsert_source(
            owner_id=owner,
            command=AttentionSourceInput(
                source_key="x",
                selector_kind="author",
                selector_ref=author,
                name=author,
                mode=mode,
                scheduled=False,
            ),
        )


def _message(factory, job, now):
    message = SimpleNamespace(
        kind=job.kind,
        job_id=job.id,
        owner_id=job.owner_id,
        operation_id=job.operation_id,
        configuration_ref=job.configuration_ref,
        configuration_version=job.configuration_version,
    )
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=300, clock=lambda: now).acquire(
            job_id=job.id, worker_id="controlled-signal"
        )
    return message, lease


def _scan(factory, settings, *, ai=False):
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session, session.begin():
        service = EventSignalService(session, settings)
        count = service.enqueue_due_in_transaction(now=now, ai_enabled=ai)
        job = session.scalar(
            select(Job).where(Job.kind == "events.signals").order_by(Job.created_at.desc())
        )
    return count, job, now


def test_native_waiting_quote_joins_after_original_arrives_without_paid_analysis(
    event_read_client, monkeypatch
):
    owner, factory, first, _, _, _, settings = _pair(event_read_client)
    _source(factory, owner, "gamma", "signal")
    signal = _post(factory, owner, "early-discussion", quote="late-original")
    assert _scan(factory, settings)[0] == 0
    late = _post(factory, owner, "late-original", author="alpha")
    with factory() as session, session.begin():
        event = session.get(Event, first)
        fact = session.scalar(
            select(EventFact)
            .join(EventFactAssignment, EventFactAssignment.fact_id == EventFact.id)
            .where(
                EventFact.owner_id == owner,
                EventFactAssignment.event_id == first,
                EventFactAssignment.relation == "root",
                EventFactAssignment.removed_revision.is_(None),
            )
        )
        event.revision += 1
        fact.revision += 1
        member = EventMember(
            id=uuid4(),
            owner_id=owner,
            topic_id=event.topic_id,
            event_id=first,
            content_id=late.id,
            content_version_id=late.latest_observation.content_version.id,
            source_key="x",
            assignment_origin="model",
            added_revision=event.revision,
            removed_revision=None,
            representative_comment_id=None,
            created_at=datetime.now(UTC),
        )
        session.add(member)
        session.flush()
        session.add(
            EventFactMember(
                id=uuid4(),
                owner_id=owner,
                topic_id=event.topic_id,
                event_id=first,
                fact_id=fact.id,
                event_member_id=member.id,
                content_id=member.content_id,
                content_version_id=member.content_version_id,
                role="report",
                assignment_origin="model",
                added_revision=fact.revision,
                removed_revision=None,
                created_at=datetime.now(UTC),
            )
        )
    count, job, now = _scan(factory, settings)
    assert count == 1
    monkeypatch.setattr(
        "events.signals.create_ai_client", lambda _: pytest.fail("native must be zero AI")
    )
    message, lease = _message(factory, job, now)
    executor = EventSignalExecutor(
        factory, settings.model_copy(update={"ai_enabled": False}), clock=lambda: now
    )
    executor.execute(message, lease)
    executor.execute(message, lease)
    with factory() as session:
        attached = session.scalar(
            select(EventFactMember).where(EventFactMember.content_id == signal.id)
        )
        assert attached.role == "mention" and attached.event_id == first
        assert session.scalar(
            select(EventFactMember.id).where(EventFactMember.content_id == signal.id)
        )
        assert session.get(Event, first).revision == 3
        assert len(session.scalars(select(EventFact)).all()) == 2
        assert session.scalar(select(AiCall)) is None
        revision = session.get(Event, first).revision
    with factory() as session:
        EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="detach",
                expected_revisions={first: revision},
                content_ids=[signal.id],
                reason="讨论误贴, 人工保持独立",
            ),
        )
    assert _scan(factory, settings)[0] == 0


def _semantic(client, monkeypatch, *, vector=(1, 0)):
    owner, factory, first, _, _, _, settings = _pair(client)
    _source(factory, owner, "gamma", "signal")
    signal = _post(factory, owner, "semantic-discussion")
    settings = settings.model_copy(
        update={
            "embeddings_enabled": True,
            "embedding_api_key": SecretStr("controlled"),
            "embedding_model": "controlled-vectors",
            "embedding_dimensions": 2,
            "embedding_base_url": "https://api.example.com/v1",
            "embedding_currency": "USD",
            "embedding_input_rate_micros_per_million": Decimal(0),
        }
    )
    with factory() as session:
        ResourceBudgetService(session).save_component_policy(
            owner_id=owner,
            command=ComponentPolicyInput(
                component_key="ai.embeddings",
                component_version="controlled",
                cost_class=CostClass.LOCAL,
                enabled_for_core=True,
                terms_reference="controlled transport only",
                reviewed_at=datetime.now(UTC),
            ),
        )
    _embedding_budget(factory, owner, datetime.now(UTC))
    requests = []

    def embedding_client(_):
        def send(request):
            requests.append(request)
            raw = request.content.decode()
            values = vector if "讨论" in raw else (1, 0) if "固定正文" in raw else (0, 1)
            return httpx.Response(
                200,
                json={
                    "model": "controlled-vectors",
                    "data": [{"index": 0, "embedding": values}],
                    "usage": {"prompt_tokens": 10},
                },
            )

        return EmbeddingClient(
            base_url="https://api.example.com/v1",
            api_key="controlled",
            model="controlled-vectors",
            dimensions=2,
            timeout_seconds=5,
            transport=httpx.MockTransport(send),
            configuration=FrozenEmbeddingConfiguration.from_settings(settings),
        )

    monkeypatch.setattr("events.embedding_execution.create_embedding_client", embedding_client)
    now = datetime.now(UTC) + timedelta(seconds=1)
    with factory() as session, session.begin():
        assert (
            EventEmbeddingService(session, settings).enqueue_due_in_transaction(
                now=now, ai_enabled=True
            )
            == 3
        )
        jobs = list(session.scalars(select(Job).where(Job.kind == "events.embed")))
    for job in jobs:
        message, lease = _message(factory, job, now)
        EventEmbeddingExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    assert len(requests) == 3
    return owner, factory, first, signal, settings


def test_existing_semantic_vectors_attach_nearly_identical_signal_with_no_judge(
    event_read_client, monkeypatch
):
    _, factory, first, signal, settings = _semantic(event_read_client, monkeypatch)
    count, job, now = _scan(factory, settings, ai=True)
    assert count == 1
    monkeypatch.setattr(
        "events.signals.create_ai_client", lambda _: pytest.fail("cosine>=.92 needs no judge")
    )
    message, lease = _message(factory, job, now)
    EventSignalExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    with factory() as session:
        assert (
            session.scalar(
                select(EventFactMember).where(EventFactMember.content_id == signal.id)
            ).event_id
            == first
        )
        assert len(session.scalars(select(AiCall)).all()) == 3


def test_semantic_review_saved_response_recovers_once(event_read_client, monkeypatch):
    _, factory, first, signal, settings = _semantic(
        event_read_client, monkeypatch, vector=(0.8, 0.6)
    )
    count, job, now = _scan(factory, settings, ai=True)
    assert count == 1
    provider = ControlledStoryClient((0.8,))
    _controlled_factory(monkeypatch, provider)
    message, lease = _message(factory, job, now)
    executor = EventSignalExecutor(factory, settings, clock=lambda: now)
    original = executor._prepare
    calls = 0

    def stop(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled stop after saved relation")
        return original(*args)

    monkeypatch.setattr(executor, "_prepare", stop)
    with pytest.raises(RuntimeError):
        executor.execute(message, lease)
    EventSignalExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    assert len(provider.calls) == 1
    with factory() as session:
        assert (
            session.scalar(
                select(EventFactMember).where(EventFactMember.content_id == signal.id)
            ).event_id
            == first
        )
        assert len(session.scalars(select(AiCall)).all()) == 4


def test_semantic_recall_expires_after_six_hours_without_repaying_vectors(
    event_read_client, monkeypatch
):
    _, factory, _, signal, settings = _semantic(event_read_client, monkeypatch)
    with factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE content_observations SET observed_at=:old,received_at=:old "
                "WHERE content_id=:content"
            ),
            {"old": datetime.now(UTC) - timedelta(hours=7), "content": signal.id},
        )
    assert _scan(factory, settings, ai=True)[0] == 0
    with factory() as session:
        assert len(session.scalars(select(AiCall)).all()) == 3
        assert (
            session.scalar(select(EventFactMember).where(EventFactMember.content_id == signal.id))
            is None
        )


def test_semantic_review_missing_saved_response_is_unknown_and_never_automatically_repaid(
    event_read_client, monkeypatch
):
    _, factory, _, signal, settings = _semantic(event_read_client, monkeypatch, vector=(0.8, 0.6))
    _, job, now = _scan(factory, settings, ai=True)
    provider = ControlledStoryClient((0.8,))
    _controlled_factory(monkeypatch, provider)
    message, lease = _message(factory, job, now)
    executor = EventSignalExecutor(factory, settings, clock=lambda: now)
    original = executor._load

    def stop_before_saved(session, *args):
        if (
            session.scalar(
                select(AiCall.id).where(
                    AiCall.job_id == job.id,
                    AiCall.purpose == "events.signal-relation",
                    AiCall.status == "succeeded",
                )
            )
            is not None
        ):
            raise RuntimeError("controlled death before business response save")
        return original(session, *args)

    monkeypatch.setattr(executor, "_load", stop_before_saved)
    with pytest.raises(RuntimeError):
        executor.execute(message, lease)
    with pytest.raises(JobExecutionFailure, match="event_signal_result_unknown"):
        EventSignalExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    assert len(provider.calls) == 1
    with factory() as session:
        assert len(session.scalars(select(AiCall)).all()) == 4
        assert (
            session.scalar(select(EventFactMember).where(EventFactMember.content_id == signal.id))
            is None
        )


def test_queued_semantic_signal_rechecks_current_source_permission_before_model(
    event_read_client, monkeypatch
):
    _, factory, _, signal, settings = _semantic(event_read_client, monkeypatch, vector=(0.8, 0.6))
    _, job, now = _scan(factory, settings, ai=True)
    with factory() as session, session.begin():
        session.execute(text("UPDATE source_access_policies SET enabled=false"))
    monkeypatch.setattr(
        "events.signals.create_ai_client", lambda _: pytest.fail("permission was withdrawn")
    )
    message, lease = _message(factory, job, now)
    with pytest.raises(JobExecutionFailure, match="event_signal_input_changed"):
        EventSignalExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    with factory() as session:
        assert len(session.scalars(select(AiCall)).all()) == 3
        assert (
            session.scalar(select(EventFactMember).where(EventFactMember.content_id == signal.id))
            is None
        )


def test_signal_revocation_after_prepare_denies_ai_and_budget_reservation(
    event_read_client, monkeypatch
):
    _, factory, _, _, settings = _semantic(event_read_client, monkeypatch, vector=(0.8, 0.6))
    _, job, now = _scan(factory, settings, ai=True)
    provider = ControlledStoryClient((0.8,))
    _controlled_factory(monkeypatch, provider)
    from events import signals

    original_factory = signals.create_event_stage_client
    with factory() as session:
        calls = session.execute(text("SELECT count(*) FROM ai_calls")).scalar()
        reservations = session.execute(
            text("SELECT count(*) FROM resource_budget_reservations")
        ).scalar()

    def revoke_after_prepare(*args, **kwargs):
        with factory.begin() as session:
            session.execute(text("UPDATE source_access_policies SET enabled=false"))
        return original_factory(*args, **kwargs)

    monkeypatch.setattr(signals, "create_event_stage_client", revoke_after_prepare)
    message, lease = _message(factory, job, now)
    with pytest.raises(JobExecutionFailure, match="event_signal_input_changed"):
        EventSignalExecutor(factory, settings, clock=lambda: now).execute(message, lease)
    assert provider.calls == []
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar() == calls
        assert (
            session.execute(text("SELECT count(*) FROM resource_budget_reservations")).scalar()
            == reservations
        )


def test_native_waiting_signal_expires_at_forty_eight_hours(event_read_client):
    owner, factory, first, _, _, _, settings = _pair(event_read_client)
    _source(factory, owner, "gamma", "signal")
    with factory() as session:
        external = session.execute(
            text(
                "SELECT external_id FROM content_records WHERE id="
                "(SELECT content_id FROM event_members WHERE event_id=:event "
                "AND removed_revision IS NULL LIMIT 1)"
            ),
            {"event": first},
        ).scalar_one()
    signal = _post(factory, owner, "expired-native-discussion", quote=external)
    old = datetime.now(UTC) - timedelta(hours=49)
    with factory() as session, session.begin():
        session.execute(
            text(
                "UPDATE content_observations SET observed_at=:old,received_at=:old "
                "WHERE content_id=:content"
            ),
            {"old": old, "content": signal.id},
        )
    assert _scan(factory, settings)[0] == 0
    with factory() as session:
        assert session.scalar(select(AiCall)) is None
        assert (
            session.scalar(select(EventFactMember).where(EventFactMember.content_id == signal.id))
            is None
        )


def test_semantic_judge_below_confidence_threshold_leaves_discussion_independent(
    event_read_client, monkeypatch
):
    _, factory, _, signal, settings = _semantic(event_read_client, monkeypatch, vector=(0.8, 0.6))
    _, job, now = _scan(factory, settings, ai=True)
    provider = ControlledStoryClient((0.79,))
    _controlled_factory(monkeypatch, provider)
    message, lease = _message(factory, job, now)
    executor = EventSignalExecutor(factory, settings, clock=lambda: now)
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(provider.calls) == 1
    with factory() as session:
        assert len(session.scalars(select(AiCall)).all()) == 4
        assert (
            session.scalar(select(EventFactMember).where(EventFactMember.content_id == signal.id))
            is None
        )
