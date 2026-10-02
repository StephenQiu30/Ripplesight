from __future__ import annotations

import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, Thread
from typing import Literal
from uuid import uuid4

import structlog
from sqlalchemy.orm import Session, sessionmaker

from db.owners import list_owner_ids_in_transaction
from operations.services import record_process_heartbeat_in_transaction


class ProcessHeartbeatReporter:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        role: Literal["api", "worker", "scheduler", "watchdog"],
        enabled: bool = True,
        interval_seconds: int = 30,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 10 <= interval_seconds <= 60:
            raise ValueError("heartbeat interval must be 10..60 seconds")
        self._sessions, self._role, self._enabled, self._interval = (
            sessions,
            role,
            enabled,
            interval_seconds,
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self.started_at = self._clock()
        self.instance_id = f"{role}:{socket.gethostname()[:48]}:{os.getpid()}:{uuid4().hex}"
        self._stop = Event()
        self._thread: Thread | None = None

    def beat(self, *, state: Literal["alive", "stopping", "error"] = "alive") -> None:
        if not self._enabled:
            return
        with self._sessions() as session, session.begin():
            for owner in list_owner_ids_in_transaction(session):
                record_process_heartbeat_in_transaction(
                    session,
                    owner_id=owner,
                    role=self._role,
                    instance_id=self.instance_id,
                    pid=os.getpid(),
                    state=state,
                    now=self._clock(),
                    started_at=self.started_at,
                    detail={"transport": "direct_database"},
                )

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._thread = Thread(target=self._run, daemon=True, name=f"hotkey-{self._role}-heartbeat")
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.beat()
            except Exception:
                # Connection exceptions may contain credentials; only log the stable condition.
                structlog.get_logger("operations").warning(
                    "heartbeat_write_failed", role=self._role
                )
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._enabled:
            try:
                self.beat(state="stopping")
            except Exception:
                structlog.get_logger("operations").warning(
                    "heartbeat_stop_write_failed", role=self._role
                )
