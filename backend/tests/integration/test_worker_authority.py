"""Both actual Worker handler boundaries finalize isolated PG leases and inboxes."""

from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_content_records import _user_scope
from tests.integration.test_content_records import content_client as content_client
from tests.integration.test_keyword_discovery import _accepted_message
from tests.process_targets import _authority_job_child

from core.errors import AuthorityUnavailableError
from jobs.execution import MessageReference
from jobs.models import Job, OutboxMessage, ProcessedMessage
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobRetryScheduledMessage
from jobs.services import JobService
from worker import app as worker_app
from worker.execution import JobProcessSupervisor


@pytest.mark.parametrize("supervised", [False, True])
@pytest.mark.parametrize("kind", ["transient", "configuration"])
def test_authority_failure_finishes_lease_inbox_and_bounded_retry(
    content_client, monkeypatch, supervised, kind
):
    owner = _user_scope(content_client)
    factory = content_client.app.state.session_factory
    current = [datetime.now(UTC)]
    with factory() as session:
        job = JobService(session, clock=lambda: current[0]).accept(
            owner_id=owner,
            command=JobAcceptanceInput(
                operation_id=uuid4(),
                kind="authority.test",
                observation=JobObservationContext(
                    configuration_ref=f"authority:{kind}", configuration_version=1
                ),
                scope={},
            ),
        )
    message = _accepted_message(factory.kw["bind"], job.id)

    def handler(_context):
        raise AuthorityUnavailableError(kind) from ConnectionError("private credentials")

    if supervised:
        monkeypatch.setattr(worker_app, "_run_job_in_child", _authority_job_child)
    dispatch = worker_app.create_job_dispatcher(
        factory,
        {"authority.test": handler},
        worker_id="owned-authority-test",
        lease_seconds=60,
        clock=lambda: current[0],
        stopping=Event(),
        supervisor=JobProcessSupervisor(
            startup_timeout_seconds=10,
            execution_timeout_seconds=10,
            terminate_grace_seconds=0.1,
            poll_interval_seconds=0.01,
        )
        if supervised
        else None,
    )
    for attempt in range(1, 4 if kind == "transient" else 2):
        reference = MessageReference(message.message_id, "owned-authority", 0, attempt)
        dispatch(message, reference)
        # Redelivery must not reopen a finished lease or create duplicate retry dispatch.
        dispatch(message, reference)
        with factory() as session:
            persisted = session.get(Job, job.id)
            retrying = kind == "transient" and attempt < 3
            assert persisted.status == ("queued" if retrying else "failed")
            assert persisted.lease_owner is None and persisted.lease_expires_at is None
            assert persisted.last_error_code == "authority_unavailable"
            assert persisted.last_error_category == (
                "transient" if kind == "transient" else "configuration_unavailable"
            )
            assert persisted.retry_count == (min(attempt, 2) if kind == "transient" else 0)
            assert persisted.next_run_at == (
                current[0] + timedelta(seconds=30) if retrying else None
            )
            assert session.get(ProcessedMessage, message.message_id) is not None
            retries = list(
                session.scalars(
                    select(OutboxMessage)
                    .where(
                        OutboxMessage.aggregate_id == job.id,
                        OutboxMessage.event_type == "job.retry_scheduled.v1",
                    )
                    .order_by(OutboxMessage.dispatch_sequence)
                )
            )
            assert len(retries) == (min(attempt, 2) if kind == "transient" else 0)
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM job_attempts WHERE job_id=:id AND finished_at IS NULL"
                    ),
                    {"id": job.id},
                )
                == 0
            )
            if retrying:
                out = retries[-1]
                message = JobRetryScheduledMessage.model_validate(
                    {
                        "schema_version": 1,
                        "message_id": out.id,
                        "event_type": out.event_type,
                        **out.payload,
                    }
                )
                current[0] = persisted.next_run_at
