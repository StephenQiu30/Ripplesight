import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from core.config import Settings
from db.metadata import Base
from main import create_app

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

TEST_DATABASE_TABLES = ", ".join(f'"{name}"' for name in sorted(Base.metadata.tables))
TEST_DATABASE_TRUNCATE = f"TRUNCATE {TEST_DATABASE_TABLES} CASCADE"


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
