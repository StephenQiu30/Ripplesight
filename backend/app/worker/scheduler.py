from __future__ import annotations

import signal
from collections.abc import Callable, Iterable, Sized
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from threading import Event
from typing import Protocol, cast
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from analysis.services import AnalysisService
from connections.schemas import SourceEntryPoint, SourceExecutionPolicy
from connections.services import (
    list_applied_hotlist_presets_in_transaction,
    load_applied_source_presets_in_transaction,
    load_source_execution_snapshot_at_in_transaction,
)
from content.discovery import plan_scheduled_keyword_discovery
from content.schemas import KeywordDiscoveryRunInput
from content.services import CommentScanService
from core.config import get_settings
from core.logging import configure_logging

# The scheduler is its own process; import the canonical registry to resolve ORM foreign keys.
from db.metadata import metadata as _registered_metadata  # noqa: F401
from db.session import create_db_engine, create_session_factory
from evidence.services import load_source_access_readiness
from jobs.coverage import CollectionDueWindowService
from jobs.models import CollectionDueWindow, Job
from jobs.schemas import (
    BudgetMetric,
    BudgetScopeKind,
    CollectionDueWindowInput,
    DueAdmissionState,
    DueSkipReason,
    JobAcceptanceInput,
    JobObservationContext,
)
from jobs.services import JobService, ResourceBudgetService, load_job_execution_configuration
from knowledge.services import KnowledgeExportService
from monitors.services import DueCollectionSchedule, MonitorScheduleService
from notifications.services import NotificationService
from sources.contracts import SourceCapability

SCHEDULER_POLL_SECONDS = 30
COLLECTION_OPERATION_NAMESPACE = UUID("515944a7-070b-4b27-86a4-bc811109031d")
HOTLIST_OPERATION_NAMESPACE = UUID("192152b2-b0e8-45dd-88db-9624c920e2e0")
_COLLECTION_PAGE_SIZE = 100
_COLLECTION_MAX_PAGES = 3
_COLLECTION_MAX_REQUESTS = 3
_COLLECTION_MAX_SECONDS = 90
_BILIBILI_INTERVAL = timedelta(hours=6)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_BILIBILI_SCHEDULE_LOCK = 0x484F544B45594249


def _bilibili_quiet(now: datetime) -> bool:
    return now.astimezone(_SHANGHAI).hour < 8


SchedulerScanFunction = Callable[[Session, datetime], int]


@dataclass(frozen=True, slots=True)
class SchedulerScan:
    name: str
    run_in_transaction: SchedulerScanFunction


