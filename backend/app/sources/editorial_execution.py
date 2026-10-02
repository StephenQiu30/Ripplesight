"""Worker composition boundary; no implicit credentials or provider/model calls."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_services import EditorialSourceService, Guard, PreparedEditorialRun, Sink
from core.errors import ApplicationError
from sources.editorial_registry import EditorialCollector, EditorialSourceRegistry
from sources.editorial_schemas import EditorialRunResult

type CollectorFactory = Callable[[PreparedEditorialRun], EditorialCollector]


class EditorialSourceExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        collector_factory: CollectorFactory | None = None,
        sink: Sink | None = None,
        execution_guard: Guard | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions, self._factory, self._sink, self._guard = (
            session_factory,
            collector_factory,
            sink,
            execution_guard,
        )
        self._clock = clock

    def execute(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        configuration_version: int,
        revision: int,
        job_id: UUID,
        operation_id: UUID,
    ) -> EditorialRunResult:
        # Session-level lock spans the admitted provider boundary and content commit.
        with self._sessions() as lock_session:
            key = int.from_bytes(profile_id.bytes[:8], "big", signed=True)
            acquired = lock_session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            lock_session.commit()
            if not acquired:
                raise ApplicationError("editorial_version_conflict")
            try:
                with self._sessions() as session:
                    service = EditorialSourceService(session, clock=self._clock)
                    prepared = service.begin_run(
                        owner_id=owner_id,
                        profile_id=profile_id,
                        configuration_version=configuration_version,
                        revision=revision,
                        job_id=job_id,
                        operation_id=operation_id,
                        guard=self._guard,
                    )
                    if prepared.should_collect:
                        collector = (
                            self._factory(prepared) if self._factory else EditorialSourceRegistry()
                        )
                        try:
                            page = collector.collect(
                                prepared.profile, prepared.cursor, prepared.known
                            )
                        finally:
                            collector.close()
                        result = service.stage_page(
                            owner_id=owner_id,
                            run_id=prepared.result.run_id,
                            page=page,
                            guard=self._guard,
                        )
                        if result.status != "running":
                            return result
                    return service.apply_page(
                        owner_id=owner_id,
                        run_id=prepared.result.run_id,
                        guard=self._guard,
                        sink=self._sink,
                    )
            finally:
                lock_session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                lock_session.commit()
