"""Run only the explicitly bound Chrome owner's source on this host."""

import os
import signal
from datetime import UTC, datetime
from threading import Event
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from connections.presets import BILIBILI_CHROME_PRESET
from content.comments_execution import CommentsExecutor
from content.discovery_execution import KeywordDiscoveryExecutor
from content.services import CommentScanService
from core.config import (
    JOB_PROCESS_TERMINATE_GRACE_SECONDS,
    Settings,
    get_settings,
)
from core.logging import configure_logging
from db.metadata import metadata as _registered_metadata  # noqa: F401
from db.session import create_db_engine, create_session_factory
from jobs.execution import JobCompletion, JobLeaseUnavailableError
from jobs.local_dispatch import pending_source_deliveries
from worker.app import JobExecutionContext, create_job_dispatcher
from worker.execution import JobProcessSupervisor
from worker.messaging import MessageDeferredError
from worker.scheduler import enqueue_due_collections_in_transaction


def run_chrome_round(
    sessions: sessionmaker[Session],
    settings: Settings,
    owner_id: UUID,
    *,
    stopping: Event | None = None,
) -> int:
    if settings.bilibili_chrome_owner_id != owner_id:
        raise ValueError("Chrome owner binding is unavailable")
    stopping = stopping or Event()
    now = datetime.now(UTC)
    if BILIBILI_CHROME_PRESET.execution_policy.quiet_at(now):
        return 0
    lease_seconds = max(120, settings.job_lease_seconds)
    # One host runner at a time; Job leases also protect against Kafka redelivery.
    with sessions() as guard:
        if not guard.scalar(text("SELECT pg_try_advisory_lock(713574101)")):
            return 0
        try:
            with sessions.begin() as session:
                enqueue_due_collections_in_transaction(
                    session, now, owner_id=owner_id, source_key="bilibili"
                )
            search = KeywordDiscoveryExecutor(sessions, lease_seconds=lease_seconds)
            comments = CommentsExecutor(sessions, lease_seconds=lease_seconds)

            def search_handler(context: JobExecutionContext) -> JobCompletion:
                context.lease, completion = search.execute(context.message, context.lease)
                return completion

            def comments_handler(context: JobExecutionContext) -> JobCompletion:
                context.lease, completion = comments.execute(context.message, context.lease)
                return completion

            dispatch = create_job_dispatcher(
                sessions,
                {"keyword.search": search_handler, "source.comments": comments_handler},
                worker_id="chrome-host",
                lease_seconds=lease_seconds,
                supervisor=(
                    JobProcessSupervisor(
                        startup_timeout_seconds=15,
                        execution_timeout_seconds=90,
                        terminate_grace_seconds=JOB_PROCESS_TERMINATE_GRACE_SECONDS,
                    )
                    if settings.environment != "test"
                    else None
                ),
                stopping=stopping,
                job_execution_timeout_seconds=settings.job_process_execution_timeout_seconds,
            )
            completed = 0
            # After search commits, the existing scanner can discover fresh posts in this round.
            for _ in range(2):
                with sessions.begin() as session:
                    CommentScanService(session).enqueue_due_comments_in_transaction(
                        now=datetime.now(UTC),
                        owner_id=owner_id,
                        source_key="bilibili",
                    )
                with sessions() as session:
                    pending = pending_source_deliveries(
                        session,
                        owner_id=owner_id,
                        source_key="bilibili",
                        now=datetime.now(UTC),
                    )
                for message, reference in pending:
                    if stopping.is_set():
                        return completed
                    try:
                        dispatch(message, reference)
                    except (JobLeaseUnavailableError, MessageDeferredError):
                        continue
                    completed += 1
            return completed
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(713574101)"))


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    owner_id = settings.bilibili_chrome_owner_id
    if owner_id is None:
        raise SystemExit("HOTKEY_BILIBILI_CHROME_OWNER_ID is required")
    url = make_url(settings.database_url.get_secret_value())
    if url.host == "host.docker.internal":
        settings = settings.model_copy(
            update={
                "database_url": SecretStr(
                    url.set(host="127.0.0.1").render_as_string(hide_password=False)
                )
            }
        )
    os.environ["HOTKEY_DATABASE_URL"] = settings.database_url.get_secret_value()
    stopping = Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    engine = create_db_engine(settings)
    try:
        count = run_chrome_round(
            create_session_factory(engine), settings, owner_id, stopping=stopping
        )
        print(f"Chrome host round completed: {count} deliveries")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
