from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.dependencies import get_public_publication_scope, get_publication_service
from core.config import Settings
from core.errors import ApplicationError


def test_publication_scope_is_explicit_and_never_uses_visitor_identity(app: FastAPI) -> None:
    request = Request({"type": "http", "app": app, "headers": []})
    try:
        get_public_publication_scope(request)
    except ApplicationError as error:
        assert error.code == "publication_not_configured"
    else:
        raise AssertionError("an unspecified publisher must not expose a personal partition")
    publisher = UUID("00000000-0000-4000-8000-000000000001")
    app.state.settings.public_publication_owner_id = publisher
    assert get_public_publication_scope(request) == publisher


def test_public_routes_have_no_session_dependency_but_personal_routes_keep_it(app: FastAPI) -> None:
    schema = app.openapi()
    for path in (
        "/api/publication/items",
        "/api/publication/topics",
        "/api/publication/catalogue/editions",
        "/api/publication/items/{content_id}/site",
        "/api/publication/media/{file_id}/{mode}/site",
        "/api/leaderboard/rules",
        "/api/site/meta",
        "/og/items/{content_id}.png",
    ):
        assert not schema["paths"][path]["get"].get("security"), path
    for path, method in (
        ("/api/topics", "get"),
        ("/api/reports", "get"),
        ("/api/publication/selected/snapshot", "get"),
        ("/api/publication/sources/{source_key}/policy", "put"),
    ):
        assert schema["paths"][path][method].get("security"), path


def test_unconfigured_public_read_is_a_stable_unpublished_state(app: FastAPI) -> None:
    app.dependency_overrides[get_publication_service] = lambda: object()
    try:
        response = TestClient(app).get("/api/publication/items")
        assert response.status_code == 503
        assert response.json()["code"] == "publication_not_configured"
        assert "set-cookie" not in response.headers
    finally:
        app.dependency_overrides.clear()


def test_blank_publication_owner_configuration_is_supported() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@localhost/hotkey_test",
        public_publication_owner_id="",  # type: ignore[arg-type]
    )
    assert settings.public_publication_owner_id is None
