from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from tests.integration.test_monitor_topics import _TRUNCATE, _csrf_headers, _initialize

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from content.discovery import plan_single_keyword_discovery
from content.discovery_execution import KeywordDiscoveryExecutor
from content.hotlist_execution import HotlistExecutor
from content.schemas import KeywordDiscoveryRunInput
from core.config import Settings
from jobs.execution import JobExecutionService, MessageReference
from jobs.models import OutboxMessage
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    JobAcceptedMessage,
)
from jobs.services import JobService, ResourceBudgetService
from main import create_app
from sources.adapters.hackernews import HackerNewsAdapter
from sources.adapters.rss import RssSourceAdapter
from sources.adapters.web_search import WebSearchAdapter
from sources.contracts import SearchRequest, SourcePageState
from worker.scheduler import (
    enqueue_due_collections_in_transaction,
    enqueue_due_hotlists_in_transaction,
)


@pytest.fixture
def monitor_topic_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(_TRUNCATE))
    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
        bootstrap_token="monitor-topics-isolated-bootstrap-token",
    )
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


@pytest.mark.parametrize("live", [False, True], ids=["controlled", "live"])
def test_hackernews_scheduled_window_reconciles_coverage_api(
    monitor_topic_client: TestClient, live: bool
) -> None:
    _scheduled_keyword_window_reconciles_coverage_api(monitor_topic_client, "hackernews", live)


@pytest.mark.parametrize("live", [False, True], ids=["controlled", "live"])
def test_google_news_scheduled_window_reconciles_coverage_api(
    monitor_topic_client: TestClient, live: bool
) -> None:
    _scheduled_keyword_window_reconciles_coverage_api(monitor_topic_client, "google_news", live)


@pytest.mark.parametrize("live", [False, True], ids=["controlled", "live"])
def test_searxng_scheduled_window_reconciles_coverage_api(
    monitor_topic_client: TestClient, live: bool
) -> None:
    _scheduled_keyword_window_reconciles_coverage_api(monitor_topic_client, "news_search", live)


@pytest.mark.parametrize("live", [False, True], ids=["controlled", "live"])
def test_36kr_newsflashes_scheduled_window_reconciles_coverage_api(
    monitor_topic_client: TestClient, live: bool
) -> None:
    _scheduled_keyword_window_reconciles_coverage_api(monitor_topic_client, "rss_36kr", live)


