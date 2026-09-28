from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from confluent_kafka import Consumer, Message, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_monitor_topics import _TRUNCATE

from connections.presets import (
    BILIBILI_PRESET,
    GOOGLE_NEWS_PRESET,
    HACKERNEWS_PRESET,
    NEWS_SEARCH_PRESET,
    SOURCE_PRESETS,
)
from connections.services import SourcePresetService
from content.discovery import (
    KeywordDiscoveryPageCommitService,
    KeywordRequestMeter,
    plan_keyword_discovery,
    plan_single_keyword_discovery,
)
from content.discovery_execution import KeywordDiscoveryExecutor
from content.hotlist_execution import HotlistExecutor
from content.models import ContentDiscovery, ContentRecord
from content.schemas import KeywordDiscoveryRunInput
from content.services import ContentService
from core.config import Settings
from core.errors import ApplicationError
from jobs.cursor import plan_cursor_request
from jobs.execution import (
    CheckpointConflictError,
    JobCompletion,
    JobExecutionFailure,
    JobExecutionService,
    MessageReference,
    StaleExecutionLeaseError,
)
from jobs.models import CoverageWindow, Job, OutboxMessage
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
    CoverageWindowInput,
    JobAcceptedMessage,
    JobFailureCategory,
    JobRetryScheduledMessage,
    JobStatus,
)
from jobs.services import (
    JOB_ACCEPTED_TOPIC,
    CoverageWindowService,
    JobService,
    OutboxService,
    ResourceBudgetService,
)
from monitors.runs import MonitorTopicRunService
from monitors.schemas import MonitorTopicRunInput
from monitors.services import MonitorTopicService, evaluate_monitor_rules
from sources.adapters.hackernews import HackerNewsAdapter
from sources.adapters.mediacrawler import MediaCrawlerAdapter
from sources.adapters.rss import RssSourceAdapter
from sources.adapters.rsshub_hotlist import RsshubHotlistAdapter
from sources.adapters.web_search import WebSearchAdapter
from sources.contracts import (
    CommentsRequest,
    SearchRequest,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceSort,
    SourceStopReason,
)
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import MessageDeferredError, create_producer, process_message, publish_outbox
from worker.scheduler import enqueue_due_hotlists_in_transaction


