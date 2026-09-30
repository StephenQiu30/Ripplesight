from __future__ import annotations

import hashlib
import os
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from connections.presets import NEWS_SEARCH_PRESET
from connections.schemas import SourceConnectionConfig
from connections.services import SourcePresetService
from content.discovery import plan_single_keyword_discovery
from content.discovery_execution import KeywordDiscoveryExecutor, build_search_adapter_factory
from content.models import ContentDiscovery, ContentObservation, ContentRecord, ContentVersion
from content.schemas import KeywordDiscoveryRunInput
from jobs.execution import JobCompletion
from jobs.models import CoverageWindow, Job
from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
from jobs.services import JobService, OutboxService, ResourceBudgetService
from sources.adapters.web_search import WebSearchAdapter
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import publish_outbox


def _news_search_run(
    *,
    topic_id: UUID,
    connection_id: UUID,
    connection_version: int,
    version: int,
    start: datetime,
    end: datetime,
    page_size: int,
) -> KeywordDiscoveryRunInput:
    return KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref=f"topic:{topic_id}",
        configuration_version=version,
        source_key="news_search",
        connection_id=connection_id,
        connection_version=connection_version,
        primary_query="AI",
        starts_at=start,
        ends_at=end,
        page_size=page_size,
        latest_max_pages=1,
        latest_max_requests=1,
        top_max_pages=1,
        top_max_requests=1,
        max_seconds=45,
    )


def _result(url: str, title: str, published_at: datetime | None) -> dict[str, str]:
    result = {
        "url": url,
        "title": title,
        "content": "<p>新闻摘要而非完整正文</p>",
        "engine": "duckduckgo news",
    }
    if published_at is not None:
        result["publishedDate"] = published_at.isoformat()
    return result


