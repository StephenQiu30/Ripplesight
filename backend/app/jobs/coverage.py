from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import TypedDict, Unpack
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from analysis.schemas import WindowAnnotationCountView
from connections.schemas import SourceExecutionPolicy
from connections.services import list_current_source_connection_versions_in_transaction
from content.schemas import CollectionContentFactView, CollectionSnapshotFactView
from core.errors import ApplicationError
from jobs.models import (
    CollectionDueWindow,
    CoverageWindow,
    Job,
    JobAttempt,
    ResourceBudgetPolicy,
    ResourceBudgetReservation,
    ResourceUsageAttempt,
)
from jobs.schemas import (
    AnalysisJobFactView,
    CollectionCoverageAnalysisView,
    CollectionCoverageAttemptView,
    CollectionCoverageBudgetView,
    CollectionCoverageGapView,
    CollectionCoverageResultStatus,
    CollectionCoverageView,
    CollectionDueWindowInput,
    CollectionDueWindowView,
    CollectionExecutionFactView,
    CoverageWindowStatus,
    DueAdmissionState,
    DueSkipReason,
    JobStatus,
)
from sources.contracts import SourceCapability


class CollectionDueConflictError(ValueError):
    """The same scheduled instant has incompatible immutable facts or admission."""


class _CoverageCursorContext(TypedDict):
    owner_id: UUID
    start: datetime
    end: datetime
    source_key: str | None
    capability: SourceCapability | None
    topic_id: UUID | None


@dataclass(frozen=True, slots=True)
class HotlistDueIdentity:
    due_at: datetime
    operation_id: UUID


def load_hotlist_due_for_job_in_transaction(
    session: Session, *, owner_id: UUID, job_id: UUID, source_key: str, operation_id: UUID
) -> HotlistDueIdentity:
    """Resolve the accepted bucket through the jobs domain without leaking its ORM model."""
    if not session.in_transaction():
        raise RuntimeError("hotlist due lookup requires the caller's transaction")
    row = session.scalar(
        select(CollectionDueWindow).where(
            CollectionDueWindow.owner_id == owner_id,
            CollectionDueWindow.job_id == job_id,
            CollectionDueWindow.source_key == source_key,
            CollectionDueWindow.capability == SourceCapability.HOTLIST.value,
            CollectionDueWindow.operation_id == operation_id,
            CollectionDueWindow.admission_state == DueAdmissionState.ACCEPTED.value,
        )
    )
    if row is None:
        raise ValueError("hotlist job is not linked to its accepted due bucket")
    return HotlistDueIdentity(due_at=_as_utc(row.due_at), operation_id=operation_id)