@pytest.mark.parametrize("live", [False, True], ids=["controlled", "live"])
def test_google_news_window_version_and_repeat_scan(live: bool) -> None:
    if live and os.getenv("HOTKEY_TEST_LIVE_GOOGLE_NEWS") != "1":
        pytest.skip("HOTKEY_TEST_LIVE_GOOGLE_NEWS=1 requires actual Google News RSS")
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=1)
    keyword = "AI"
    feed = f"""<rss version="2.0"><channel><title>AI news</title>
    <item><title>AI at start</title><guid>google-start</guid><link>https://news.google.com/articles/start</link>
    <pubDate>{start.strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate></item>
    <item><title>AI without date</title><link>https://news.google.com/articles/unknown</link></item>
    <item><title>AI at end</title><guid>google-end</guid><link>https://news.google.com/articles/end</link>
    <pubDate>{now.strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate></item>
    <item><title>Other topic</title><guid>google-other</guid><link>https://news.google.com/articles/other</link></item>
    <item><title>AI duplicate</title><guid>google-start</guid><link>https://news.google.com/articles/duplicate</link></item>
    </channel></rss>"""
    requested: list[httpx.Request] = []
    completed: list[UUID] = []

    def response(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        assert request.url.host == "news.google.com"
        return httpx.Response(200, text=feed)

    def execute(job_id: UUID) -> None:
        with sessions() as session:
            lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=job_id, worker_id="google-news-test"
            )
        message = _accepted_message(engine, job_id)
        renewed, completion = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: RssSourceAdapter(
                source_key="google_news",
                feed_url_template=str(GOOGLE_NEWS_PRESET.config["feed_url_template"]),
                allowed_hosts=frozenset({"news.google.com"}),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=None if live else httpx.MockTransport(response),
            ),
        ).execute(message, lease)
        assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
        with sessions() as session:
            JobExecutionService(session, lease_seconds=60).complete(
                renewed,
                message=MessageReference(
                    message_id=message.message_id,
                    topic="hotkey.tests.google-news",
                    partition=0,
                    offset=len(completed),
                ),
                completion=completion,
            )
        completed.append(job_id)

    try:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"google-news-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=GOOGLE_NEWS_PRESET
            )
            ResourceBudgetService(session).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.google-news-test-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=3,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) "
                    "VALUES (:id, :owner_id, 'Google News test', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"AI\"]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key="google_news",
                connection_id=preset.connection_id,
                connection_version=preset.connection_version,
                primary_query=keyword,
                starts_at=start,
                ends_at=now,
                page_size=100,
                latest_max_pages=1,
                latest_max_requests=2,
                top_max_pages=1,
                top_max_requests=2,
                max_seconds=90,
            )
            first = JobService(session).accept_in_transaction(
                owner_id=owner_id, command=plan_single_keyword_discovery(run)
            )
            session.execute(
                text("UPDATE monitor_topics SET current_version = 2 WHERE id = :id"),
                {"id": topic_id},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 2, :owner_id, '[\"unmatched-token\"]'::jsonb, "
                    "'[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
        execute(first.id)
        with sessions() as session:
            first_ids = set(
                session.scalars(
                    text(
                        "SELECT record.external_id FROM content_records AS record "
                        "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                        "WHERE discovery.job_id = :job_id"
                    ),
                    {"job_id": first.id},
                ).all()
            )
            job = session.get(Job, first.id)
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == first.id)
            )
            assert job is not None and coverage is not None
            assert (job.requests_sent, coverage.page_count, coverage.status) == (1, 1, "partial")
            assert coverage.stop_reason == "unverified_terminal"
            assert job.items_saved == len(first_ids)
            assert len(first_ids) > 0
            sample = session.execute(
                text(
                    "SELECT observation.canonical_url, observation.observed_at, "
                    "observation.content_version_id, discovery.first_observed_at, "
                    "record.external_id FROM content_records AS record "
                    "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                    "JOIN content_observations AS observation "
                    "ON observation.content_id = record.id "
                    "AND observation.job_id = discovery.job_id "
                    "WHERE discovery.job_id = :job_id "
                    "ORDER BY record.external_id LIMIT 1"
                ),
                {"job_id": first.id},
            ).one()
            assert sample.canonical_url is not None
            assert sample.content_version_id is not None
            assert sample.observed_at == sample.first_observed_at
            if not live:
                assert first_ids == {"google-start", "url:https://news.google.com/articles/unknown"}
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM resource_usage_attempts "
                        "WHERE operation_id = :operation_id"
                    ),
                    {"operation_id": job.operation_id},
                )
                == 1
            )
        with sessions.begin() as session:
            second = JobService(session).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(run.model_copy(update={"run_id": uuid4()})),
            )
        execute(second.id)
        with sessions() as session:
            repeated_ids = set(
                session.scalars(
                    text(
                        "SELECT record.external_id FROM content_records AS record "
                        "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                        "WHERE discovery.job_id = :job_id"
                    ),
                    {"job_id": second.id},
                ).all()
            )
            assert first_ids & repeated_ids
            assert session.scalar(
                text(
                    "SELECT count(*) FROM content_records WHERE owner_id = :owner_id "
                    "AND source_key = 'google_news' AND external_id = ANY(:ids)"
                ),
                {"owner_id": owner_id, "ids": list(first_ids & repeated_ids)},
            ) == len(first_ids & repeated_ids)
        if not live:
            assert len(requested) == 2
            with sessions.begin() as session:
                denied = JobService(session).accept_in_transaction(
                    owner_id=owner_id,
                    command=plan_single_keyword_discovery(
                        run.model_copy(update={"run_id": uuid4()})
                    ),
                )
            with sessions() as session:
                denied_lease = JobExecutionService(session, lease_seconds=60).acquire(
                    job_id=denied.id, worker_id="google-news-denied"
                )
            denied_requests: list[httpx.Request] = []

            def redirect(request: httpx.Request) -> httpx.Response:
                denied_requests.append(request)
                return httpx.Response(
                    302, headers={"location": "https://outside.example.com/forbidden"}
                )

            with pytest.raises(JobExecutionFailure) as denied_error:
                KeywordDiscoveryExecutor(
                    sessions,
                    lease_seconds=60,
                    adapter_factory=lambda before, cancelled, max_requests, max_seconds: (
                        RssSourceAdapter(
                            source_key="google_news",
                            feed_url_template=str(GOOGLE_NEWS_PRESET.config["feed_url_template"]),
                            allowed_hosts=frozenset({"news.google.com"}),
                            before_request=before,
                            cancelled=cancelled,
                            max_requests=max_requests,
                            max_seconds=max_seconds,
                            transport=httpx.MockTransport(redirect),
                        )
                    ),
                ).execute(_accepted_message(engine, denied.id), denied_lease)
            assert denied_error.value.error_code == "source_access_denied"
            assert len(denied_requests) == 1
            with sessions() as session:
                denied_job = session.get(Job, denied.id)
                denied_coverage = session.scalar(
                    select(CoverageWindow).where(CoverageWindow.last_job_id == denied.id)
                )
                assert denied_job is not None and denied_coverage is not None
                assert (denied_job.requests_sent, denied_coverage.stop_reason) == (
                    1,
                    "access_denied",
                )
            with sessions.begin() as session:
                exhausted = JobService(session).accept_in_transaction(
                    owner_id=owner_id,
                    command=plan_single_keyword_discovery(
                        run.model_copy(update={"run_id": uuid4()})
                    ),
                )
            execute(exhausted.id)
            with sessions() as session:
                exhausted_job = session.get(Job, exhausted.id)
                exhausted_coverage = session.scalar(
                    select(CoverageWindow).where(CoverageWindow.last_job_id == exhausted.id)
                )
                assert exhausted_job is not None and exhausted_coverage is not None
                assert (exhausted_job.requests_sent, exhausted_coverage.stop_reason) == (
                    0,
                    "budget_exhausted",
                )
                assert session.scalar(
                    text(
                        "SELECT count(*) FROM content_records WHERE owner_id = :owner_id "
                        "AND source_key = 'google_news'"
                    ),
                    {"owner_id": owner_id},
                ) == len(first_ids)
            assert len(requested) == 2
        print(
            "Google News:",
            "live" if live else "controlled",
            first.id,
            second.id,
            len(first_ids),
            len(repeated_ids),
            sample.observed_at.isoformat(),
            sample.external_id,
            sample.canonical_url,
            sample.content_version_id,
        )
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def test_searxng_two_scans_keep_identity_and_failed_page_gap() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    requested: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        assert request.url.host == "127.0.0.1"
        assert request.url.params["engines"] == "duckduckgo news"
        if request.url.params["pageno"] == "2":
            return httpx.Response(
                200,
                json={
                    "query": "AI",
                    "results": [],
                    "unresponsive_engines": [["duckduckgo news", "TimeoutException"]],
                },
            )
        tracking = "first" if len(requested) <= 2 else "second"
        return httpx.Response(
            200,
            json={
                "query": "AI",
                "results": [
                    {
                        "url": f"https://example.com/ai?topic=go&utm_source={tracking}",
                        "title": "AI current",
                        "content": "AI summary",
                        "publishedDate": (now - timedelta(hours=1)).isoformat(),
                        "engine": "duckduckgo news",
                    },
                    {
                        "url": "https://example.com/old",
                        "title": "AI old",
                        "publishedDate": (now - timedelta(days=2)).isoformat(),
                        "engine": "duckduckgo news",
                    },
                    {
                        "url": "https://example.com/unknown?topic=ai",
                        "title": "AI without date",
                        "engine": "duckduckgo news",
                    },
                ],
                "unresponsive_engines": [],
            },
        )

    def execute(job_id: UUID, offset: int) -> None:
        with sessions() as session:
            lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=job_id, worker_id="searxng-test"
            )
        message = _accepted_message(engine, job_id)
        renewed, completion = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: WebSearchAdapter(
                source_key="news_search",
                base_url="http://127.0.0.1:8888",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(response),
            ),
        ).execute(message, lease)
        assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
        with sessions() as session:
            JobExecutionService(session, lease_seconds=60).complete(
                renewed,
                message=MessageReference(
                    message_id=message.message_id,
                    topic="hotkey.tests.searxng",
                    partition=0,
                    offset=offset,
                ),
                completion=completion,
            )

    try:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"searxng-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=NEWS_SEARCH_PRESET
            )
            ResourceBudgetService(session).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.searxng-test-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=4,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'SearXNG test', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"AI\"]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key="news_search",
                connection_id=preset.connection_id,
                connection_version=preset.connection_version,
                primary_query="AI",
                starts_at=now - timedelta(days=1),
                ends_at=now,
                page_size=100,
                latest_max_pages=2,
                latest_max_requests=2,
                top_max_pages=1,
                top_max_requests=1,
                max_seconds=90,
            )
            first = JobService(session).accept_in_transaction(
                owner_id=owner_id, command=plan_single_keyword_discovery(run)
            )
        execute(first.id, 0)
        with sessions.begin() as session:
            second = JobService(session).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(run.model_copy(update={"run_id": uuid4()})),
            )
        execute(second.id, 1)
        with sessions() as session:
            rows = session.execute(
                text(
                    "SELECT record.id, record.external_id, observation.canonical_url, "
                    "observation.published_at, discovery.first_observed_at, "
                    "discovery.job_id FROM content_records AS record "
                    "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                    "JOIN content_observations AS observation "
                    "ON observation.content_id = record.id "
                    "AND observation.job_id = discovery.job_id "
                    "WHERE record.owner_id = :owner_id AND record.source_key = 'news_search' "
                    "ORDER BY discovery.job_id, record.external_id"
                ),
                {"owner_id": owner_id},
            ).all()
            jobs = [session.get(Job, job_id) for job_id in (first.id, second.id)]
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == second.id)
            )
            assert len(rows) == 4
            assert len({row.id for row in rows}) == 2
            assert {row.canonical_url for row in rows} == {
                "https://example.com/ai?topic=go",
                "https://example.com/unknown?topic=ai",
            }
            assert sum(row.published_at is None for row in rows) == 2
            assert all(row.first_observed_at is not None for row in rows)
            assert all(job is not None and job.requests_sent == 2 for job in jobs)
            assert all(
                job is not None
                and job.checkpoint["source.engine"] == "duckduckgo news"
                and job.checkpoint["source.diagnostic"] == "engine_timeout"
                and job.checkpoint["cursor.pages"] == 2
                for job in jobs
            )
            assert coverage is not None
            assert (coverage.page_count, coverage.stop_reason) == (4, "upstream_error")
        assert [request.url.params["pageno"] for request in requested] == ["1", "2", "1", "2"]
        with sessions.begin() as session:
            exhausted = JobService(session).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(run.model_copy(update={"run_id": uuid4()})),
            )
        execute(exhausted.id, 2)
        with sessions() as session:
            exhausted_job = session.get(Job, exhausted.id)
            assert exhausted_job is not None
            assert (exhausted_job.requests_sent, exhausted_job.items_saved) == (0, 0)
        assert len(requested) == 4
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def test_36kr_newsflashes_rules_empty_failure_and_repeat_scan() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=1)
    hotlist_due_at = datetime.fromtimestamp((int(now.timestamp()) // 1800) * 1800, UTC)
    requested: list[httpx.Request] = []
    build_date = (now - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    published = (now - timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    old = (now - timedelta(days=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    feed = f"""<rss version="2.0"><channel><title>36Kr 快讯</title>
    <lastBuildDate>{build_date}</lastBuildDate>
    <item><title>AI AI 发布</title><guid>https://www.36kr.com/newsflashes/one</guid>
    <link>https://www.36kr.com/newsflashes/one</link>
    <pubDate>{published}</pubDate><description>今日进展</description></item>
    <item><title>daily 发布</title><guid>https://www.36kr.com/newsflashes/daily</guid>
    <link>https://www.36kr.com/newsflashes/daily</link></item>
    <item><title>人工智能 发布招聘</title>
    <guid>https://www.36kr.com/newsflashes/excluded</guid>
    <link>https://www.36kr.com/newsflashes/excluded</link></item>
    <item><title>新产品发布</title><guid>https://www.36kr.com/newsflashes/two</guid>
    <link>https://www.36kr.com/newsflashes/two</link>
    <description>人工智能落地</description></item>
    <item><title>AI 发布旧闻</title><guid>https://www.36kr.com/newsflashes/old</guid>
    <link>https://www.36kr.com/newsflashes/old</link><pubDate>{old}</pubDate></item>
    <item><title>AI 重复</title><guid>https://www.36kr.com/newsflashes/one</guid>
    <link>https://www.36kr.com/newsflashes/duplicate</link></item>
    </channel></rss>"""
    empty_feed = "<rss version='2.0'><channel><title>36Kr 空快讯</title></channel></rss>"
    run: KeywordDiscoveryRunInput | None = None

    def execute(xml: str, *, version: int = 1, status: int = 200, fail: bool = False) -> UUID:
        assert run is not None
        with sessions.begin() as session:
            accepted = JobService(session).accept_in_transaction(
                owner_id=owner_id,
                command=plan_single_keyword_discovery(
                    run.model_copy(update={"run_id": uuid4(), "configuration_version": version})
                ),
            )
        with sessions() as session:
            lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=accepted.id, worker_id="rss-36kr-test"
            )
        message = _accepted_message(engine, accepted.id)

        def response(request: httpx.Request) -> httpx.Response:
            requested.append(request)
            assert request.url.path == "/36kr/newsflashes"
            assert "q" not in request.url.params
            return httpx.Response(status, text=xml)

        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: RssSourceAdapter(
                source_key="rss_36kr",
                feed_url_template="http://127.0.0.1:1200/36kr/newsflashes",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(response),
            ),
        )
        if fail:
            with pytest.raises(JobExecutionFailure) as captured:
                executor.execute(message, lease)
            assert captured.value.error_code == "source_upstream_unavailable"
        else:
            renewed, completion = executor.execute(message, lease)
            assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
            with sessions() as session:
                JobExecutionService(session, lease_seconds=60).complete(
                    renewed,
                    message=MessageReference(
                        message_id=message.message_id,
                        topic="hotkey.tests.rss-36kr",
                        partition=0,
                        offset=len(requested) - 1,
                    ),
                    completion=completion,
                )
        return accepted.id

    try:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"rss-36kr-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=SOURCE_PRESETS["rss_36kr"]
            )
            hotlist = SourcePresetService(
                session, clock=lambda: hotlist_due_at - timedelta(seconds=1)
            ).apply_in_transaction(owner_id=owner_id, preset=SOURCE_PRESETS["hotlist_36kr"])
            assert preset.connection_id != hotlist.connection_id
            ResourceBudgetService(session).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.rss-36kr-test-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, '36Kr 快讯测试', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    'VALUES (:id, 1, :owner_id, \'["AI","人工智能"]\'::jsonb, '
                    "'[\"发布\"]'::jsonb, '[\"招聘\"]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key="rss_36kr",
                connection_id=preset.connection_id,
                connection_version=preset.connection_version,
                primary_query="AI",
                starts_at=start,
                ends_at=now,
                page_size=100,
                latest_max_pages=1,
                latest_max_requests=1,
                top_max_pages=1,
                top_max_requests=1,
                max_seconds=90,
            )
        first = execute(feed)
        second = execute(feed)
        with sessions.begin() as session:
            session.execute(
                text("UPDATE monitor_topics SET current_version = 2 WHERE id = :id"),
                {"id": topic_id},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 2, :owner_id, '[\"unmatched-token\"]'::jsonb, "
                    "'[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
        no_match = execute(feed, version=2)
        with sessions.begin() as session:
            session.execute(
                text("UPDATE monitor_topics SET current_version = 1 WHERE id = :id"),
                {"id": topic_id},
            )
        empty = execute(empty_feed)
        failed = execute(empty_feed, status=503, fail=True)
        with sessions() as session:
            failure_coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == failed)
            )
            assert failure_coverage is not None
            assert failure_coverage.stop_reason == "upstream_error"
        recovered = execute(feed)
        with sessions.begin() as session:
            assert enqueue_due_hotlists_in_transaction(session, now) == 1
        with sessions() as session:
            hotlist_job_id = session.scalar(
                text(
                    "SELECT job_id FROM collection_due_windows "
                    "WHERE owner_id = :owner_id AND source_key = 'hotlist_36kr' "
                    "AND due_at = :due_at"
                ),
                {"owner_id": owner_id, "due_at": hotlist_due_at},
            )
            assert hotlist_job_id is not None
            hotlist_lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=hotlist_job_id, worker_id="hotlist-36kr-isolation"
            )
        hotlist_message = _accepted_message(engine, hotlist_job_id)

        def hotlist_response(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/36kr/hot-list"
            return httpx.Response(
                200,
                text=(
                    "<rss version='2.0'><channel><title>36Kr 榜</title>"
                    "<item><title>AI 发布</title>"
                    "<link>https://www.36kr.com/newsflashes/one</link>"
                    "</item></channel></rss>"
                ),
            )

        hotlist_renewed, hotlist_completion = HotlistExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda source_key, feed_url, allowed_hosts, before, cancelled: (
                RsshubHotlistAdapter(
                    source_key=source_key,
                    feed_url=feed_url,
                    allowed_hosts=allowed_hosts,
                    before_request=before,
                    cancelled=cancelled,
                    transport=httpx.MockTransport(hotlist_response),
                )
            ),
        ).execute(hotlist_message, hotlist_lease)
        assert hotlist_completion.status is JobStatus.SUCCEEDED
        with sessions() as session:
            JobExecutionService(session, lease_seconds=60).complete(
                hotlist_renewed,
                message=MessageReference(
                    message_id=hotlist_message.message_id,
                    topic="hotkey.tests.hotlist-36kr",
                    partition=0,
                    offset=0,
                ),
                completion=hotlist_completion,
            )
        with sessions() as session:
            jobs = {
                key: session.get(Job, job_id)
                for key, job_id in {
                    "first": first,
                    "second": second,
                    "no_match": no_match,
                    "empty": empty,
                    "failed": failed,
                    "recovered": recovered,
                }.items()
            }
            assert all(job is not None for job in jobs.values())
            assert [jobs[key].requests_sent for key in jobs] == [1] * 6
            assert [jobs[key].items_saved for key in jobs] == [2, 2, 0, 0, 0, 2]
            assert jobs["first"].checkpoint["collection.observed_count"] == 5
            assert jobs["no_match"].checkpoint["collection.observed_count"] == 5
            assert jobs["empty"].checkpoint["collection.observed_count"] == 0
            assert (
                jobs["first"].checkpoint["source.feed_updated_at"]
                == (now - timedelta(minutes=5)).isoformat()
            )
            assert jobs["failed"].checkpoint["cursor.pages"] == 1
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM content_records WHERE owner_id = :owner_id "
                        "AND source_key = 'rss_36kr'"
                    ),
                    {"owner_id": owner_id},
                )
                == 2
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_discoveries WHERE owner_id = :owner_id"),
                    {"owner_id": owner_id},
                )
                == 6
            )
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM resource_budget_policies "
                        "WHERE owner_id = :owner_id AND budget_key IN "
                        "('source.rss_36kr.network.daily', 'source.hotlist_36kr.network.daily')"
                    ),
                    {"owner_id": owner_id},
                )
                == 2
            )
            source_usage = dict(
                session.execute(
                    text(
                        "SELECT policy.budget_key, sum(reservation.actual_units) "
                        "FROM resource_budget_reservations AS reservation "
                        "JOIN resource_budget_policies AS policy "
                        "ON policy.id = reservation.budget_policy_id "
                        "WHERE policy.owner_id = :owner_id "
                        "AND policy.budget_key IN "
                        "('source.rss_36kr.network.daily', 'source.hotlist_36kr.network.daily') "
                        "GROUP BY policy.budget_key"
                    ),
                    {"owner_id": owner_id},
                ).all()
            )
            assert source_usage == {
                "source.rss_36kr.network.daily": 6,
                "source.hotlist_36kr.network.daily": 1,
            }
            assert (
                session.scalar(
                    text(
                        "SELECT entry_count FROM hotlist_snapshots "
                        "WHERE owner_id = :owner_id AND job_id = :job_id"
                    ),
                    {"owner_id": owner_id, "job_id": hotlist_job_id},
                )
                == 1
            )
        assert len(requested) == 6
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


