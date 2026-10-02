from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService
from leaderboard.models import LeaderboardSourceState
from leaderboard.schedule import CONFIGURATION_REF

pytestmark = pytest.mark.skipif(
    not os.getenv("HOTKEY_TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)


def test_health_uses_success_or_original_owned_admission_without_writing_a_poll() -> None:
    from leaderboard.health import load_source_health_in_transaction

    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    owner, other = uuid4(), uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        with Session(engine) as session, session.begin():
            for job_owner, age in ((owner, 26), (other, 80)):
                JobService(
                    session, clock=lambda age=age: now - timedelta(hours=age)
                ).accept_in_transaction(
                    owner_id=job_owner,
                    command=JobAcceptanceInput(
                        operation_id=uuid4(),
                        kind="leaderboard.refresh",
                        observation=JobObservationContext(
                            configuration_ref=CONFIGURATION_REF, configuration_version=1
                        ),
                        scope={},
                    ),
                )
            session.add(
                LeaderboardSourceState(
                    source_key="artificial-analysis",
                    ok=False,
                    checked_at=now,
                    last_ok_at=now - timedelta(hours=27),
                    changed=None,
                    row_count=None,
                    new_models=None,
                    request_count=1,
                    error_code="TimeoutException",
                )
            )
        with Session(engine) as session, session.begin():
            before = session.execute(text("SELECT count(*) FROM jobs")).scalar_one()

            def read(at, external):
                return {
                    row.source_key: row
                    for row in load_source_health_in_transaction(
                        session,
                        owner_id=owner,
                        now=at,
                        enabled=True,
                        external_requests_enabled=external,
                    )
                }

            values = read(now, True)
            failed = values["artificial-analysis"]
            assert failed.failing and failed.stale
            assert failed.last_successful_poll_at == now - timedelta(hours=27)
            assert failed.anchor_at == failed.last_successful_poll_at
            never = values["arena-text"]
            assert never.anchor_at == now - timedelta(hours=26)
            assert not never.stale and not never.failing
            assert read(now + timedelta(microseconds=1), True)["arena-text"].stale
            disabled = read(now + timedelta(days=1), False)["artificial-analysis"]
            assert not disabled.enabled and not disabled.stale
            assert disabled.last_successful_poll_at == failed.last_successful_poll_at
            assert session.in_transaction()
            assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == before
            assert (
                session.execute(text("SELECT count(*) FROM leaderboard_source_states")).scalar_one()
                == 1
            )
            assert not session.new and not session.dirty
    finally:
        engine.dispose()
