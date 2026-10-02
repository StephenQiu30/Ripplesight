import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db.demo import DEFAULT_DEMO_SCOPE_ID
from publication.schedule import enqueue_due_publication_in_transaction
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


def test_projection_schedule_is_bounded_fair_and_pending_replays_do_not_fork() -> None:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("requires isolated PostgreSQL")
    engine = create_engine(url)
    sessions = sessionmaker(engine)
    owner = DEFAULT_DEMO_SCOPE_ID
    now = datetime.now(UTC)
    try:
        with sessions.begin() as session:
            for index in range(25):
                PublicationService(session).save_source_policy_in_transaction(
                    owner_id=owner,
                    actor_id=owner,
                    source_key=f"controlled-{index:02}",
                    now=now,
                    command=SourcePolicyInput(
                        operation_id=uuid4(),
                        expected_revision=0,
                        license_name="Controlled test",
                        reason="test",
                    ),
                )
            assert enqueue_due_publication_in_transaction(session, now=now, enabled=False) == 0
            assert enqueue_due_publication_in_transaction(session, now=now, limit=20) == 20
        with sessions.begin() as session:
            assert enqueue_due_publication_in_transaction(session, now=now, limit=20) == 5
        with sessions.begin() as session:
            assert (
                enqueue_due_publication_in_transaction(session, now=now + timedelta(minutes=10))
                == 0
            )
            assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 25
            assert session.execute(text("SELECT count(*) FROM outbox_messages")).scalar_one() == 25
            session.execute(text("UPDATE publication_republish_runs SET status='completed'"))
        with sessions.begin() as session:
            later = now + timedelta(minutes=10)
            assert enqueue_due_publication_in_transaction(session, now=later, limit=20) == 20
        with sessions.begin() as session:
            assert enqueue_due_publication_in_transaction(session, now=later, limit=20) == 5
            assert (
                session.execute(
                    text("SELECT count(DISTINCT source_key) FROM publication_republish_runs")
                ).scalar_one()
                == 25
            )
            assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 50
    finally:
        engine.dispose()
