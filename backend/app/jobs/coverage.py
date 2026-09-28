from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from connections.schemas import SourceExecutionPolicy
from content.models import HotlistSnapshot
from jobs.models import (
    CollectionDueWindow,
    CoverageWindow,
    Job,
    JobAttempt,
    ResourceBudgetReservation,
    ResourceUsageAttempt,
)
from jobs.schemas import (
    AnalysisJobFactView,
    CollectionCoverageGapView,
    CollectionCoverageStatus,
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

if TYPE_CHECKING:
    from analysis.services import AnalysisService
    from content.services import ContentService

from analysis.schemas import WindowAnnotationCountView
from connections.schemas import SourceConnectionFactView
from connections.services import load_current_connection_facts_in_transaction
from content.schemas import CollectionContentCountView, CollectionSnapshotFactView


class CollectionDueConflictError(ValueError):
    """The same scheduled instant has incompatible immutable facts or admission."""


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
        """Project due, job, usage and committed snapshot facts for each scheduled bucket."""
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
            hotlist_snapshot = None
            if job.kind == "source.hotlist":
                hotlist_snapshot = self._session.scalar(
                    select(HotlistSnapshot).where(
                        HotlistSnapshot.owner_id == owner_id,
                        HotlistSnapshot.due_window_id == due.id,
                        HotlistSnapshot.job_id == job.id,
                        HotlistSnapshot.operation_id == job.operation_id,
                        HotlistSnapshot.source_key == due.source_key,
                    )
                )
                if hotlist_snapshot is not None:
                    page_count = 1
                    observed = hotlist_snapshot.entry_count
            confirmed = bool(coverage) and all(row.status == "confirmed" for row in coverage)
            if job.kind == "source.hotlist":
                confirmed = hotlist_snapshot is not None and job.status == JobStatus.SUCCEEDED.value
            status = (
                CoverageWindowStatus.CONFIRMED
                if confirmed
                else CoverageWindowStatus.PARTIAL
                if any(row.status == "partial" for row in coverage)
                or (
                    job.kind == "source.hotlist" and job.status in {"failed", "partially_succeeded"}
                )
                else CoverageWindowStatus.RUNNING
                if any(row.status == "running" for row in coverage)
                or (job.kind == "source.hotlist" and job.status in {"queued", "running"})
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
        self, *, owner_id: UUID
    ) -> tuple[AnalysisJobFactView, ...]:
        if not self._session.in_transaction():
            raise RuntimeError("analysis job reads require the caller's transaction")
        rows = self._session.scalars(
            select(Job).where(Job.owner_id == owner_id, Job.kind == "analysis.annotate")
        ).all()
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


class CollectionCoverageService:
    """Compose selected due facts with bounded, owner-scoped domain projections."""

    def __init__(
        self,
        session: Session,
        *,
        content: ContentService,
        analysis: AnalysisService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._content = content
        self._analysis = analysis
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_coverage(
        self,
        *,
        owner_id: UUID,
        start: datetime,
        end: datetime,
        source_key: str | None,
        capability: SourceCapability | None,
        topic_id: UUID | None,
        limit: int,
        cursor: str | None,
        cursor_key: bytes,
    ) -> tuple[list[CollectionCoverageView], str | None]:
        start, end = _as_utc(start), _as_utc(end)
        if start >= end or end - start > timedelta(days=31):
            raise ValueError("coverage range must be forward and at most 31 days")
        if not 1 <= limit <= 100 or len(cursor_key) < 32:
            raise ValueError("invalid coverage pagination context")
        context = json.dumps(
            [
                str(owner_id),
                start.isoformat(),
                end.isoformat(),
                source_key,
                capability.value if capability is not None else None,
                str(topic_id) if topic_id is not None else None,
                limit,
            ],
            separators=(",", ":"),
        ).encode()
        as_of = _as_utc(self._clock())
        anchor: CollectionDueWindow | None = None
        if cursor is not None:
            as_of, anchor_id = self._decode_cursor(cursor, context=context, key=cursor_key)
            anchor = self._session.scalar(
                select(CollectionDueWindow).where(
                    CollectionDueWindow.id == anchor_id,
                    CollectionDueWindow.owner_id == owner_id,
                )
            )
            if anchor is None or not start <= _as_utc(anchor.due_at) < end:
                raise ValueError("invalid coverage cursor boundary")
        conditions = [
            CollectionDueWindow.owner_id == owner_id,
            CollectionDueWindow.due_at >= start,
            CollectionDueWindow.due_at < end,
            CollectionDueWindow.recorded_at <= as_of,
        ]
        if source_key is not None:
            conditions.append(CollectionDueWindow.source_key == source_key)
        if capability is not None:
            conditions.append(CollectionDueWindow.capability == capability.value)
        if topic_id is not None:
            conditions.append(CollectionDueWindow.topic_id == topic_id)
        if anchor is not None:
            conditions.append(
                or_(
                    CollectionDueWindow.due_at < anchor.due_at,
                    and_(
                        CollectionDueWindow.due_at == anchor.due_at,
                        CollectionDueWindow.id < anchor.id,
                    ),
                )
            )
        rows = list(
            self._session.scalars(
                select(CollectionDueWindow)
                .where(*conditions)
                .order_by(CollectionDueWindow.due_at.desc(), CollectionDueWindow.id.desc())
                .limit(limit + 1)
            ).all()
        )
        selected = rows[:limit]
        next_cursor = (
            self._encode_cursor(as_of, selected[-1].id, context=context, key=cursor_key)
            if len(rows) > limit
            else None
        )
        return self._project(owner_id=owner_id, rows=selected), next_cursor

    def get_coverage(self, *, owner_id: UUID, window_id: UUID) -> CollectionCoverageView:
        row = self._session.scalar(
            select(CollectionDueWindow).where(
                CollectionDueWindow.owner_id == owner_id,
                CollectionDueWindow.id == window_id,
            )
        )
        if row is None:
            raise LookupError("coverage window is absent or belongs to another owner")
        return self._project(owner_id=owner_id, rows=[row])[0]

    @staticmethod
    def _encode_cursor(as_of: datetime, row_id: UUID, *, context: bytes, key: bytes) -> str:
        micros = int(as_of.timestamp() * 1_000_000)
        payload = bytes([1]) + micros.to_bytes(8, "big") + row_id.bytes
        signature = hmac.new(key, context + payload, hashlib.sha256).digest()[:16]
        return base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode()

    @staticmethod
    def _decode_cursor(value: str, *, context: bytes, key: bytes) -> tuple[datetime, UUID]:
        try:
            if (
                len(value) > 80
                or not value
                or any(
                    character
                    not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                    for character in value
                )
            ):
                raise ValueError
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            if base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != value:
                raise ValueError
            if len(raw) != 41 or raw[0] != 1:
                raise ValueError
            payload, signature = raw[:25], raw[25:]
            expected = hmac.new(key, context + payload, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            as_of = datetime.fromtimestamp(int.from_bytes(raw[1:9], "big") / 1_000_000, UTC)
            return as_of, UUID(bytes=raw[9:25])
        except (ValueError, OverflowError) as error:
            raise ValueError("invalid coverage cursor") from error

    def _project(
        self, *, owner_id: UUID, rows: list[CollectionDueWindow]
    ) -> list[CollectionCoverageView]:
        if not rows:
            return []
        job_ids = tuple(row.job_id for row in rows if row.job_id is not None)
        jobs = {
            job.id: job
            for job in self._session.scalars(
                select(Job).where(Job.owner_id == owner_id, Job.id.in_(job_ids))
            ).all()
        }
        if len(jobs) != len(set(job_ids)):
            raise RuntimeError("accepted due has no owner-scoped job")
        if any(
            row.job_id is not None
            and (
                jobs[row.job_id].operation_id != row.operation_id
                or jobs[row.job_id].source_key != row.source_key
                or jobs[row.job_id].source_capability != row.capability
            )
            for row in rows
        ):
            raise RuntimeError("accepted due and job facts disagree")
        attempts: dict[UUID, int] = {}
        coverage: dict[UUID, list[CoverageWindow]] = {}
        usage: dict[UUID, set[UUID]] = {}
        reservations: dict[UUID, list[ResourceBudgetReservation]] = {}
        operations = tuple(job.operation_id for job in jobs.values())
        if job_ids:
            for attempt in self._session.scalars(
                select(JobAttempt).where(JobAttempt.job_id.in_(job_ids))
            ):
                attempts[attempt.job_id] = attempts.get(attempt.job_id, 0) + 1
            for window in self._session.scalars(
                select(CoverageWindow).where(
                    CoverageWindow.owner_id == owner_id,
                    CoverageWindow.last_job_id.in_(job_ids),
                )
            ):
                if window.last_job_id is not None:
                    coverage.setdefault(window.last_job_id, []).append(window)
            for usage_attempt in self._session.scalars(
                select(ResourceUsageAttempt).where(
                    ResourceUsageAttempt.owner_id == owner_id,
                    ResourceUsageAttempt.operation_id.in_(operations),
                    ResourceUsageAttempt.usage_kind == "network_request",
                )
            ):
                usage.setdefault(usage_attempt.operation_id, set()).add(usage_attempt.attempt_id)
            for reservation in self._session.scalars(
                select(ResourceBudgetReservation).where(
                    ResourceBudgetReservation.owner_id == owner_id,
                    ResourceBudgetReservation.operation_id.in_(operations),
                    ResourceBudgetReservation.metric == "network_request",
                )
            ):
                reservations.setdefault(reservation.operation_id, []).append(reservation)
        content = {
            item.job_id: item
            for item in self._content.collection_counts_in_transaction(
                owner_id=owner_id, job_ids=job_ids
            )
        }
        snapshots = {
            item.job_id: item
            for item in self._content.collection_snapshots_in_transaction(
                owner_id=owner_id, job_ids=job_ids
            )
        }
        analysis_windows = {
            row.job_id: (
                row.topic_id,
                jobs[row.job_id].configuration_version,
                content[row.job_id].content_version_ids,
            )
            for row in rows
            if row.job_id is not None and row.topic_id is not None and row.job_id in content
        }
        analysis = self._analysis.collection_annotation_counts_in_transaction(
            owner_id=owner_id, windows=analysis_windows
        )
        current_connections = load_current_connection_facts_in_transaction(
            self._session,
            owner_id=owner_id,
            source_keys=tuple({row.source_key for row in rows}),
        )
        prior_due = aliased(CollectionDueWindow)
        prior_job = aliased(Job)
        latest_success = (
            select(func.max(prior_job.completed_at))
            .join(prior_due, prior_due.job_id == prior_job.id)
            .where(
                prior_due.owner_id == owner_id,
                prior_due.source_key == CollectionDueWindow.source_key,
                prior_due.capability == CollectionDueWindow.capability,
                prior_due.due_at <= CollectionDueWindow.due_at,
                prior_job.owner_id == owner_id,
                prior_job.status == JobStatus.SUCCEEDED.value,
            )
            .correlate(CollectionDueWindow)
            .scalar_subquery()
        )
        successes: dict[UUID, datetime | None] = {
            window_id: completed_at
            for window_id, completed_at in self._session.execute(
                select(CollectionDueWindow.id, latest_success).where(
                    CollectionDueWindow.owner_id == owner_id,
                    CollectionDueWindow.id.in_([row.id for row in rows]),
                )
            ).all()
        }
        return [
            self._row_view(
                row,
                job=jobs.get(row.job_id) if row.job_id is not None else None,
                attempts=attempts,
                coverage=coverage,
                usage=usage,
                reservations=reservations,
                content=content,
                snapshots=snapshots,
                analysis=analysis,
                current_connections=current_connections,
                last_success_at=successes.get(row.id),
            )
            for row in rows
        ]

    @staticmethod
    def _row_view(
        row: CollectionDueWindow,
        *,
        job: Job | None,
        attempts: dict[UUID, int],
        coverage: dict[UUID, list[CoverageWindow]],
        usage: dict[UUID, set[UUID]],
        reservations: dict[UUID, list[ResourceBudgetReservation]],
        content: Mapping[UUID, CollectionContentCountView],
        snapshots: Mapping[UUID, CollectionSnapshotFactView],
        analysis: Mapping[UUID, WindowAnnotationCountView],
        current_connections: dict[str, SourceConnectionFactView],
        last_success_at: datetime | None,
    ) -> CollectionCoverageView:
        content_fact = content.get(job.id) if job is not None else None
        snapshot = snapshots.get(job.id) if job is not None else None
        analysis_fact = analysis.get(job.id) if job is not None else None
        windows = coverage.get(job.id, []) if job is not None else []
        requests = usage.get(job.operation_id, set()) if job is not None else set()
        budget_rows = reservations.get(job.operation_id, []) if job is not None else []
        page_count = (
            (1 if snapshot is not None else sum(window.page_count for window in windows))
            if job is not None
            else None
        )
        observed = (
            snapshot.entry_count
            if snapshot is not None
            else (job.checkpoint.get("collection.observed_count") if job is not None else None)
        )
        if observed is not None and (type(observed) is not int or observed < 0):
            raise RuntimeError("invalid observed count checkpoint")
        if observed is None and job is not None and job.requests_sent == 0:
            observed = 0
        confirmed = (
            snapshot is not None and job is not None and job.status == JobStatus.SUCCEEDED.value
            if row.capability == SourceCapability.HOTLIST.value
            else bool(windows) and all(window.status == "confirmed" for window in windows)
        )
        if job is None:
            status = CollectionCoverageStatus.UNATTEMPTED
        elif job.status == JobStatus.FAILED.value:
            status = CollectionCoverageStatus.FAILED
        elif job.status == JobStatus.CANCELLED.value:
            status = CollectionCoverageStatus.STOPPED
        elif confirmed and observed == 0:
            status = CollectionCoverageStatus.EMPTY
        elif confirmed and analysis_fact is not None and analysis_fact.pending_count:
            status = CollectionCoverageStatus.ANALYSIS_PENDING
        elif confirmed:
            status = CollectionCoverageStatus.CONFIRMED
        elif job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
            status = CollectionCoverageStatus.RUNNING
        else:
            status = CollectionCoverageStatus.PARTIAL
        stop_reason = next((window.stop_reason for window in windows if window.stop_reason), None)
        gap_reason = (
            row.reason or stop_reason or (job.last_error_code if job else None) or status.value
        )
        budget_by_attempt: dict[UUID, list[ResourceBudgetReservation]] = {}
        for reservation in budget_rows:
            budget_by_attempt.setdefault(reservation.reservation_id, []).append(reservation)
        reconciled = (
            job is not None
            and job.requests_sent == len(requests)
            and requests == set(budget_by_attempt)
            and all(
                item.status == "settled" and item.actual_units == 1
                for group in budget_by_attempt.values()
                for item in group
            )
        )
        if job is not None and job.requests_sent > 0 and not reconciled and confirmed:
            status = CollectionCoverageStatus.PARTIAL
            gap_reason = "budget_unreconciled"
        content_ids = set(content_fact.content_ids if content_fact is not None else ())
        if snapshot is not None:
            content_ids.update(snapshot.content_ids)
        return CollectionCoverageView(
            window_id=row.id,
            source_key=row.source_key,
            capability=SourceCapability(row.capability),
            topic_id=row.topic_id,
            due_at=_as_utc(row.due_at),
            window_start=_as_utc(row.window_start),
            window_end=_as_utc(row.window_end),
            admission_state=DueAdmissionState(row.admission_state),
            admission_reason=row.reason,
            current_connection_version=(
                current_connections[row.source_key].version
                if row.source_key in current_connections
                else None
            ),
            current_connection_status=(
                current_connections[row.source_key].status
                if row.source_key in current_connections
                else None
            ),
            job_connection_version=(
                job.scope.get("connection_version")
                if job is not None and type(job.scope.get("connection_version")) is int
                else None
            ),
            job_id=job.id if job is not None else None,
            job_status=JobStatus(job.status) if job is not None else None,
            attempts=attempts.get(job.id, 0) if job is not None else None,
            started_at=_as_utc(job.started_at) if job is not None and job.started_at else None,
            finished_at=_as_utc(job.completed_at) if job is not None and job.completed_at else None,
            last_success_at=_as_utc(last_success_at) if last_success_at is not None else None,
            coverage_status=status,
            terminal_evidence=confirmed if job is not None else None,
            request_count=job.requests_sent if job is not None else None,
            request_attempt_count=len(requests) if job is not None else None,
            page_count=page_count,
            observed_count=observed,
            inserted_count=content_fact.first_ingested_count if content_fact is not None else None,
            deduplicated_count=(
                content_fact.deduplicated_count if content_fact is not None else None
            ),
            analysis_pending_count=(
                analysis_fact.pending_count if analysis_fact is not None else None
            ),
            analysis_failed_count=analysis_fact.failed_count if analysis_fact is not None else None,
            analysis_invalid_count=(
                analysis_fact.abnormal_count if analysis_fact is not None else None
            ),
            analysis_valid_count=(
                analysis_fact.annotated_count if analysis_fact is not None else None
            ),
            budget_limit=min((item.limit_units for item in budget_rows), default=None),
            budget_reserved=(
                sum(
                    any(item.status == "reserved" for item in group)
                    for group in budget_by_attempt.values()
                )
                if budget_rows
                else None
            ),
            budget_consumed=len(requests) if budget_rows and reconciled else None,
            gaps=()
            if confirmed and reconciled
            else (
                CollectionCoverageGapView(
                    start=_as_utc(row.window_start),
                    end=_as_utc(row.window_end),
                    reason=gap_reason,
                ),
            ),
            content_ids=tuple(sorted(content_ids, key=str)),
            snapshot_ids=(snapshot.snapshot_id,) if snapshot is not None else (),
        )
