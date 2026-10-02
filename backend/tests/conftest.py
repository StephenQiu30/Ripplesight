import os
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from core.config import Settings
from db.metadata import Base
from identity.models import IdentityUser
from identity.services import IdentityService
from main import create_app

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

TEST_DATABASE_TABLES = ", ".join(f'"{name}"' for name in sorted(Base.metadata.tables))
TEST_DATABASE_TRUNCATE = f"TRUNCATE {TEST_DATABASE_TABLES} CASCADE"


def create_test_account(session: Session, *, owner_id: UUID | None = None) -> IdentityUser:
    """Persist an explicit account for a business fixture in its existing transaction."""
    identifier = owner_id or uuid4()
    user = session.get(IdentityUser, identifier)
    if user is None:
        now = datetime.now(UTC)
        user = IdentityUser(
            id=identifier,
            username=f"reader.{identifier.hex}",
            email=None,
            github_user_id=None,
            password_hash=None,
            credential_version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
    return user


def authenticate_test_client(client: TestClient, *, owner_id: UUID | None = None) -> UUID:
    """Explicit business fixtures use persisted sessions, with no dependency override."""
    settings = client.app.state.settings
    with client.app.state.session_factory.begin() as session:
        user = create_test_account(session, owner_id=owner_id)
        created = IdentityService(session, settings)._new_session(user, datetime.now(UTC))
    client.cookies.clear()
    client.cookies.set("hotkey_session", created.session_token)
    client.cookies.set("hotkey_csrf", created.csrf_token)
    client.headers["Origin"] = settings.web_origin
    return user.id


def authenticated_owner_id(session: Session) -> UUID:
    """Existing single-account business fixtures identify their explicit test account."""
    with session.get_bind().connect() as connection:
        return connection.execute(text("SELECT id FROM identity_users")).scalar_one()


def authenticated_headers(client: TestClient) -> dict[str, str]:
    return {"X-HotKey-CSRF": client.cookies["hotkey_csrf"], "Origin": client.headers["Origin"]}


def validate_test_database_url(value: str) -> None:
    parsed = make_url(value)
    if (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"hotkey_test_[a-z0-9_]+", parsed.database or "")
        or parsed.query
    ):
        raise ValueError("integration tests require a local isolated hotkey_test_<suffix> database")


def pytest_sessionstart(session: pytest.Session) -> None:
    value = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if value is not None:
        try:
            validate_test_database_url(value)
        except (ValueError, TypeError) as error:
            raise pytest.UsageError("unsafe HOTKEY_TEST_DATABASE_URL") from error


@pytest.fixture(autouse=True)
def isolated_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def isolated_integration_database(request: pytest.FixtureRequest) -> Iterator[None]:
    value = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if value is None or request.node.path.parent.name != "integration":
        yield
        return
    validate_test_database_url(value)
    engine = create_engine(value)
    try:
        with engine.begin() as connection:
            connection.execute(text(TEST_DATABASE_TRUNCATE))
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text(TEST_DATABASE_TRUNCATE))
        engine.dispose()


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test",
    )
    return create_app(settings)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
