from __future__ import annotations

import argparse
import signal
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid5

from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings, get_settings
from core.logging import configure_logging
from db.metadata import metadata as _registered_metadata  # noqa: F401
from db.owners import list_owner_ids_in_transaction
from db.session import create_db_engine, create_session_factory
from jobs.execution import (
    JobExecutionFailure,
    JobExecutionService,
    JobLeaseUnavailableError,
    MessageReference,
)
from jobs.operator_maintenance import load_watchdog_message_in_transaction
from jobs.services import JobService
from operations.heartbeat import ProcessHeartbeatReporter
from operations.maintenance import OperationsMaintenanceExecutor
from operations.schemas import MaintenanceInput
from operations.services import OperationsService

_NAMESPACE = UUID("01f8f409-a707-48fc-a3d7-685f5bcfc3fd")


def run_watchdog_once(sessions: sessionmaker[Session], settings: Settings) -> bool:
    """Execute the watchdog independently when the Kafka worker or scheduler is down."""
    if not settings.operations_maintenance_enabled:
        return False
    with sessions() as session, session.begin():
        owners = list_owner_ids_in_transaction(session)
    results = [_run_owner_watchdog(sessions, settings, owner) for owner in owners]
    return any(results)


def _run_owner_watchdog(sessions: sessionmaker[Session], settings: Settings, owner: UUID) -> bool:
    now = datetime.now(UTC)
    with sessions() as session:
        accepted = OperationsService(session, maintenance_enabled=True).enqueue_maintenance(
            owner_id=owner,
            command=MaintenanceInput(
                operation_id=uuid5(_NAMESPACE, f"{owner}:{int(now.timestamp()) // 60}"),
                action="watchdog",
                reason="外部进程检查真实服务心跳",
            ),
        )
        job = JobService(session).get_status(owner_id=owner, job_id=accepted.job_id)
        session.rollback()
        with session.begin():
            message = load_watchdog_message_in_transaction(session, owner_id=owner, job_id=job.id)
        execution = JobExecutionService(session, lease_seconds=settings.job_lease_seconds)
        try:
            lease = execution.acquire(job_id=job.id, worker_id="external-watchdog")
        except JobLeaseUnavailableError:
            return False
    reference = MessageReference(
        message.message_id, "operations.watchdog.local", 0, int(now.timestamp())
    )
    try:
        result = OperationsMaintenanceExecutor(sessions, settings).execute(message, lease)
    except JobExecutionFailure as failure:
        with sessions() as session:
            JobExecutionService(session, lease_seconds=settings.job_lease_seconds).record_failure(
                lease, message=reference, failure=failure
            )
        return False
    with sessions() as session:
        JobExecutionService(session, lease_seconds=settings.job_lease_seconds).complete(
            lease, message=reference, completion=result
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent HotKey process heartbeat watchdog")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.operations_maintenance_enabled:
        print("HotKey watchdog disabled by configuration")
        return
    engine = create_db_engine(settings)
    sessions = create_session_factory(engine, settings=settings)
    stopped = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signum, _frame: stopped.set())
    heartbeat = ProcessHeartbeatReporter(sessions, role="watchdog")
    heartbeat.start()
    try:
        while not stopped.is_set():
            run_watchdog_once(sessions, settings)
            if args.once:
                break
            stopped.wait(30)
    finally:
        heartbeat.stop()
        engine.dispose()


if __name__ == "__main__":
    main()
