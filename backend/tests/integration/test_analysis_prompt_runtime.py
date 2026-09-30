from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from analysis.services import AnalysisService


@pytest.fixture
def runtime_store() -> Iterator[tuple[Engine, sessionmaker[Session], str]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    version = f"runtime-test-{uuid4()}"
    try:
        yield engine, sessions, version
    finally:
        engine.dispose()


def test_runtime_session_schema_is_available_in_fresh_database() -> None:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT id, prompt_version, ai_enabled, started_at, last_seen_at, stopped_at "
                    "FROM analysis_prompt_runtime_sessions LIMIT 0"
                )
            )
    finally:
        engine.dispose()


def test_disabled_start_heartbeat_and_stop_are_idempotent(
    runtime_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    engine, sessions, version = runtime_store
    run_id = uuid4()
    started = datetime(2026, 9, 28, 0, tzinfo=UTC)
    seen = started + timedelta(seconds=30)
    stopped = started + timedelta(seconds=60)

    with sessions() as session, session.begin():
        service = AnalysisService(session)
        assert service.start_prompt_runtime_in_transaction(
            run_id=run_id, prompt_version=version, ai_enabled=False, started_at=started
        )
        assert not service.start_prompt_runtime_in_transaction(
            run_id=run_id, prompt_version=version, ai_enabled=False, started_at=started
        )
        with pytest.raises(ValueError, match="conflicts"):
            service.start_prompt_runtime_in_transaction(
                run_id=run_id, prompt_version=version, ai_enabled=True, started_at=started
            )
    with sessions() as session, session.begin():
        service = AnalysisService(session)
        assert service.heartbeat_prompt_runtime_in_transaction(run_id=run_id, observed_at=seen)
        assert not service.heartbeat_prompt_runtime_in_transaction(run_id=run_id, observed_at=seen)
        with pytest.raises(ValueError, match="out of order"):
            service.heartbeat_prompt_runtime_in_transaction(run_id=run_id, observed_at=started)
    with sessions() as session, session.begin():
        service = AnalysisService(session)
        assert service.stop_prompt_runtime_in_transaction(run_id=run_id, stopped_at=stopped)
        assert not service.stop_prompt_runtime_in_transaction(run_id=run_id, stopped_at=stopped)
        with pytest.raises(ValueError, match="stopped"):
            service.heartbeat_prompt_runtime_in_transaction(
                run_id=run_id, observed_at=stopped + timedelta(seconds=1)
            )
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT ai_enabled, started_at, last_seen_at, stopped_at "
                "FROM analysis_prompt_runtime_sessions WHERE id = :id"
            ),
            {"id": run_id},
        ).one()
        activated = connection.execute(
            text(
                "SELECT count(*) FROM analysis_prompt_activations WHERE prompt_version = :version"
            ),
            {"version": version},
        ).scalar_one()
    assert row.ai_enabled is False
    assert row.started_at.astimezone(UTC) == started
    assert row.last_seen_at.astimezone(UTC) == stopped
    assert row.stopped_at.astimezone(UTC) == stopped
    assert activated == 0


def test_enabled_start_is_atomic_and_crash_gap_survives_restart(
    runtime_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    engine, sessions, version = runtime_store
    first_run, restart_run = uuid4(), uuid4()
    started = datetime(2026, 9, 28, 1, tzinfo=UTC)
    heartbeat = started + timedelta(seconds=30)
    restart = started + timedelta(hours=1)

    with pytest.raises(RuntimeError, match="rollback"), sessions() as session, session.begin():
        assert AnalysisService(session).start_prompt_runtime_in_transaction(
            run_id=first_run, prompt_version=version, ai_enabled=True, started_at=started
        )
        raise RuntimeError("rollback")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM analysis_prompt_runtime_sessions WHERE id = :id"),
                {"id": first_run},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM analysis_prompt_activations "
                    "WHERE prompt_version = :version"
                ),
                {"version": version},
            ).scalar_one()
            == 0
        )

    with sessions() as session, session.begin():
        service = AnalysisService(session)
        assert service.start_prompt_runtime_in_transaction(
            run_id=first_run, prompt_version=version, ai_enabled=True, started_at=started
        )
        assert service.heartbeat_prompt_runtime_in_transaction(
            run_id=first_run, observed_at=heartbeat
        )
    with sessions() as session, session.begin():
        assert AnalysisService(session).start_prompt_runtime_in_transaction(
            run_id=restart_run, prompt_version=version, ai_enabled=True, started_at=restart
        )
    with engine.connect() as connection:
        first = connection.execute(
            text(
                "SELECT last_seen_at, stopped_at FROM analysis_prompt_runtime_sessions "
                "WHERE id = :id"
            ),
            {"id": first_run},
        ).one()
        activation = connection.execute(
            text(
                "SELECT activated_at FROM analysis_prompt_activations "
                "WHERE prompt_version = :version"
            ),
            {"version": version},
        ).scalar_one()
    assert first.last_seen_at.astimezone(UTC) == heartbeat
    assert first.stopped_at is None
    assert activation.astimezone(UTC) == started

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from sqlalchemy import create_engine, text; "
            "engine = create_engine(os.environ['HOTKEY_TEST_DATABASE_URL']); "
            "connection = engine.connect(); "
            "print(connection.execute(text('SELECT count(*) FROM "
            "analysis_prompt_runtime_sessions WHERE prompt_version = :version'), "
            "{'version': os.environ['HOTKEY_TEST_PROMPT_VERSION']}).scalar_one()); "
            "connection.close(); engine.dispose()",
        ],
        env={**os.environ, "HOTKEY_TEST_PROMPT_VERSION": version},
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout.strip() == "2"


def test_runtime_schema_rejects_backwards_clock(
    runtime_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    engine, _, version = runtime_store
    started = datetime(2026, 9, 28, 2, tzinfo=UTC)
    insert_sql = text(
        "INSERT INTO analysis_prompt_runtime_sessions "
        "(id, prompt_version, ai_enabled, started_at, last_seen_at, stopped_at) "
        "VALUES (:id, :version, false, :started, :seen, :stopped)"
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert_sql,
            {
                "id": uuid4(),
                "version": version,
                "started": started,
                "seen": started - timedelta(seconds=1),
                "stopped": None,
            },
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert_sql,
            {
                "id": uuid4(),
                "version": version,
                "started": started,
                "seen": started,
                "stopped": started - timedelta(seconds=1),
            },
        )