def _scheduled_keyword_window_reconciles_coverage_api(
    monitor_topic_client: TestClient, source_key: str, live: bool
) -> None:
    live_flag = {
        "hackernews": "HOTKEY_TEST_LIVE_HN",
        "google_news": "HOTKEY_TEST_LIVE_GOOGLE_NEWS",
        "news_search": "HOTKEY_TEST_LIVE_SEARXNG",
        "rss_36kr": "HOTKEY_TEST_LIVE_36KR_NEWSFLASHES",
    }[source_key]
    if live and os.getenv(live_flag) != "1":
        pytest.skip(f"{live_flag}=1 is required for an actual source request")

    _initialize(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
        assert owner_id is not None
        preset = SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS[source_key]
        )
        ResourceBudgetService(session).save_budget_policy_in_transaction(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.live-coverage-hour",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=datetime.now(UTC) - timedelta(seconds=10),
                enabled=True,
            ),
        )
    keyword = "人工智能" if source_key == "rss_36kr" else "AI"
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={
            "name": f"{source_key} 真实覆盖对账",
            "match_any": [keyword],
            "match_all": [],
            "exclude": [],
            "source_keys": [source_key],
            "collection_interval_seconds": 600,
        },
    )
    assert created.status_code == 201, created.json()
    topic_id = UUID(created.json()["id"])
    resumed = monitor_topic_client.post(
        created.headers["location"] + "/resume",
        headers=_csrf_headers(monitor_topic_client),
    )
    assert resumed.status_code == 200, resumed.json()

    due_at = datetime.now(UTC)
    with factory.begin() as session:
        session.execute(
            text("UPDATE monitor_schedules SET next_run_at = :due_at WHERE topic_id = :topic_id"),
            {"due_at": due_at, "topic_id": topic_id},
        )
        assert enqueue_due_collections_in_transaction(session, due_at) == 1
    with factory() as session:
        due = session.execute(
            text(
                "SELECT id, job_id, window_start, window_end, connection_version "
                "FROM collection_due_windows WHERE owner_id = :owner_id "
                "AND topic_id = :topic_id AND due_at = :due_at"
            ),
            {"owner_id": owner_id, "topic_id": topic_id, "due_at": due_at},
        ).one()
        outbox = session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == due.job_id)
        )
        assert outbox is not None
        accepted = JobAcceptedMessage.model_validate(
            {
                "schema_version": 2,
                "message_id": outbox.id,
                "event_type": "job.accepted.v2",
                **outbox.payload,
            }
        )
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=60).acquire(
            job_id=due.job_id, worker_id=f"{source_key}-live-coverage"
        )

    def adapter_factory(
        before: Callable[[int], bool],
        cancelled: Callable[[], bool],
        max_requests: int,
        max_seconds: float,
    ) -> HackerNewsAdapter | RssSourceAdapter | WebSearchAdapter:
        if source_key == "hackernews":
            return HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=(
                    None
                    if live
                    else httpx.MockTransport(
                        lambda _request: httpx.Response(
                            200,
                            json={
                                "hits": [{"objectID": "000201", "title": "AI coverage"}],
                                "nbPages": 1,
                            },
                        )
                    )
                ),
            )
        if source_key == "news_search":
            return WebSearchAdapter(
                source_key="news_search",
                base_url="http://127.0.0.1:8888",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=(
                    None
                    if live
                    else httpx.MockTransport(
                        lambda request: httpx.Response(
                            200,
                            json={
                                "query": request.url.params["q"],
                                "results": (
                                    [
                                        {
                                            "url": "https://example.com/ai?topic=go&utm_source=search",
                                            "title": "AI coverage",
                                            "content": "AI coverage summary",
                                            "engine": "duckduckgo news",
                                        }
                                    ]
                                    if request.url.params["pageno"] == "1"
                                    else []
                                ),
                                "unresponsive_engines": [],
                            },
                        )
                    )
                ),
            )
        if source_key == "rss_36kr":
            return RssSourceAdapter(
                source_key="rss_36kr",
                feed_url_template="http://127.0.0.1:1200/36kr/newsflashes",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=(
                    None
                    if live
                    else httpx.MockTransport(
                        lambda request: httpx.Response(
                            200,
                            text=(
                                "<rss version='2.0'><channel><title>36Kr</title>"
                                "<lastBuildDate>Sat, 26 Sep 2026 20:00:00 GMT</lastBuildDate>"
                                "<item><title>人工智能 coverage</title>"
                                "<guid>https://www.36kr.com/newsflashes/controlled</guid>"
                                "<link>https://www.36kr.com/newsflashes/controlled</link>"
                                "</item></channel></rss>"
                            ),
                        )
                    )
                ),
            )
        return RssSourceAdapter(
            source_key="google_news",
            feed_url_template=str(SOURCE_PRESETS["google_news"].config["feed_url_template"]),
            allowed_hosts=frozenset({"news.google.com"}),
            before_request=before,
            cancelled=cancelled,
            max_requests=max_requests,
            max_seconds=max_seconds,
            transport=(
                None
                if live
                else httpx.MockTransport(
                    lambda _request: httpx.Response(
                        200,
                        text=(
                            "<rss version='2.0'><channel><title>AI</title><item>"
                            "<title>AI coverage</title><guid>google-coverage</guid>"
                            "<link>https://news.google.com/articles/coverage</link>"
                            "</item></channel></rss>"
                        ),
                    )
                )
            ),
        )

    renewed, completion = KeywordDiscoveryExecutor(
        factory,
        lease_seconds=60,
        adapter_factory=adapter_factory,
    ).execute(accepted, lease)
    with factory() as session:
        JobExecutionService(session, lease_seconds=60).complete(
            renewed,
            message=MessageReference(
                message_id=accepted.message_id,
                topic=outbox.topic,
                partition=0,
                offset=0,
            ),
            completion=completion,
        )

    response = monitor_topic_client.get(
        "/api/collection-coverage",
        params={
            "start": (due_at - timedelta(minutes=1)).isoformat(),
            "end": (due_at + timedelta(minutes=1)).isoformat(),
            "source_key": source_key,
            "capability": "search",
            "topic_id": str(topic_id),
        },
    )
    assert response.status_code == 200, response.json()
    rows = response.json()["items"]
    assert len(rows) == 1
    row = rows[0]
    detail = monitor_topic_client.get(f"/api/collection-coverage/{due.id}")
    assert detail.status_code == 200
    assert detail.json() == row

    with factory() as session:
        facts = session.execute(
            text(
                "SELECT job.operation_id, job.status, job.requests_sent, job.items_saved, "
                "(SELECT count(*) FROM job_attempts WHERE job_id = job.id), "
                "(SELECT count(*) FROM resource_usage_attempts "
                " WHERE operation_id = job.operation_id), "
                "(SELECT count(*) FROM resource_budget_reservations "
                " WHERE operation_id = job.operation_id), "
                "(SELECT count(*) FROM content_discoveries WHERE job_id = job.id), "
                "(SELECT count(*) FROM content_observations WHERE job_id = job.id), "
                "(SELECT coalesce(sum(page_count), 0) FROM coverage_windows "
                " WHERE last_job_id = job.id) "
                "FROM jobs AS job WHERE job.id = :job_id"
            ),
            {"job_id": due.job_id},
        ).one()
        content_ids = set(
            session.scalars(
                text("SELECT content_id FROM content_discoveries WHERE job_id = :job_id"),
                {"job_id": due.job_id},
            ).all()
        )
        sample = session.execute(
            text(
                "SELECT record.external_id, observation.canonical_url "
                "FROM content_records AS record "
                "JOIN content_discoveries AS discovery ON discovery.content_id = record.id "
                "JOIN content_observations AS observation ON observation.content_id = record.id "
                "WHERE discovery.job_id = :job_id ORDER BY record.external_id LIMIT 1"
            ),
            {"job_id": due.job_id},
        ).first()
    assert sample is not None
    if source_key == "hackernews":
        assert sample.canonical_url == f"https://news.ycombinator.com/item?id={sample.external_id}"
    elif source_key == "google_news":
        assert sample.canonical_url.startswith("https://news.google.com/")
    elif not live:
        if source_key == "rss_36kr":
            assert sample.canonical_url == "https://www.36kr.com/newsflashes/controlled"
        else:
            assert sample.canonical_url == "https://example.com/ai?topic=go"
    else:
        assert sample.canonical_url.startswith(
            "https://www.36kr.com/newsflashes/" if source_key == "rss_36kr" else "https://"
        )
    assert row["window_id"] == str(due.id)
    assert row["job_id"] == str(due.job_id)
    assert row["admission_state"] == "accepted"
    assert row["job_status"] == facts.status
    assert row["job_connection_version"] == due.connection_version
    assert row["current_connection_version"] == due.connection_version
    assert row["attempts"] == facts[4] == 1
    assert row["request_count"] == row["request_attempt_count"] == facts.requests_sent == facts[5]
    assert row["page_count"] == facts[9] == facts.requests_sent
    assert row["inserted_count"] == facts[7] == facts[8] == facts.items_saved
    assert set(row["content_ids"]) == {str(content_id) for content_id in content_ids}
    assert facts[6] == 2 * facts.requests_sent
    assert row["budget_consumed"] == facts.requests_sent
    assert row["budget_reserved"] == 0
    assert row["coverage_status"] == "partial"
    assert row["terminal_evidence"] is False
    expected_gap = (
        row["gaps"][0]["reason"] if source_key == "news_search" and live else "unverified_terminal"
    )
    if source_key == "news_search" and live:
        assert expected_gap in {"budget_exhausted", "unverified_terminal"}
    assert row["gaps"] == [
        {
            "start": due.window_start.isoformat().replace("+00:00", "Z"),
            "end": due.window_end.isoformat().replace("+00:00", "Z"),
            "reason": expected_gap,
        }
    ]
    if source_key == "news_search":
        with factory() as session:
            checkpoint = session.scalar(
                text("SELECT checkpoint FROM jobs WHERE id = :job_id"),
                {"job_id": due.job_id},
            )
        assert checkpoint["source.engine"] == "duckduckgo news"
        assert checkpoint["cursor.pages"] == facts[9]
        if live:
            assert checkpoint["source.actual_engine"] == "duckduckgo news"
            repeat = WebSearchAdapter(
                source_key="news_search",
                base_url="http://127.0.0.1:8888",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=lambda attempt: attempt <= 3,
                max_requests=3,
            )
            repeated_ids: set[str] = set()
            token: str | None = None
            for _ in range(3):
                repeated_page = repeat.fetch_page(
                    SearchRequest(
                        source_key="news_search",
                        query="AI",
                        page_size=100,
                        page_token=token,
                    )
                )
                repeated_ids.update(post.external_id for post in repeated_page.items)
                if repeated_page.state is not SourcePageState.MORE:
                    break
                token = repeated_page.next_page_token
            assert sample.external_id in repeated_ids
    if source_key == "rss_36kr":
        with factory() as session:
            checkpoint = session.scalar(
                text("SELECT checkpoint FROM jobs WHERE id = :job_id"),
                {"job_id": due.job_id},
            )
        assert checkpoint["source.feed_updated_at"]
        assert checkpoint["cursor.pages"] == facts[9] == 1
        if live:
            repeat = RssSourceAdapter(
                source_key="rss_36kr",
                feed_url_template="http://127.0.0.1:1200/36kr/newsflashes",
                allowed_hosts=frozenset({"127.0.0.1"}),
                before_request=lambda attempt: attempt <= 1,
            ).fetch_page(SearchRequest(source_key="rss_36kr", query=keyword, page_size=100))
            assert sample.external_id in {post.external_id for post in repeat.items}
            with factory.begin() as session:
                second = JobService(session).accept_in_transaction(
                    owner_id=owner_id,
                    command=plan_single_keyword_discovery(
                        KeywordDiscoveryRunInput(
                            run_id=uuid4(),
                            configuration_ref=f"topic:{topic_id}",
                            configuration_version=1,
                            source_key="rss_36kr",
                            connection_id=preset.connection_id,
                            connection_version=preset.connection_version,
                            primary_query=keyword,
                            starts_at=due.window_start,
                            ends_at=due.window_end,
                            page_size=100,
                            latest_max_pages=1,
                            latest_max_requests=1,
                            top_max_pages=1,
                            top_max_requests=1,
                            max_seconds=90,
                        )
                    ),
                )
            with factory() as session:
                second_lease = JobExecutionService(session, lease_seconds=60).acquire(
                    job_id=second.id, worker_id="rss-36kr-live-repeat"
                )
                second_outbox = session.scalar(
                    select(OutboxMessage).where(OutboxMessage.aggregate_id == second.id)
                )
                assert second_outbox is not None
                second_message = JobAcceptedMessage.model_validate(
                    {
                        "schema_version": 2,
                        "message_id": second_outbox.id,
                        "event_type": "job.accepted.v2",
                        **second_outbox.payload,
                    }
                )
            second_renewed, second_completion = KeywordDiscoveryExecutor(
                factory,
                lease_seconds=60,
                adapter_factory=adapter_factory,
            ).execute(second_message, second_lease)
            with factory() as session:
                JobExecutionService(session, lease_seconds=60).complete(
                    second_renewed,
                    message=MessageReference(
                        message_id=second_message.message_id,
                        topic=second_outbox.topic,
                        partition=0,
                        offset=1,
                    ),
                    completion=second_completion,
                )
            with factory() as session:
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM content_records "
                            "WHERE owner_id = :owner_id AND source_key = 'rss_36kr' "
                            "AND external_id = :external_id"
                        ),
                        {"owner_id": owner_id, "external_id": sample.external_id},
                    )
                    == 1
                )
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM content_observations AS observation "
                            "JOIN content_records AS record ON record.id = observation.content_id "
                            "WHERE record.owner_id = :owner_id AND record.source_key = 'rss_36kr' "
                            "AND record.external_id = :external_id"
                        ),
                        {"owner_id": owner_id, "external_id": sample.external_id},
                    )
                    == 2
                )
            print("rss_36kr live repeat:", second.id, sample.external_id)
    print(
        f"{source_key} scheduled coverage:",
        "live" if live else "controlled",
        due.id,
        due.job_id,
        due.window_start.isoformat(),
        due.window_end.isoformat(),
        facts.requests_sent,
        facts.items_saved,
        sample.external_id,
        sample.canonical_url,
        row["gaps"][0]["reason"],
    )