@pytest.mark.parametrize("source_key", ["google_news", "news_search", "rss_36kr"])
def test_news_search_kafka_redelivery_keeps_one_persisted_observation(
    source_key: str,
) -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    bootstrap = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if database_url is None or bootstrap is None:
        pytest.skip("isolated PostgreSQL and Kafka endpoints are required")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    kafka_topic = f"hotkey.tests.{source_key}.{uuid4().hex}"
    group_id = f"hotkey-{source_key}-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    consumer_first: Consumer | None = None
    consumer_second: Consumer | None = None
    created_topic = False
    requested: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        if source_key == "news_search":
            return httpx.Response(
                200,
                json={
                    "query": "AI",
                    "results": [
                        {
                            "url": "https://example.com/ai-kafka?topic=go&utm_source=search",
                            "title": "AI Kafka",
                            "engine": "duckduckgo news",
                        }
                    ],
                    "unresponsive_engines": [],
                },
            )
        if source_key == "rss_36kr":
            return httpx.Response(
                200,
                text=(
                    "<rss version='2.0'><channel><title>36Kr 快讯</title><item>"
                    "<title>AI Kafka</title>"
                    "<guid>https://www.36kr.com/newsflashes/kafka-one</guid>"
                    "<link>https://www.36kr.com/newsflashes/kafka-one</link>"
                    "</item></channel></rss>"
                ),
            )
        return httpx.Response(
            200,
            text=(
                "<rss version='2.0'><channel><title>AI</title><item>"
                "<title>AI Kafka</title><guid>google-kafka-one</guid>"
                "<link>https://news.google.com/articles/kafka-one</link>"
                "</item></channel></rss>"
            ),
        )

    def new_consumer() -> Consumer:
        return Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": group_id,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
                "session.timeout.ms": 6_000,
            }
        )

    def receive(consumer: Consumer) -> Message:
        consumer.subscribe([kafka_topic])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = consumer.poll(0.2)
            if message is None:
                continue
            if message.error() is not None:
                raise RuntimeError(str(message.error()))
            return message
        raise AssertionError(f"{source_key} Kafka message was not received")

    try:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"{source_key}-kafka-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id,
                preset=SOURCE_PRESETS[source_key],
            )
            ResourceBudgetService(session).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key=f"global.{source_key}-kafka-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'Google Kafka', 'paused', "
                    "'pending_source_selection', 1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"AI\"]'::jsonb, '[]'::jsonb, '[]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key=source_key,
                connection_id=preset.connection_id,
                connection_version=preset.connection_version,
                primary_query="AI",
                starts_at=now - timedelta(days=1),
                ends_at=now,
                page_size=100,
                latest_max_pages=1,
                latest_max_requests=2,
                top_max_pages=1,
                top_max_requests=2,
                max_seconds=90,
            )
            job = JobService(session).accept_in_transaction(
                owner_id=owner_id, command=plan_single_keyword_discovery(run)
            )
        with sessions.begin() as session:
            session.execute(
                text("UPDATE outbox_messages SET topic = :topic WHERE aggregate_id = :job_id"),
                {"topic": kafka_topic, "job_id": job.id},
            )
        admin.create_topics([NewTopic(kafka_topic, num_partitions=1, replication_factor=1)])[
            kafka_topic
        ].result(10)
        created_topic = True

        def adapter_factory(
            before: Callable[[int], bool],
            cancelled: Callable[[], bool],
            max_requests: int,
            max_seconds: float,
        ) -> RssSourceAdapter | WebSearchAdapter:
            if source_key == "news_search":
                return WebSearchAdapter(
                    source_key=source_key,
                    base_url="http://127.0.0.1:8888",
                    allowed_hosts=frozenset({"127.0.0.1"}),
                    before_request=before,
                    cancelled=cancelled,
                    max_requests=max_requests,
                    max_seconds=max_seconds,
                    transport=httpx.MockTransport(response),
                )
            rss_preset = SOURCE_PRESETS[source_key]
            return RssSourceAdapter(
                source_key=source_key,
                feed_url_template=str(rss_preset.config["feed_url_template"]),
                allowed_hosts=frozenset(rss_preset.config["allowed_hosts"]),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(response),
            )

        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=adapter_factory,
        )

        def collect(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        handler = create_job_message_handler(
            sessions,
            {"keyword.search": collect},
            worker_id="google-kafka-test",
            lease_seconds=60,
        )
        producer = create_producer(
            Settings(
                database_url=database_url,
                kafka_bootstrap_servers=bootstrap,
                kafka_delivery_timeout_seconds=10,
            )
        )
        with sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(producer, envelope, timeout_seconds=10)
                )
                == 1
            )

        consumer_first = new_consumer()
        first_message = receive(consumer_first)
        handler(first_message)
        first_offset = first_message.offset()
        consumer_first.close()
        consumer_first = None

        consumer_second = new_consumer()
        repeated_message = receive(consumer_second)
        assert repeated_message.offset() == first_offset
        process_message(consumer_second, repeated_message, {kafka_topic: handler})
        committed = consumer_second.committed([TopicPartition(kafka_topic, 0)], timeout=5)
        assert committed[0].offset == first_offset + 1
        with sessions() as session:
            persisted = session.get(Job, job.id)
            assert persisted is not None
            assert (persisted.requests_sent, persisted.items_saved) == (1, 1)
            assert (
                session.scalar(
                    text("SELECT count(*) FROM processed_messages WHERE job_id = :job_id"),
                    {"job_id": job.id},
                )
                == 1
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_discoveries WHERE job_id = :job_id"),
                    {"job_id": job.id},
                )
                == 1
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_observations WHERE job_id = :job_id"),
                    {"job_id": job.id},
                )
                == 1
            )
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM resource_usage_attempts "
                        "WHERE operation_id = :operation_id"
                    ),
                    {"operation_id": persisted.operation_id},
                )
                == 1
            )
        assert len(requested) == 1
    finally:
        if consumer_first is not None:
            consumer_first.close()
        if consumer_second is not None:
            consumer_second.close()
        if created_topic:
            admin.delete_topics([kafka_topic])[kafka_topic].result(10)
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def test_job_execution_failure_allows_traceback_assignment() -> None:
    failure = JobExecutionFailure(
        error_code="search_policy_unavailable",
        category=JobFailureCategory.CONFIGURATION_UNAVAILABLE,
        occurred_at=datetime.now(UTC),
        next_action="配置预算政策后重试",
    )
    failure.__traceback__ = None


