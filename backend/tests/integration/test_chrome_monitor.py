from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import authenticate_test_client, authenticated_headers
from tests.unit.sources.test_keyword_demo import identity, transport_handler

from connections import services as connections
from connections.models import SourceConnection
from connections.presets import BILIBILI_CHROME_PRESET
from content import comments_execution, discovery_execution
from content.models import ContentRecord
from core.config import Settings
from jobs.models import Job
from main import create_app
from worker import chrome, scheduler


@pytest.mark.parametrize("risk_stop", [False, True])
def test_chrome_owner_preset_real_pipeline_and_idempotent_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    risk_stop: bool,
) -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("independent database required")
    owner = uuid4()
    settings = Settings(
        environment="test",
        database_url=database_url,
        log_level="ERROR",
        bilibili_chrome_owner_id=owner,
        bilibili_chrome_identity_env=identity(tmp_path),
    )
    # Quiet hours are a separate admission test; this fixture runs at any wall time.
    preset = replace(
        BILIBILI_CHROME_PRESET,
        execution_policy=BILIBILI_CHROME_PRESET.execution_policy.model_copy(
            update={"quiet_windows": ()}
        ),
    )
    monkeypatch.setattr(connections, "BILIBILI_CHROME_PRESET", preset)
    monkeypatch.setattr(chrome, "BILIBILI_CHROME_PRESET", preset)
    for module in (discovery_execution, comments_execution, scheduler):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        response = transport_handler(request, fail_comments=risk_stop)
        if request.url.path.endswith("search/type"):
            data = response.json()
            data["data"]["result"] = [
                dict(
                    data["data"]["result"][0],
                    pubdate=int((datetime.now(UTC) - timedelta(minutes=10)).timestamp()),
                )
            ]
            return httpx.Response(200, json=data)
        return response

    original = discovery_execution.BilibiliChromeAdapter
    for module in (discovery_execution, comments_execution):
        monkeypatch.setattr(
            module,
            "BilibiliChromeAdapter",
            lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)),
        )
    with TestClient(create_app(settings)) as client:
        authenticate_test_client(client, owner_id=uuid4())
        denied = client.post(
            "/api/source-connections/bilibili/chrome", headers=authenticated_headers(client)
        )
        assert denied.status_code == 409
        assert denied.json()["code"] == "connection_credentials_missing"
        authenticate_test_client(client, owner_id=owner)
        response = client.post(
            "/api/source-connections/bilibili/chrome", headers=authenticated_headers(client)
        )
        assert response.status_code == 200, response.json()
        response = client.post(
            "/api/topics",
            headers=authenticated_headers(client),
            json={
                "name": "Chrome monitor",
                "match_any": ["DeepSeek"],
                "match_all": [],
                "exclude": [],
                "source_keys": ["bilibili"],
                "collection_interval_seconds": 3600,
                "weekly_report_enabled": False,
            },
        )
        assert response.status_code == 201, response.json()
        topic_id = response.json()["id"]
        response = client.post(
            f"/api/topics/{topic_id}/resume", headers=authenticated_headers(client)
        )
        assert response.status_code == 200, response.json()
        operation = {"operation_id": str(uuid4()), "source_keys": ["bilibili"]}
        response = client.post(
            f"/api/topics/{topic_id}/runs", headers=authenticated_headers(client), json=operation
        )
        assert response.status_code == 202, response.json()
        factory = client.app.state.session_factory
        assert chrome.run_chrome_round(factory, settings, owner) >= 1
        if risk_stop:
            with factory() as session:
                connection = session.scalar(
                    select(SourceConnection).where(SourceConnection.owner_id == owner)
                )
                assert connection is not None and connection.status == "disabled"
                assert connection.safety_stop_reason == "rate_limited"
            count = len(requests)
            assert chrome.run_chrome_round(factory, settings, owner) == 0
            assert len(requests) == count
            assert (
                client.post(
                    "/api/source-connections/bilibili/chrome", headers=authenticated_headers(client)
                ).status_code
                == 409
            )
            resumed = client.put(
                "/api/source-connections/bilibili",
                headers=authenticated_headers(client),
                json={
                    "status": "active",
                    "expected_version": connection.current_version,
                    "owner_confirmed": True,
                    "allowed_hosts": ["api.bilibili.com", "www.bilibili.com"],
                },
            )
            assert resumed.status_code == 200, resumed.json()
            with factory.begin() as session:
                applied = connections.load_applied_source_presets_in_transaction(
                    session, owner_id=owner, source_keys=("bilibili",)
                )
                assert applied["bilibili"].bilibili_transport == "chrome"
            return
        with factory() as session:
            jobs = session.scalars(select(Job).where(Job.owner_id == owner)).all()
            assert all(job.status == "partially_succeeded" for job in jobs), [
                (job.kind, job.status, job.last_error_code) for job in jobs
            ]
            records = session.scalars(
                select(ContentRecord).where(ContentRecord.owner_id == owner)
            ).all()
            assert {record.object_type for record in records} == {"post", "comment"}
        page = client.get("/api/contents", params={"topic_id": topic_id}).json()
        assert page["items"]
        post_id = next(record.id for record in records if record.object_type == "post")
        comments = client.get(f"/api/contents/{post_id}/comments")
        assert comments.status_code == 200 and len(comments.json()["items"]) == 1
        count = len(requests)
        assert chrome.run_chrome_round(factory, settings, owner) == 0
        assert len(requests) == count

        with factory.begin() as session:
            future = datetime.now(UTC) + timedelta(hours=1, seconds=5)
            assert (
                scheduler.enqueue_due_collections_in_transaction(
                    session, future, owner_id=owner, source_key="bilibili"
                )
                == 1
            )
            assert (
                scheduler.enqueue_due_collections_in_transaction(
                    session, future, owner_id=owner, source_key="bilibili"
                )
                == 0
            )
        authenticate_test_client(client, owner_id=uuid4())
        assert client.get(f"/api/contents/{post_id}").status_code == 404
