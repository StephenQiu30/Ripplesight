from __future__ import annotations

import os
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from connections.presets import HACKERNEWS_PRESET
from connections.services import SourcePresetService
from content.discovery import plan_single_keyword_discovery
from content.discovery_execution import KeywordDiscoveryExecutor
from content.models import ContentDiscovery, ContentObservation, ContentRecord
from content.schemas import KeywordDiscoveryRunInput
from jobs.execution import JobCompletion
from jobs.models import CoverageWindow, Job
from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
from jobs.services import JobService, OutboxService, ResourceBudgetService
from sources.adapters.hackernews import HackerNewsAdapter
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import publish_outbox


def test_hackernews_pages_are_persisted_once_after_kafka_redelivery() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    bootstrap_servers = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if database_url is None or bootstrap_servers is None:
        pytest.skip("PostgreSQL and Kafka are required for HN replay")

    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    kafka_topic = f"hotkey.tests.plan007.{uuid4().hex}"
    group_id = f"hotkey-tests-plan007-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    producer = Producer({"bootstrap.servers": bootstrap_servers})
    consumers: list[Consumer] = []
    requested: list[str] = []
    try:
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'HN Kafka replay', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"AI\"]', '[]', '[]', :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            applied = SourcePresetService(session, clock=lambda: now).apply_in_transaction(
                owner_id=owner_id, preset=HACKERNEWS_PRESET
            )
            ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.plan007.kafka.daily",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=86_400,
                    window_anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
                    enabled=True,
                ),
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key="hackernews",
                connection_id=applied.connection_id,
                connection_version=applied.connection_version,
                primary_query="AI",
                starts_at=now - timedelta(days=1),
                ends_at=now,
                page_size=1,
                latest_max_pages=2,
                latest_max_requests=2,
                top_max_pages=1,
                top_max_requests=1,
                max_seconds=45,
            )
            accepted = JobService(session, clock=lambda: now).accept_in_transaction(
                owner_id=owner_id, command=plan_single_keyword_discovery(run)
            )

        admin.create_topics([NewTopic(kafka_topic, 1, 1)])[kafka_topic].result(10)

        def new_consumer() -> Consumer:
            consumer = Consumer(
                {
                    "bootstrap.servers": bootstrap_servers,
                    "group.id": group_id,
                    "enable.auto.commit": False,
                    "auto.offset.reset": "earliest",
                }
            )
            consumer.subscribe([kafka_topic])
            consumers.append(consumer)
            return consumer

        def next_message(consumer: Consumer) -> Message:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                message = consumer.poll(1.0)
                if message is not None:
                    assert message.error() is None
                    return message
            raise AssertionError("HN Kafka job message was not delivered")

        with sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(
                        producer, replace(envelope, topic=kafka_topic), timeout_seconds=10
                    )
                )
                == 1
            )

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            assert request.url.path == "/api/v1/search_by_date"
            page = int(request.url.params["page"])
            assert page in {0, 1}
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "objectID": f"story-{page}",
                            "title": f"AI story {page}",
                            "author": "hn-user",
                            "created_at_i": int((now - timedelta(hours=page + 1)).timestamp()),
                            "url": f"https://example.com/story-{page}",
                            "points": None,
                            "num_comments": page,
                        }
                    ],
                    "page": page,
                    "hitsPerPage": 1,
                    "nbPages": 2,
                    "nbHits": 2,
                    "exhaustiveNbHits": True,
                },
            )

        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            component_key="collector.hackernews",
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(respond),
            ),
        )

        def search(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        handler = create_job_message_handler(
            sessions,
            {"keyword.search": search},
            worker_id="hackernews-kafka-test",
            lease_seconds=60,
        )
        first_consumer = new_consumer()
        first = next_message(first_consumer)
        handler(first)
        first_consumer.close()  # Reopen without committing the offset.
        second_consumer = new_consumer()
        redelivered = next_message(second_consumer)
        assert (redelivered.partition(), redelivered.offset()) == (
            first.partition(),
            first.offset(),
        )
        handler(redelivered)
        second_consumer.commit(message=redelivered, asynchronous=False)

        assert [httpx.URL(url).params["page"] for url in requested] == ["0", "1"]
        with sessions() as session:
            job = session.get(Job, accepted.id)
            assert job is not None
            assert (job.status, job.requests_sent, job.items_saved) == ("succeeded", 2, 2)
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(text("processed_messages"))
                    .where(text("job_id = :job_id"))
                    .params(job_id=accepted.id)
                )
                == 1
            )
            assert session.execute(
                select(ContentRecord.external_id, ContentObservation.canonical_url)
                .join(ContentObservation, ContentObservation.content_id == ContentRecord.id)
                .where(ContentRecord.owner_id == owner_id)
                .order_by(ContentRecord.external_id)
            ).all() == [
                ("story-0", "https://news.ycombinator.com/item?id=story-0"),
                ("story-1", "https://news.ycombinator.com/item?id=story-1"),
            ]
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentDiscovery)
                    .where(ContentDiscovery.owner_id == owner_id)
                )
                == 2
            )
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == accepted.id)
            )
            assert coverage is not None
            assert (coverage.status, coverage.stop_reason, coverage.page_count) == (
                "confirmed",
                None,
                2,
            )
            assert session.execute(
                text(
                    "SELECT count(*), sum(actual_units) FROM resource_budget_reservations "
                    "WHERE owner_id = :owner_id"
                ),
                {"owner_id": owner_id},
            ).one() == (4, 4)
    finally:
        for consumer in consumers:
            consumer.close()
        with suppress(Exception):
            admin.delete_topics([kafka_topic], operation_timeout=10)[kafka_topic].result(10)
        engine.dispose()
