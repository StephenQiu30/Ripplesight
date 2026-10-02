"""Bounded current cadence admission to the original Jobs/Outbox."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from core.errors import ApplicationError
from monitors.codex_execution import list_due_codex_monitors_in_transaction
from monitors.codex_schemas import CodexTickInput
from monitors.codex_services import CodexResetService

_NAMESPACE = UUID("a2e4f9e5-a65c-44ea-85a2-5306b8ff19ee")


def enqueue_due_codex_monitors_in_transaction(
    session: Session, now: datetime, *, enabled: bool
) -> int:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("Codex scheduler requires aware caller transaction")
    if not enabled:
        return 0
    count = 0
    for due in list_due_codex_monitors_in_transaction(session, now=now):
        window = datetime.fromtimestamp(
            int(now.timestamp()) // due.interval_seconds * due.interval_seconds, UTC
        )
        operation = uuid5(
            _NAMESPACE,
            f"{due.owner_id}:{due.monitor_id}:{due.configuration_version}:"
            f"{due.monitor_revision}:{window.isoformat()}",
        )
        try:
            with session.begin_nested():
                CodexResetService(session, clock=lambda: now).enqueue_tick_in_transaction(
                    owner_id=due.owner_id,
                    monitor_id=due.monitor_id,
                    command=CodexTickInput(
                        operation_id=operation,
                        expected_revision=due.monitor_revision,
                        reason="Scheduled official announcement poll",
                    ),
                    scheduled_for_at=window,
                )
            count += 1
        except ApplicationError:
            continue
    return count
