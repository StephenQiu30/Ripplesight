"""Replayable local projection rebuilds use existing jobs, leases and checkpoints."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import JobFailureCategory, JobMessage, JobStatus
from jobs.services import load_job_execution_configuration
from publication.publication_models import PublicationRepublishRun
from publication.services import PublicationService


class PublicationRepublishExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        indexing_enabled: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions, self.indexing_enabled = sessions, indexing_enabled
        self.clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        message: JobMessage,
        lease: ExecutionLease,
        *,
        cancelled: Callable[[], bool] | None = None,
        checkpoint: Callable[[int, Mapping[str, str | int | bool | None]], None] | None = None,
    ) -> JobCompletion | None:
        if message.kind != "publication.republish":
            raise ValueError("publication executor received another kind")
        with self.sessions.begin() as session:
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("publication_job_mismatch", JobFailureCategory.INVALID_INPUT)
            try:
                run_id = UUID(str(configuration.scope["republish_run_id"]))
                source_key = str(configuration.scope["source_key"])
                policy_revision = int(str(configuration.scope["policy_revision"]))
            except (ValueError, KeyError, TypeError) as error:
                raise self._failure(
                    "publication_job_mismatch", JobFailureCategory.INVALID_INPUT
                ) from error
            run = session.scalar(
                select(PublicationRepublishRun).where(
                    PublicationRepublishRun.owner_id == message.owner_id,
                    PublicationRepublishRun.id == run_id,
                )
            )
            if (
                run is None
                or run.job_id != message.job_id
                or run.source_key != source_key
                or run.policy_revision != policy_revision
            ):
                raise self._failure("publication_job_mismatch", JobFailureCategory.INVALID_INPUT)
            if run.status == "completed":
                return JobCompletion(status=JobStatus.SUCCEEDED)
            if run.status == "cancelled":
                return None
        checkpoint_sequence = lease.checkpoint_sequence
        while True:
            if cancelled and cancelled():
                with self.sessions.begin() as session:
                    JobExecutionService(
                        session, lease_seconds=30, clock=self.clock
                    ).require_current_lease_allowing_cancel_in_transaction(lease)
                    PublicationService(session).finish_republish_in_transaction(
                        owner_id=message.owner_id,
                        run_id=run_id,
                        status="cancelled",
                        now=self.clock(),
                    )
                return None
            with self.sessions.begin() as session:
                JobExecutionService(
                    session, lease_seconds=30, clock=self.clock
                ).require_current_lease_in_transaction(lease)
                progress = PublicationService(
                    session, indexing_enabled=self.indexing_enabled
                ).republish_page_in_transaction(
                    owner_id=message.owner_id, run_id=run_id, limit=100, now=self.clock()
                )
            if progress["status"] == "failed":
                raise self._failure("publication_policy_changed", JobFailureCategory.INVALID_INPUT)
            if checkpoint:
                checkpoint_sequence += 1
                checkpoint(
                    checkpoint_sequence,
                    {
                        "publication_run_id": str(run_id),
                        "after_content_id": str(progress["after"]) if progress["after"] else None,
                        "processed_count": int(progress["processed"]),
                        "status": str(progress["status"]),
                    },
                )
            if progress["status"] == "completed":
                return JobCompletion(status=JobStatus.SUCCEEDED)

    def _failure(self, code: str, category: JobFailureCategory) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=category,
            occurred_at=self.clock(),
            next_action="核对发布许可修订与固定材料后重新受理重建",
            manual_retry_allowed=False,
        )
