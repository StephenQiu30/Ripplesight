import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from content.identity_history import register_new_owner_history_in_transaction
from core.config import Settings
from db.metadata import Base
from identity.models import IdentityUser
from identity.services import IdentityService
from main import create_app
from tests.journal_support import JournalContext, validate_test_database_url

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

_BUSINESS_FIXTURE_PASSWORD_HASH = PasswordHash.recommended().hash("fixed-business-fixture-password")

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
            password_hash=_BUSINESS_FIXTURE_PASSWORD_HASH,
            credential_version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        # This fixture just created an account in an isolated fresh test history.
        register_new_owner_history_in_transaction(session, owner_id=identifier, now=now)
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


@pytest.fixture(scope="session", autouse=True)
def runtime_journal() -> Iterator[JournalContext | None]:
    """Supply a real restricted independent reader to migrated integration consumers."""
    raw = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if raw is None:
        yield None
        return
    # Local import avoids loading test support before conftest initialization.
    from tests.journal_support import isolated_journal

    with isolated_journal(raw) as context, pytest.MonkeyPatch.context() as patch:
        patch.setenv(
            "HOTKEY_RESTRICTION_JOURNAL_READ_URL",
            context.urls["reader"].render_as_string(hide_password=False),
        )
        patch.setenv("HOTKEY_RESTRICTION_JOURNAL_LEDGER_ID", str(context.ledger_id))
        patch.setenv("HOTKEY_RESTRICTION_JOURNAL_EPOCH", "1")
        yield context


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