@pytest.mark.parametrize("host", ["127.0.0.1", "host.docker.internal"])
def test_news_search_kafka_replay_preserves_normalized_identity_and_partial_coverage(
    host: str,
) -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    bootstrap_servers = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if database_url is None or bootstrap_servers is None:
        pytest.skip("PostgreSQL and Kafka are required for SearXNG replay")

    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(days=1)
    kafka_topic = f"hotkey.tests.plan036.{uuid4().hex}"
    group_id = f"hotkey-tests-plan036-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    producer = Producer({"bootstrap.servers": bootstrap_servers})
    consumers: list[Consumer] = []
    requested: list[str] = []
    preset = replace(
        NEWS_SEARCH_PRESET,
        config=dict(NEWS_SEARCH_PRESET.config)
        | {"base_url": f"http://{host}:8888", "allowed_hosts": (host,)},
    )

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.url.scheme == "http"
        assert request.url.host == host
        assert request.url.port == 8888
        assert request.url.path == "/search"
        assert dict(request.url.params) == {
            "q": "AI",
            "format": "json",
            "pageno": "1",
            "engines": "duckduckgo news",
        }
        tracking_value = "first" if len(requested) == 1 else "second"
        return httpx.Response(
            200,
            json={
                "results": [
                    _result(
                        f"https://example.org/story?id=42&utm_source={tracking_value}",
                        "AI 窗口开始",
                        start,
                    ),
                    _result(
                        "https://example.org/story?utm_source=duplicate&id=42",
                        "AI 同页重复链接",
                        start,
                    ),
                    _result(
                        "https://example.org/story?id=43&utm_medium=search",
                        "AI 窗口内部",
                        end - timedelta(hours=1),
                    ),
                    _result("https://example.org/story?id=44", "AI 无发布时间", None),
                    _result(
                        "https://example.org/story?id=45",
                        "AI 窗口之前",
                        start - timedelta(seconds=1),
                    ),
                    _result("https://example.org/story?id=46", "AI 窗口结束", end),
                    _result(
                        "https://example.org/story?id=47",
                        "普通新闻",
                        end - timedelta(hours=1),
                    ),
                ],
                "unresponsive_engines": [],
            },
        )

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
        raise AssertionError("SearXNG Kafka job message was not delivered")

    try:
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'SearXNG replay', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": end},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"AI\"]', '[]', '[]', :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": end},
            )
            applied = SourcePresetService(session, clock=lambda: end).apply_in_transaction(
                owner_id=owner_id, preset=preset
            )
            ResourceBudgetService(session, clock=lambda: end).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.plan036.kafka.daily",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=86_400,
                    window_anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
                    enabled=True,
                ),
            )
            first_job = JobService(session, clock=lambda: end).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(
                    _news_search_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=1,
                        start=start,
                        end=end,
                        page_size=20,
                    )
                ),
            )

        admin.create_topics([NewTopic(kafka_topic, 1, 1)])[kafka_topic].result(10)
        factory = build_search_adapter_factory(
            "news_search", SourceConnectionConfig.model_validate(dict(preset.config))
        )

        def adapter_factory(before, cancelled, max_requests, max_seconds):
            adapter = factory(before, cancelled, max_requests, max_seconds)
            assert isinstance(adapter, WebSearchAdapter)
            adapter._transport = httpx.MockTransport(respond)
            return adapter

        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            component_key="collector.news_search",
            adapter_factory=adapter_factory,
        )

        def search(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        handler = create_job_message_handler(
            sessions,
            {"keyword.search": search},
            worker_id="news-search-kafka-test",
            lease_seconds=60,
        )
        with sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(
                        producer, replace(envelope, topic=kafka_topic), timeout_seconds=10
                    )
                )
                == 1
            )
        first_consumer = new_consumer()
        first_message = next_message(first_consumer)
        handler(first_message)
        first_consumer.close()  # Let Kafka redeliver the same uncommitted offset.
        second_consumer = new_consumer()
        redelivered = next_message(second_consumer)
        assert (redelivered.partition(), redelivered.offset()) == (
            first_message.partition(),
            first_message.offset(),
        )
        handler(redelivered)
        second_consumer.commit(message=redelivered, asynchronous=False)
        assert len(requested) == 1

        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 2, :owner_id, '[\"AI\"]', '[]', '[]', :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": end},
            )
            session.execute(
                text("UPDATE monitor_topics SET current_version = 2 WHERE id = :id"),
                {"id": topic_id},
            )
            second_job = JobService(session, clock=lambda: end).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(
                    _news_search_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=2,
                        start=start,
                        end=end,
                        page_size=2,
                    )
                ),
            )
        with sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(
                        producer, replace(envelope, topic=kafka_topic), timeout_seconds=10
                    )
                )
                == 1
            )
        second_message = next_message(second_consumer)
        assert second_message.offset() > redelivered.offset()
        handler(second_message)
        second_consumer.commit(message=second_message, asynchronous=False)
        assert len(requested) == 2

        expected_ids = [
            "url:" + hashlib.sha256(f"https://example.org/story?id={id}".encode()).hexdigest()
            for id in (42, 43, 44)
        ]
        with sessions() as session:
            jobs = [session.get(Job, job_id) for job_id in (first_job.id, second_job.id)]
            assert all(job is not None for job in jobs)
            assert [(job.status, job.requests_sent, job.items_saved) for job in jobs] == [
                ("partially_succeeded", 1, 3),
                ("partially_succeeded", 1, 2),
            ]
            assert [job.checkpoint["collection.observed_count"] for job in jobs] == [6, 2]
            assert [job.checkpoint["collection.source_engine"] for job in jobs] == [
                "duckduckgo news",
                "duckduckgo news",
            ]
            assert [job.checkpoint["collection.source_page_number"] for job in jobs] == [1, 1]
            assert dict(
                session.execute(
                    select(ContentRecord.external_id, ContentRecord.identity_basis).where(
                        ContentRecord.owner_id == owner_id
                    )
                ).all()
            ) == {external_id: "url_fallback" for external_id in expected_ids}
            assert (
                session.scalars(
                    select(ContentVersion.text_scope).where(ContentVersion.owner_id == owner_id)
                ).all()
                == ["truncated"] * 3
            )
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentDiscovery)
                    .where(ContentDiscovery.owner_id == owner_id)
                )
                == 5
            )
            assert session.execute(
                select(ContentObservation.published_at)
                .join(ContentRecord, ContentRecord.id == ContentObservation.content_id)
                .where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.external_id == expected_ids[2],
                )
            ).scalars().all() == [None]
            coverages = session.scalars(
                select(CoverageWindow)
                .where(CoverageWindow.owner_id == owner_id)
                .order_by(CoverageWindow.rule_version)
            ).all()
            assert [
                (coverage.rule_version, coverage.status, coverage.stop_reason, coverage.page_count)
                for coverage in coverages
            ] == [
                (1, "partial", "unverified_terminal", 1),
                (2, "partial", "budget_exhausted", 1),
            ]
            assert session.execute(
                text(
                    "SELECT p.budget_key, w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id = w.budget_policy_id "
                    "WHERE p.owner_id = :owner_id ORDER BY p.budget_key"
                ),
                {"owner_id": owner_id},
            ).all() == [
                ("global.plan036.kafka.daily", 2),
                ("source.news_search.network.daily", 2),
            ]
            assert dict(
                session.execute(
                    text(
                        "SELECT job_id, count(*) FROM processed_messages "
                        "WHERE job_id IN (:first, :second) GROUP BY job_id"
                    ),
                    {"first": first_job.id, "second": second_job.id},
                ).all()
            ) == {first_job.id: 1, second_job.id: 1}
    finally:
        for consumer in consumers:
            consumer.close()
        with suppress(Exception):
            admin.delete_topics([kafka_topic], operation_timeout=10)[kafka_topic].result(10)
        engine.dispose()
