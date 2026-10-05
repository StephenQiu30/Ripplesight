"""Worker composition boundary; no implicit credentials or provider/model calls."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_services import EditorialSourceService, Guard, PreparedEditorialRun, Sink
from core.errors import ApplicationError
from sources.contracts import SourceStopReason, WebPageResult
from sources.editorial_body import LocalEditorialBodyFetcher
from sources.editorial_registry import EditorialCollector, EditorialSourceRegistry
from sources.editorial_schemas import EditorialRunResult

type CollectorFactory = Callable[[PreparedEditorialRun], EditorialCollector]
type BodyFetcherFactory = Callable[[PreparedEditorialRun], LocalEditorialBodyFetcher]


class EditorialSourceExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        collector_factory: CollectorFactory | None = None,
        body_fetcher_factory: BodyFetcherFactory | None = None,
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
        self._body_factory = body_fetcher_factory

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
                            self._factory(prepared)
                            if self._factory
                            else EditorialSourceRegistry(source_added_at=prepared.source_added_at)
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
                    result = service.apply_page(
                        owner_id=owner_id,
                        run_id=prepared.result.run_id,
                        guard=self._guard,
                        sink=self._sink,
                    )
                    if result.status != "running":
                        return result
                    configuration = prepared.profile.configuration.body_extraction
                    if configuration is None or not configuration.enabled:
                        return result
                    fetcher = self._body_factory(prepared) if self._body_factory else None
                    while True:
                        checkpoint = service.body_checkpoint(
                            owner_id=owner_id, run_id=prepared.result.run_id, guard=self._guard
                        )
                        if checkpoint is None:
                            return result
                        if (checkpoint.request_pending) or checkpoint.next_index >= len(
                            checkpoint.targets
                        ):
                            return service.finish_body_phase(
                                owner_id=owner_id, run_id=prepared.result.run_id, guard=self._guard
                            )
                        target = service.begin_body_request(
                            owner_id=owner_id, run_id=prepared.result.run_id, guard=self._guard
                        )
                        response = (
                            fetcher.fetch(target, configuration)
                            if fetcher
                            else WebPageResult(
                                document=None,
                                stop_reason=SourceStopReason.ACCESS_DENIED,
                                target_status_code=None,
                                collector_call_count=0,
                                target_request_count=None,
                            )
                        )
                        # Atomically store the original version/ALL inputs and its result reference.
                        # A lost uncommitted response remains unknown, never a second body cache.
                        service.apply_body_response(
                            owner_id=owner_id,
                            run_id=prepared.result.run_id,
                            response=response,
                            guard=self._guard,
                        )
            finally:
                lock_session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                lock_session.commit()
