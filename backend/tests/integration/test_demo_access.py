from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from tests.integration.test_monitor_topics import (
    monitor_topic_client as _topic_client,  # noqa: F401
)

from db.demo import DEFAULT_DEMO_SCOPE_ID


def test_demo_openapi_has_no_account_or_session_contract(app: FastAPI) -> None:
    schema = app.openapi()

    assert not any(path.startswith("/api/identity") for path in schema["paths"])
    assert not schema.get("components", {}).get("securitySchemes")
    assert not any(name.startswith("Identity") for name in schema["components"]["schemas"])
    assert not any(
        operation.get("security")
        for path in schema["paths"].values()
        for operation in path.values()
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("GET", "/api/identity/session"),
        ("GET", "/api/identity/workspace"),
        ("POST", "/api/identity/initialize"),
        ("POST", "/api/identity/sessions"),
        ("DELETE", "/api/identity/session"),
    ),
)
async def test_removed_identity_endpoints_return_404(app: FastAPI, method: str, path: str) -> None:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.request(method, path)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "set-cookie" not in response.headers


def test_anonymous_demo_can_read_and_write_without_a_session(
    request: pytest.FixtureRequest,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    for path in (
        "/api/topics",
        "/api/contents",
        "/api/source-capabilities",
        "/api/hotlists/sources",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert "set-cookie" not in response.headers
    payload = {"name": "Demo topic", "match_any": ["AI"], "match_all": [], "exclude": []}
    for headers in ({}, {"X-HotKey-CSRF": "wrong"}):
        denied = client.post("/api/topics", headers=headers, json=payload)
        assert denied.status_code == 403
        assert denied.json()["code"] == "csrf_invalid"
    created = client.post("/api/topics", headers={"X-HotKey-CSRF": "1"}, json=payload)
    assert created.status_code == 201
    assert "set-cookie" not in created.headers
    assert not client.cookies
    assert client.get(created.headers["location"]).json() == created.json()
    with client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT owner_id FROM monitor_topics")) == DEFAULT_DEMO_SCOPE_ID
        assert (
            session.scalar(text("SELECT created_by FROM monitor_topic_versions"))
            == DEFAULT_DEMO_SCOPE_ID
        )
