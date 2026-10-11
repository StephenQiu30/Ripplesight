from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.integration.test_keyword_discovery import _accepted_message, _post
from tests.integration.test_monitor_topics import _csrf_headers, _topic_payload
from tests.integration.test_topic_runs import _ready_topic
from tests.integration.test_topic_runs import monitor_topic_client as monitor_topic_client

from content.discovery_execution import KeywordDiscoveryExecutor
from jobs.execution import JobExecutionService
from jobs.models import CoverageWindow, Job
from sources.contracts import (
    SearchRequest,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourceStopReason,
)
from worker.scheduler import enqueue_due_collections_in_transaction

CONFIG = {
    "search_language": "en",
    "search_window_seconds": 600,
    "max_queries": 1,
    "max_items_per_query": 3,
    "max_requests_per_query": 3,
}


def configure(client: TestClient, location: str, *, version: int = 1, **config: object) -> dict:
    response = client.patch(
        location,
        headers=_csrf_headers(client),
        json={
            **_topic_payload(),
            "source_keys": ["hackernews"],
            "expected_version": version,
            "collection_interval_seconds": 3600,
            "report_time": "08:00:00",
            "match_any": ["AI", "模型"],
            "match_all": [],
            "exclude": [],
            **CONFIG,
            **config,
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()


@pytest.mark.parametrize("scheduled", [False, True])
def test_settings_version_clone_and_frozen_entry_points(
    monitor_topic_client: TestClient, scheduled: bool
) -> None:
    client = monitor_topic_client
    location = _ready_topic(client, source_keys=("hackernews",), source_min_interval=0)
    topic = configure(client, location)
    assert topic["current_version"] == 2
    assert {key: topic[key] for key in CONFIG} == CONFIG
    assert client.get(location).json() == topic
    clone = client.post(location + "/clone", headers=_csrf_headers(client))
    assert clone.status_code == 201, clone.json()
    assert {key: clone.json()[key] for key in CONFIG} == CONFIG
    payload = {"operation_id": str(uuid4()), "source_keys": ["hackernews"]}
    sessions = client.app.state.session_factory
    if scheduled:
        now = datetime.now(UTC)
        with sessions.begin() as session:
            session.execute(
                text("UPDATE monitor_schedules SET next_run_at=:now WHERE topic_id=:id"),
                {"now": now, "id": topic["id"]},
            )
            assert enqueue_due_collections_in_transaction(session, now) == 1
        with sessions() as session:
            job_id = str(session.scalar(select(Job.id).where(Job.kind == "keyword.search")))
    else:
        accepted = client.post(location + "/runs", headers=_csrf_headers(client), json=payload)
        assert accepted.status_code == 202, accepted.json()
        source = accepted.json()["sources"][0]
        assert len(source["job_ids"]) == 1
        job_id = source["job_ids"][0]
    receipt = client.get(f"/api/jobs/{job_id}").json()["query_plan"]
    assert receipt["max_queries"] == 1
    assert [item["admitted"] for item in receipt["queries"]] == [True, False]
    frozen = receipt["collection"]
    assert frozen["topic"] == CONFIG
    assert frozen["max_items_per_query"] == 3 and frozen["max_requests_per_query"] == 3
    assert datetime.fromisoformat(frozen["ends_at"]) - datetime.fromisoformat(
        frozen["starts_at"]
    ) == timedelta(seconds=600)
    if not scheduled:
        assert source["query_plan"] == receipt
    changed = configure(
        client,
        location,
        version=2,
        search_language="zh",
        search_window_seconds=1200,
        max_queries=2,
        max_items_per_query=8,
        max_requests_per_query=1,
    )
    assert changed["current_version"] == 3
    assert client.get(f"/api/jobs/{job_id}").json()["query_plan"] == receipt
    stale = client.patch(
        location,
        headers=_csrf_headers(client),
        json={**_topic_payload(), **CONFIG, "expected_version": 2},
    )
    assert stale.status_code == 409
    if not scheduled:
        replayed = client.post(location + "/runs", headers=_csrf_headers(client), json=payload)
        assert replayed.status_code == 200 and replayed.json() == accepted.json()
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 1
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0


@pytest.mark.parametrize("missing_time", [False, True])
def test_cross_page_cap_and_language_use_frozen_settings(
    monitor_topic_client: TestClient, missing_time: bool
) -> None:
    client = monitor_topic_client
    location = _ready_topic(client, source_keys=("hackernews",), source_min_interval=0)
    configure(client, location)
    accepted = client.post(
        location + "/runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert accepted.status_code == 202
    job_id = UUID(accepted.json()["sources"][0]["job_ids"][0])
    configure(client, location, version=2, search_language="zh", max_items_per_query=10)
    sessions = client.app.state.session_factory
    engine = sessions.kw["bind"]
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=60).acquire(
            job_id=job_id, worker_id="frozen-config-test"
        )
    now = datetime.now(UTC)
    submitted: list[SearchRequest] = []

    def post(identifier: str, language: str | None, *, unknown_time: bool = False):
        return _post(identifier, now - timedelta(seconds=10), body="AI release").model_copy(
            update={
                "source_key": "hackernews",
                "language": language,
                "published_at": None if unknown_time else now - timedelta(seconds=10),
            }
        )

    class Adapter:
        source_key = "hackernews"
        capabilities = frozenset({SourceCapability.SEARCH})

        def __init__(self, before):
            self.before = before

        def fetch_page(self, request: SearchRequest) -> SourcePage:
            submitted.append(request)
            assert self.before(len(submitted))
            items = (
                (post("unknown", None), post("zh", "zh-Hant"))
                if len(submitted) == 1
                else (post("en", "en-US", unknown_time=missing_time), post("overflow", "en"))
            )
            return SourcePage(
                source_key="hackernews",
                capability=SourceCapability.SEARCH,
                state=SourcePageState.MORE if len(submitted) == 1 else SourcePageState.COMPLETE,
                items=items,
                next_page_token="next" if len(submitted) == 1 else None,
                watermark=None,
                stop_reason=None if len(submitted) == 1 else SourceStopReason.END_OF_RESULTS,
                observed_at=now,
                request_count=1,
                adapter_version="controlled-1",
            )

    renewed, completion = KeywordDiscoveryExecutor(
        sessions,
        lease_seconds=60,
        adapter_factory=lambda before, _cancelled, _limit, _seconds: Adapter(before),
    ).execute(_accepted_message(engine, job_id), lease)
    assert [request.page_size for request in submitted] == [3, 3]
    assert completion.status.value == "partially_succeeded"
    assert renewed.checkpoint["collection.observed_count"] == 4
    assert renewed.checkpoint["collection.language_unknown_count"] == 1
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM content_discoveries")) == (
            0 if missing_time else 1
        )
        assert session.scalar(select(CoverageWindow.status)) == "partial"
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("search_language", "fr"),
        ("search_window_seconds", 599),
        ("search_window_seconds", 2592001),
        ("max_queries", 0),
        ("max_queries", 51),
        ("max_items_per_query", 0),
        ("max_items_per_query", 2001),
        ("max_requests_per_query", 0),
        ("max_requests_per_query", 101),
        ("max_queries", True),
        ("max_queries", 1.5),
    ],
)
def test_invalid_limits_do_not_create_versions(
    monitor_topic_client: TestClient, field: str, value: object
) -> None:
    response = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), field: value},
    )
    assert response.status_code == 422, response.json()
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM monitor_topic_versions")) == 0


