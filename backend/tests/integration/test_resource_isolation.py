from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.conftest import authenticate_test_client, authenticated_owner_id
from tests.integration.test_monitor_topics import (
    monitor_topic_client as _topic_client,  # noqa: F401
)

from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/topics/{topic_id}", None),
        (
            "PATCH",
            "/api/topics/{topic_id}",
            {
                "name": "changed",
                "match_any": ["term"],
                "match_all": [],
                "exclude": [],
                "expected_version": 1,
            },
        ),
        ("POST", "/api/topics/{topic_id}/clone", None),
        ("POST", "/api/topics/{topic_id}/pause", None),
        ("POST", "/api/topics/{topic_id}/resume", None),
        ("POST", "/api/topics/{topic_id}/archive", None),
        ("GET", "/api/jobs/{job_id}", None),
        ("POST", "/api/jobs/{job_id}/cancel", None),
        ("POST", "/api/jobs/{job_id}/retry", None),
    ],
)
def test_internal_partition_cannot_read_or_mutate_other_partition_resources(
    request: pytest.FixtureRequest, method: str, path: str, payload: dict | None
) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    headers = {"X-HotKey-CSRF": monitor_topic_client.cookies["hotkey_csrf"]}
    topic = monitor_topic_client.post(
        "/api/topics",
        headers=headers,
        json={"name": "partition topic", "match_any": ["term"], "match_all": [], "exclude": []},
    )
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        owner_id = authenticated_owner_id(session)
        job = JobService(session).accept(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=uuid4(),
                kind="monitor.collect",
                observation=JobObservationContext(
                    configuration_ref="partition-config",
                    configuration_version=1,
                ),
                scope={},
            ),
        )
    assert topic.status_code == 201
    topic_id, job_id = topic.json()["id"], str(job.id)
    authenticate_test_client(monitor_topic_client)
    headers = {"X-HotKey-CSRF": monitor_topic_client.cookies["hotkey_csrf"]}
    try:
        denied = monitor_topic_client.request(
            method, path.format(topic_id=topic_id, job_id=job_id), headers=headers, json=payload
        )
        absent = monitor_topic_client.request(
            method, path.format(topic_id=uuid4(), job_id=uuid4()), headers=headers, json=payload
        )
        assert denied.status_code == absent.status_code == 404
        assert denied.json()["code"] == absent.json()["code"] == "resource_not_found"
        assert denied.json()["message"] == absent.json()["message"]
        assert "partition-config" not in denied.text
        assert monitor_topic_client.get("/api/topics").json() == {"items": [], "next_cursor": None}
        assert monitor_topic_client.get("/api/contents").json() == {
            "items": [],
            "next_cursor": None,
        }
        assert denied.headers.get("cache-control") == "no-store"
    finally:
        authenticate_test_client(monitor_topic_client, owner_id=owner_id)
    assert monitor_topic_client.get(f"/api/topics/{topic_id}").json() == topic.json()
    assert monitor_topic_client.get(f"/api/jobs/{job_id}").json()["status"] == "queued"
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM monitor_topic_versions")) == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 1