def test_live_rsshub_hotlist_window_reconciles_coverage_api(
    monitor_topic_client: TestClient,
) -> None:
    if os.getenv("HOTKEY_TEST_LIVE_RSSHUB") != "1":
        pytest.skip("HOTKEY_TEST_LIVE_RSSHUB=1 requires the local RSSHub service")

    _initialize(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    now = datetime.now(UTC)
    due_at = datetime.fromtimestamp((int(now.timestamp()) // 1800) * 1800, UTC)
    with factory.begin() as session:
        owner_id = session.scalar(text("SELECT id FROM identity_users"))
        assert owner_id is not None
        preset_service = SourcePresetService(session, clock=lambda: due_at - timedelta(seconds=1))
        preset_service.apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hotlist_36kr"]
        )
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.live-hotlist-hour",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=due_at - timedelta(seconds=10),
                enabled=True,
            ),
        )
    with factory.begin() as session:
        assert enqueue_due_hotlists_in_transaction(session, now) == 1
    with factory() as session:
        due = session.execute(
            text(
                "SELECT id, job_id, window_start, window_end, connection_version "
                "FROM collection_due_windows WHERE owner_id = :owner_id "
                "AND source_key = 'hotlist_36kr' AND due_at = :due_at"
            ),
            {"owner_id": owner_id, "due_at": due_at},
        ).one()
        outbox = session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == due.job_id)
        )
        assert outbox is not None
        accepted = JobAcceptedMessage.model_validate(
            {
                "schema_version": 2,
                "message_id": outbox.id,
                "event_type": "job.accepted.v2",
                **outbox.payload,
            }
        )
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=60).acquire(
            job_id=due.job_id, worker_id="rsshub-live-coverage"
        )
    renewed, completion = HotlistExecutor(factory, lease_seconds=60).execute(accepted, lease)
    with factory() as session:
        JobExecutionService(session, lease_seconds=60).complete(
            renewed,
            message=MessageReference(
                message_id=accepted.message_id,
                topic=outbox.topic,
                partition=0,
                offset=0,
            ),
            completion=completion,
        )

    response = monitor_topic_client.get(
        "/api/collection-coverage",
        params={
            "start": (due_at - timedelta(minutes=1)).isoformat(),
            "end": (due_at + timedelta(minutes=1)).isoformat(),
            "source_key": "hotlist_36kr",
            "capability": "hotlist",
        },
    )
    assert response.status_code == 200, response.json()
    rows = response.json()["items"]
    assert len(rows) == 1
    row = rows[0]
    detail = monitor_topic_client.get(f"/api/collection-coverage/{due.id}")
    assert detail.status_code == 200
    assert detail.json() == row
    with factory() as session:
        facts = session.execute(
            text(
                "SELECT job.status, job.requests_sent, snapshot.id AS snapshot_id, "
                "snapshot.entry_count, "
                "(SELECT count(*) FROM hotlist_entries WHERE snapshot_id = snapshot.id), "
                "(SELECT count(*) FROM resource_usage_attempts "
                " WHERE operation_id = job.operation_id), "
                "(SELECT count(*) FROM resource_budget_reservations "
                " WHERE operation_id = job.operation_id), "
                "(SELECT count(*) FROM job_attempts WHERE job_id = job.id) "
                "FROM jobs AS job JOIN hotlist_snapshots AS snapshot ON snapshot.job_id = job.id "
                "WHERE job.id = :job_id"
            ),
            {"job_id": due.job_id},
        ).one()
    assert row["window_id"] == str(due.id)
    assert row["job_id"] == str(due.job_id)
    assert row["admission_state"] == "accepted"
    assert row["job_status"] == facts.status == "succeeded"
    assert row["job_connection_version"] == due.connection_version
    assert row["current_connection_version"] == due.connection_version
    assert row["attempts"] == facts[7] == 1
    assert row["request_count"] == row["request_attempt_count"] == facts.requests_sent == 1
    assert row["page_count"] == 1
    assert row["observed_count"] == facts.entry_count == facts[4]
    assert row["snapshot_ids"] == [str(facts.snapshot_id)]
    assert row["budget_consumed"] == facts[5] == 1
    assert row["budget_reserved"] == 0
    assert facts[6] == 2
    assert row["coverage_status"] == ("confirmed" if facts.entry_count else "empty")
    assert row["terminal_evidence"] is True
    assert row["gaps"] == []
    print(
        "RSSHub hotlist scheduled coverage:",
        due.id,
        due.job_id,
        due.window_start.isoformat(),
        due.window_end.isoformat(),
        facts.snapshot_id,
        facts.entry_count,
    )
