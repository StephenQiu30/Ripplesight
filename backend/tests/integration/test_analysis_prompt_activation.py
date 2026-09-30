from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.services import AnalysisService
from worker.scheduler import (
    heartbeat_analysis_prompt_runtime,
    start_analysis_prompt_runtime_at_startup,
    stop_analysis_prompt_runtime,
)


@pytest.fixture
def activation_store() -> Iterator[tuple[Engine, sessionmaker[Session], list[str]]]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    versions = [ANALYSIS_PROMPT_VERSION]
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM analysis_prompt_runtime_sessions WHERE prompt_version = :version"
                ),
                {"version": ANALYSIS_PROMPT_VERSION},
            )
            connection.execute(
                text("DELETE FROM analysis_prompt_activations WHERE prompt_version = :version"),
                {"version": ANALYSIS_PROMPT_VERSION},
            )
        yield engine, sessions, versions
    finally:
        engine.dispose()


def test_scheduler_activation_is_disabled_or_persisted_once_across_restarts(
    activation_store: tuple[Engine, sessionmaker[Session], list[str]],
) -> None:
    engine, sessions, _ = activation_store
    first_start = datetime(2026, 9, 28, 0, tzinfo=UTC)
    restart = first_start + timedelta(hours=2)

    disabled_run = start_analysis_prompt_runtime_at_startup(
        sessions, ai_enabled=False, started_at=first_start
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM analysis_prompt_activations")
            ).scalar_one()
            == 0
        )

    first_run = start_analysis_prompt_runtime_at_startup(
        sessions, ai_enabled=True, started_at=first_start
    )
    restart_run = start_analysis_prompt_runtime_at_startup(
        sessions, ai_enabled=True, started_at=restart
    )
    assert len({disabled_run, first_run, restart_run}) == 3
    heartbeat_analysis_prompt_runtime(
        sessions, run_id=first_run, observed_at=first_start + timedelta(seconds=30)
    )
    stop_analysis_prompt_runtime(
        sessions, run_id=first_run, stopped_at=first_start + timedelta(seconds=45)
    )
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT activated_at FROM analysis_prompt_activations "
                "WHERE prompt_version = :version"
            ),
            {"version": ANALYSIS_PROMPT_VERSION},
        ).one()
        runtime_states = connection.execute(
            text(
                "SELECT ai_enabled, started_at, stopped_at FROM analysis_prompt_runtime_sessions "
                "WHERE id IN (:disabled, :first, :restart) ORDER BY started_at, ai_enabled"
            ),
            {"disabled": disabled_run, "first": first_run, "restart": restart_run},
        ).all()
    assert row.activated_at.astimezone(UTC) == first_start
    assert [(enabled, at.astimezone(UTC), stop) for enabled, at, stop in runtime_states] == [
        (False, first_start, None),
        (True, first_start, first_start + timedelta(seconds=45)),
        (True, restart, None),
    ]

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from sqlalchemy import create_engine, text; "
            "engine = create_engine(os.environ['HOTKEY_TEST_DATABASE_URL']); "
            "connection = engine.connect(); "
            "print(connection.execute(text('SELECT activated_at FROM "
            "analysis_prompt_activations WHERE prompt_version = :version'), "
            "{'version': os.environ['HOTKEY_TEST_PROMPT_VERSION']}).scalar_one()"
            ".astimezone(__import__('datetime').UTC).isoformat()); "
            "connection.close(); engine.dispose()",
        ],
        env={**os.environ, "HOTKEY_TEST_PROMPT_VERSION": ANALYSIS_PROMPT_VERSION},
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout.strip() == first_start.isoformat()


def test_prompt_activation_rolls_back_and_new_version_has_its_own_time(
    activation_store: tuple[Engine, sessionmaker[Session], list[str]],
) -> None:
    engine, sessions, versions = activation_store
    first_version = f"test-activation-{uuid4()}"
    second_version = f"test-activation-{uuid4()}"
    versions.extend((first_version, second_version))
    first_start = datetime(2026, 9, 28, 1, tzinfo=UTC)
    second_start = first_start + timedelta(minutes=30)

    with pytest.raises(RuntimeError, match="rollback"), sessions() as session, session.begin():
        assert AnalysisService(session).record_prompt_activation_in_transaction(
            prompt_version=first_version, activated_at=first_start
        )
        raise RuntimeError("rollback")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM analysis_prompt_activations "
                    "WHERE prompt_version = :version"
                ),
                {"version": first_version},
            ).scalar_one()
            == 0
        )

    with sessions() as session, session.begin():
        service = AnalysisService(session)
        assert service.record_prompt_activation_in_transaction(
            prompt_version=first_version, activated_at=first_start
        )
        assert service.record_prompt_activation_in_transaction(
            prompt_version=second_version, activated_at=second_start
        )
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT prompt_version, activated_at FROM analysis_prompt_activations "
                "WHERE prompt_version IN (:first, :second)"
            ),
            {"first": first_version, "second": second_version},
        ).all()
    assert {version: at.astimezone(UTC) for version, at in rows} == {
        first_version: first_start,
        second_version: second_start,
    }


def test_concurrent_prompt_activation_inserts_one_row(
    activation_store: tuple[Engine, sessionmaker[Session], list[str]],
) -> None:
    engine, sessions, versions = activation_store
    version = f"test-activation-{uuid4()}"
    versions.append(version)
    started_at = datetime(2026, 9, 28, 2, tzinfo=UTC)
    barrier = Barrier(2)

    def attempt() -> bool:
        with sessions() as session, session.begin():
            barrier.wait(timeout=5)
            return AnalysisService(session).record_prompt_activation_in_transaction(
                prompt_version=version, activated_at=started_at
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: attempt(), range(2)))
    assert sorted(results) == [False, True]
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM analysis_prompt_activations "
                    "WHERE prompt_version = :version"
                ),
                {"version": version},
            ).scalar_one()
            == 1
        )
