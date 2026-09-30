from __future__ import annotations

import os
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import UUID, uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from connections.presets import GOOGLE_NEWS_PRESET
from connections.services import SourcePresetService
from content.discovery import plan_single_keyword_discovery
from content.discovery_execution import KeywordDiscoveryExecutor
from content.models import ContentDiscovery, ContentObservation, ContentRecord
from content.schemas import KeywordDiscoveryRunInput
from jobs.execution import JobCompletion
from jobs.models import CoverageWindow, Job
from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
from jobs.services import JobService, OutboxService, ResourceBudgetService
from sources.adapters.rss import RssSourceAdapter
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import publish_outbox


def _rss_item(guid: str, title: str, *, published_at: datetime | None = None) -> str:
    published = (
        f"<pubDate>{format_datetime(published_at, usegmt=True)}</pubDate>"
        if published_at is not None
        else ""
    )
    return (
        f"<item><guid>{guid}</guid><title>{title}</title>"
        f"<link>https://news.google.com/articles/{guid}</link>{published}</item>"
    )


def _google_news_run(
    *,
    topic_id: UUID,
    connection_id: UUID,
    connection_version: int,
    version: int,
    start: datetime,
    end: datetime,
    page_size: int = 20,
) -> KeywordDiscoveryRunInput:
    return KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref=f"topic:{topic_id}",
        configuration_version=version,
        source_key="google_news",
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