def _as_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("due window timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _automatic_skip(command: CollectionDueWindowInput) -> DueSkipReason | None:
    policy = command.policy_snapshot
    if policy is None:
        return None
    if not policy.enabled:
        return DueSkipReason.DISABLED
    if policy.quiet_at(command.due_at):
        return DueSkipReason.QUIET
    return None


class CollectionDueWindowService:
    """Own due facts; the scheduler and JobService share the caller's transaction."""

    def __init__(self, session: Session, *, clock: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def record_due_in_transaction(
        self, command: CollectionDueWindowInput
    ) -> CollectionDueWindowView:
        self._require_transaction()
        now = _as_utc(self._clock())
        skip = _automatic_skip(command)
        self._session.execute(
            insert(CollectionDueWindow)
            .values(
                id=uuid4(),
                owner_id=command.owner_id,
                schedule_key=command.schedule_key,
                topic_id=command.topic_id,
                source_key=command.source_key,
                capability=command.capability.value,
                due_at=command.due_at,
                window_start=command.window_start,
                window_end=command.window_end,
                connection_version=command.connection_version,
                policy_snapshot=(
                    command.policy_snapshot.model_dump(mode="json")
                    if command.policy_snapshot is not None
                    else None
                ),
                admission_state=(DueAdmissionState.SKIPPED if skip else DueAdmissionState.PENDING),
                reason=skip.value if skip else None,
                recorded_at=now,
            )
            .on_conflict_do_nothing(constraint="collection_due_windows_owner_schedule_due_key")
        )
        model = self._lock(command.owner_id, command.schedule_key, command.due_at)
        if (
            model.topic_id != command.topic_id
            or model.source_key != command.source_key
            or model.capability != command.capability.value
            or _as_utc(model.window_start) != command.window_start
            or _as_utc(model.window_end) != command.window_end
            or model.connection_version != command.connection_version
            or model.policy_snapshot
            != (
                command.policy_snapshot.model_dump(mode="json")
                if command.policy_snapshot is not None
                else None
            )
        ):
            raise CollectionDueConflictError("scheduled instant conflicts with its frozen facts")
        return self._view(model)

    def record_elapsed_in_transaction(
        self,
        *,
        first_due: CollectionDueWindowInput,
        interval_seconds: int,
        through_at: datetime,
        snapshot_at: Callable[[datetime], tuple[int | None, SourceExecutionPolicy | None]],
    ) -> tuple[CollectionDueWindowView, ...]:
        """Replay deterministic due instants after a stopped scan, without inventing jobs."""
        self._require_transaction()
        through = _as_utc(through_at)
        if not 1 <= interval_seconds <= 86_400 or first_due.due_at > through:
            raise ValueError("recovery needs a bounded interval and a prior due point")
        cadence = timedelta(seconds=interval_seconds)
        count = (through - first_due.due_at) // cadence + 1
        latest = self._session.scalar(
            select(func.max(CollectionDueWindow.due_at)).where(
                CollectionDueWindow.owner_id == first_due.owner_id,
                CollectionDueWindow.schedule_key == first_due.schedule_key,
            )
        )
        start_index = 0
        if latest is not None:
            elapsed = _as_utc(latest) - first_due.due_at
            if elapsed < timedelta(0) or elapsed % cadence:
                raise CollectionDueConflictError(
                    "last persisted due is outside the recovery cadence"
                )
            start_index = elapsed // cadence
        if count - start_index > 1000:
            raise ValueError("recover at most 1000 due points per transaction")
        result: list[CollectionDueWindowView] = []
        for index in range(start_index, count):
            offset = timedelta(seconds=index * interval_seconds)
            due_at = first_due.due_at + offset
            connection_version, policy_snapshot = snapshot_at(due_at)
            command = first_due.model_copy(
                update={
                    "due_at": due_at,
                    "window_start": first_due.window_start + offset,
                    "window_end": first_due.window_end + offset,
                    "connection_version": connection_version,
                    "policy_snapshot": policy_snapshot,
                }
            )
            recorded = self.record_due_in_transaction(command)
            if recorded.admission_state is DueAdmissionState.PENDING and index < count - 1:
                recorded = self.mark_missed_in_transaction(
                    owner_id=command.owner_id,
                    schedule_key=command.schedule_key,
                    due_at=command.due_at,
                )
            result.append(recorded)
        return tuple(result)

    def mark_accepted_in_transaction(
        self,
        *,
        owner_id: UUID,
        schedule_key: UUID,
        due_at: datetime,
        operation_id: UUID,
        job_id: UUID,
    ) -> CollectionDueWindowView:
        self._require_transaction()
        model = self._lock(owner_id, schedule_key, due_at)
        job = self._session.get(Job, job_id)
        if (
            job is None
            or job.owner_id != owner_id
            or job.operation_id != operation_id
            or job.source_key != model.source_key
            or job.source_capability != model.capability
            or model.connection_version is None
            or model.policy_snapshot is None
            or job.scope.get("connection_version") != model.connection_version
            or (model.topic_id is not None and job.configuration_ref != f"topic:{model.topic_id}")
        ):
            raise CollectionDueConflictError("accepted due requires an existing owner-scoped job")
        if model.admission_state == DueAdmissionState.ACCEPTED:
            if model.job_id != job_id or model.operation_id != operation_id:
                raise CollectionDueConflictError("due was accepted for another job")
            return self._view(model)
        if model.admission_state != DueAdmissionState.PENDING:
            raise CollectionDueConflictError("only a pending due may be accepted")
        model.admission_state = DueAdmissionState.ACCEPTED.value
        model.operation_id = operation_id
        model.job_id = job_id
        return self._view(model)

    def mark_skipped_in_transaction(
        self,
        *,
        owner_id: UUID,
        schedule_key: UUID,
        due_at: datetime,
        reason: DueSkipReason,
    ) -> CollectionDueWindowView:
        self._require_transaction()
        model = self._lock(owner_id, schedule_key, due_at)
        if model.admission_state == DueAdmissionState.SKIPPED and model.reason == reason.value:
            return self._view(model)
        if model.admission_state != DueAdmissionState.PENDING:
            raise CollectionDueConflictError("only a pending due may be skipped")
        model.admission_state = DueAdmissionState.SKIPPED.value
        model.reason = reason.value
        return self._view(model)

    def mark_missed_in_transaction(
        self, *, owner_id: UUID, schedule_key: UUID, due_at: datetime
    ) -> CollectionDueWindowView:
        self._require_transaction()
        model = self._lock(owner_id, schedule_key, due_at)
        if model.admission_state == DueAdmissionState.MISSED:
            return self._view(model)
        if model.admission_state != DueAdmissionState.PENDING:
            raise CollectionDueConflictError("only a pending due may be marked missed")
        model.admission_state = DueAdmissionState.MISSED.value
        model.reason = "scheduler_interrupted"
        return self._view(model)

    def list_due(
        self, *, owner_id: UUID, start: datetime, end: datetime
    ) -> tuple[CollectionDueWindowView, ...]:
        start, end = _as_utc(start), _as_utc(end)
        if start >= end:
            raise ValueError("due query must be a forward half-open range")
        rows = self._session.scalars(
            select(CollectionDueWindow)
            .where(
                CollectionDueWindow.owner_id == owner_id,
                CollectionDueWindow.due_at >= start,
                CollectionDueWindow.due_at < end,
            )
            .order_by(CollectionDueWindow.due_at, CollectionDueWindow.schedule_key)
        ).all()
        return tuple(self._view(row) for row in rows)

    def list_execution_facts(
        self, *, owner_id: UUID, start: datetime, end: datetime
    ) -> tuple[CollectionExecutionFactView, ...]:
        """Project job, attempt, budget and coverage facts without content ORM access."""
        result: list[CollectionExecutionFactView] = []
        for due in self.list_due(owner_id=owner_id, start=start, end=end):
            if due.job_id is None:
                result.append(
                    CollectionExecutionFactView(
                        due=due,
                        job_status=None,
                        requests_sent=None,
                        request_attempt_count=None,
                        charged_request_count=None,
                        request_budget_reconciled=None,
                        page_count=None,
                        observed_count=None,
                        coverage_status=None,
                        stop_reason=due.reason,
                        has_gap=True,
                    )
                )
                continue
            job = self._session.get(Job, due.job_id)
            if job is None or job.owner_id != owner_id or job.operation_id != due.operation_id:
                raise RuntimeError("accepted due has no owner-scoped job")
            usage_attempts = self._session.scalars(
                select(ResourceUsageAttempt).where(
                    ResourceUsageAttempt.owner_id == owner_id,
                    ResourceUsageAttempt.operation_id == job.operation_id,
                    ResourceUsageAttempt.usage_kind == "network_request",
                )
            ).all()
            reservations = self._session.scalars(
                select(ResourceBudgetReservation).where(
                    ResourceBudgetReservation.owner_id == owner_id,
                    ResourceBudgetReservation.operation_id == job.operation_id,
                    ResourceBudgetReservation.metric == "network_request",
                )
            ).all()
            budget_rows_by_attempt: dict[UUID, list[ResourceBudgetReservation]] = {}
            for row in reservations:
                budget_rows_by_attempt.setdefault(row.reservation_id, []).append(row)
            attempted_ids = {row.attempt_id for row in usage_attempts}
            reconciled = (
                job.requests_sent == len(attempted_ids)
                and attempted_ids == set(budget_rows_by_attempt)
                and all(
                    row.status == "settled" and row.actual_units == 1
                    for rows in budget_rows_by_attempt.values()
                    for row in rows
                )
            )
            charged_count = len(attempted_ids) if reconciled else None
            coverage = self._session.scalars(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.last_job_id == job.id,
                )
            ).all()
            page_count = sum(row.page_count for row in coverage)
            observed = job.checkpoint.get("collection.observed_count")
            if observed is not None and (type(observed) is not int or observed < 0):
                raise RuntimeError("collection observed count checkpoint is invalid")
            if observed is None and page_count == 0 and job.requests_sent == 0:
                observed = 0
            if observed is None and job.last_error_code == "hotlist_source_empty":
                observed = 0
            if job.kind == "source.hotlist" and job.checkpoint.get("snapshot_id") is not None:
                page_count = 1
            confirmed = bool(coverage) and all(row.status == "confirmed" for row in coverage)
            status = (
                CoverageWindowStatus.CONFIRMED
                if confirmed
                else CoverageWindowStatus.PARTIAL
                if any(row.status == "partial" for row in coverage)
                else CoverageWindowStatus.RUNNING
                if any(row.status == "running" for row in coverage)
                else None
            )
            result.append(
                CollectionExecutionFactView(
                    due=due,
                    job_status=JobStatus(job.status),
                    requests_sent=job.requests_sent,
                    request_attempt_count=len(attempted_ids),
                    charged_request_count=charged_count,
                    request_budget_reconciled=reconciled,
                    page_count=page_count,
                    observed_count=observed,
                    coverage_status=status,
                    stop_reason=(
                        next((row.stop_reason for row in coverage if row.stop_reason), None)
                        or job.last_error_code
                    ),
                    has_gap=not confirmed or not reconciled,
                )
            )
        return tuple(result)

    def list_analysis_jobs_in_transaction(
        self, *, owner_id: UUID, topic_ids: set[UUID] | None = None
    ) -> tuple[AnalysisJobFactView, ...]:
        if not self._session.in_transaction():
            raise RuntimeError("analysis job reads require the caller's transaction")
        if topic_ids is not None and not topic_ids:
            return ()
        query = select(Job).where(Job.owner_id == owner_id, Job.kind == "analysis.annotate")
        if topic_ids is not None:
            query = query.where(
                Job.configuration_ref.in_(tuple(f"topic:{topic_id}" for topic_id in topic_ids))
            )
        rows = self._session.scalars(query).all()
        return tuple(
            AnalysisJobFactView(
                id=row.id,
                status=JobStatus(row.status),
                scope=row.scope,
                last_error_code=row.last_error_code,
            )
            for row in rows
        )

    def _lock(self, owner_id: UUID, schedule_key: UUID, due_at: datetime) -> CollectionDueWindow:
        model = self._session.scalar(
            select(CollectionDueWindow)
            .where(
                CollectionDueWindow.owner_id == owner_id,
                CollectionDueWindow.schedule_key == schedule_key,
                CollectionDueWindow.due_at == _as_utc(due_at),
            )
            .with_for_update()
        )
        if model is None:
            raise CollectionDueConflictError("due window is not recorded")
        return model

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("due mutations require the caller's transaction")

    @staticmethod
    def _view(model: CollectionDueWindow) -> CollectionDueWindowView:
        return CollectionDueWindowView(
            id=model.id,
            owner_id=model.owner_id,
            schedule_key=model.schedule_key,
            topic_id=model.topic_id,
            source_key=model.source_key,
            capability=SourceCapability(model.capability),
            due_at=_as_utc(model.due_at),
            window_start=_as_utc(model.window_start),
            window_end=_as_utc(model.window_end),
            connection_version=model.connection_version,
            policy_snapshot=(
                SourceExecutionPolicy.model_validate(model.policy_snapshot)
                if model.policy_snapshot is not None
                else None
            ),
            admission_state=DueAdmissionState(model.admission_state),
            reason=model.reason,
            operation_id=model.operation_id,
            job_id=model.job_id,
            recorded_at=_as_utc(model.recorded_at),
        )


class CollectionCoverageQueryService:
    """Read a bounded page of owner-visible due windows and their committed facts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_coverage(
        self,
        *,
        owner_id: UUID,
        start: datetime,
        end: datetime,
        source_key: str | None = None,
        capability: SourceCapability | None = None,
        topic_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[tuple[CollectionCoverageView, ...], str | None]:
        if (
            start.utcoffset() != timedelta(0)
            or end.utcoffset() != timedelta(0)
            or not start < end <= start + timedelta(days=31)
            or not 1 <= limit <= 100
        ):
            raise ValueError("coverage query needs a UTC range of at most 31 days")
        cursor_id = (
            self._decode_cursor(
                cursor,
                owner_id=owner_id,
                start=start,
                end=end,
                source_key=source_key,
                capability=capability,
                topic_id=topic_id,
            )
            if cursor is not None
            else None
        )
        connections = self._visible_connections(owner_id=owner_id)
        if not connections:
            if cursor_id is not None:
                raise ValueError("coverage cursor does not belong to this query")
            return (), None
        query = select(CollectionDueWindow).where(
            CollectionDueWindow.owner_id == owner_id,
            CollectionDueWindow.source_key.in_(connections),
            CollectionDueWindow.due_at >= start,
            CollectionDueWindow.due_at < end,
        )
        if source_key is not None:
            query = query.where(CollectionDueWindow.source_key == source_key)
        if capability is not None:
            query = query.where(CollectionDueWindow.capability == capability.value)
        if topic_id is not None:
            query = query.where(CollectionDueWindow.topic_id == topic_id)
        if cursor_id is not None:
            anchor = self._session.scalar(query.where(CollectionDueWindow.id == cursor_id))
            if anchor is None:
                raise ValueError("coverage cursor does not belong to this query")
            query = query.where(
                or_(
                    CollectionDueWindow.due_at < anchor.due_at,
                    and_(
                        CollectionDueWindow.due_at == anchor.due_at,
                        CollectionDueWindow.id < anchor.id,
                    ),
                )
            )
        rows = self._session.scalars(
            query.order_by(CollectionDueWindow.due_at.desc(), CollectionDueWindow.id.desc()).limit(
                limit + 1
            )
        ).all()
        page = [(row, connections[row.source_key]) for row in rows[:limit]]
        next_cursor = (
            self._encode_cursor(
                page[-1][0].id,
                owner_id=owner_id,
                start=start,
                end=end,
                source_key=source_key,
                capability=capability,
                topic_id=topic_id,
            )
            if len(rows) > limit
            else None
        )
        return self._project(owner_id=owner_id, rows=page), next_cursor

    def get_coverage(self, *, owner_id: UUID, window_id: UUID) -> CollectionCoverageView:
        connections = self._visible_connections(owner_id=owner_id)
        row = self._session.scalar(
            select(CollectionDueWindow).where(
                CollectionDueWindow.owner_id == owner_id,
                CollectionDueWindow.source_key.in_(connections),
                CollectionDueWindow.id == window_id,
            )
        )
        if row is None:
            raise ApplicationError("resource_not_found")
        return self._project(owner_id=owner_id, rows=((row, connections[row.source_key]),))[0]

    def _visible_connections(self, *, owner_id: UUID) -> dict[str, int]:
        return {
            item.source_key: item.current_version
            for item in list_current_source_connection_versions_in_transaction(
                self._session, owner_id=owner_id
            )
        }

    @staticmethod
    def _cursor_digest(
        window_id: UUID,
        *,
        owner_id: UUID,
        start: datetime,
        end: datetime,
        source_key: str | None,
        capability: SourceCapability | None,
        topic_id: UUID | None,
    ) -> bytes:
        context = json.dumps(
            [
                str(owner_id),
                start.isoformat(),
                end.isoformat(),
                source_key,
                capability.value if capability is not None else None,
                str(topic_id) if topic_id is not None else None,
                str(window_id),
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(context.encode()).digest()[:16]

    @classmethod
    def _encode_cursor(cls, window_id: UUID, **context: Unpack[_CoverageCursorContext]) -> str:
        digest = cls._cursor_digest(window_id, **context)
        return base64.urlsafe_b64encode(b"\x01" + window_id.bytes + digest).decode().rstrip("=")

    @classmethod
    def _decode_cursor(cls, token: str, **context: Unpack[_CoverageCursorContext]) -> UUID:
        try:
            if len(token) != 44:
                raise ValueError("invalid cursor length")
            raw = base64.b64decode(token, altchars=b"-_", validate=True)
            if len(raw) != 33 or raw[0] != 1:
                raise ValueError("invalid cursor payload")
            window_id = UUID(bytes=raw[1:17])
            digest = cls._cursor_digest(window_id, **context)
            if not hmac.compare_digest(raw[17:], digest):
                raise ValueError("cursor does not match query")
            return window_id
        except (ValueError, binascii.Error) as error:
            raise ValueError("invalid coverage cursor") from error

    @staticmethod
    def _range_gaps(
        *, due: CollectionDueWindow, coverage: list[CoverageWindow]
    ) -> tuple[CollectionCoverageGapView, ...]:
        start, end = _as_utc(due.window_start), _as_utc(due.window_end)
        clipped = [
            (max(start, _as_utc(row.starts_at)), min(end, _as_utc(row.ends_at)), row)
            for row in coverage
            if row.starts_at < end and row.ends_at > start
        ]
        boundaries = sorted(
            {start, end, *(point for left, right, _ in clipped for point in (left, right))}
        )
        gaps: list[CollectionCoverageGapView] = []
        for left, right in pairwise(boundaries):
            if any(
                low <= left <= right <= high and row.status == CoverageWindowStatus.CONFIRMED.value
                for low, high, row in clipped
            ):
                continue
            reason = next(
                (
                    row.stop_reason
                    for low, high, row in clipped
                    if low <= left <= right <= high and row.stop_reason
                ),
                "unverified_terminal",
            )
            if gaps and gaps[-1].ends_at == left and gaps[-1].reason == reason:
                previous = gaps.pop()
                left = previous.starts_at
            gaps.append(CollectionCoverageGapView(starts_at=left, ends_at=right, reason=reason))
        return tuple(gaps)

    def _project(
        self, *, owner_id: UUID, rows: Sequence[tuple[CollectionDueWindow, int]]
    ) -> tuple[CollectionCoverageView, ...]:
        if not rows:
            return ()
        # Selection and access checks precede every cross-domain lookup.
        dues = [row[0] for row in rows]
        current_versions = {row[0].id: row[1] for row in rows}
        job_ids = tuple(due.job_id for due in dues if due.job_id is not None)
        jobs = {
            job.id: job
            for job in self._session.scalars(
                select(Job).where(Job.owner_id == owner_id, Job.id.in_(job_ids))
            ).all()
        }
        if len(jobs) != len(job_ids):
            raise RuntimeError("accepted coverage due has no owner-scoped Job")
        attempts_by_job: dict[UUID, list[JobAttempt]] = defaultdict(list)
        coverage_by_job: dict[UUID, list[CoverageWindow]] = defaultdict(list)
        range_coverage_by_job: dict[UUID, list[CoverageWindow]] = defaultdict(list)
        if job_ids:
            for attempt in self._session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id.in_(job_ids))
                .order_by(JobAttempt.started_at, JobAttempt.id)
            ):
                attempts_by_job[attempt.job_id].append(attempt)
            for window in self._session.scalars(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.last_job_id.in_(job_ids),
                )
            ):
                if window.last_job_id is not None:
                    coverage_by_job[window.last_job_id].append(window)
            target_hashes = {
                bytes.fromhex(raw_hash)
                for job in jobs.values()
                if isinstance((raw_hash := job.scope.get("target_hash")), str)
                and len(raw_hash) == 64
                and all(character in "0123456789abcdef" for character in raw_hash)
            }
            if target_hashes:
                by_scope: dict[tuple[str, str, bytes, str, int], list[CoverageWindow]] = (
                    defaultdict(list)
                )
                for window in self._session.scalars(
                    select(CoverageWindow).where(
                        CoverageWindow.owner_id == owner_id,
                        CoverageWindow.target_hash.in_(target_hashes),
                        CoverageWindow.starts_at < max(due.window_end for due in dues),
                        CoverageWindow.ends_at > min(due.window_start for due in dues),
                    )
                ):
                    by_scope[
                        (
                            window.source_key,
                            window.capability,
                            window.target_hash,
                            window.sort_key,
                            window.rule_version,
                        )
                    ].append(window)
                for due in dues:
                    if due.job_id is None:
                        continue
                    job = jobs[due.job_id]
                    raw_hash = job.scope.get("target_hash")
                    sort_key = job.scope.get("sort_key")
                    rule_version = job.scope.get("rule_version")
                    if (
                        not isinstance(raw_hash, str)
                        or len(raw_hash) != 64
                        or any(character not in "0123456789abcdef" for character in raw_hash)
                        or not isinstance(sort_key, str)
                        or type(rule_version) is not int
                    ):
                        continue
                    scope = (
                        due.source_key,
                        due.capability,
                        bytes.fromhex(raw_hash),
                        sort_key,
                        rule_version,
                    )
                    range_coverage_by_job[due.job_id] = [
                        window
                        for window in by_scope.get(scope, ())
                        if window.starts_at < due.window_end and window.ends_at > due.window_start
                    ]
        operation_ids = tuple(job.operation_id for job in jobs.values())
        usage_by_operation: dict[UUID, list[ResourceUsageAttempt]] = defaultdict(list)
        reservations_by_operation: dict[UUID, list[tuple[ResourceBudgetReservation, str]]] = (
            defaultdict(list)
        )
        if operation_ids:
            for usage in self._session.scalars(
                select(ResourceUsageAttempt).where(
                    ResourceUsageAttempt.owner_id == owner_id,
                    ResourceUsageAttempt.operation_id.in_(operation_ids),
                    ResourceUsageAttempt.usage_kind == "network_request",
                )
            ):
                usage_by_operation[usage.operation_id].append(usage)
            for reservation, budget_key in self._session.execute(
                select(ResourceBudgetReservation, ResourceBudgetPolicy.budget_key)
                .join(
                    ResourceBudgetPolicy,
                    and_(
                        ResourceBudgetPolicy.id == ResourceBudgetReservation.budget_policy_id,
                        ResourceBudgetPolicy.owner_id == ResourceBudgetReservation.owner_id,
                    ),
                )
                .where(
                    ResourceBudgetReservation.owner_id == owner_id,
                    ResourceBudgetReservation.operation_id.in_(operation_ids),
                    ResourceBudgetReservation.metric == "network_request",
                )
            ):
                reservations_by_operation[reservation.operation_id].append(
                    (reservation, budget_key)
                )

        # Content and analysis remain owned by their services. Both read all page jobs at once.
        from content.services import ContentService

        content_service = ContentService(self._session)
        content_by_job = {
            fact.job_id: fact
            for fact in content_service.collection_facts_in_transaction(
                owner_id=owner_id, job_ids=job_ids
            )
        }
        snapshots_by_job = {
            fact.job_id: fact
            for fact in content_service.collection_snapshot_facts_in_transaction(
                owner_id=owner_id, job_ids=job_ids
            )
            if fact.snapshot_id is not None
        }
        targets_by_job = {
            due.job_id: (
                due.topic_id,
                jobs[due.job_id].configuration_version,
                content_by_job[due.job_id].content_version_ids,
            )
            for due in dues
            if due.job_id is not None
            and due.topic_id is not None
            and jobs[due.job_id].configuration_ref == f"topic:{due.topic_id}"
            and due.job_id in content_by_job
            and content_by_job[due.job_id].analysis_targets_complete
            and (
                content_by_job[due.job_id].content_version_ids
                or jobs[due.job_id].status == JobStatus.SUCCEEDED.value
            )
        }
        from analysis.services import AnalysisService

        analysis_by_job = AnalysisService(self._session).collection_analysis_counts_in_transaction(
            owner_id=owner_id, targets_by_job=targets_by_job
        )
        return tuple(
            self._view(
                due=due,
                current_connection_version=current_versions[due.id],
                job=jobs.get(due.job_id) if due.job_id is not None else None,
                attempts=attempts_by_job.get(due.job_id, []) if due.job_id is not None else [],
                coverage=coverage_by_job.get(due.job_id, []) if due.job_id is not None else [],
                range_coverage=range_coverage_by_job.get(due.job_id, [])
                if due.job_id is not None
                else [],
                usage=usage_by_operation.get(jobs[due.job_id].operation_id, [])
                if due.job_id is not None
                else [],
                reservations=reservations_by_operation.get(jobs[due.job_id].operation_id, [])
                if due.job_id is not None
                else [],
                content=content_by_job.get(due.job_id) if due.job_id is not None else None,
                snapshot=snapshots_by_job.get(due.job_id) if due.job_id is not None else None,
                analysis=analysis_by_job.get(due.job_id) if due.job_id is not None else None,
            )
            for due in dues
        )

    @staticmethod
    def _view(
        *,
        due: CollectionDueWindow,
        current_connection_version: int,
        job: Job | None,
        attempts: list[JobAttempt],
        coverage: list[CoverageWindow],
        range_coverage: list[CoverageWindow],
        usage: list[ResourceUsageAttempt],
        reservations: list[tuple[ResourceBudgetReservation, str]],
        content: CollectionContentFactView | None,
        snapshot: CollectionSnapshotFactView | None,
        analysis: WindowAnnotationCountView | None,
    ) -> CollectionCoverageView:
        if job is not None and (
            job.owner_id != due.owner_id or job.operation_id != due.operation_id
        ):
            raise RuntimeError("coverage due and Job identity disagree")
        matching_coverage = [
            window
            for window in range_coverage
            if window.source_key == due.source_key
            and window.capability == due.capability
            and job is not None
            and window.rule_version == job.configuration_version
            and window.target_hash.hex() == job.scope.get("target_hash")
            and window.sort_key == job.scope.get("sort_key")
        ]
        gaps = (
            ()
            if snapshot is not None and due.capability == SourceCapability.HOTLIST.value
            else CollectionCoverageQueryService._range_gaps(due=due, coverage=matching_coverage)
        )
        attempt_ids = {row.attempt_id for row in usage}
        reservations_by_attempt: dict[UUID, list[ResourceBudgetReservation]] = defaultdict(list)
        for reservation, _ in reservations:
            reservations_by_attempt[reservation.reservation_id].append(reservation)
        budget_reconciled = job is not None and (
            job.requests_sent == len(attempt_ids)
            and attempt_ids == set(reservations_by_attempt)
            and all(
                row.status == "settled" and row.actual_units == 1
                for rows in reservations_by_attempt.values()
                for row in rows
            )
        )
        stop_reason = (
            next((window.stop_reason for window in matching_coverage if window.stop_reason), None)
            or (job.last_error_code if job is not None else None)
            or due.reason
        )
        if job is None:
            status = (
                CollectionCoverageResultStatus.PENDING
                if due.admission_state == DueAdmissionState.PENDING.value
                else CollectionCoverageResultStatus.NOT_ATTEMPTED
            )
        elif job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
            status = CollectionCoverageResultStatus.PENDING
        elif job.status == JobStatus.CANCELLED.value:
            status = CollectionCoverageResultStatus.STOPPED
        elif job.status == JobStatus.FAILED.value:
            status = CollectionCoverageResultStatus.FAILED
        elif (snapshot is not None and snapshot.entry_count == 0) or (
            usage and all(row.outcome == "empty" for row in usage)
        ):
            status = CollectionCoverageResultStatus.EMPTY
        elif job.status == JobStatus.PARTIALLY_SUCCEEDED.value:
            status = CollectionCoverageResultStatus.PARTIAL
        elif (matching_coverage and not gaps) or snapshot is not None:
            status = CollectionCoverageResultStatus.COMPLETE
        else:
            status = CollectionCoverageResultStatus.PARTIAL
        if job is not None and not budget_reconciled:
            if status in {
                CollectionCoverageResultStatus.COMPLETE,
                CollectionCoverageResultStatus.EMPTY,
            }:
                status = CollectionCoverageResultStatus.PARTIAL
            gaps = (
                *gaps,
                CollectionCoverageGapView(
                    starts_at=_as_utc(due.window_start),
                    ends_at=_as_utc(due.window_end),
                    reason="request_budget_unreconciled",
                ),
            )
            stop_reason = stop_reason or "request_budget_unreconciled"
        if stop_reason is None and status in {
            CollectionCoverageResultStatus.STOPPED,
            CollectionCoverageResultStatus.FAILED,
        }:
            stop_reason = status.value
        if matching_coverage and not gaps:
            terminal_evidence = "verified_terminal"
        elif snapshot is not None:
            terminal_evidence = "snapshot_observed"
        elif matching_coverage:
            terminal_evidence = "unverified_terminal"
        else:
            terminal_evidence = None
        if not matching_coverage and snapshot is None:
            gaps = (
                CollectionCoverageGapView(
                    starts_at=_as_utc(due.window_start),
                    ends_at=_as_utc(due.window_end),
                    reason=stop_reason or status.value,
                ),
                *tuple(gap for gap in gaps if gap.reason == "request_budget_unreconciled"),
            )
        budget_totals: dict[tuple[str, int, int], list[int]] = {}
        for reservation, budget_key in reservations:
            key = (budget_key, reservation.policy_version, reservation.limit_units)
            totals = budget_totals.setdefault(key, [0, 0])
            if reservation.status == "reserved":
                totals[0] += reservation.requested_units
            elif reservation.actual_units is not None:
                totals[1] += reservation.actual_units
        budgets = (
            tuple(
                CollectionCoverageBudgetView(
                    budget_key=key[0],
                    policy_version=key[1],
                    limit_units=key[2],
                    reserved_units=totals[0],
                    consumed_units=totals[1],
                )
                for key, totals in sorted(budget_totals.items())
            )
            if reservations
            else None
        )
        observed = job.checkpoint.get("collection.observed_count") if job is not None else None
        if observed is not None and (type(observed) is not int or observed < 0):
            raise RuntimeError("collection observed count checkpoint is invalid")
        if observed is None and snapshot is not None:
            observed = snapshot.entry_count
        if observed is None and job is not None and job.requests_sent == 0:
            observed = 0
        page_count = (
            sum(window.page_count for window in coverage)
            if coverage
            else 1
            if snapshot is not None
            else 0
            if job is not None and job.requests_sent == 0
            else None
        )
        success_times = (
            [job.completed_at]
            if job is not None and job.status == JobStatus.SUCCEEDED.value and job.completed_at
            else []
        )
        if snapshot is not None and snapshot.observed_at is not None:
            success_times.append(snapshot.observed_at)
        return CollectionCoverageView(
            window_id=due.id,
            source_key=due.source_key,
            capability=SourceCapability(due.capability),
            topic_id=due.topic_id,
            due_at=_as_utc(due.due_at),
            window_start=_as_utc(due.window_start),
            window_end=_as_utc(due.window_end),
            admission_state=DueAdmissionState(due.admission_state),
            admission_reason=due.reason,
            current_connection_version=current_connection_version,
            job_connection_version=(
                job.scope.get("connection_version")
                if job is not None and type(job.scope.get("connection_version")) is int
                else None
            ),
            job_id=job.id if job is not None else None,
            job_status=JobStatus(job.status) if job is not None else None,
            attempts=tuple(
                CollectionCoverageAttemptView(
                    attempt_id=item.id,
                    collection_cycle_no=item.collection_cycle_no,
                    started_at=_as_utc(item.started_at),
                    finished_at=_as_utc(item.finished_at) if item.finished_at else None,
                    outcome=item.outcome,
                )
                for item in attempts
            )
            if job is not None
            else None,
            started_at=_as_utc(job.started_at) if job is not None and job.started_at else None,
            finished_at=_as_utc(job.completed_at) if job is not None and job.completed_at else None,
            last_success_at=max(success_times) if success_times else None,
            coverage_status=status,
            terminal_evidence=terminal_evidence,
            stop_reason=stop_reason,
            request_count=job.requests_sent if job is not None else None,
            request_attempt_count=len({row.attempt_id for row in usage})
            if job is not None
            else None,
            page_count=page_count,
            observed_count=observed,
            inserted_count=content.first_ingested_count if content is not None else None,
            deduplicated_count=content.deduplicated_count if content is not None else None,
            analysis=CollectionCoverageAnalysisView(
                pending_count=analysis.pending_count,
                failed_count=analysis.failed_count,
                invalid_count=analysis.abnormal_count,
                valid_count=analysis.annotated_count,
            )
            if analysis is not None
            else None,
            budgets=budgets,
            gaps=gaps,
            content_ids=content.content_ids if content is not None else None,
            snapshot_ids=(snapshot.snapshot_id,)
            if snapshot is not None
            else ()
            if job is not None
            else None,
        )
