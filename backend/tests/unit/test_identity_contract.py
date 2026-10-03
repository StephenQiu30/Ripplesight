from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from core.config import Settings
from core.errors import ApplicationError
from identity.schemas import (
    EmailCodeInput,
    IdentityCredentialsInput,
    IdentityCredentialsUpdateInput,
    IdentityPasswordLoginInput,
)
from identity.services import IdentityService, safe_return_to


@pytest.mark.parametrize(
    "target",
    [
        "https://bad.example/",
        "//bad.example",
        "//[bad",
        "/topics\x7f",
        "/\\bad",
        "/login",
        "/api/private",
        "/%2fother.example",
        "/topics\nLocation:bad",
    ],
)
def test_login_return_target_rejects_external_or_recursive_navigation(target: str) -> None:
    assert safe_return_to(target) == "/topics"


def test_login_return_target_preserves_a_system_deep_link() -> None:
    assert safe_return_to("/monitors/abc?tab=reading") == "/monitors/abc?tab=reading"


def test_identity_input_normalizes_identity_without_exposing_password() -> None:
    value = IdentityCredentialsInput(username="Test.User", password="a sufficiently long password")
    assert value.username == "test.user"
    assert "sufficiently" not in repr(value)
    assert (
        EmailCodeInput(email=" Test.User+news@Example.com ").email == "test.user+news@example.com"
    )
    with pytest.raises(ValidationError):
        EmailCodeInput(email="user@example.com\nBcc:other@example.com")


@pytest.mark.parametrize(
    ("identifier", "normalized"),
    [
        ("Test.User", "test.user"),
        (" Test.User+news@Example.com ", "test.user+news@example.com"),
        ("account@" + "a" * 63 + ".example.com", "account@" + "a" * 63 + ".example.com"),
    ],
)
def test_password_login_accepts_a_normalized_email_or_legacy_username(
    identifier: str, normalized: str
) -> None:
    value = IdentityPasswordLoginInput(username=identifier, password="a sufficiently long password")
    assert value.username == normalized
    assert "sufficiently" not in repr(value)


@pytest.mark.parametrize(
    "identifier",
    [
        "invalid@",
        "two@@example.com",
        "user@example.com\nBcc:other@example.com",
        "bad username",
        "a" * 65,
        "account@" + "a" * 64 + ".example.com",
    ],
)
def test_password_login_rejects_invalid_email_and_legacy_username(identifier: str) -> None:
    with pytest.raises(ValidationError):
        IdentityPasswordLoginInput(username=identifier, password="a sufficiently long password")


@pytest.mark.parametrize("username", ["user@example.com", "a" * 65])
def test_email_password_login_does_not_broaden_credentials_update_username(username: str) -> None:
    with pytest.raises(ValidationError):
        IdentityCredentialsUpdateInput(username=username, password="a sufficiently long password")


def test_identity_partial_integration_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test@localhost/hotkey_test",
            github_client_id="one-half",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test@localhost/hotkey_test",
            environment="production",
        )


def test_openapi_exposes_session_security_and_never_credentials_as_query(app: FastAPI) -> None:
    schema = app.openapi()
    assert schema["components"]["securitySchemes"]["SessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "hotkey_session",
    }
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete", "head"}:
                continue
            assert not any(p["in"] == "cookie" for p in operation.get("parameters", []))
            if path in {"/api/topics", "/api/contents", "/feed.xml"}:
                assert operation["security"] == [{"SessionCookie": []}]
                assert "401" in operation["responses"]
    identity = schema["components"]["schemas"]["IdentitySessionView"]
    assert set(identity["properties"]) == {"user", "expires_at"}
    user = schema["components"]["schemas"]["IdentityUserView"]
    assert user["properties"]["has_password"]["type"] == "boolean"
    assert "has_password" in user["required"]
    assert user["properties"]["github_connected"]["type"] == "boolean"
    assert "github_connected" in user["required"]
    for path, method in (
        ("/api/identity/email/link/challenges", "post"),
        ("/api/identity/email/link", "put"),
        ("/api/identity/github/link", "post"),
    ):
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"200", "401", "403", "422", "429", "503", "500"} <= set(operation["responses"])
        assert any(p["name"] == "X-HotKey-CSRF" for p in operation["parameters"])
    assert "409" in schema["paths"]["/api/identity/email/link"]["put"]["responses"]
    login = schema["components"]["schemas"]["IdentityPasswordLoginInput"]
    assert login["properties"]["username"]["maxLength"] == 254
    credentials = schema["components"]["schemas"]["IdentityCredentialsUpdateInput"]
    assert credentials["properties"]["username"]["maxLength"] == 64
    updated = schema["paths"]["/api/identity/credentials"]["put"]["responses"]
    assert "204" not in updated
    assert updated["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/IdentitySessionView"
    }
    assert not any(path.endswith(("/initialize", "/workspace")) for path in schema["paths"])


def test_non_ascii_csrf_is_rejected_without_an_internal_error() -> None:
    with pytest.raises(ApplicationError, match="csrf_invalid"):
        IdentityService.validate_csrf(None, cookie="é" * 43, header="é" * 43)
