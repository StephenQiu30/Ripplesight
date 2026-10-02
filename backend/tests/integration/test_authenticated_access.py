from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from tests.conftest import authenticated_owner_id
from tests.integration.test_monitor_topics import (
    monitor_topic_client as _topic_client,  # noqa: F401
)


def test_openapi_declares_session_identity_and_cookie_security(app: FastAPI) -> None:
    schema = app.openapi()
    assert "/api/identity/sessions" in schema["paths"]
    assert "/api/identity/session" in schema["paths"]
    assert "IdentitySessionView" in schema["components"]["schemas"]
    schemes = schema["components"]["securitySchemes"]
    assert any(
        value == {"type": "apiKey", "in": "cookie", "name": "hotkey_session"}
        for value in schemes.values()
    )
    for path in (
        "/api/topics",
        "/api/contents",
        "/api/source-capabilities",
        "/api/hotlists/sources",
    ):
        assert schema["paths"][path]["get"].get("security"), path
    assert not schema["paths"]["/api/identity/options"]["get"].get("security")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"), (("GET", "/api/identity/workspace"), ("POST", "/api/identity/initialize"))
)
async def test_obsolete_identity_endpoints_return_404(app: FastAPI, method: str, path: str) -> None:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.request(method, path)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "set-cookie" not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    (
        "/api/topics",
        "/api/contents",
        "/api/source-capabilities",
        "/api/hotlists/sources",
        "/api/identity/session",
        "/feed.xml",
        "/selected.md",
        "/mcp",
    ),
)
async def test_anonymous_business_reads_require_a_real_session(app: FastAPI, path: str) -> None:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(path)
    assert response.status_code == 401, response.text
    assert response.json()["code"] == "invalid_session"
    assert "set-cookie" not in response.headers


def test_authenticated_business_writes_require_session_bound_csrf(
    request: pytest.FixtureRequest,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    for path in (
        "/api/topics",
        "/api/contents",
        "/api/source-capabilities",
        "/api/hotlists/sources",
    ):
        assert client.get(path).status_code == 200
    payload = {"name": "Personal topic", "match_any": ["AI"], "match_all": [], "exclude": []}
    for headers in ({}, {"X-HotKey-CSRF": "wrong"}, {"X-HotKey-CSRF": "1"}):
        denied = client.post("/api/topics", headers=headers, json=payload)
        assert denied.status_code == 403
        assert denied.json()["code"] == "csrf_invalid"
    created = client.post(
        "/api/topics", headers={"X-HotKey-CSRF": client.cookies["hotkey_csrf"]}, json=payload
    )
    assert created.status_code == 201, created.text
    assert client.get(created.headers["location"]).json() == created.json()
    with client.app.state.session_factory() as session:
        owner = authenticated_owner_id(session)
        assert session.scalar(text("SELECT owner_id FROM monitor_topics")) == owner
        assert session.scalar(text("SELECT created_by FROM monitor_topic_versions")) == owner