class _ReportScanService(Protocol):
    def enqueue_due_in_transaction(self, *, now: datetime) -> int | Sized: ...


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("scheduler timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def collection_schedule_id(schedule: DueCollectionSchedule) -> UUID:
    identity = ":".join(
        (
            "schedule",
            str(schedule.owner_id),
            str(schedule.topic_id),
            schedule.source_key,
            schedule.capability.value,
        )
    )
    return uuid5(COLLECTION_OPERATION_NAMESPACE, identity)


def collection_operation_id(
    schedule: DueCollectionSchedule,
    due_at: datetime,
    connection_version: int,
) -> UUID:
    identity = (
        f"collect:{collection_schedule_id(schedule)}:{_utc_text(due_at)}:"
        f"{schedule.topic_version}:{connection_version}"
    )
    return uuid5(COLLECTION_OPERATION_NAMESPACE, identity)


def hotlist_operation_id(
    owner_id: UUID,
    source_key: str,
    now: datetime,
    interval_seconds: int,
    connection_version: int,
) -> UUID:
    if now.tzinfo is None or interval_seconds < 600 or connection_version < 1:
        raise ValueError("hotlist operation requires aware time, interval and connection version")
    bucket = int(now.astimezone(UTC).timestamp()) // interval_seconds
    due_at = datetime.fromtimestamp(bucket * interval_seconds, UTC)
    return uuid5(
        HOTLIST_OPERATION_NAMESPACE,
        f"hotlist:{owner_id}:{source_key}:{_utc_text(due_at)}:{connection_version}",
    )


def hotlist_schedule_id(owner_id: UUID, source_key: str) -> UUID:
    return uuid5(HOTLIST_OPERATION_NAMESPACE, f"schedule:{owner_id}:{source_key}")


def _hotlist_due_on_or_after(value: datetime, interval_seconds: int) -> datetime:
    current = value.astimezone(UTC)
    bucket = (int(current.timestamp()) // interval_seconds) * interval_seconds
    due_at = datetime.fromtimestamp(bucket, UTC)
    return due_at if due_at >= current else due_at + timedelta(seconds=interval_seconds)


def enqueue_due_hotlists_in_transaction(session: Session, now: datetime) -> int:
    if not session.in_transaction() or now.tzinfo is None:
        raise RuntimeError("hotlist scan requires a transaction and aware time")
    interval = get_settings().hotlist_interval_seconds
    scheduled_at = datetime.fromtimestamp(
        (int(now.astimezone(UTC).timestamp()) // interval) * interval, UTC
    )
    accepted = 0
    for preset in list_applied_hotlist_presets_in_transaction(session):
        schedule_key = hotlist_schedule_id(preset.owner_id, preset.source_key)
        first_due = _hotlist_due_on_or_after(preset.active_since_at, interval)
        if first_due > scheduled_at:
            continue
        previous = session.scalar(
            select(CollectionDueWindow)
            .where(
                CollectionDueWindow.owner_id == preset.owner_id,
                CollectionDueWindow.schedule_key == schedule_key,
            )
            .order_by(CollectionDueWindow.due_at.desc())
            .limit(1)
        )
        cadence = timedelta(seconds=interval)
        if previous is not None:
            previous_due = previous.due_at.astimezone(UTC)
            if previous_due > scheduled_at:
                continue
            same_cadence = (
                previous.window_end - previous.window_start == cadence
                and int(previous_due.timestamp()) % interval == 0
            )
            if not same_cadence:
                # A changed interval begins a new measurable span.
                if previous_due == scheduled_at:
                    continue
                first_due = scheduled_at
            elif (
                previous_due >= preset.active_since_at
                and previous.connection_version == preset.connection_version
            ):
                first_due = previous_due
            elif first_due <= previous_due:
                first_due = previous_due + cadence
        if first_due > scheduled_at:
            continue
        due_service = CollectionDueWindowService(session, clock=lambda: now)
        due = None
        count = min((scheduled_at - first_due) // cadence + 1, 1000)
        for index in range(count):
            due_at = first_due + index * cadence
            connection_id, connection_version, policy = (
                load_source_execution_snapshot_at_in_transaction(
                    session,
                    owner_id=preset.owner_id,
                    source_key=preset.source_key,
                    due_at=due_at,
                )
            )
            due = due_service.record_due_in_transaction(
                CollectionDueWindowInput(
                    owner_id=preset.owner_id,
                    schedule_key=schedule_key,
                    topic_id=None,
                    source_key=preset.source_key,
                    capability=SourceCapability.HOTLIST,
                    due_at=due_at,
                    window_start=due_at - cadence,
                    window_end=due_at,
                    connection_version=connection_version,
                    policy_snapshot=policy,
                )
            )
            if due_at < scheduled_at and due.admission_state is DueAdmissionState.PENDING:
                due_service.mark_missed_in_transaction(
                    owner_id=preset.owner_id, schedule_key=schedule_key, due_at=due_at
                )
        if due is None or due.due_at != scheduled_at:
            # More than 1000 elapsed points are reconciled by subsequent scans.
            continue
        if connection_id != preset.connection_id or connection_version != preset.connection_version:
            if due.admission_state is DueAdmissionState.PENDING:
                due_service.mark_missed_in_transaction(
                    owner_id=preset.owner_id, schedule_key=schedule_key, due_at=scheduled_at
                )
            continue
        if due.admission_state is not DueAdmissionState.PENDING:
            continue
        if policy is None or not policy.enabled:
            due_service.mark_skipped_in_transaction(
                owner_id=preset.owner_id,
                schedule_key=schedule_key,
                due_at=scheduled_at,
                reason=DueSkipReason.DISABLED,
            )
            continue
        if policy.quiet_at(now):
            due_service.mark_skipped_in_transaction(
                owner_id=preset.owner_id,
                schedule_key=schedule_key,
                due_at=scheduled_at,
                reason=DueSkipReason.QUIET,
            )
            continue
        if not _budget_available(
            session, owner_id=preset.owner_id, source_key=preset.source_key, now=now
        ):
            due_service.mark_skipped_in_transaction(
                owner_id=preset.owner_id,
                schedule_key=schedule_key,
                due_at=scheduled_at,
                reason=DueSkipReason.BUDGET,
            )
            continue
        if policy.min_interval_seconds and session.scalar(
            select(Job.id)
            .where(
                Job.owner_id == preset.owner_id,
                Job.source_key == preset.source_key,
                Job.kind == "source.hotlist",
                Job.created_at > now - timedelta(seconds=policy.min_interval_seconds),
            )
            .limit(1)
        ):
            due_service.mark_skipped_in_transaction(
                owner_id=preset.owner_id,
                schedule_key=schedule_key,
                due_at=scheduled_at,
                reason=DueSkipReason.RATE_LIMITED,
            )
            continue
        command = JobAcceptanceInput(
            operation_id=hotlist_operation_id(
                preset.owner_id, preset.source_key, now, interval, preset.connection_version
            ),
            kind="source.hotlist",
            observation=JobObservationContext(
                configuration_ref=f"source:{preset.source_key}",
                configuration_version=preset.connection_version,
                source_key=preset.source_key,
                source_capability=SourceCapability.HOTLIST,
            ),
            scheduled_for_at=scheduled_at,
            scope={
                "connection_id": str(preset.connection_id),
                "connection_version": preset.connection_version,
                "interval_seconds": interval,
            },
        )
        service = JobService(session, clock=lambda: now)
        if service.operation_exists_in_transaction(
            owner_id=preset.owner_id,
            kind="source.hotlist",
            operation_id=command.operation_id,
        ):
            raise RuntimeError("hotlist job exists without its accepted due fact")
        job = service.accept_in_transaction(owner_id=preset.owner_id, command=command)
        due_service.mark_accepted_in_transaction(
            owner_id=preset.owner_id,
            schedule_key=schedule_key,
            due_at=scheduled_at,
            operation_id=command.operation_id,
            job_id=job.id,
        )
        accepted += 1
    return accepted


def collection_window_start(
    now: datetime,
    *,
    interval_seconds: int,
    previous_end: datetime | None,
    lookback_seconds: int = 0,
) -> datetime:
    """Start where the last window ended, reaching back to catch late-indexed posts.

    Sources publish and index with delays, so a window judged by publish time must
    overlap earlier ones; re-seen posts are deduplicated when they are saved.
    """
    if now.tzinfo is None or not 600 <= interval_seconds <= 86_400:
        raise ValueError("collection window requires an aware time and valid interval")
    if lookback_seconds < 0:
        raise ValueError("collection lookback cannot be negative")
    now_utc = now.astimezone(UTC)
    if previous_end is None:
        base = now_utc - timedelta(seconds=interval_seconds)
    else:
        if previous_end.tzinfo is None:
            raise ValueError("previous collection window end must be timezone-aware")
        base = previous_end.astimezone(UTC)
        if base >= now_utc:
            raise ValueError("previous collection window end must precede the current scan")
    return base - timedelta(seconds=lookback_seconds)


def _previous_collection_end(
    session: Session,
    *,
    schedule: DueCollectionSchedule,
) -> datetime | None:
    if schedule.last_job_id is None:
        return None
    configuration = load_job_execution_configuration(session, job_id=schedule.last_job_id)
    if (
        configuration is None
        or configuration.owner_id != schedule.owner_id
        or configuration.kind != "keyword.search"
        or configuration.observation.configuration_ref != f"topic:{schedule.topic_id}"
        or configuration.observation.source_key != schedule.source_key
    ):
        raise RuntimeError("last collection job does not match the claimed schedule")
    value = configuration.scope.get("ends_at")
    if not isinstance(value, str):
        raise RuntimeError("last collection job has no window end")
    try:
        end = datetime.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError("last collection job window end is invalid") from error
    if end.utcoffset() != timedelta(0):
        raise RuntimeError("last collection job window end must be UTC")
    return end


def _accept_collection_schedule(
    session: Session,
    *,
    schedule: DueCollectionSchedule,
    due_at: datetime,
    connection_id: UUID,
    connection_version: int,
    policy: SourceExecutionPolicy,
    now: datetime,
) -> tuple[UUID, ...]:
    window_start = collection_window_start(
        due_at,
        interval_seconds=max(schedule.interval_seconds, policy.min_interval_seconds),
        previous_end=_previous_collection_end(session, schedule=schedule),
        lookback_seconds=get_settings().collection_lookback_seconds,
    )
    schedule_operation_id = collection_operation_id(schedule, due_at, connection_version)
    accepted_ids: list[UUID] = []
    for query in schedule.search_queries[: policy.max_queries]:
        operation_id = uuid5(schedule_operation_id, f"query:{query}")
        is_bilibili = schedule.source_key == "bilibili"
        command = plan_scheduled_keyword_discovery(
            KeywordDiscoveryRunInput(
                run_id=operation_id,
                configuration_ref=f"topic:{schedule.topic_id}",
                configuration_version=schedule.topic_version,
                source_key=schedule.source_key,
                connection_id=connection_id,
                connection_version=connection_version,
                primary_query=query,
                starts_at=window_start,
                ends_at=due_at,
                page_size=min(
                    policy.max_items_per_query,
                    5 if is_bilibili else _COLLECTION_PAGE_SIZE,
                ),
                latest_max_pages=1 if is_bilibili else _COLLECTION_MAX_PAGES,
                latest_max_requests=min(
                    policy.max_requests,
                    26 if is_bilibili else _COLLECTION_MAX_REQUESTS,
                ),
                top_max_pages=1,
                top_max_requests=1,
                max_seconds=min(
                    policy.max_seconds,
                    220 if is_bilibili else _COLLECTION_MAX_SECONDS,
                ),
                entry_point=SourceEntryPoint.SCHEDULED,
                scheduled_for_at=due_at,
            )
        )
        command = command.model_copy(
            update={
                "scope": {
                    **command.scope,
                    "schedule_key": str(collection_schedule_id(schedule)),
                    "due_at": _utc_text(due_at),
                }
            }
        )
        accepted = JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=schedule.owner_id,
            command=command,
        )
        accepted_ids.append(accepted.id)
    if not accepted_ids:
        raise RuntimeError("collection schedule has no upstream search queries")
    return tuple(accepted_ids)


def _budget_available(session: Session, *, owner_id: UUID, source_key: str, now: datetime) -> bool:
    budgets = ResourceBudgetService(session, clock=lambda: now).budget_usage_snapshot(
        owner_id=owner_id
    )
    relevant = [
        budget
        for budget in budgets
        if budget.metric is BudgetMetric.NETWORK_REQUEST
        and (
            budget.scope_kind is BudgetScopeKind.GLOBAL
            or (
                budget.scope_kind is BudgetScopeKind.SOURCE and budget.scope_reference == source_key
            )
        )
    ]
    return any(budget.scope_kind is BudgetScopeKind.SOURCE for budget in relevant) and all(
        budget.enabled and budget.remaining_units is not None and budget.remaining_units > 0
        for budget in relevant
    )


def _source_budget_available(
    session: Session, schedule: DueCollectionSchedule, now: datetime
) -> bool:
    return _budget_available(
        session, owner_id=schedule.owner_id, source_key=schedule.source_key, now=now
    )


def _process_collection_schedule(
    session: Session,
    *,
    schedule: DueCollectionSchedule,
    now: datetime,
    bilibili_accepted: bool,
) -> tuple[int, bool]:
    schedule_key = collection_schedule_id(schedule)
    due_service = CollectionDueWindowService(session, clock=lambda: now)

    def snapshot_at(due_at: datetime) -> tuple[int | None, SourceExecutionPolicy | None]:
        _, version, policy = load_source_execution_snapshot_at_in_transaction(
            session, owner_id=schedule.owner_id, source_key=schedule.source_key, due_at=due_at
        )
        return version, policy

    first_version, first_policy = snapshot_at(schedule.next_run_at)
    first_due = CollectionDueWindowInput(
        owner_id=schedule.owner_id,
        schedule_key=schedule_key,
        topic_id=schedule.topic_id,
        source_key=schedule.source_key,
        capability=schedule.capability,
        due_at=schedule.next_run_at.astimezone(UTC),
        window_start=schedule.next_run_at.astimezone(UTC)
        - timedelta(seconds=schedule.interval_seconds + get_settings().collection_lookback_seconds),
        window_end=schedule.next_run_at.astimezone(UTC),
        connection_version=first_version,
        policy_snapshot=first_policy,
    )
    # The due ledger limits each replay to 1000 points. Advance through long
    # outages in bounded batches while the schedule row remains locked.
    elapsed: tuple[object, ...] = ()
    through = min(now, first_due.due_at + timedelta(seconds=schedule.interval_seconds * 999))
    while True:
        elapsed = due_service.record_elapsed_in_transaction(
            first_due=first_due,
            interval_seconds=schedule.interval_seconds,
            through_at=through,
            snapshot_at=snapshot_at,
        )
        if through == now:
            break
        through = min(now, through + timedelta(seconds=schedule.interval_seconds * 999))
    latest = elapsed[-1]
    next_run_at = latest.due_at + timedelta(seconds=schedule.interval_seconds)
    if latest.admission_state is DueAdmissionState.ACCEPTED:
        MonitorScheduleService(session).advance_collection_in_transaction(
            schedule=schedule, job_id=latest.job_id, next_run_at=next_run_at, updated_at=now
        )
        return 0, False

    def skip(reason: DueSkipReason) -> tuple[int, bool]:
        if latest.admission_state is DueAdmissionState.PENDING:
            due_service.mark_skipped_in_transaction(
                owner_id=schedule.owner_id,
                schedule_key=schedule_key,
                due_at=latest.due_at,
                reason=reason,
            )
        MonitorScheduleService(session).advance_collection_in_transaction(
            schedule=schedule, job_id=None, next_run_at=next_run_at, updated_at=now
        )
        return 0, False

    if latest.admission_state is DueAdmissionState.SKIPPED:
        if latest.reason is None:
            raise RuntimeError("skipped due has no reason")
        return skip(DueSkipReason(latest.reason))
    applied = load_applied_source_presets_in_transaction(
        session, owner_id=schedule.owner_id, source_keys=(schedule.source_key,)
    ).get(schedule.source_key)
    connection_id, _, _ = load_source_execution_snapshot_at_in_transaction(
        session, owner_id=schedule.owner_id, source_key=schedule.source_key, due_at=latest.due_at
    )
    if (
        applied is None
        or schedule.capability not in applied.capabilities
        or applied.connection_id != connection_id
        or applied.connection_version != latest.connection_version
        or latest.policy_snapshot is None
        or not load_source_access_readiness(session, owner_id=schedule.owner_id, now=now).get(
            (schedule.source_key, schedule.capability), False
        )
    ):
        return skip(DueSkipReason.DISABLED)
    policy = latest.policy_snapshot
    if not policy.enabled:
        return skip(DueSkipReason.DISABLED)
    if policy.quiet_at(latest.due_at) or policy.quiet_at(now):
        return skip(DueSkipReason.QUIET)
    if schedule.source_key == "bilibili":
        if not get_settings().mediacrawler_enabled or bilibili_accepted:
            return skip(DueSkipReason.DISABLED)
        if not session.scalar(select(func.pg_try_advisory_xact_lock(_BILIBILI_SCHEDULE_LOCK))):
            return 0, False
    if not _source_budget_available(session, schedule, now):
        return skip(DueSkipReason.BUDGET)
    if policy.min_interval_seconds:
        recent = session.scalar(
            select(Job.id)
            .where(
                Job.owner_id == schedule.owner_id,
                Job.source_key == schedule.source_key,
                Job.kind == "keyword.search",
                Job.created_at > now - timedelta(seconds=policy.min_interval_seconds),
            )
            .limit(1)
        )
        if recent is not None:
            return skip(DueSkipReason.RATE_LIMITED)
    accepted_ids = _accept_collection_schedule(
        session,
        schedule=schedule,
        due_at=latest.due_at,
        connection_id=applied.connection_id,
        connection_version=applied.connection_version,
        policy=policy,
        now=now,
    )
    first_operation_id = uuid5(
        collection_operation_id(schedule, latest.due_at, applied.connection_version),
        f"query:{schedule.search_queries[0]}",
    )
    due_service.mark_accepted_in_transaction(
        owner_id=schedule.owner_id,
        schedule_key=schedule_key,
        due_at=latest.due_at,
        operation_id=first_operation_id,
        job_id=accepted_ids[0],
    )
    MonitorScheduleService(session).advance_collection_in_transaction(
        schedule=schedule, job_id=accepted_ids[-1], next_run_at=next_run_at, updated_at=now
    )
    return len(accepted_ids), schedule.source_key == "bilibili"


def enqueue_due_collections_in_transaction(session: Session, now: datetime) -> int:
    """Claim and accept due collection rows; isolate one bad row with a savepoint."""
    if not session.in_transaction():
        raise RuntimeError("collection scan requires the caller's transaction")
    now_utc = now.astimezone(UTC) if now.tzinfo is not None else now
    schedules = MonitorScheduleService(session).claim_due_collections_in_transaction(now=now_utc)
    accepted = 0
    bilibili_accepted = False
    logger = structlog.get_logger("scheduler")
    for schedule in schedules:
        try:
            with session.begin_nested():
                accepted_count, accepted_bilibili = _process_collection_schedule(
                    session, schedule=schedule, now=now_utc, bilibili_accepted=bilibili_accepted
                )
        except Exception as error:
            logger.warning(
                "scheduler_collection_row_failed",
                owner_id=str(schedule.owner_id),
                topic_id=str(schedule.topic_id),
                source_key=schedule.source_key,
                error_type=type(error).__name__,
                exc_info=True,
            )
            continue
        accepted += accepted_count
        bilibili_accepted = bilibili_accepted or accepted_bilibili
    return accepted


def enqueue_due_comments_in_transaction(session: Session, now: datetime) -> int:
    return CommentScanService(session).enqueue_due_comments_in_transaction(
        now=now,
        skip_bilibili=(not get_settings().mediacrawler_enabled or _bilibili_quiet(now)),
    )


def enqueue_due_analysis_in_transaction(session: Session, now: datetime) -> int:
    if not session.in_transaction():
        raise RuntimeError("analysis scan requires the caller's transaction")
    if now.tzinfo is None:
        raise ValueError("analysis scan time must be timezone-aware")
    topics = MonitorScheduleService(session).list_active_topics_for_scanning_in_transaction()
    accepted = 0
    logger = structlog.get_logger("scheduler")
    for topic in topics:
        try:
            with session.begin_nested():
                jobs = AnalysisService(session).enqueue_due_batches_in_transaction(
                    owner_id=topic.owner_id,
                    topic_id=topic.topic_id,
                    now=now.astimezone(UTC),
                )
        except Exception as error:
            logger.warning(
                "scheduler_analysis_topic_failed",
                owner_id=str(topic.owner_id),
                topic_id=str(topic.topic_id),
                error_type=type(error).__name__,
                exc_info=True,
            )
            continue
        accepted += len(jobs)
    return accepted


def _optional_report_scan() -> SchedulerScan | None:
    try:
        module = import_module("reports.services")
    except ModuleNotFoundError as error:
        if error.name in {"reports", "reports.services"}:
            return None
        raise
    service_type = getattr(module, "ReportService", None)
    method = getattr(service_type, "enqueue_due_in_transaction", None)
    if service_type is None or not callable(method):
        return None
    factory = cast(Callable[[Session], _ReportScanService], service_type)

    def run_report_scan(session: Session, now: datetime) -> int:
        result = factory(session).enqueue_due_in_transaction(now=now)
        return result if isinstance(result, int) else len(result)

    return SchedulerScan(name="reports", run_in_transaction=run_report_scan)


def _registered_scheduler_scans() -> tuple[SchedulerScan, ...]:
    scans = [
        SchedulerScan(name="hotlists", run_in_transaction=enqueue_due_hotlists_in_transaction),
        SchedulerScan(
            name="collection",
            run_in_transaction=enqueue_due_collections_in_transaction,
        ),
        SchedulerScan(
            name="comments",
            run_in_transaction=enqueue_due_comments_in_transaction,
        ),
        SchedulerScan(
            name="analysis",
            run_in_transaction=enqueue_due_analysis_in_transaction,
        ),
    ]
    report_scan = _optional_report_scan()
    if report_scan is not None:
        scans.append(report_scan)
    scans.append(
        SchedulerScan(
            name="knowledge",
            run_in_transaction=lambda session, now: KnowledgeExportService(
                session, get_settings()
            ).enqueue_due_in_transaction(now=now),
        )
    )
    scans.append(
        SchedulerScan(
            name="notifications",
            run_in_transaction=lambda session, now: NotificationService(
                session, get_settings()
            ).enqueue_due_in_transaction(now=now),
        )
    )
    return tuple(scans)


def run_scheduler_round(
    sessions: sessionmaker[Session],
    scans: Iterable[SchedulerScan],
    *,
    now: datetime,
) -> dict[str, int]:
    logger = structlog.get_logger("scheduler")
    results: dict[str, int] = {}
    for scan in scans:
        try:
            with sessions() as session, session.begin():
                results[scan.name] = scan.run_in_transaction(session, now)
        except Exception as error:
            logger.error(
                "scheduler_scan_failed",
                scan=scan.name,
                error_type=type(error).__name__,
                exc_info=True,
            )
    return results


def run_scheduler() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("scheduler")
    stopping = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    engine = create_db_engine(settings)
    sessions = create_session_factory(engine)
    scans = _registered_scheduler_scans()
    try:
        while not stopping.is_set():
            started_at = datetime.now(UTC)
            results = run_scheduler_round(sessions, scans, now=started_at)
            logger.info("scheduler_round_completed", scan_counts=results)
            stopping.wait(SCHEDULER_POLL_SECONDS)
    finally:
        engine.dispose()
    logger.info("scheduler_stopped")


if __name__ == "__main__":
    run_scheduler()