@pytest.mark.parametrize(
    "request_limit,expected_saved,expected_pages", [(3, 150, [0, 1]), (1, 100, [0])]
)
def test_native_hn_keeps_page_size_and_obeys_frozen_limits(
    monitor_topic_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    request_limit: int,
    expected_saved: int,
    expected_pages: list[int],
) -> None:
    from dataclasses import replace

    import httpx
    from tests.integration import test_topic_runs

    from connections.presets import SOURCE_PRESETS
    from content.models import ContentRecord
    from sources.adapters.hackernews import HackerNewsAdapter

    preset = SOURCE_PRESETS["hackernews"]
    presets = {
        **SOURCE_PRESETS,
        "hackernews": replace(
            preset,
            execution_policy=preset.execution_policy.model_copy(
                update={"max_items_per_query": 200, "min_interval_seconds": 0}
            ),
        ),
    }
    monkeypatch.setattr("connections.services.SOURCE_PRESETS", presets)
    monkeypatch.setattr(test_topic_runs, "SOURCE_PRESETS", presets)
    client = monitor_topic_client
    location = _ready_topic(client, source_keys=("hackernews",))
    configure(
        client,
        location,
        search_language="any",
        max_items_per_query=150,
        max_requests_per_query=request_limit,
    )
    response = client.post(
        location + "/runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert response.status_code == 202, response.json()
    job_id = UUID(response.json()["sources"][0]["job_ids"][0])
    sessions = client.app.state.session_factory
    with sessions() as session:
        lease = JobExecutionService(session, lease_seconds=60).acquire(
            job_id=job_id, worker_id="native-hn-cap"
        )
    requests = []
    published = int((datetime.now(UTC) - timedelta(seconds=30)).timestamp())

    def handle(request):
        page = int(request.url.params["page"])
        size = int(request.url.params["hitsPerPage"])
        requests.append((page, size))
        hits = [
            {
                "objectID": str(index + 1),
                "title": "AI release",
                "created_at_i": published,
                "points": 1,
                "num_comments": 0,
            }
            for index in range(page * size, min(200, (page + 1) * size))
        ]
        return httpx.Response(
            200,
            json={
                "hits": hits,
                "page": page,
                "hitsPerPage": size,
                "nbHits": 200,
                "nbPages": 2,
                "exhaustiveNbHits": True,
            },
        )

    renewed, completion = KeywordDiscoveryExecutor(
        sessions,
        lease_seconds=60,
        adapter_factory=lambda before, cancelled, limit, seconds: HackerNewsAdapter(
            before_request=before,
            cancelled=cancelled,
            max_requests=limit,
            max_seconds=seconds,
            transport=httpx.MockTransport(handle),
        ),
    ).execute(_accepted_message(sessions.kw["bind"], job_id), lease)
    assert requests == [(page, 100) for page in expected_pages]
    assert completion.status.value == "partially_succeeded"
    assert renewed.checkpoint["collection.observed_count"] == len(expected_pages) * 100
    with sessions() as session:
        identifiers = set(session.scalars(select(ContentRecord.external_id)))
        assert identifiers == {str(index) for index in range(1, expected_saved + 1)}
        assert session.scalar(select(CoverageWindow.status)) == "partial"
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == len(
            expected_pages
        )


def test_update_omitting_new_fields_preserves_collection_settings(
    monitor_topic_client: TestClient,
) -> None:
    client = monitor_topic_client
    location = _ready_topic(client, source_keys=("hackernews",), source_min_interval=0)
    configure(client, location)
    response = client.patch(
        location,
        headers=_csrf_headers(client),
        json={
            **_topic_payload(),
            "source_keys": ["hackernews"],
            "expected_version": 2,
            "match_any": ["AI", "模型"],
            "match_all": [],
            "exclude": [],
            "collection_interval_seconds": 3600,
            "report_time": "08:00:00",
        },
    )
    assert response.status_code == 200, response.json()
    assert response.json()["current_version"] == 2
    assert {key: response.json()[key] for key in CONFIG} == CONFIG