def test_google_news_kafka_replay_and_second_rule_version_keep_one_identity() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    bootstrap_servers = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if database_url is None or bootstrap_servers is None:
        pytest.skip("PostgreSQL and Kafka are required for Google News replay")

    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(days=1)
    feed_updated_at = end - timedelta(minutes=10)
    kafka_topic = f"hotkey.tests.plan035.{uuid4().hex}"
    group_id = f"hotkey-tests-plan035-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    producer = Producer({"bootstrap.servers": bootstrap_servers})
    consumers: list[Consumer] = []
    requested: list[str] = []
    upstream_status = 200
    feed = (
        "<rss version='2.0'><channel><title>Google News</title>"
        f"<lastBuildDate>{format_datetime(feed_updated_at, usegmt=True)}</lastBuildDate>"
        + _rss_item("native-start", "AI 窗口开始", published_at=start)
        + _rss_item("native-middle", "AI 窗口内部", published_at=end - timedelta(hours=1))
        + _rss_item("native-unknown", "AI 未知发布时间")
        + (
            "<item><title>AI 无 GUID</title>"
            "<link>https://news.google.com/articles/native-fallback</link></item>"
        )
        + _rss_item("native-before", "AI 窗口之前", published_at=start - timedelta(seconds=1))
        + _rss_item("native-end", "AI 窗口结束", published_at=end)
        + _rss_item("native-unrelated", "普通新闻", published_at=end - timedelta(hours=1))
        + "</channel></rss>"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.url.scheme == "https"
        assert request.url.host == "news.google.com"
        assert request.url.path == "/rss/search"
        assert dict(request.url.params) == {
            "q": "AI",
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        }
        return httpx.Response(upstream_status, text=feed)

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
        raise AssertionError("Google News Kafka job message was not delivered")

    try:
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'Google News replay', 'paused', "
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
            session.add(
                ContentRecord(
                    id=uuid4(),
                    owner_id=owner_id,
                    source_key="google_news",
                    object_type="post",
                    native_scope=None,
                    external_id="native-start",
                    identity_basis=None,
                    created_at=end,
                )
            )
            applied = SourcePresetService(session, clock=lambda: end).apply_in_transaction(
                owner_id=owner_id, preset=GOOGLE_NEWS_PRESET
            )
            ResourceBudgetService(session, clock=lambda: end).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.plan035.kafka.daily",
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
                    _google_news_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=1,
                        start=start,
                        end=end,
                    )
                ),
            )

        admin.create_topics([NewTopic(kafka_topic, 1, 1)])[kafka_topic].result(10)
        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            component_key="collector.google_news",
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: RssSourceAdapter(
                source_key="google_news",
                feed_url_template=(
                    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
                ),
                allowed_hosts=frozenset({"news.google.com"}),
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
            worker_id="google-news-kafka-test",
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
        first_consumer.close()  # Force the same Kafka offset to be delivered again.
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
                    _google_news_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=2,
                        start=start,
                        end=end,
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

        with sessions() as session:
            jobs = [session.get(Job, job_id) for job_id in (first_job.id, second_job.id)]
            assert all(job is not None for job in jobs)
            assert [(job.status, job.requests_sent, job.items_saved) for job in jobs] == [
                ("partially_succeeded", 1, 4),
                ("partially_succeeded", 1, 4),
            ]
            assert [job.checkpoint["collection.observed_count"] for job in jobs] == [7, 7]
            assert [job.checkpoint["collection.source_feed_updated_at"] for job in jobs] == [
                feed_updated_at.isoformat(),
                feed_updated_at.isoformat(),
            ]
            assert session.execute(
                select(ContentRecord.external_id, ContentRecord.identity_basis)
                .where(ContentRecord.owner_id == owner_id)
                .order_by(ContentRecord.external_id)
            ).all() == [
                ("native-middle", "guid"),
                ("native-start", "guid"),
                ("native-unknown", "guid"),
                ("url:https://news.google.com/articles/native-fallback", "url_fallback"),
            ]
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentDiscovery)
                    .where(ContentDiscovery.owner_id == owner_id)
                )
                == 8
            )
            assert session.execute(
                select(ContentObservation.published_at)
                .join(ContentRecord, ContentRecord.id == ContentObservation.content_id)
                .where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.external_id == "native-unknown",
                )
            ).scalars().all() == [None, None]
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
                (2, "partial", "unverified_terminal", 1),
            ]
            assert session.execute(
                text(
                    "SELECT p.budget_key, w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id = w.budget_policy_id "
                    "WHERE p.owner_id = :owner_id ORDER BY p.budget_key"
                ),
                {"owner_id": owner_id},
            ).all() == [
                ("global.plan035.kafka.daily", 2),
                ("source.google_news.network.daily", 2),
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

        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 3, :owner_id, '[\"AI\"]', '[]', '[]', :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": end},
            )
            session.execute(
                text("UPDATE monitor_topics SET current_version = 3 WHERE id = :id"),
                {"id": topic_id},
            )
            truncated_job = JobService(session, clock=lambda: end).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(
                    _google_news_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=3,
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
        truncated_message = next_message(second_consumer)
        handler(truncated_message)
        second_consumer.commit(message=truncated_message, asynchronous=False)
        assert len(requested) == 3
        with sessions() as session:
            job = session.get(Job, truncated_job.id)
            assert job is not None
            assert (job.status, job.requests_sent, job.items_saved) == ("partially_succeeded", 1, 2)
            assert job.checkpoint["collection.observed_count"] == 2
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == truncated_job.id)
            )
            assert coverage is not None
            assert (coverage.status, coverage.stop_reason, coverage.page_count) == (
                "partial",
                "budget_exhausted",
                1,
            )
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentRecord)
                    .where(ContentRecord.owner_id == owner_id)
                )
                == 4
            )
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentDiscovery)
                    .where(ContentDiscovery.owner_id == owner_id)
                )
                == 10
            )
            assert session.execute(
                text(
                    "SELECT p.budget_key, w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id = w.budget_policy_id "
                    "WHERE p.owner_id = :owner_id ORDER BY p.budget_key"
                ),
                {"owner_id": owner_id},
            ).all() == [
                ("global.plan035.kafka.daily", 3),
                ("source.google_news.network.daily", 3),
            ]

        upstream_status = 503
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 4, :owner_id, '[\"AI\"]', '[]', '[]', :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": end},
            )
            session.execute(
                text("UPDATE monitor_topics SET current_version = 4 WHERE id = :id"),
                {"id": topic_id},
            )
            failed_job = JobService(session, clock=lambda: end).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(
                    _google_news_run(
                        topic_id=topic_id,
                        connection_id=applied.connection_id,
                        connection_version=applied.connection_version,
                        version=4,
                        start=start,
                        end=end,
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
        failure_message = next_message(second_consumer)
        handler(failure_message)
        second_consumer.commit(message=failure_message, asynchronous=False)
        assert len(requested) == 4
        with sessions() as session:
            job = session.get(Job, failed_job.id)
            assert job is not None
            assert (job.status, job.requests_sent, job.items_saved) == ("failed", 1, 0)
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == failed_job.id)
            )
            assert coverage is not None
            assert (coverage.status, coverage.stop_reason, coverage.page_count) == (
                "partial",
                "upstream_error",
                1,
            )
            assert (
                session.scalar(
                    select(text("count(*)"))
                    .select_from(ContentRecord)
                    .where(ContentRecord.owner_id == owner_id)
                )
                == 4
            )
            assert session.execute(
                text(
                    "SELECT p.budget_key, w.used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id = w.budget_policy_id "
                    "WHERE p.owner_id = :owner_id ORDER BY p.budget_key"
                ),
                {"owner_id": owner_id},
            ).all() == [
                ("global.plan035.kafka.daily", 4),
                ("source.google_news.network.daily", 4),
            ]
    finally:
        for consumer in consumers:
            consumer.close()
        with suppress(Exception):
            admin.delete_topics([kafka_topic], operation_timeout=10)[kafka_topic].result(10)
        engine.dispose()