def test_bilibili_saved_search_output_commits_posts_and_cached_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay the five-video/two-comment JSONL shape without launching a browser."""
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    owner_id, connection_id, topic_id, policy_id, retention_id = (uuid4() for _ in range(5))
    now = datetime.now(UTC)
    start, end = now - timedelta(days=1), now
    videos = (
        ("117335704734360", "Claude DeepSeek", "公开视频简介", 1790401149),
        ("117335721579544", "DeepSeek 折叠屏", "", 1790401063),
        ("117335687959822", "DeepSeek 小说", "-", 1790400547),
        ("117335688023302", "deepseek 心得", "公开视频正文", 1790400534),
        ("117335671180288", "万众瞩目大肥鱼", "公开视频描述", 1790400393),
    )
    comments = (
        (videos[0][0], "318652179920"),
        (videos[1][0], "318651673424"),
    )
    output = tmp_path / "output"
    crawler = tmp_path / "crawler"
    crawler.mkdir()
    run = KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref=f"topic:{topic_id}",
        configuration_version=1,
        source_key="bilibili",
        connection_id=connection_id,
        connection_version=1,
        primary_query="DeepSeek",
        starts_at=start,
        ends_at=end,
        page_size=5,
        latest_max_pages=1,
        latest_max_requests=26,
        top_max_pages=1,
        top_max_requests=26,
        max_seconds=220,
    )
    command = plan_keyword_discovery(run)[0]

    def replay(_self: MediaCrawlerAdapter, _request: SearchRequest, run_dir: Path) -> None:
        jsonl = run_dir / "bili" / "jsonl"
        jsonl.mkdir(parents=True)
        (jsonl / "search_contents_fixture.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "video_id": video_id,
                        "video_url": f"https://www.bilibili.com/video/av{video_id}",
                        "title": title,
                        "desc": description,
                        "create_time": int(now.timestamp()) - (1790401149 - published),
                        "creator_hash": f"author-{video_id}",
                        "nickname": "作者",
                        "liked_count": "1",
                        "video_play_count": "2",
                        "video_comment": "1",
                        "video_share_count": "0",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for video_id, title, description, published in videos
            ),
            encoding="utf-8",
        )
        (jsonl / "search_comments_fixture.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "video_id": video_id,
                        "comment_id": comment_id,
                        "parent_comment_id": "0",
                        "create_time": int(now.timestamp()),
                        "content": "一级评论",
                        "like_count": 0,
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for video_id, comment_id in comments
            ),
            encoding="utf-8",
        )
        return None

    monkeypatch.setattr(MediaCrawlerAdapter, "_validate_crawler", lambda _self: None)
    monkeypatch.setattr(MediaCrawlerAdapter, "_run_child", replay)
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO identity_users (id, username, password_hash, credential_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"bilibili-{owner_id}", "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics (id, owner_id, name, status, readiness_status, "
                    "current_version, created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'Bilibili replay', 'paused', 'pending_source_selection', "
                    "1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions (topic_id, version, created_by, "
                    "match_any, match_all, exclude, created_at) VALUES "
                    "(:id, 1, :owner_id, CAST(:terms AS jsonb), '[]', '[]', :now)"
                ),
                {
                    "id": topic_id,
                    "owner_id": owner_id,
                    "now": now,
                    "terms": json.dumps(["DeepSeek", "大肥鱼"]),
                },
            )
            session.execute(
                text(
                    "INSERT INTO source_connections (id, owner_id, source_key, status, "
                    "current_version, created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'bilibili', 'active', 1, :now, :now)"
                ),
                {"id": connection_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO source_connection_versions (connection_id, version, owner_id, "
                    "secret_ref, created_by, created_at) VALUES "
                    "(:id, 1, :owner_id, 'env:CONTROLLED_FIXTURE', :owner_id, :now)"
                ),
                {"id": connection_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO source_access_policies "
                    "(id, owner_id, source_key, capability, status, enabled, access_basis, "
                    "terms_reference, processing_purpose, component_name, component_version, "
                    "component_license, field_purposes, reviewed_at, policy_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'bilibili', 'search', 'approved', true, 'public_web', "
                    "'https://example.invalid/terms', '受控重放', 'collector.bilibili', '1', "
                    "'test', CAST(:fields AS jsonb), :now, 1, :now, :now)"
                ),
                {
                    "id": policy_id,
                    "owner_id": owner_id,
                    "now": now,
                    "fields": json.dumps(
                        dict(BILIBILI_PRESET.capabilities[0].field_purposes), ensure_ascii=False
                    ),
                },
            )
            session.execute(
                text(
                    "INSERT INTO evidence_retention_policies "
                    "(id, owner_id, source_policy_id, source_policy_version, data_class, "
                    "requested_days, source_max_days, effective_days, policy_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, :policy_id, 1, 'structured', 30, NULL, 30, 1, :now, :now)"
                ),
                {"id": retention_id, "owner_id": owner_id, "policy_id": policy_id, "now": now},
            )
            accepted = JobService(session).accept_in_transaction(owner_id=owner_id, command=command)
        with Session(engine) as session:
            lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=accepted.id, worker_id="bilibili-replay"
            )
        with Session(engine) as session:
            budget = ResourceBudgetService(session)
            budget.save_component_policy(
                owner_id=owner_id,
                command=ComponentPolicyInput(
                    component_key="collector.bilibili",
                    component_version="1",
                    cost_class=CostClass.LOCAL,
                    enabled_for_core=True,
                    terms_reference="https://example.invalid/terms",
                    reviewed_at=now,
                ),
            )
            budget.save_budget_policy(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.bilibili-network.daily",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=60,
                    window_seconds=86_400,
                    window_anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
                    enabled=True,
                ),
            )
            budget.save_budget_policy(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="source.bilibili.network.daily",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.SOURCE,
                    scope_reference="bilibili",
                    limit_units=60,
                    window_seconds=86_400,
                    window_anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
                    enabled=True,
                ),
            )

        adapter: MediaCrawlerAdapter | None = None

        def adapter_factory(
            before_request: Callable[[int], bool],
            cancelled: Callable[[], bool],
            max_requests: int,
            max_seconds: float,
        ) -> MediaCrawlerAdapter:
            nonlocal adapter
            adapter = MediaCrawlerAdapter(
                crawler_dir=crawler,
                output_dir=output,
                owner_key=owner_id.hex,
                before_request=before_request,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                verify_revision=False,
            )
            return adapter

        _, completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            adapter_factory=adapter_factory,
        ).execute(_accepted_message(engine, accepted.id), lease)
        assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
        assert adapter is not None
        with Session(engine) as session:
            records = session.scalars(
                select(ContentRecord).where(ContentRecord.owner_id == owner_id)
            ).all()
            assert {record.external_id for record in records} == {video[0] for video in videos}
            job = session.get(Job, accepted.id)
            assert job is not None
            assert (job.requests_sent, job.items_saved) == (26, 5)
            assert (
                session.execute(
                    text(
                        "SELECT count(*) FROM resource_usage_attempts WHERE operation_id = :id "
                        "AND outcome = 'failed'"
                    ),
                    {"id": command.operation_id},
                ).scalar_one()
                == 26
            )
        cached = [
            adapter.fetch_page(
                CommentsRequest(source_key="bilibili", post_external_id=video_id, page_size=20)
            )
            for video_id, _ in comments
        ]
        assert [page.request_count for page in cached] == [0, 0]
        assert [page.items[0].external_id for page in cached] == [
            comment_id for _, comment_id in comments
        ]
    finally:
        with engine.begin() as connection:
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            connection.execute(
                text("DELETE FROM content_records WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM source_connection_versions WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topics WHERE id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
        engine.dispose()


def _run_hn_handler_in_process(
    database_url: str,
    bootstrap: str,
    kafka_topic: str,
    group_id: str,
    worker_id: str,
    commit_offset: bool,
    expect_deferred: bool,
    result_queue: Queue,
) -> None:
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "session.timeout.ms": 6_000,
        }
    )
    try:
        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        json={
                            "hits": [{"objectID": "000201", "title": "DeepSeek Kafka"}],
                            "nbPages": 1,
                        },
                    )
                ),
            ),
        )

        def collect(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        handler = create_job_message_handler(
            sessions,
            {"keyword.search": collect},
            worker_id=worker_id,
            lease_seconds=60,
        )
        consumer.subscribe([kafka_topic])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = consumer.poll(0.2)
            if message is None:
                continue
            if message.error() is not None:
                raise RuntimeError(str(message.error()))
            if commit_offset:
                try:
                    process_message(consumer, message, {kafka_topic: handler})
                except MessageDeferredError:
                    if not expect_deferred:
                        raise
                    result_queue.put((message.partition(), message.offset()))
                    return
                if expect_deferred:
                    raise AssertionError("HN Kafka worker unexpectedly completed a leased job")
            else:
                handler(message)
            result_queue.put((message.partition(), message.offset()))
            return
        raise AssertionError("HN Kafka worker process did not receive a message")
    finally:
        consumer.close()
        engine.dispose()


@pytest.mark.parametrize(
    "mode",
    ["controlled", "concurrent", "process-restart", "live", "production-worker"],
)
def test_hackernews_kafka_redelivery_does_not_repeat_persisted_search(mode: str) -> None:
    live = mode in {"live", "production-worker"}
    process_restart = mode == "process-restart"
    production_worker = mode == "production-worker"
    concurrent = mode == "concurrent"
    if live and os.getenv("HOTKEY_TEST_LIVE_HN") != "1":
        pytest.skip("HOTKEY_TEST_LIVE_HN=1 is required for an actual HN request")
    if production_worker and os.getenv("HOTKEY_TEST_PRODUCTION_WORKER") != "1":
        pytest.skip("HOTKEY_TEST_PRODUCTION_WORKER=1 requires a fresh isolated Kafka broker")
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    bootstrap = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if database_url is None or bootstrap is None:
        pytest.skip("PostgreSQL and Kafka integration endpoints are required")

    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    keyword = "AI" if live else "DeepSeek"
    kafka_topic = JOB_ACCEPTED_TOPIC if production_worker else f"hotkey.tests.hn.{uuid4().hex}"
    group_id = f"hotkey-tests-hn-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    if production_worker and kafka_topic in admin.list_topics(timeout=5).topics:
        pytest.skip("production Worker test requires an unused isolated job topic")
    first: Consumer | None = None
    second: Consumer | None = None
    created_topic = False
    try:
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"hn-kafka-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=HACKERNEWS_PRESET
            )
            ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.hn-kafka-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'HN Kafka', :status, :readiness, 1, :now, :now)"
                ),
                {
                    "id": topic_id,
                    "owner_id": owner_id,
                    "status": "active",
                    "readiness": "ready",
                    "now": now,
                },
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, "
                    "source_keys, created_at) "
                    "VALUES (:id, 1, :owner_id, CAST(:match_any AS jsonb), "
                    "'[]'::jsonb, '[]'::jsonb, CAST(:source_keys AS jsonb), :now)"
                ),
                {
                    "id": topic_id,
                    "owner_id": owner_id,
                    "match_any": json.dumps([keyword]),
                    "source_keys": json.dumps(["hackernews"]),
                    "now": now,
                },
            )
        with sessions() as session:
            accepted_run = MonitorTopicRunService(
                session, Settings(database_url=database_url), clock=lambda: now
            ).run(
                owner_id=owner_id,
                topic_id=topic_id,
                command=MonitorTopicRunInput(operation_id=uuid4(), source_keys=["hackernews"]),
            )
        assert not accepted_run.replayed
        assert accepted_run.view.topic_version == 1
        assert len(accepted_run.view.sources[0].job_ids) == 1
        with sessions() as session:
            accepted = session.get(Job, accepted_run.view.sources[0].job_ids[0])
            assert accepted is not None
            assert accepted.scope["manual_request_id"] == str(accepted_run.view.operation_id)
        with sessions.begin() as session:
            session.execute(
                text("UPDATE outbox_messages SET topic = :topic WHERE aggregate_id = :job_id"),
                {"topic": kafka_topic, "job_id": accepted.id},
            )

        admin.create_topics([NewTopic(kafka_topic, num_partitions=1, replication_factor=1)])[
            kafka_topic
        ].result(10)
        created_topic = True

        def consumer() -> Consumer:
            return Consumer(
                {
                    "bootstrap.servers": bootstrap,
                    "group.id": group_id,
                    "enable.auto.commit": False,
                    "enable.auto.offset.store": False,
                    "auto.offset.reset": "earliest",
                    "session.timeout.ms": 6_000,
                }
            )

        def receive(target: Consumer) -> Message:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                message = target.poll(0.2)
                if message is None:
                    continue
                if message.error() is not None:
                    raise RuntimeError(str(message.error()))
                return message
            raise AssertionError("HN Kafka message was not received")

        requested: list[httpx.Request] = []
        request_started = Event()
        release_request = Event()

        def algolia_response(request: httpx.Request) -> httpx.Response:
            requested.append(request)
            if concurrent:
                request_started.set()
                assert release_request.wait(timeout=10)
            return httpx.Response(
                200,
                json={
                    "hits": [{"objectID": "000201", "title": "DeepSeek Kafka"}],
                    "nbPages": 1,
                },
            )

        executor = KeywordDiscoveryExecutor(
            sessions,
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=None if live else httpx.MockTransport(algolia_response),
            ),
        )

        def collect(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        producer = create_producer(
            Settings(
                database_url=database_url,
                kafka_bootstrap_servers=bootstrap,
                kafka_delivery_timeout_seconds=10,
            )
        )
        with sessions() as session:
            assert (
                OutboxService(session).publish_pending(
                    lambda envelope: publish_outbox(producer, envelope, timeout_seconds=10),
                )
                == 1
            )
        if production_worker:

            def run_production_worker(
                *, expected_job_id: UUID, expected_offset: int, expected_log: str | None = None
            ) -> None:
                worker_env = {
                    **os.environ,
                    "HOTKEY_DATABASE_URL": database_url,
                    "HOTKEY_KAFKA_BOOTSTRAP_SERVERS": bootstrap,
                    "HOTKEY_KAFKA_GROUP_ID": group_id,
                    "HOTKEY_ENVIRONMENT": "test",
                    "HOTKEY_LOG_LEVEL": "INFO",
                }
                process = subprocess.Popen(
                    [sys.executable, "-m", "worker"],
                    cwd=Path(__file__).resolve().parents[2] / "app",
                    env=worker_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                selector = selectors.DefaultSelector()
                assert process.stdout is not None
                selector.register(process.stdout, selectors.EVENT_READ)
                verifier = consumer()
                observed_log = ""
                try:
                    deadline = time.monotonic() + 35
                    while time.monotonic() < deadline:
                        for key, _events in selector.select(timeout=0.2):
                            observed_log += os.read(key.fd, 4096).decode(errors="replace")
                        if process.poll() is not None:
                            raise AssertionError(
                                f"production Worker exited early: {process.returncode}"
                            )
                        with sessions() as session:
                            processed = session.scalar(
                                text(
                                    "SELECT count(*) FROM processed_messages WHERE job_id = :job_id"
                                ),
                                {"job_id": expected_job_id},
                            )
                        committed = verifier.committed([TopicPartition(kafka_topic, 0)], timeout=2)
                        if (
                            processed == (0 if expected_log else 1)
                            and committed[0].offset == expected_offset
                            and (expected_log is None or expected_log in observed_log)
                        ):
                            return
                    raise AssertionError("production Worker did not reach the expected state")
                finally:
                    process.terminate()
                    try:
                        process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate(timeout=5)
                    selector.close()
                    verifier.close()

            run_production_worker(expected_job_id=accepted.id, expected_offset=1)
            with engine.connect() as connection:
                first_counts = connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM content_records WHERE owner_id = :owner_id), "
                        "(SELECT count(*) FROM resource_usage_attempts "
                        " WHERE operation_id = :operation_id), "
                        "(SELECT count(*) FROM processed_messages WHERE job_id = :job_id)"
                    ),
                    {
                        "owner_id": owner_id,
                        "operation_id": accepted.operation_id,
                        "job_id": accepted.id,
                    },
                ).one()
            assert first_counts[0] >= 1
            rewinder = consumer()
            try:
                rewinder.commit(offsets=[TopicPartition(kafka_topic, 0, 0)], asynchronous=False)
                committed = rewinder.committed([TopicPartition(kafka_topic, 0)], timeout=5)
                assert committed[0].offset == 0
            finally:
                rewinder.close()
            run_production_worker(expected_job_id=accepted.id, expected_offset=1)
            with engine.connect() as connection:
                replay_counts = connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM content_records WHERE owner_id = :owner_id), "
                        "(SELECT count(*) FROM resource_usage_attempts "
                        " WHERE operation_id = :operation_id), "
                        "(SELECT count(*) FROM processed_messages WHERE job_id = :job_id)"
                    ),
                    {
                        "owner_id": owner_id,
                        "operation_id": accepted.operation_id,
                        "job_id": accepted.id,
                    },
                ).one()
            assert replay_counts == first_counts
            with sessions() as session:
                incomplete_run = MonitorTopicRunService(
                    session, Settings(database_url=database_url), clock=lambda: now
                ).run(
                    owner_id=owner_id,
                    topic_id=topic_id,
                    command=MonitorTopicRunInput(operation_id=uuid4(), source_keys=["hackernews"]),
                )
            incomplete_job_id = incomplete_run.view.sources[0].job_ids[0]
            with sessions.begin() as session:
                session.execute(
                    text("UPDATE outbox_messages SET topic = :topic WHERE aggregate_id = :job_id"),
                    {"topic": kafka_topic, "job_id": incomplete_job_id},
                )
            with sessions() as session:
                assert (
                    OutboxService(session).publish_pending(
                        lambda envelope: publish_outbox(producer, envelope, timeout_seconds=10),
                    )
                    == 1
                )
            with sessions() as session:
                JobExecutionService(session, lease_seconds=60).acquire(
                    job_id=incomplete_job_id, worker_id="hn-production-held-lease"
                )
            run_production_worker(
                expected_job_id=incomplete_job_id,
                expected_offset=1,
                expected_log="message_processing_deferred",
            )
            with sessions() as session:
                incomplete = session.get(Job, incomplete_job_id)
                assert incomplete is not None
                assert incomplete.requests_sent == 0
        elif process_restart:
            context = get_context("spawn")

            def run_worker_process(
                *, commit_offset: bool, worker_id: str, expect_deferred: bool = False
            ) -> tuple[int, int]:
                result_queue = context.Queue()
                process = context.Process(
                    target=_run_hn_handler_in_process,
                    args=(
                        database_url,
                        bootstrap,
                        kafka_topic,
                        group_id,
                        worker_id,
                        commit_offset,
                        expect_deferred,
                        result_queue,
                    ),
                )
                process.start()
                try:
                    try:
                        position = result_queue.get(timeout=25)
                    except Empty as error:
                        raise AssertionError("HN Kafka worker process did not finish") from error
                    process.join(timeout=5)
                    assert process.exitcode == 0
                    return position
                finally:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                    result_queue.close()

            delivered_position = run_worker_process(
                commit_offset=False, worker_id="hn-kafka-first-process"
            )
            replay_position = run_worker_process(
                commit_offset=True, worker_id="hn-kafka-restarted-process"
            )
            assert replay_position == delivered_position
            second = consumer()
            committed = second.committed([TopicPartition(kafka_topic, 0)], timeout=5)
            assert committed[0].offset == replay_position[1] + 1
            second.close()
            second = None

            with sessions() as session:
                incomplete_run = MonitorTopicRunService(
                    session, Settings(database_url=database_url), clock=lambda: now
                ).run(
                    owner_id=owner_id,
                    topic_id=topic_id,
                    command=MonitorTopicRunInput(operation_id=uuid4(), source_keys=["hackernews"]),
                )
            incomplete_job_id = incomplete_run.view.sources[0].job_ids[0]
            with sessions.begin() as session:
                session.execute(
                    text("UPDATE outbox_messages SET topic = :topic WHERE aggregate_id = :job_id"),
                    {"topic": kafka_topic, "job_id": incomplete_job_id},
                )
            with sessions() as session:
                assert (
                    OutboxService(session).publish_pending(
                        lambda envelope: publish_outbox(producer, envelope, timeout_seconds=10),
                    )
                    == 1
                )
            with sessions() as session:
                JobExecutionService(session, lease_seconds=60).acquire(
                    job_id=incomplete_job_id, worker_id="hn-kafka-held-lease"
                )
            deferred_position = run_worker_process(
                commit_offset=True,
                worker_id="hn-kafka-deferred-process",
                expect_deferred=True,
            )
            assert deferred_position == (replay_position[0], replay_position[1] + 1)
            second = consumer()
            committed = second.committed([TopicPartition(kafka_topic, 0)], timeout=5)
            assert committed[0].offset == replay_position[1] + 1
            with sessions() as session:
                assert (
                    session.scalar(
                        text("SELECT count(*) FROM processed_messages WHERE job_id = :job_id"),
                        {"job_id": incomplete_job_id},
                    )
                    == 0
                )
        else:
            first = consumer()
            first.subscribe([kafka_topic])
            delivered = receive(first)
            first_handler = create_job_message_handler(
                sessions,
                {"keyword.search": collect},
                worker_id="hn-kafka-first-worker",
                lease_seconds=60,
            )
            if concurrent:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    running = pool.submit(first_handler, delivered)
                    try:
                        assert request_started.wait(timeout=10)
                        duplicate_handler = create_job_message_handler(
                            sessions,
                            {"keyword.search": collect},
                            worker_id="hn-kafka-concurrent-worker",
                            lease_seconds=60,
                        )
                        with pytest.raises(MessageDeferredError):
                            duplicate_handler(delivered)
                    finally:
                        release_request.set()
                    running.result(timeout=10)
            else:
                first_handler(delivered)
            first.close()
            first = None

            second = consumer()
            second.subscribe([kafka_topic])
            replay = receive(second)
            assert replay.offset() == delivered.offset()
            create_job_message_handler(
                sessions,
                {"keyword.search": collect},
                worker_id="hn-kafka-restarted-worker",
                lease_seconds=60,
            )(replay)
            second.commit(message=replay, asynchronous=False)
            committed = second.committed([TopicPartition(kafka_topic, 0)], timeout=5)
            assert committed[0].offset == replay.offset() + 1

        with engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM content_records WHERE owner_id = :owner_id), "
                    "(SELECT count(*) FROM content_discoveries WHERE job_id = :job_id), "
                    "(SELECT count(*) FROM content_observations WHERE job_id = :job_id), "
                    "(SELECT count(*) FROM resource_usage_attempts "
                    " WHERE operation_id = :operation_id), "
                    "(SELECT count(*) FROM processed_messages WHERE job_id = :job_id)"
                ),
                {
                    "owner_id": owner_id,
                    "job_id": accepted.id,
                    "operation_id": accepted.operation_id,
                },
            ).one()
            if live:
                content_count, discovery_count, observation_count, usage_count, processed_count = (
                    tuple(result)
                )
                assert content_count >= 1
                assert (discovery_count, observation_count) == (content_count, content_count)
                assert processed_count == 1
                with sessions() as session:
                    job = session.get(Job, accepted.id)
                    assert job is not None
                    assert job.scope["connection_version"] == preset.connection_version
                    assert 1 <= job.requests_sent <= 3
                    assert job.items_saved == content_count
                    assert usage_count == job.requests_sent
                    coverage = session.scalar(
                        select(CoverageWindow).where(CoverageWindow.last_job_id == accepted.id)
                    )
                    assert coverage is not None
                    assert coverage.page_count == job.requests_sent
                    assert coverage.status == "partial"
                    print(
                        "HN live run:",
                        job.status,
                        job.requests_sent,
                        content_count,
                        coverage.stop_reason,
                    )
                budget = connection.execute(
                    text(
                        "SELECT count(DISTINCT reservation_id), count(*), sum(actual_units) "
                        "FROM resource_budget_reservations "
                        "WHERE owner_id = :owner_id AND operation_id = :operation_id"
                    ),
                    {"owner_id": owner_id, "operation_id": accepted.operation_id},
                ).one()
                assert budget == (job.requests_sent, 2 * job.requests_sent, 2 * job.requests_sent)
                samples = connection.execute(
                    text(
                        "SELECT record.external_id, observation.canonical_url "
                        "FROM content_records AS record "
                        "JOIN content_observations AS observation "
                        "ON observation.content_id = record.id "
                        "WHERE record.owner_id = :owner_id ORDER BY record.external_id"
                    ),
                    {"owner_id": owner_id},
                ).all()
                assert all(
                    url == f"https://news.ycombinator.com/item?id={identifier}"
                    for identifier, url in samples
                )
                print(f"HN live persisted sample IDs: {[row.external_id for row in samples[:3]]}")
            else:
                assert tuple(result) == (1, 1, 1, 1, 1)
                if not process_restart:
                    assert len(requested) == 1
                if concurrent:
                    assert (
                        connection.execute(
                            text("SELECT count(*) FROM job_attempts WHERE job_id = :job_id"),
                            {"job_id": accepted.id},
                        ).scalar_one()
                        == 1
                    )
    finally:
        if first is not None:
            first.close()
        if second is not None:
            second.close()
        if created_topic:
            with suppress(Exception):
                admin.delete_topics([kafka_topic], operation_timeout=10)[kafka_topic].result(10)
        with engine.begin() as connection:
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            connection.execute(
                text("DELETE FROM content_records WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM source_connection_versions WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
        engine.dispose()


def test_hackernews_second_page_rate_limit_preserves_first_page_and_unknown_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    owner_id, topic_id = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=1)
    requested: list[httpx.Request] = []
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"hn-search-{owner_id}", "now": now},
            )
            preset = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=HACKERNEWS_PRESET
            )
            ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
                owner_id=owner_id,
                command=BudgetPolicyInput(
                    budget_key="global.hn-controlled-hour",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind=BudgetScopeKind.GLOBAL,
                    scope_reference=None,
                    limit_units=10,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(seconds=10),
                    enabled=True,
                ),
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'HN search', 'paused', 'pending_source_selection', "
                    "1, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:id, 1, :owner_id, '[\"DeepSeek\"]'::jsonb, "
                    "'[]'::jsonb, '[\"sponsored\"]'::jsonb, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            run = KeywordDiscoveryRunInput(
                run_id=uuid4(),
                configuration_ref=f"topic:{topic_id}",
                configuration_version=1,
                source_key="hackernews",
                connection_id=preset.connection_id,
                connection_version=preset.connection_version,
                primary_query="DeepSeek",
                starts_at=start,
                ends_at=now,
                page_size=7,
                latest_max_pages=2,
                latest_max_requests=3,
                top_max_pages=1,
                top_max_requests=1,
                max_seconds=90,
            )
            accepted = JobService(session, clock=lambda: now).accept_in_transaction(
                owner_id=owner_id, command=plan_keyword_discovery(run)[0]
            )
        with Session(engine) as session:
            lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=accepted.id, worker_id="hn-controlled-search"
            )

        def algolia_response(request: httpx.Request) -> httpx.Response:
            requested.append(request)
            assert request.url.host == "hn.algolia.com"
            assert request.url.path == "/api/v1/search_by_date"
            if request.url.params["page"] == "0":
                return httpx.Response(
                    200,
                    json={
                        "hits": [
                            {
                                "objectID": "000101",
                                "title": "DeepSeek published",
                                "author": "hn-author",
                                "created_at_i": int((now - timedelta(hours=1)).timestamp()),
                                "points": 7,
                                "num_comments": 2,
                            },
                            {"objectID": "000102", "title": "DeepSeek published"},
                            {
                                "objectID": "000103",
                                "title": "DeepSeek window start",
                                "created_at_i": int(start.timestamp()),
                            },
                            {
                                "objectID": "000104",
                                "title": "DeepSeek window end",
                                "created_at_i": int(now.timestamp()),
                            },
                            {
                                "objectID": "000105",
                                "title": "DeepSeek before window",
                                "created_at_i": int((start - timedelta(seconds=1)).timestamp()),
                            },
                            {"objectID": "000106", "title": "Unrelated story"},
                            {"objectID": "000107", "title": "DeepSeek sponsored story"},
                        ],
                        "nbPages": 2,
                    },
                )
            assert request.url.params["page"] == "1"
            return httpx.Response(429, headers={"retry-after": "30"})

        _, completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(algolia_response),
            ),
        ).execute(_accepted_message(engine, accepted.id), lease)

        assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
        assert [request.url.params["page"] for request in requested] == ["0", "1"]
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT record.external_id, observation.published_at, "
                    "observation.like_count, version.body, discovery.first_observed_at "
                    "FROM content_records AS record "
                    "JOIN content_observations AS observation "
                    "ON observation.content_id = record.id "
                    "JOIN content_versions AS version "
                    "ON version.id = observation.content_version_id "
                    "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                    "WHERE record.owner_id = :owner_id AND discovery.job_id = :job_id"
                ),
                {"owner_id": owner_id, "job_id": accepted.id},
            ).all()
            by_id = {row.external_id: row for row in rows}
            assert set(by_id) == {"000101", "000102", "000103"}
            assert by_id["000101"].published_at == now - timedelta(hours=1)
            assert by_id["000101"].like_count == 7
            assert by_id["000102"].published_at is None
            assert by_id["000102"].like_count is None
            assert by_id["000103"].published_at == start
            assert all(row.body is None and row.first_observed_at >= now for row in rows)
            job = session.get(Job, accepted.id)
            assert job is not None
            assert job.scope["connection_version"] == preset.connection_version
            assert (job.requests_sent, job.items_saved) == (2, 3)
            assert job.checkpoint["collection.observed_count"] == 7
            coverage = session.scalar(
                select(CoverageWindow).where(CoverageWindow.last_job_id == accepted.id)
            )
            assert coverage is not None
            assert (coverage.status, coverage.stop_reason, coverage.page_count) == (
                "partial",
                "rate_limited",
                2,
            )
            usage = session.execute(
                text(
                    "SELECT count(DISTINCT reservation_id), count(*), sum(actual_units) "
                    "FROM resource_budget_reservations "
                    "WHERE owner_id = :owner_id AND operation_id = :operation_id"
                ),
                {"owner_id": owner_id, "operation_id": job.operation_id},
            ).one()
            assert usage == (2, 4, 4)
            network_attempts = session.scalar(
                text(
                    "SELECT count(*) FROM resource_usage_attempts "
                    "WHERE owner_id = :owner_id AND operation_id = :operation_id "
                    "AND usage_kind = 'network_request'"
                ),
                {"owner_id": owner_id, "operation_id": job.operation_id},
            )
            assert network_attempts == 2

        recovered_at = now + timedelta(minutes=3)
        with Session(engine) as session:
            recovered_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: recovered_at
            ).acquire(job_id=accepted.id, worker_id="hn-recovered-search")
        assert recovered_lease.epoch == lease.epoch + 1
        with Session(engine) as session, pytest.raises(StaleExecutionLeaseError):
            JobExecutionService(session, lease_seconds=60, clock=lambda: recovered_at).complete(
                lease,
                message=MessageReference(
                    message_id=uuid4(),
                    topic="hotkey.tests.hn",
                    partition=0,
                    offset=0,
                ),
                completion=JobCompletion(status=JobStatus.SUCCEEDED),
            )
        with Session(engine) as session:
            assert session.get(Job, accepted.id).status == JobStatus.RUNNING.value
            assert (
                session.scalar(
                    text("SELECT count(*) FROM processed_messages WHERE job_id = :job_id"),
                    {"job_id": accepted.id},
                )
                == 0
            )
            JobExecutionService(session, lease_seconds=60, clock=lambda: recovered_at).complete(
                recovered_lease,
                message=MessageReference(
                    message_id=uuid4(),
                    topic="hotkey.tests.hn",
                    partition=0,
                    offset=0,
                ),
                completion=completion,
            )
        with Session(engine) as session:
            assert session.get(Job, accepted.id).status == JobStatus.PARTIALLY_SUCCEEDED.value

        interrupted_run = run.model_copy(
            update={"run_id": uuid4(), "primary_query": "DeepSeek interrupted"}
        )
        with Session(engine) as session:
            interrupted_job = JobService(session).accept(
                owner_id=owner_id, command=plan_keyword_discovery(interrupted_run)[0]
            )
        with Session(engine) as session:
            interrupted_lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=interrupted_job.id, worker_id="hn-interrupted-search"
            )

        def interrupt_after_content_write(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("forced HN checkpoint interruption")

        def interrupted_adapter(
            before: Callable[[int], bool],
            cancelled: Callable[[], bool],
            max_requests: int,
            max_seconds: float,
        ) -> HackerNewsAdapter:
            return HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        json={
                            "hits": [{"objectID": "000108", "title": "DeepSeek interrupted"}],
                            "nbPages": 1,
                        },
                    )
                ),
            )

        with monkeypatch.context() as patch:
            patch.setattr(
                CoverageWindowService,
                "record_cursor_page_in_transaction",
                interrupt_after_content_write,
            )
            with pytest.raises(RuntimeError, match="forced HN checkpoint interruption"):
                KeywordDiscoveryExecutor(
                    sessionmaker(bind=engine),
                    lease_seconds=60,
                    adapter_factory=interrupted_adapter,
                ).execute(_accepted_message(engine, interrupted_job.id), interrupted_lease)
        with Session(engine) as session:
            interrupted_state = session.get(Job, interrupted_job.id)
            assert interrupted_state is not None
            assert (
                interrupted_state.requests_sent,
                interrupted_state.items_saved,
                interrupted_state.checkpoint_sequence,
            ) == (1, 0, 0)
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM content_records "
                        "WHERE owner_id = :owner_id AND external_id = '000108'"
                    ),
                    {"owner_id": owner_id},
                )
                == 0
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM content_discoveries WHERE job_id = :job_id"),
                    {"job_id": interrupted_job.id},
                )
                == 0
            )
            assert (
                session.scalar(
                    text("SELECT count(*) FROM coverage_windows WHERE last_job_id = :job_id"),
                    {"job_id": interrupted_job.id},
                )
                == 0
            )
            assert session.execute(
                text(
                    "SELECT count(*), sum(actual_units) FROM resource_budget_reservations "
                    "WHERE operation_id = :operation_id AND status = 'settled'"
                ),
                {"operation_id": interrupted_job.operation_id},
            ).one() == (2, 2)
            assert session.execute(
                text(
                    "SELECT count(*), min(outcome) FROM resource_usage_attempts "
                    "WHERE operation_id = :operation_id"
                ),
                {"operation_id": interrupted_job.operation_id},
            ).one() == (1, "failed")

        disabled_run = run.model_copy(
            update={"run_id": uuid4(), "primary_query": "DeepSeek disabled"}
        )
        with Session(engine) as session:
            disabled_job = JobService(session).accept(
                owner_id=owner_id, command=plan_keyword_discovery(disabled_run)[0]
            )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE source_connections SET status = 'disabled' WHERE id = :id"),
                {"id": preset.connection_id},
            )
        with Session(engine) as session:
            disabled_lease = JobExecutionService(session, lease_seconds=60).acquire(
                job_id=disabled_job.id, worker_id="hn-disabled-search"
            )
        denied_requests: list[httpx.Request] = []

        def denied_transport(request: httpx.Request) -> httpx.Response:
            denied_requests.append(request)
            return httpx.Response(200, json={"hits": [], "nbPages": 0})

        def disabled_adapter(
            before: Callable[[int], bool],
            cancelled: Callable[[], bool],
            max_requests: int,
            max_seconds: float,
        ) -> HackerNewsAdapter:
            return HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(denied_transport),
            )

        with pytest.raises(JobExecutionFailure) as disabled_error:
            KeywordDiscoveryExecutor(
                sessionmaker(bind=engine),
                lease_seconds=60,
                adapter_factory=disabled_adapter,
            ).execute(_accepted_message(engine, disabled_job.id), disabled_lease)
        assert disabled_error.value.error_code == "search_connection_changed"
        assert denied_requests == []
        with Session(engine) as session:
            disabled_state = session.get(Job, disabled_job.id)
            assert disabled_state is not None and disabled_state.requests_sent == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            connection.execute(
                text("DELETE FROM content_records WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM source_connection_versions WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
        engine.dispose()


def test_query_plan_persists_independent_jobs_without_leaking_query_to_outbox() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    owner_id = uuid4()
    run = KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref="topic:fixture",
        configuration_version=3,
        source_key="x",
        connection_id=uuid4(),
        connection_version=1,
        primary_query="product fault",
        starts_at=datetime(2026, 9, 22, tzinfo=UTC),
        ends_at=datetime(2026, 9, 23, tzinfo=UTC),
        page_size=20,
        latest_max_pages=3,
        latest_max_requests=6,
        top_max_pages=2,
        top_max_requests=4,
        max_seconds=30,
    )
    commands = plan_keyword_discovery(run)
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, now(), now())"
                ),
                {"id": owner_id, "username": f"discovery-{owner_id}"},
            )
            accepted = [
                JobService(session).accept_in_transaction(owner_id=owner_id, command=command)
                for command in commands
            ]

        with Session(engine) as session:
            jobs = session.scalars(select(Job).where(Job.owner_id == owner_id)).all()
            messages = session.scalars(
                select(OutboxMessage).where(
                    OutboxMessage.aggregate_id.in_([job.id for job in jobs])
                )
            ).all()
            assert len(jobs) == len(messages) == len(accepted) == 2
            assert {job.scope["sort_key"] for job in jobs} == {"latest", "top"}
            assert {job.scope["query"] for job in jobs} == {"product fault"}
            assert all("query" not in message.payload for message in messages)
            assert all("product fault" not in str(message.payload) for message in messages)

        for command, original in zip(commands, accepted, strict=True):
            with Session(engine) as session:
                repeated = JobService(session).accept(owner_id=owner_id, command=command)
            assert repeated.id == original.id

        changed = run.model_copy(update={"primary_query": "different search"})
        with Session(engine) as session, pytest.raises(ApplicationError) as captured:
            JobService(session).accept(
                owner_id=owner_id,
                command=plan_keyword_discovery(changed)[0],
            )
        assert captured.value.code == "idempotency_conflict"

        with Session(engine) as session:
            messages = session.scalars(
                select(OutboxMessage).where(
                    OutboxMessage.aggregate_id.in_([job.id for job in accepted])
                )
            ).all()
            assert len(messages) == 2
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
        engine.dispose()


def _post(
    identifier: str,
    published_at: datetime,
    *,
    url: str | None = None,
    body: str | None = "product fault release",
    like_count: int = 0,
    text_scope: str = "full",
) -> SourcePost:
    return SourcePost(
        source_key="x",
        external_id=identifier,
        author_external_id="author-1",
        published_at=published_at,
        text=body,
        language="en",
        like_count=like_count,
        comment_count=0,
        repost_count=0,
        canonical_url=url or f"https://example.invalid/posts/{identifier}",
        conversation_external_id=None,
        parent_external_id=None,
        quote_external_id=None,
        repost_external_id=None,
        text_scope=text_scope,
    )


def _page(
    now: datetime,
    state: SourcePageState,
    posts: tuple[SourcePost, ...],
    token: str | None = None,
) -> SourcePage:
    return SourcePage(
        source_key="x",
        capability=SourceCapability.SEARCH,
        state=state,
        items=posts,
        next_page_token=token,
        watermark=None,
        stop_reason=(
            SourceStopReason.END_OF_RESULTS if state is SourcePageState.COMPLETE else None
        ),
        observed_at=now,
        request_count=1,
        adapter_version="controlled-1",
    )


def _accepted_message(engine: Engine, job_id: UUID) -> JobAcceptedMessage:
    with Session(engine) as session:
        outbox = session.scalar(select(OutboxMessage).where(OutboxMessage.aggregate_id == job_id))
        assert outbox is not None
        return JobAcceptedMessage.model_validate(
            {
                "schema_version": 2,
                "message_id": outbox.id,
                "event_type": "job.accepted.v2",
                **outbox.payload,
            }
        )


def test_pages_atomically_save_distinct_channel_discoveries_and_unverified_gap() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    owner_id, connection_id, policy_id, retention_id, topic_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(UTC).replace(microsecond=0)
    start, end = now - timedelta(hours=3), now
    run = KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref=f"topic:{topic_id}",
        configuration_version=3,
        source_key="x",
        connection_id=connection_id,
        connection_version=1,
        primary_query="product fault",
        starts_at=start,
        ends_at=end,
        page_size=20,
        latest_max_pages=3,
        latest_max_requests=6,
        top_max_pages=1,
        top_max_requests=4,
        max_seconds=30,
    )
    commands = plan_keyword_discovery(run)
    target_hash = hashlib.sha256(f"{run.configuration_ref}\0{run.primary_query}".encode()).digest()
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO identity_users "
                    "(id, username, password_hash, credential_version, created_at, updated_at) "
                    "VALUES (:id, :username, 'test-only-hash', 1, :now, :now)"
                ),
                {"id": owner_id, "username": f"discovery-pages-{owner_id}", "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topics "
                    "(id, owner_id, name, status, readiness_status, current_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'Controlled topic', 'paused', "
                    "'pending_source_selection', 4, :now, :now)"
                ),
                {"id": topic_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO monitor_topic_versions "
                    "(topic_id, version, created_by, match_any, match_all, exclude, created_at) "
                    "VALUES (:topic_id, 3, :owner_id, CAST(:match_any AS jsonb), "
                    "CAST(:match_all AS jsonb), CAST(:exclude AS jsonb), :now), "
                    "(:topic_id, 4, :owner_id, '[\"future version\"]', '[]', '[]', :now)"
                ),
                {
                    "topic_id": topic_id,
                    "owner_id": owner_id,
                    "match_any": json.dumps(["product fault", "hotkey"]),
                    "match_all": json.dumps(["release"]),
                    "exclude": json.dumps(["spam"]),
                    "now": now,
                },
            )
            session.execute(
                text(
                    "INSERT INTO source_connections "
                    "(id, owner_id, source_key, status, current_version, created_at, updated_at) "
                    "VALUES (:id, :owner_id, 'x', 'active', 1, :now, :now)"
                ),
                {"id": connection_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO source_connection_versions "
                    "(connection_id, version, owner_id, secret_ref, created_by, created_at) "
                    "VALUES (:id, 1, :owner_id, 'env:CONTROLLED_FIXTURE', :owner_id, :now)"
                ),
                {"id": connection_id, "owner_id": owner_id, "now": now},
            )
            session.execute(
                text(
                    "INSERT INTO source_access_policies "
                    "(id, owner_id, source_key, capability, status, enabled, access_basis, "
                    "terms_reference, processing_purpose, component_name, component_version, "
                    "component_license, field_purposes, reviewed_at, policy_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, 'x', 'search', 'approved', true, 'official_api', "
                    "'https://example.invalid/controlled-terms', '受控作品验证', "
                    "'controlled-collector', '1', 'MIT', CAST(:fields AS jsonb), "
                    ":now, 1, :now, :now)"
                ),
                {
                    "id": policy_id,
                    "owner_id": owner_id,
                    "now": now,
                    "fields": json.dumps(
                        {
                            name: "受控资料字段"
                            for name in (
                                "object_type",
                                "external_id",
                                "canonical_url",
                                "author_external_id",
                                "published_at",
                                "like_count",
                                "comment_count",
                                "repost_count",
                                "text_scope",
                                "text_origin",
                                "body",
                                "truncation_reason",
                            )
                        },
                        ensure_ascii=False,
                    ),
                },
            )
            session.execute(
                text(
                    "INSERT INTO evidence_retention_policies "
                    "(id, owner_id, source_policy_id, source_policy_version, data_class, "
                    "requested_days, source_max_days, effective_days, policy_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :owner_id, :policy_id, 1, 'structured', 30, NULL, 30, 1, :now, :now)"
                ),
                {"id": retention_id, "owner_id": owner_id, "policy_id": policy_id, "now": now},
            )
            accepted = [
                JobService(session, clock=lambda: now).accept_in_transaction(
                    owner_id=owner_id, command=command
                )
                for command in commands
            ]

        windows = {
            sort: CoverageWindowInput(
                owner_id=owner_id,
                source_key="x",
                capability=SourceCapability.SEARCH,
                target_hash=target_hash,
                sort_key=sort,
                rule_version=3,
                starts_at=start,
                ends_at=end,
            )
            for sort in (SourceSort.LATEST, SourceSort.TOP)
        }
        latest_id, top_id = (job.id for job in accepted)
        with Session(engine) as session:
            latest_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: now
            ).acquire(job_id=latest_id, worker_id="controlled-latest")
        with Session(engine) as session:
            budget = ResourceBudgetService(session, clock=lambda: now)
            budget.save_component_policy(
                owner_id=owner_id,
                command=ComponentPolicyInput(
                    component_key="collector.controlled",
                    component_version="1",
                    cost_class=CostClass.LOCAL,
                    enabled_for_core=True,
                    terms_reference="https://example.invalid/controlled-terms",
                    reviewed_at=now,
                ),
            )
            budget_policy = BudgetPolicyInput(
                budget_key="global.controlled-requests",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=2,
                window_seconds=60,
                window_anchor_at=now,
                enabled=True,
            )
            budget.save_budget_policy(owner_id=owner_id, command=budget_policy)
        first_request = plan_cursor_request(
            window=windows[SourceSort.LATEST],
            checkpoint=latest_lease.checkpoint,
            live_token=None,
            max_pages=3,
            max_rescans=1,
        )
        old = _post("old", start - timedelta(minutes=1))
        a = _post("a", start + timedelta(minutes=1))
        invalid = _post("invalid", start + timedelta(minutes=2), url="not-a-url")
        excluded = _post(
            "excluded",
            start + timedelta(minutes=3),
            body="product fault release spam",
        )
        unrelated_high = _post(
            "unrelated-high",
            start + timedelta(minutes=4),
            body="unrelated meme release",
            like_count=100_000,
        )
        missing_text = _post("missing-text", start + timedelta(minutes=5), body=None)
        zero_interaction = _post(
            "zero-interaction",
            start + timedelta(minutes=6),
            body="HOTKEY RELEASE launch",
        )
        with Session(engine) as session, pytest.raises(ValueError):
            KeywordDiscoveryPageCommitService(
                session, lease_seconds=60, clock=lambda: now
            ).commit_page(
                owner_id=owner_id,
                lease=latest_lease,
                window=windows[SourceSort.LATEST],
                request=first_request,
                page_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=1,
                page=_page(now, SourcePageState.MORE, (old, a, invalid), "cursor-1"),
            )
        with Session(engine) as session:
            assert (
                session.scalar(select(ContentRecord).where(ContentRecord.owner_id == owner_id))
                is None
            )
            assert (
                session.scalar(select(CoverageWindow).where(CoverageWindow.owner_id == owner_id))
                is None
            )
            assert session.get(Job, latest_id).checkpoint_sequence == 0

        with Session(engine) as session:
            meter = KeywordRequestMeter(
                session,
                owner_id=owner_id,
                lease=latest_lease,
                operation_id=commands[0].operation_id,
                source_key="x",
                connection_id=connection_id,
                connection_version=1,
                component_key="collector.controlled",
                max_requests=3,
                deadline_at=now + timedelta(seconds=30),
                lease_seconds=60,
                clock=lambda: now,
            )
            assert meter.before_request(1)
            assert meter.before_request(2)
            assert not meter.before_request(3)
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT requests_sent FROM jobs WHERE id = :id"), {"id": latest_id}
                    ).scalar_one()
                    == 2
                )
                assert (
                    connection.execute(
                        text(
                            "SELECT count(*) FROM resource_usage_attempts WHERE outcome = 'started'"
                        )
                    ).scalar_one()
                    == 2
                )
            with pytest.raises(ValueError, match="usage does not match"):
                KeywordDiscoveryPageCommitService(
                    session, lease_seconds=60, clock=lambda: now
                ).commit_page(
                    owner_id=owner_id,
                    lease=latest_lease,
                    window=windows[SourceSort.LATEST],
                    request=first_request,
                    page_operation_id=uuid4(),
                    connection_id=connection_id,
                    connection_version=1,
                    page=_page(now, SourcePageState.MORE, (old, a), "cursor-1"),
                    meter=meter,
                )
            first = KeywordDiscoveryPageCommitService(
                session, lease_seconds=60, clock=lambda: now
            ).commit_page(
                owner_id=owner_id,
                lease=latest_lease,
                window=windows[SourceSort.LATEST],
                request=first_request,
                page_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=1,
                page=_page(now, SourcePageState.MORE, (old, a), "cursor-1").model_copy(
                    update={
                        "items": (
                            old,
                            a,
                            excluded,
                            unrelated_high,
                            missing_text,
                            zero_interaction,
                        ),
                        "request_count": 2,
                    }
                ),
                meter=meter,
            )
            assert first.saved_items == 2
            assert first.filtered_items == 4
            assert first.lease.checkpoint["collection.observed_count"] == 6
            topic_job = session.get(Job, latest_id)
            assert topic_job is not None
            assert topic_job.scope["relevance_filter_position"] == "local"
            assert not {"match_any", "match_all", "exclude"}.intersection(topic_job.scope)

        with Session(engine) as session, session.begin():
            rules = MonitorTopicService(session).get_topic_rules_in_transaction(
                owner_id=owner_id,
                topic_id=topic_id,
                version=3,
            )
            assert evaluate_monitor_rules(rules, "HOTKEY release").matched
            with pytest.raises(ApplicationError) as missing_version:
                MonitorTopicService(session).get_topic_rules_in_transaction(
                    owner_id=owner_id,
                    topic_id=topic_id,
                    version=2,
                )
            assert missing_version.value.code == "resource_not_found"
            with pytest.raises(ApplicationError) as wrong_owner:
                MonitorTopicService(session).get_topic_rules_in_transaction(
                    owner_id=uuid4(),
                    topic_id=topic_id,
                    version=3,
                )
            assert wrong_owner.value.code == "resource_not_found"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM resource_usage_attempts WHERE outcome = 'succeeded'")
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT used_units FROM resource_budget_windows")
                ).scalar_one()
                == 2
            )
        with Session(engine) as session:
            ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
                owner_id=owner_id,
                command=budget_policy.model_copy(update={"limit_units": 6}),
            )
            resumed = KeywordRequestMeter(
                session,
                owner_id=owner_id,
                lease=first.lease,
                operation_id=commands[0].operation_id,
                source_key="x",
                connection_id=connection_id,
                connection_version=1,
                component_key="collector.controlled",
                max_requests=2,
                deadline_at=now + timedelta(seconds=30),
                lease_seconds=60,
                clock=lambda: now,
            )
            assert not resumed.before_request(1)
        assert first.coverage.status == "running"
        with Session(engine) as session, pytest.raises(CheckpointConflictError):
            KeywordDiscoveryPageCommitService(
                session, lease_seconds=60, clock=lambda: now
            ).commit_page(
                owner_id=owner_id,
                lease=latest_lease,
                window=windows[SourceSort.LATEST],
                request=first_request,
                page_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=1,
                page=_page(now, SourcePageState.MORE, (a,), "cursor-1"),
            )
        b = _post("b", start + timedelta(minutes=3), text_scope="truncated")
        submitted_latest: list[SearchRequest] = []

        class ControlledLatestAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, request: SearchRequest) -> SourcePage:
                submitted_latest.append(request)
                assert self._before_request(len(submitted_latest))
                if len(submitted_latest) == 1:
                    return _page(now, SourcePageState.MORE, (old, a), "cursor-1")
                return _page(now, SourcePageState.COMPLETE, (a, b))

        latest_renewed, latest_completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda before, _cancelled, _limit, _seconds: ControlledLatestAdapter(
                before
            ),
            clock=lambda: now,
        ).execute(_accepted_message(engine, latest_id), first.lease)
        assert latest_renewed.checkpoint_sequence == 3
        assert latest_completion.status is JobStatus.PARTIALLY_SUCCEEDED
        assert [(request.sort, request.page_token) for request in submitted_latest] == [
            (SourceSort.LATEST, None),
            (SourceSort.LATEST, "cursor-1"),
        ]
        assert [(request.starts_at, request.ends_at) for request in submitted_latest] == [
            (start, end),
            (start, end),
        ]
        with Session(engine) as session:
            latest_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.sort_key == SourceSort.LATEST.value,
                )
            )
            assert latest_coverage is not None
            assert (latest_coverage.status, latest_coverage.stop_reason) == (
                "partial",
                "unverified_terminal",
            )

        with Session(engine) as session:
            top_lease = JobExecutionService(session, lease_seconds=60, clock=lambda: now).acquire(
                job_id=top_id, worker_id="controlled-top"
            )
        top_request = plan_cursor_request(
            window=windows[SourceSort.TOP],
            checkpoint=top_lease.checkpoint,
            live_token=None,
            max_pages=1,
            max_rescans=1,
        )
        c = _post("c", start + timedelta(minutes=4))
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE source_connections SET status = 'disabled' WHERE id = :id"),
                {"id": connection_id},
            )
        with Session(engine) as session, pytest.raises(ApplicationError) as captured:
            KeywordDiscoveryPageCommitService(
                session, lease_seconds=60, clock=lambda: now
            ).commit_page(
                owner_id=owner_id,
                lease=top_lease,
                window=windows[SourceSort.TOP],
                request=top_request,
                page_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=1,
                page=_page(now, SourcePageState.MORE, (a, c), "top-cursor"),
            )
        assert captured.value.code == "connection_disabled"
        with Session(engine) as session, pytest.raises(ApplicationError) as captured:
            KeywordRequestMeter(
                session,
                owner_id=owner_id,
                lease=top_lease,
                operation_id=commands[1].operation_id,
                source_key="x",
                connection_id=connection_id,
                connection_version=1,
                component_key="collector.controlled",
                max_requests=4,
                deadline_at=now + timedelta(seconds=30),
                lease_seconds=60,
                clock=lambda: now,
            ).before_request(1)
        assert captured.value.code == "connection_disabled"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT requests_sent FROM jobs WHERE id = :id"), {"id": top_id}
                ).scalar_one()
                == 0
            )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE source_connections SET status = 'active' WHERE id = :id"),
                {"id": connection_id},
            )

        class CrashingSearchAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, _request: SearchRequest) -> SourcePage:
                assert self._before_request(1)
                raise RuntimeError("controlled transport failure")

        with pytest.raises(JobExecutionFailure) as transport_error:
            KeywordDiscoveryExecutor(
                sessionmaker(bind=engine),
                lease_seconds=60,
                component_key="collector.controlled",
                adapter_factory=lambda before, _cancelled, _limit, _seconds: CrashingSearchAdapter(
                    before
                ),
                clock=lambda: now,
            ).execute(_accepted_message(engine, top_id), top_lease)
        assert transport_error.value.error_code == "search_source_failed"
        assert transport_error.value.category is JobFailureCategory.TRANSIENT
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM resource_usage_attempts WHERE outcome = 'failed'")
                ).scalar_one()
                == 1
            )
        with Session(engine) as session:
            failed_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.sort_key == SourceSort.TOP.value,
                )
            )
            assert failed_coverage is not None
            assert (
                failed_coverage.status,
                failed_coverage.stop_reason,
                failed_coverage.page_count,
            ) == ("partial", "upstream_error", 0)
        submitted: list[SearchRequest] = []

        class ControlledSearchAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, request: SearchRequest) -> SourcePage:
                submitted.append(request)
                assert self._before_request(1)
                return _page(now, SourcePageState.MORE, (a, c), "top-cursor")

        top_renewed, completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda before, _cancelled, _limit, _seconds: ControlledSearchAdapter(
                before
            ),
            clock=lambda: now,
        ).execute(_accepted_message(engine, top_id), top_lease)
        assert top_renewed.checkpoint_sequence == 1
        assert completion.status is JobStatus.PARTIALLY_SUCCEEDED
        assert completion.failure is not None
        assert completion.failure.error_code == "search_scope_incomplete"
        assert [(request.query, request.sort, request.page_token) for request in submitted] == [
            ("product fault", SourceSort.TOP, None)
        ]
        assert [(request.starts_at, request.ends_at) for request in submitted] == [(start, end)]
        with Session(engine) as session:
            records = session.scalars(
                select(ContentRecord).where(ContentRecord.owner_id == owner_id)
            ).all()
            discoveries = session.scalars(
                select(ContentDiscovery).where(ContentDiscovery.owner_id == owner_id)
            ).all()
            assert len(records) == 4
            assert len(discoveries) == 5
            assert {item.job_id for item in discoveries} == {latest_id, top_id}
            assert session.get(Job, latest_id).items_saved == 3
            assert session.get(Job, top_id).items_saved == 2
            assert session.get(Job, latest_id).checkpoint["collection.observed_count"] == 10
            assert session.get(Job, top_id).checkpoint["collection.observed_count"] == 2
            counts = ContentService(session).collection_counts_in_transaction(
                owner_id=owner_id, job_ids=(latest_id, top_id)
            )
            assert sum(item.first_ingested_count for item in counts) == 4
            assert (
                sum(item.deduplicated_count for item in counts)
                == sum(item.observation_count for item in counts) - 4
            )
            assert "cursor-1" not in json.dumps(session.get(Job, latest_id).checkpoint)
            top_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.sort_key == SourceSort.TOP.value,
                )
            )
            assert top_coverage is not None
            assert (top_coverage.status, top_coverage.stop_reason) == (
                "partial",
                "budget_exhausted",
            )

        with Session(engine) as session:
            ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
                owner_id=owner_id,
                command=budget_policy.model_copy(update={"limit_units": 8}),
            )
            auth_run = run.model_copy(update={"run_id": uuid4(), "primary_query": "auth challenge"})
            auth_job = JobService(session, clock=lambda: now).accept(
                owner_id=owner_id, command=plan_keyword_discovery(auth_run)[0]
            )
            auth_lease = JobExecutionService(session, lease_seconds=60, clock=lambda: now).acquire(
                job_id=auth_job.id, worker_id="controlled-auth"
            )

        class ControlledStoppedAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(
                self,
                before_request: Callable[[int], bool],
                reason: SourceStopReason,
                retry_at: datetime | None = None,
            ) -> None:
                self._before_request = before_request
                self._reason = reason
                self._retry_at = retry_at

            def fetch_page(self, _request: SearchRequest) -> SourcePage:
                assert self._before_request(1)
                return SourcePage(
                    source_key="x",
                    capability=SourceCapability.SEARCH,
                    state=SourcePageState.STOPPED,
                    items=(),
                    next_page_token=None,
                    watermark=None,
                    stop_reason=self._reason,
                    observed_at=now,
                    request_count=1,
                    adapter_version="controlled-1",
                    retry_at=self._retry_at,
                )

        with pytest.raises(JobExecutionFailure) as auth_error:
            KeywordDiscoveryExecutor(
                sessionmaker(bind=engine),
                lease_seconds=60,
                component_key="collector.controlled",
                adapter_factory=lambda before, _cancelled, _limit, _seconds: (
                    ControlledStoppedAdapter(before, SourceStopReason.AUTHENTICATION_REQUIRED)
                ),
                clock=lambda: now,
            ).execute(_accepted_message(engine, auth_job.id), auth_lease)
        assert auth_error.value.error_code == "source_authentication_required"
        assert auth_error.value.category is JobFailureCategory.AUTHENTICATION_REQUIRED
        with Session(engine) as session:
            auth_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.target_hash
                    == hashlib.sha256(f"{run.configuration_ref}\0auth challenge".encode()).digest(),
                )
            )
            assert auth_coverage is not None
            assert (auth_coverage.status, auth_coverage.stop_reason, auth_coverage.page_count) == (
                "partial",
                "authentication_required",
                1,
            )
            assert session.get(Job, auth_job.id).requests_sent == 1

        with Session(engine) as session:
            rate_run = run.model_copy(
                update={"run_id": uuid4(), "primary_query": "rate challenge", "max_seconds": 90}
            )
            rate_job = JobService(session, clock=lambda: now).accept(
                owner_id=owner_id, command=plan_keyword_discovery(rate_run)[0]
            )
            rate_lease = JobExecutionService(session, lease_seconds=60, clock=lambda: now).acquire(
                job_id=rate_job.id, worker_id="controlled-rate"
            )
        with pytest.raises(JobExecutionFailure) as rate_error:
            KeywordDiscoveryExecutor(
                sessionmaker(bind=engine),
                lease_seconds=60,
                component_key="collector.controlled",
                adapter_factory=lambda before, _cancelled, _limit, _seconds: (
                    ControlledStoppedAdapter(
                        before, SourceStopReason.RATE_LIMITED, now + timedelta(seconds=60)
                    )
                ),
                clock=lambda: now,
            ).execute(_accepted_message(engine, rate_job.id), rate_lease)
        assert rate_error.value.error_code == "source_rate_limited"
        assert rate_error.value.category is JobFailureCategory.RATE_LIMITED
        assert rate_error.value.retry_at == now + timedelta(seconds=60)
        assert rate_error.value.max_attempts == 3
        with Session(engine) as session:
            JobExecutionService(session, lease_seconds=60, clock=lambda: now).record_failure(
                rate_lease,
                message=MessageReference(
                    message_id=_accepted_message(engine, rate_job.id).message_id,
                    topic="hotkey.jobs.accepted.v2",
                    partition=0,
                    offset=37,
                ),
                failure=rate_error.value,
            )
            rate_state = session.get(Job, rate_job.id)
            assert rate_state is not None and rate_state.status == "queued"
            retry_outbox = session.scalar(
                select(OutboxMessage).where(
                    OutboxMessage.aggregate_id == rate_job.id,
                    OutboxMessage.dispatch_sequence == 2,
                )
            )
            assert retry_outbox is not None
            retry_message = JobRetryScheduledMessage.model_validate(
                {
                    "schema_version": 1,
                    "message_id": retry_outbox.id,
                    "event_type": retry_outbox.event_type,
                    **retry_outbox.payload,
                }
            )
            retry_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: now + timedelta(seconds=60)
            ).acquire(job_id=rate_job.id, worker_id="controlled-rate-retry")

        class RateRecoveredAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, request: SearchRequest) -> SourcePage:
                assert request.page_token is None
                assert self._before_request(1)
                return _page(
                    now + timedelta(seconds=60),
                    SourcePageState.COMPLETE,
                    (_post("rate-recovered", start + timedelta(minutes=5)),),
                )

        resumed_lease, resumed_completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda before, _cancelled, _limit, remaining: (
                RateRecoveredAdapter(before)
                if 0 < remaining <= 30
                else pytest.fail("retry must receive only its remaining time budget")
            ),
            clock=lambda: now + timedelta(seconds=60),
        ).execute(retry_message, retry_lease)
        assert resumed_lease.checkpoint_sequence == 2
        assert resumed_completion.status is JobStatus.PARTIALLY_SUCCEEDED
        with Session(engine) as session:
            rate_state = session.get(Job, rate_job.id)
            assert rate_state is not None
            assert (rate_state.requests_sent, rate_state.items_saved) == (2, 1)

        with Session(engine) as session:
            deadline_run = run.model_copy(
                update={
                    "run_id": uuid4(),
                    "primary_query": "deadline query",
                    "max_seconds": 1,
                }
            )
            deadline_job = JobService(session, clock=lambda: now).accept(
                owner_id=owner_id, command=plan_keyword_discovery(deadline_run)[0]
            )
            deadline_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: now
            ).acquire(job_id=deadline_job.id, worker_id="controlled-deadline")
        expired_lease, expired = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda _before, _cancelled, _limit, _seconds: pytest.fail(
                "expired search must not construct a source adapter"
            ),
            clock=lambda: now + timedelta(seconds=2),
        ).execute(_accepted_message(engine, deadline_job.id), deadline_lease)
        assert expired_lease.checkpoint_sequence == 0
        assert expired.status is JobStatus.PARTIALLY_SUCCEEDED
        assert expired.failure is not None
        assert expired.failure.error_code == "search_time_budget_exhausted"
        with Session(engine) as session:
            deadline_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.target_hash
                    == hashlib.sha256(f"{run.configuration_ref}\0deadline query".encode()).digest(),
                )
            )
            assert deadline_coverage is not None
            assert (
                deadline_coverage.status,
                deadline_coverage.stop_reason,
                deadline_coverage.page_count,
            ) == ("partial", "budget_exhausted", 0)
            assert session.get(Job, deadline_job.id).requests_sent == 0

        late_at = now + timedelta(seconds=61)
        with Session(engine) as session:
            late_run = run.model_copy(
                update={
                    "run_id": uuid4(),
                    "primary_query": "late rate challenge",
                    "latest_max_pages": 1,
                }
            )
            late_job = JobService(session, clock=lambda: late_at).accept(
                owner_id=owner_id, command=plan_keyword_discovery(late_run)[0]
            )
            late_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: late_at
            ).acquire(job_id=late_job.id, worker_id="controlled-late-rate")
        with pytest.raises(JobExecutionFailure) as late_error:
            KeywordDiscoveryExecutor(
                sessionmaker(bind=engine),
                lease_seconds=60,
                component_key="collector.controlled",
                adapter_factory=lambda before, _cancelled, _limit, _seconds: (
                    ControlledStoppedAdapter(
                        before, SourceStopReason.RATE_LIMITED, late_at + timedelta(seconds=60)
                    )
                ),
                clock=lambda: late_at,
            ).execute(_accepted_message(engine, late_job.id), late_lease)
        assert late_error.value.category is JobFailureCategory.RATE_LIMITED
        assert late_error.value.retry_at is None
        assert late_error.value.max_attempts is None
        assert late_error.value.manual_retry_allowed is False

        with Session(engine) as session:
            cancel_run = run.model_copy(
                update={"run_id": uuid4(), "primary_query": "cancel challenge"}
            )
            cancel_job = JobService(session, clock=lambda: late_at).accept(
                owner_id=owner_id, command=plan_keyword_discovery(cancel_run)[0]
            )
            cancel_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: late_at
            ).acquire(job_id=cancel_job.id, worker_id="controlled-cancel")

        class CancelledSearchAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, _request: SearchRequest) -> SourcePage:
                assert self._before_request(1)
                with Session(engine) as cancel_session:
                    JobService(cancel_session, clock=lambda: late_at).request_cancel(
                        owner_id=owner_id, job_id=cancel_job.id
                    )
                return _page(
                    late_at,
                    SourcePageState.MORE,
                    (_post("cancelled", start + timedelta(minutes=6)),),
                    "cancel-cursor",
                )

        cancel_message = _accepted_message(engine, cancel_job.id)
        cancelled_lease, cancelled_completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda before, _cancelled, _limit, _seconds: CancelledSearchAdapter(
                before
            ),
            clock=lambda: late_at,
        ).execute(cancel_message, cancel_lease)
        with Session(engine) as session:
            JobExecutionService(session, lease_seconds=60, clock=lambda: late_at).complete(
                cancelled_lease,
                message=MessageReference(
                    message_id=cancel_message.message_id,
                    topic="hotkey.jobs.accepted.v2",
                    partition=0,
                    offset=38,
                ),
                completion=cancelled_completion,
            )
            cancel_state = session.get(Job, cancel_job.id)
            assert cancel_state is not None
            assert (cancel_state.status, cancel_state.requests_sent, cancel_state.items_saved) == (
                "cancelled",
                1,
                0,
            )
            assert (
                session.scalar(
                    select(ContentDiscovery).where(ContentDiscovery.job_id == cancel_job.id)
                )
                is None
            )
            assert (
                session.execute(
                    text(
                        "SELECT outcome FROM resource_usage_attempts "
                        "WHERE owner_id = :owner_id AND operation_id = :operation_id"
                    ),
                    {
                        "owner_id": owner_id,
                        "operation_id": plan_keyword_discovery(cancel_run)[0].operation_id,
                    },
                ).scalar_one()
                == "failed"
            )
            cancel_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.target_hash
                    == hashlib.sha256(
                        f"{run.configuration_ref}\0cancel challenge".encode()
                    ).digest(),
                )
            )
            assert cancel_coverage is not None
            assert (
                cancel_coverage.status,
                cancel_coverage.stop_reason,
                cancel_coverage.page_count,
            ) == ("partial", "cancelled", 0)

        progress_clock = [late_at]
        with Session(engine) as session:
            progress_run = run.model_copy(
                update={
                    "run_id": uuid4(),
                    "primary_query": "mid-run deadline",
                    "max_seconds": 1,
                }
            )
            progress_job = JobService(session, clock=lambda: progress_clock[0]).accept(
                owner_id=owner_id, command=plan_keyword_discovery(progress_run)[0]
            )
            progress_lease = JobExecutionService(
                session, lease_seconds=60, clock=lambda: progress_clock[0]
            ).acquire(job_id=progress_job.id, worker_id="controlled-mid-deadline")

        class ExpiringSearchAdapter:
            source_key = "x"
            capabilities = frozenset({SourceCapability.SEARCH})

            def __init__(self, before_request: Callable[[int], bool]) -> None:
                self._before_request = before_request

            def fetch_page(self, _request: SearchRequest) -> SourcePage:
                assert self._before_request(1)
                progress_clock[0] = late_at + timedelta(seconds=2)
                return _page(
                    late_at,
                    SourcePageState.MORE,
                    (_post("mid-deadline", start + timedelta(minutes=7)),),
                    "next-private-cursor",
                )

        progress_renewed, progress_completion = KeywordDiscoveryExecutor(
            sessionmaker(bind=engine),
            lease_seconds=60,
            component_key="collector.controlled",
            adapter_factory=lambda before, _cancelled, _limit, _seconds: ExpiringSearchAdapter(
                before
            ),
            clock=lambda: progress_clock[0],
        ).execute(_accepted_message(engine, progress_job.id), progress_lease)
        assert progress_renewed.checkpoint_sequence == 1
        assert progress_completion.status is JobStatus.PARTIALLY_SUCCEEDED
        assert progress_completion.failure is not None
        assert progress_completion.failure.error_code == "search_time_budget_exhausted"
        with Session(engine) as session:
            progress_coverage = session.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.target_hash
                    == hashlib.sha256(
                        f"{run.configuration_ref}\0mid-run deadline".encode()
                    ).digest(),
                )
            )
            assert progress_coverage is not None
            assert (
                progress_coverage.status,
                progress_coverage.stop_reason,
                progress_coverage.page_count,
            ) == ("partial", "budget_exhausted", 1)
            assert session.get(Job, progress_job.id).items_saved == 1
    finally:
        with engine.begin() as connection:
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            connection.execute(
                text("DELETE FROM content_records WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM source_connection_versions WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(
                text("DELETE FROM monitor_topics WHERE id = :topic_id"),
                {"topic_id": topic_id},
            )
            connection.execute(text("DELETE FROM identity_users WHERE id = :id"), {"id": owner_id})
        engine.dispose()
