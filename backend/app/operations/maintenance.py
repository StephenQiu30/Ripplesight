from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid5

import httpx
from minio import Minio
from redis import Redis
from sqlalchemy import delete, select
from sqlalchemy.engine import Connection, CursorResult
from sqlalchemy.orm import Session, sessionmaker

from ai.operations_reading import load_model_cost_circuits_in_transaction
from analysis.operations_reading import load_editorial_processing_health_in_transaction
from backups.adapters.minio import MinioEvidenceRestoreVerifier, MinioObjectInventory
from backups.adapters.postgres import PostgresDumpAdapter
from backups.restore import BackupRestoreService
from backups.schemas import BackupManifest
from backups.services import BackupService
from connections.editorial_schemas import EditorialSourceOperationalHealth
from connections.editorial_services import list_editorial_source_health_in_transaction
from content.operations_reading import load_ingestion_health_in_transaction
from content.services import ContentObservationCleanup
from core.config import Settings
from db.owners import list_owner_ids_in_transaction
from evidence.adapters.cache import RedisCacheCleanup
from evidence.adapters.minio import MinioObjectCleanup
from evidence.schemas import CleanupTargetKind
from evidence.services import CleanupProcessor, LifecycleService
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.operator_maintenance import (
    load_operator_job_health_in_transaction,
    republish_due_jobs_in_transaction,
)
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    JobFailureCategory,
    JobMessage,
    JobStatus,
)
from jobs.services import ResourceBudgetService, load_job_execution_configuration
from leaderboard.health import load_source_health_in_transaction
from monitors.codex_services import read_codex_operational_health_in_transaction
from notifications.card import notification_card
from notifications.feishu import FeishuDeliveryError, FeishuWebhook
from notifications.operations_reading import load_delivery_health_in_transaction
from operations.models import Feedback, FeedbackAttachment, FeedbackCooldown, OperatorAuditOperation
from operations.reporting import WeeklySource, source_health_report
from operations.schemas import (
    MaintenanceFindingView,
    MaintenanceInput,
    MaintenanceScheduleView,
    MaintenanceStateView,
    OperatorAuditView,
)
from operations.services import OperationsService, accept_maintenance_in_transaction
from publication.notification_reading import weekly_selected_source_counts_in_transaction
from reports.operations_reading import load_daily_edition_health_in_transaction

_NAMESPACE = UUID("80939130-52b1-4552-8221-4cf2ac86d8ae")
MAINTENANCE_INTERVALS = {
    "lifecycle_sweep": 600,
    "recover": 600,
    "alerts": 600,
    "digest": 86400,
    "source_health": 604800,
    "feedback_forward": 600,
    "backup": 86400,
    "verify_backup": 3600,
    "retention": 86400,
    "watchdog": 60,
}


def _enabled(action: str, settings: Settings) -> bool:
    if not settings.operations_maintenance_enabled:
        return False
    if action == "backup":
        return settings.operations_backup_directory is not None
    if action == "verify_backup":
        return (
            settings.operations_backup_directory is not None
            and settings.operations_restore_database_url is not None
        )
    if action == "feedback_forward":
        return settings.feedback_forward_enabled and settings.operations_webhook_url is not None
    return True


def _latest_backup_id(session: Session, owner: UUID) -> UUID | None:
    row = session.scalar(
        select(OperatorAuditOperation)
        .where(
            OperatorAuditOperation.owner_id == owner,
            OperatorAuditOperation.action == "maintenance.backup",
            OperatorAuditOperation.status == "succeeded",
        )
        .order_by(OperatorAuditOperation.updated_at.desc())
        .limit(1)
    )
    return (
        UUID(str(row.after_state["backup_id"]))
        if row and row.after_state.get("backup_id")
        else None
    )


def enqueue_due_maintenance_in_transaction(
    session: Session, *, now: datetime, settings: Settings
) -> int:
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("maintenance scheduling requires aware caller transaction")
    if not settings.operations_maintenance_enabled:
        return 0
    return sum(
        _enqueue_owner_maintenance_in_transaction(session, owner=owner, now=now, settings=settings)
        for owner in list_owner_ids_in_transaction(session)
    )


def _enqueue_owner_maintenance_in_transaction(
    session: Session, *, owner: UUID, now: datetime, settings: Settings
) -> int:
    accepted = 0
    for action, interval in MAINTENANCE_INTERVALS.items():
        # An external process executes watchdog; a Scheduler task cannot prove its own loss.
        if action == "watchdog" or not _enabled(action, settings):
            continue
        backup_id = _latest_backup_id(session, owner) if action == "verify_backup" else None
        if action == "verify_backup" and backup_id is None:
            continue
        anchor = (
            datetime(1970, 1, 5, 1, tzinfo=UTC)
            if action == "source_health"
            else datetime(
                1970, 1, 1, {"digest": 1, "backup": 18, "retention": 19}.get(action, 0), tzinfo=UTC
            )
        )
        slot = int((now - anchor).total_seconds()) // interval
        operation = uuid5(_NAMESPACE, f"{owner}:{action}:{slot}:{backup_id or ''}")
        result = accept_maintenance_in_transaction(
            session,
            owner_id=owner,
            command=MaintenanceInput(
                operation_id=operation,
                action=action,
                backup_id=backup_id,
                reason="执行已启用的维护周期",
            ),
            now=now,
        )
        accepted += not result.replayed
    return accepted


def _all_sources_in_transaction(
    session: Session, *, owner_id: UUID
) -> tuple[EditorialSourceOperationalHealth, ...]:
    rows: list[EditorialSourceOperationalHealth] = []
    after = None
    while True:
        page = list_editorial_source_health_in_transaction(
            session, owner_id=owner_id, limit=200, after_source_key=after
        )
        rows.extend(page)
        if len(page) < 200:
            return tuple(rows)
        after = page[-1].source_key


def maintenance_findings(
    session: Session, *, owner_id: UUID, settings: Settings, now: datetime
) -> tuple[list[MaintenanceFindingView], dict[str, object]]:
    service = OperationsService(
        session,
        clock=lambda: now,
        maintenance_enabled=settings.operations_maintenance_enabled,
        feedback_forward_enabled=settings.feedback_forward_enabled,
        backup_configured=settings.operations_backup_directory is not None,
    )
    health = service.get_health(owner_id=owner_id)
    session.rollback()
    with session.begin():
        jobs = load_operator_job_health_in_transaction(session, owner_id=owner_id, now=now)
        ingestion = load_ingestion_health_in_transaction(session, owner_id=owner_id, now=now)
        processing = load_editorial_processing_health_in_transaction(
            session, owner_id=owner_id, now=now
        )
        sources = _all_sources_in_transaction(session, owner_id=owner_id)
        delivery = load_delivery_health_in_transaction(session, owner_id=owner_id, now=now)
        circuits = load_model_cost_circuits_in_transaction(session, owner_id=owner_id)
        codex = read_codex_operational_health_in_transaction(session, owner_id=owner_id, now=now)
        daily = load_daily_edition_health_in_transaction(session, owner_id=owner_id, now=now)
        boards = load_source_health_in_transaction(
            session,
            owner_id=owner_id,
            now=now,
            enabled=settings.leaderboard_enabled,
            external_requests_enabled=settings.leaderboard_external_requests_enabled,
        )
        backup = session.scalar(
            select(OperatorAuditOperation)
            .where(
                OperatorAuditOperation.owner_id == owner_id,
                OperatorAuditOperation.action == "maintenance.backup",
                OperatorAuditOperation.status == "succeeded",
            )
            .order_by(OperatorAuditOperation.updated_at.desc())
            .limit(1)
        )
        backup_at = backup.updated_at if backup else None
    findings: list[MaintenanceFindingView] = []
    for role in ("api", "worker", "scheduler"):
        candidates = [heartbeat for heartbeat in health.heartbeats if heartbeat.role == role]
        if not candidates or all(item.state != "alive" for item in candidates):
            findings.append(
                MaintenanceFindingView(
                    key=f"process.{role}",
                    severity="now",
                    title=f"{role} 心跳失联",
                    detail="未发现90秒内的真实存活心跳",
                )
            )
    for issue in health.failure_issues:
        findings.append(
            MaintenanceFindingView(
                key=f"source.{issue.source_key}.{issue.configuration_ref}",
                severity="today",
                title=f"来源连续失败: {issue.source_key}",
                detail=issue.failure.error_code,
            )
        )
    worker_started = max(
        (item.started_at for item in health.heartbeats if item.role == "worker"), default=None
    )
    settled = worker_started is None or now - worker_started >= timedelta(
        minutes=settings.operations_startup_grace_minutes
    )
    collecting = (
        settings.editorial_sources_enabled
        and settings.editorial_public_requests_enabled
        and any(item.enabled and item.kind != "external" for item in sources)
    )
    if (
        settled
        and collecting
        and (
            ingestion.last_received_at is None
            or now - ingestion.last_received_at
            > timedelta(minutes=settings.operations_quiet_minutes)
        )
    ):
        findings.append(
            MaintenanceFindingView(
                key="content.collect",
                severity="now",
                title="网站停止收录新内容",
                detail=(
                    f"超过{settings.operations_quiet_minutes}分钟未收录新文章;检查来源、网络与采集任务"
                ),
            )
        )
    if (
        settled
        and collecting
        and settings.ai_enabled
        and (processing.waiting_over_two_hours >= 10 or processing.failed_count >= 20)
    ):
        findings.append(
            MaintenanceFindingView(
                key="content.process",
                severity="now",
                title="新内容处理卡住",
                detail=(
                    f"{processing.waiting_over_two_hours}条等待超过2小时;"
                    f"最近3小时{processing.failed_count}条处理失败;精选和热点缺少新内容"
                ),
            )
        )
    if settings.report_editions_enabled and daily.due and not daily.current_complete:
        findings.append(
            MaintenanceFindingView(
                key="report.daily",
                severity="now",
                title="今天的日报仍未就绪",
                detail=(
                    f"北京10点后昨日窗口{daily.expected_key}仍无当前有效完整刊物;"
                    f"状态{daily.status or '尚未受理'};错误{daily.failure_code or '无'}"
                ),
            )
        )
    if delivery.failed_last_day:
        findings.append(
            MaintenanceFindingView(
                key="deliveries.failed",
                severity="today",
                title="内容推送未送达",
                detail=(
                    f"过去24小时{delivery.failed_last_day}条投递被拒绝;检查目标与渠道,不会自动重发"
                ),
            )
        )
    if delivery.unknown_count:
        findings.append(
            MaintenanceFindingView(
                key="deliveries.unknown",
                severity="digest",
                title="内容推送结果未知",
                detail=(f"{delivery.unknown_count}条投递需要核对目的地后人工标记,不会自动重发"),
            )
        )
    if settings.codex_resets_enabled and codex.enabled:
        if codex.stuck_oldest_collected_at is not None:
            findings.append(
                MaintenanceFindingView(
                    key="monitor.stuck",
                    severity="today",
                    title="Codex 重置监控待识别超过1小时",
                    detail=(
                        f"最早未处理帖子收录于{codex.stuck_oldest_collected_at.isoformat()};"
                        "后续确认与推送可能延迟,请检查识别运行记录"
                    ),
                )
            )
        if codex.held_unreviewed_count:
            findings.append(
                MaintenanceFindingView(
                    key="monitor.review",
                    severity="today",
                    title="Codex 重置消息需要人工复核",
                    detail=(
                        f"最近48小时{codex.held_unreviewed_count}条帖子待确认;"
                        "结论未生效且未推送,请在重置公告后台检查"
                    ),
                )
            )
    seen_models = set()
    for circuit in circuits:
        identity = (circuit.provider, circuit.model)
        if identity in seen_models:
            continue
        seen_models.add(identity)
        findings.append(
            MaintenanceFindingView(
                key=f"model.cost.{circuit.provider}.{circuit.model}",
                severity="today",
                title="模型费用超过冻结上限,新请求已暂停",
                detail=(
                    f"{circuit.provider}/{circuit.model}:实际{circuit.actual_micros}"
                    f"微{circuit.currency or '未知币种'},上限{circuit.cap_micros};"
                    f"核对原调用{circuit.call_id}后人工确认"
                ),
            )
        )
    stale_boards = [item for item in boards if item.stale]
    if stale_boards:
        findings.append(
            MaintenanceFindingView(
                key="leaderboard.fetch",
                severity="digest",
                title="模型榜来源超过26小时未成功更新",
                detail=(
                    "、".join(item.source_key for item in stale_boards) + ";继续显示上一份固定证据"
                ),
            )
        )
    if jobs.queued_over_two_hours:
        findings.append(
            MaintenanceFindingView(
                key="jobs.backlog",
                severity="digest",
                title="任务积压超过两小时",
                detail=f"{jobs.queued_over_two_hours} 个到期任务",
            )
        )
    if jobs.expired_running_count:
        findings.append(
            MaintenanceFindingView(
                key="jobs.expired",
                severity="today",
                title="执行租约已过期",
                detail=f"{jobs.expired_running_count} 个任务需要原任务恢复",
            )
        )
    if jobs.unknown_result_count:
        findings.append(
            MaintenanceFindingView(
                key="jobs.unknown",
                severity="digest",
                title="收费或投递结果未知",
                detail=f"{jobs.unknown_result_count} 个任务需要人工核对,不会自动再次请求",
            )
        )
    for budget in health.budgets:
        if budget.enabled and budget.remaining_units == 0:
            findings.append(
                MaintenanceFindingView(
                    key=f"budget.{budget.budget_key}",
                    severity="today",
                    title="预算硬限已达到",
                    detail=budget.budget_key,
                )
            )
    if settings.operations_backup_directory is not None and (
        backup_at is None or backup_at < now - timedelta(hours=25)
    ):
        findings.append(
            MaintenanceFindingView(
                key="backup.stale",
                severity="today",
                title="备份超过一天未成功",
                detail="候选备份与恢复验证分别核收",
            )
        )
    return findings, {
        "health": health.model_dump(mode="json"),
        "jobs": json.loads(json.dumps(asdict(jobs), default=str)),
        "findings": [item.model_dump() for item in findings],
        "ingestion": json.loads(json.dumps(asdict(ingestion), default=str)),
        "processing": json.loads(json.dumps(asdict(processing), default=str)),
        "delivery": asdict(delivery),
        "codex": codex.model_dump(mode="json"),
        "model_circuits": json.loads(json.dumps([asdict(row) for row in circuits], default=str)),
        "daily": json.loads(json.dumps(asdict(daily), default=str)),
        "leaderboard_sources": [item.model_dump(mode="json") for item in boards],
    }


def read_maintenance_state(
    session: Session, *, owner_id: UUID, settings: Settings, now: datetime
) -> MaintenanceStateView:
    findings, _ = maintenance_findings(session, owner_id=owner_id, settings=settings, now=now)
    session.rollback()
    with session.begin():
        rows = list(
            session.scalars(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.owner_id == owner_id,
                    OperatorAuditOperation.action.like("maintenance.%"),
                )
                .order_by(OperatorAuditOperation.updated_at.desc())
                .limit(500)
            )
        )
        latest: dict[str, OperatorAuditView] = {}
        for row in rows:
            latest.setdefault(
                row.action.removeprefix("maintenance."),
                OperatorAuditView.model_validate(row, from_attributes=True),
            )
        return MaintenanceStateView(
            schedules=[
                MaintenanceScheduleView(
                    action=action,
                    interval_seconds=interval,
                    enabled=_enabled(action, settings),
                    latest_audit=latest.get(action),
                )
                for action, interval in MAINTENANCE_INTERVALS.items()
            ],
            findings=findings,
            backups=[
                OperatorAuditView.model_validate(row, from_attributes=True)
                for row in rows
                if row.action in {"maintenance.backup", "maintenance.verify_backup"}
            ][:100],
        )


class OperationsMaintenanceExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        client: httpx.Client | None = None,
    ):
        self._sessions, self._settings, self._clock, self._client = (
            sessions,
            settings,
            clock or (lambda: datetime.now(UTC)),
            client,
        )

    def _guard(self, session: Session, lease: ExecutionLease | None) -> None:
        if lease is not None:
            JobExecutionService(
                session, lease_seconds=self._settings.job_lease_seconds, clock=self._clock
            ).require_current_lease_in_transaction(lease)

    def execute(self, message: JobMessage, lease: ExecutionLease | None = None) -> JobCompletion:
        if message.kind != "operations.maintenance":
            raise ValueError("maintenance executor received another job kind")
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.kind != message.kind
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
            ):
                raise self._failure("operations_job_mismatch")
            action = str(configuration.scope["action"])
            audit_id = UUID(str(configuration.scope["audit_id"]))
            audit = session.scalar(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.owner_id == message.owner_id,
                    OperatorAuditOperation.id == audit_id,
                    OperatorAuditOperation.job_id == message.job_id,
                )
                .with_for_update()
            )
            if audit is None or audit.operation_id != message.operation_id:
                raise self._failure("operations_audit_mismatch")
            if audit.status == "succeeded":
                return JobCompletion(status=JobStatus.SUCCEEDED)
            unknown = audit.status == "unknown" or audit.error_code == "request_started"
            if unknown:
                audit.status, audit.error_code, audit.updated_at = (
                    "unknown",
                    "result_unknown",
                    self._clock(),
                )
            backup_id = (
                UUID(str(configuration.scope["backup_id"]))
                if configuration.scope.get("backup_id")
                else None
            )
        if unknown:
            raise self._failure("operations_result_unknown", manual=False)
        if action not in MAINTENANCE_INTERVALS or not _enabled(action, self._settings):
            raise self._failure("operations_maintenance_disabled")
        try:
            result = self._run(action, message, audit_id, backup_id, lease)
        except JobExecutionFailure:
            raise
        except Exception as error:
            with self._sessions() as session, session.begin():
                audit = session.get(OperatorAuditOperation, audit_id)
                if audit is not None and audit.status != "unknown":
                    audit.status, audit.error_code, audit.updated_at = (
                        "failed",
                        "maintenance_failed",
                        self._clock(),
                    )
            raise self._failure("operations_maintenance_failed") from error
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            audit = session.get(OperatorAuditOperation, audit_id)
            if audit is None or audit.status == "unknown":
                raise self._failure("operations_result_unknown", manual=False)
            audit.status, audit.after_state, audit.error_code, audit.updated_at = (
                "succeeded",
                {**audit.after_state, **result},
                None,
                self._clock(),
            )
        return JobCompletion(status=JobStatus.SUCCEEDED)

    def _run(
        self,
        action: str,
        message: JobMessage,
        audit_id: UUID,
        backup_id: UUID | None,
        lease: ExecutionLease | None,
    ) -> dict[str, object]:
        now = self._clock()
        if action == "recover":
            with self._sessions() as session, session.begin():
                self._guard(session, lease)
                ids = republish_due_jobs_in_transaction(session, owner_id=message.owner_id, now=now)
                return {"redispatched_job_ids": [str(value) for value in ids]}
        if action == "lifecycle_sweep":
            return self._cleanup()
        if action == "backup":
            return self._backup()
        if action == "verify_backup":
            if backup_id is None:
                raise ValueError("backup verification requires identity")
            return self._verify_backup(backup_id)
        if action == "retention":
            return self._retain(message.owner_id)
        if action == "feedback_forward":
            return self._forward_feedback(message, audit_id, lease)
        with self._sessions() as session:
            saved = session.get(OperatorAuditOperation, audit_id)
            if saved is not None and saved.after_state.get("delivered") is True:
                return {**saved.after_state, "completed_from_saved_delivery": True}
        with self._sessions() as session:
            findings, snapshot = maintenance_findings(
                session, owner_id=message.owner_id, settings=self._settings, now=now
            )
        if action == "source_health":
            with self._sessions() as session, session.begin():
                source_rows = _all_sources_in_transaction(session, owner_id=message.owner_id)
                ingestion = load_ingestion_health_in_transaction(
                    session, owner_id=message.owner_id, now=now
                )
                selected = weekly_selected_source_counts_in_transaction(
                    session, owner_id=message.owner_id, now=now
                )
            body, summary = source_health_report(
                now=now,
                sources=tuple(
                    WeeklySource(**row.model_dump(exclude={"id"})) for row in source_rows
                ),
                ingestion=ingestion,
                selected_current=sum(row.current_count for row in selected),
                selected_previous=sum(row.previous_count for row in selected),
            )
            snapshot["source_health_report"], snapshot["source_health_summary"] = body, summary
            if (
                self._settings.operations_alerts_enabled
                and self._settings.operations_webhook_url is not None
            ):
                self._deliver(message, audit_id, "HotKey 来源周报", body, lease, snapshot)
                snapshot["delivered"] = True
            else:
                snapshot["delivered"] = False
        if action in {"alerts", "digest", "watchdog"}:
            chosen = [
                item for item in findings if (item.severity == "digest") == (action == "digest")
            ]
            chosen = self._finding_updates(message.owner_id, chosen, findings, action, now)
            snapshot["sent_finding_keys"] = [item.key for item in chosen]
            if (
                chosen
                and self._settings.operations_alerts_enabled
                and self._settings.operations_webhook_url is not None
            ):
                self._deliver(
                    message,
                    audit_id,
                    "HotKey 运维" if action != "digest" else "HotKey 运维摘要",
                    "\n".join(f"{item.title}: {item.detail}" for item in chosen),
                    lease,
                    snapshot,
                )
                snapshot["delivered"] = True
            else:
                snapshot["delivered"] = False
        return snapshot

    def _finding_updates(
        self,
        owner: UUID,
        chosen: list[MaintenanceFindingView],
        current: list[MaintenanceFindingView],
        action: str,
        now: datetime,
    ) -> list[MaintenanceFindingView]:
        with self._sessions() as session:
            recent = list(
                session.scalars(
                    select(OperatorAuditOperation)
                    .where(
                        OperatorAuditOperation.owner_id == owner,
                        OperatorAuditOperation.action.in_(
                            ["maintenance.alerts", "maintenance.digest", "maintenance.watchdog"]
                        ),
                        OperatorAuditOperation.status.in_(["succeeded", "unknown"]),
                        OperatorAuditOperation.updated_at > now - timedelta(days=1),
                    )
                    .order_by(OperatorAuditOperation.updated_at.desc())
                    .limit(500)
                )
            )
            sendable = []
            for item in chosen:
                receipts = [
                    row
                    for row in recent
                    if isinstance(row.after_state.get("sent_finding_keys"), list)
                    and item.key in cast(list[object], row.after_state["sent_finding_keys"])
                    and (row.after_state.get("delivered") is True or row.status == "unknown")
                ]
                last = receipts[0] if receipts else None
                repeat = timedelta(hours=1 if item.severity == "now" else 24)
                if last is None or (last.status != "unknown" and last.updated_at <= now - repeat):
                    sendable.append(item)
            if action != "digest":
                previous = next(
                    (
                        row
                        for row in recent
                        if row.status == "succeeded" and row.after_state.get("delivered") is True
                    ),
                    None,
                )
                current_keys = {item.key for item in current}
                if previous is not None:
                    raw_findings = previous.after_state.get("findings", [])
                    for raw in raw_findings if isinstance(raw_findings, list) else []:
                        if (
                            isinstance(raw, dict)
                            and raw.get("key") not in current_keys
                            and raw.get("severity") != "digest"
                        ):
                            sendable.append(
                                MaintenanceFindingView(
                                    key=f"recovered.{raw['key']}",
                                    severity="now",
                                    title=f"已恢复: {raw.get('title', raw['key'])}",
                                    detail="当前真实状态已不再满足故障条件",
                                )
                            )
            return sendable

    def _minio(self) -> Minio:
        return Minio(
            self._settings.minio_endpoint,
            access_key=self._settings.minio_access_key,
            secret_key=self._settings.minio_secret_key,
            secure=self._settings.minio_secure,
        )

    def _cleanup(self) -> dict[str, object]:
        with self._sessions() as session:
            expired = LifecycleService(session, clock=self._clock).expire_due(limit=100)
        redis = Redis.from_url(self._settings.redis_url)
        try:
            result = CleanupProcessor(
                self._sessions,
                clock=self._clock,
                handlers={
                    CleanupTargetKind.REDIS_CACHE: RedisCacheCleanup(redis),
                    CleanupTargetKind.MINIO_OBJECT: MinioObjectCleanup(
                        self._minio(), self._settings.minio_bucket
                    ),
                    CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION: ContentObservationCleanup(
                        self._sessions
                    ),
                },
            ).process_due(limit=100)
        finally:
            redis.close()
        return {
            "expired": len(expired),
            "cleanup_succeeded": result.succeeded,
            "cleanup_failed": result.failed,
        }

    def _backup(self) -> dict[str, object]:
        root = self._settings.operations_backup_directory
        if root is None:
            raise ValueError("backup directory missing")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._sessions() as session:
            bind = session.get_bind()
            engine = bind.engine if isinstance(bind, Connection) else bind
        store = MinioObjectInventory(self._minio(), self._settings.minio_bucket)
        result = BackupService(
            engine=engine,
            archive_writer=PostgresDumpAdapter(self._settings.database_url.get_secret_value()),
            object_inspector=store,
            object_archiver=store,
            evidence_bucket=self._settings.minio_bucket,
            schema_path=Path(__file__).resolve().parents[2] / "database" / "schema.sql",
            clock=self._clock,
        ).create_candidate(root)
        return {
            "backup_id": str(result.manifest.backup_id),
            "candidate_name": result.directory.name,
            "table_count": len(result.manifest.database.tables),
            "database_sha256": result.manifest.database.archive_sha256,
            "evidence_mode": result.manifest.evidence_mode.value,
            "missing_evidence": sum(
                item.state.value == "missing" for item in result.manifest.evidence_objects
            ),
            "restore_verified": False,
        }

    def _candidate(self, backup_id: UUID) -> Path:
        root = self._settings.operations_backup_directory
        if root is None or not root.is_dir():
            raise ValueError("backup directory unavailable")
        for path in root.iterdir():
            if (
                path.is_symlink()
                or not path.is_dir()
                or not path.name.startswith("hotkey-backup-")
                or not path.name.endswith(backup_id.hex)
            ):
                continue
            manifest = BackupManifest.model_validate_json((path / "manifest.json").read_bytes())
            if manifest.backup_id == backup_id:
                return path
        raise ValueError("backup candidate not found")

    def _verify_backup(self, backup_id: UUID) -> dict[str, object]:
        isolation = self._settings.operations_restore_database_url
        if isolation is None:
            raise ValueError("isolated restore URL missing")
        result = BackupRestoreService(
            source_database_url=self._settings.database_url.get_secret_value(),
            isolation_database_url=isolation.get_secret_value(),
            schema_path=Path(__file__).resolve().parents[2] / "database" / "schema.sql",
            evidence_restore_verifier=MinioEvidenceRestoreVerifier(
                self._minio(), self._settings.minio_bucket
            ),
        ).verify(self._candidate(backup_id))
        return {
            "backup_id": str(result.backup_id),
            "database_restored": result.database_restored,
            "table_count": result.table_count,
            "evidence_objects_verified": result.evidence_objects_verified,
            "duration_seconds": result.duration_seconds,
            "restore_verified": result.database_restored,
            "production_restore": False,
        }

    def _retain(self, owner: UUID) -> dict[str, object]:
        now = self._clock()
        with self._sessions() as session, session.begin():
            obsolete = list(
                session.scalars(
                    select(Feedback)
                    .where(
                        Feedback.owner_id == owner,
                        Feedback.status.in_(["resolved", "rejected"]),
                        Feedback.updated_at < now - timedelta(days=180),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            )
            for row in obsolete:
                row.content = row.email = row.page_url = row.note = None
                row.status, row.revision, row.updated_at = "deleted", row.revision + 1, now
                session.execute(
                    delete(FeedbackAttachment).where(
                        FeedbackAttachment.owner_id == owner,
                        FeedbackAttachment.feedback_id == row.id,
                    )
                )
            active_sources = select(Feedback.source_hash).where(
                Feedback.owner_id == owner, Feedback.status != "deleted"
            )
            deleted_result = session.execute(
                delete(FeedbackCooldown).where(
                    FeedbackCooldown.owner_id == owner,
                    FeedbackCooldown.banned.is_(False),
                    FeedbackCooldown.updated_at < now - timedelta(days=30),
                    FeedbackCooldown.source_hash.not_in(active_sources),
                )
            )
            deleted = deleted_result.rowcount if isinstance(deleted_result, CursorResult) else 0
            protected = {
                row.target_ref
                for row in session.scalars(
                    select(OperatorAuditOperation).where(
                        OperatorAuditOperation.owner_id == owner,
                        OperatorAuditOperation.action == "maintenance.verify_backup",
                        OperatorAuditOperation.status == "accepted",
                    )
                )
            }
        removed = 0
        root = self._settings.operations_backup_directory
        if root and root.is_dir():
            for path in root.iterdir():
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not path.name.startswith("hotkey-backup-")
                ):
                    continue
                try:
                    manifest = BackupManifest.model_validate_json(
                        (path / "manifest.json").read_bytes()
                    )
                except (OSError, ValueError):
                    continue
                age = (now - manifest.created_at).days
                keep = (
                    365
                    if manifest.created_at.day == 1
                    else 90
                    if manifest.created_at.weekday() == 0
                    else 30
                )
                if age > keep and str(manifest.backup_id) not in protected:
                    with (path / "database.dump").open("rb") as dump:
                        matching = (
                            hashlib.file_digest(dump, "sha256").hexdigest()
                            == manifest.database.archive_sha256
                        )
                    if matching:
                        shutil.rmtree(path)
                        removed += 1
        return {
            "feedback_scrubbed": len(obsolete),
            "cooldowns_removed": deleted,
            "backup_bundles_removed": removed,
            "protected_backup_ids": sorted(protected),
        }

    def _forward_feedback(
        self, message: JobMessage, audit_id: UUID, lease: ExecutionLease | None
    ) -> dict[str, object]:
        with self._sessions() as session, session.begin():
            audit = session.get(OperatorAuditOperation, audit_id)
            assert audit is not None
            saved_ids = audit.after_state.get("feedback_ids")
            statement = select(Feedback).where(
                Feedback.owner_id == message.owner_id,
                Feedback.status != "deleted",
            )
            if isinstance(saved_ids, list):
                statement = statement.where(
                    Feedback.id.in_([UUID(str(value)) for value in saved_ids])
                )
            else:
                statement = statement.where(
                    Feedback.status != "deleted",
                    Feedback.forwarded_at.is_(None),
                    Feedback.forward_error.is_(None),
                )
            rows = list(session.scalars(statement.order_by(Feedback.created_at).limit(20)))
            ids = [row.id for row in rows]
            body = "\n\n".join(
                f"反馈 {row.id}\n{row.content}\n页面: {row.page_url or '-'}" for row in rows
            )
        if not ids:
            return {"forwarded": 0}
        try:
            self._deliver(
                message,
                audit_id,
                "HotKey 私有反馈",
                body[:12000],
                lease,
                {"feedback_ids": [str(value) for value in ids]},
            )
        except JobExecutionFailure as error:
            if error.error_code == "operations_delivery_unknown":
                with self._sessions() as session, session.begin():
                    for row in session.scalars(
                        select(Feedback).where(
                            Feedback.owner_id == message.owner_id, Feedback.id.in_(ids)
                        )
                    ):
                        row.forward_error = "delivery_unknown"
            raise
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            for row in session.scalars(
                select(Feedback).where(Feedback.owner_id == message.owner_id, Feedback.id.in_(ids))
            ):
                row.forwarded_at = self._clock()
        return {"forwarded": len(ids), "feedback_ids": [str(value) for value in ids]}

    def _deliver(
        self,
        message: JobMessage,
        audit_id: UUID,
        title: str,
        body: str,
        lease: ExecutionLease | None,
        saved_state: dict[str, object] | None = None,
    ) -> None:
        url = self._settings.operations_webhook_url
        if url is None:
            raise self._failure("operations_delivery_disabled")
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            audit = session.scalar(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.id == audit_id,
                    OperatorAuditOperation.owner_id == message.owner_id,
                )
                .with_for_update()
            )
            assert audit is not None
            if audit.after_state.get("delivered") is True:
                return
            attempt = int(str(audit.after_state.get("delivery_attempt", 0))) + 1
            reservation = uuid5(_NAMESPACE, f"network:{audit_id}:{attempt}")
            decision = ResourceBudgetService(
                session, clock=self._clock
            ).reserve_budget_in_transaction(
                owner_id=message.owner_id,
                command=BudgetReservationInput(
                    reservation_id=reservation,
                    operation_id=message.operation_id,
                    metric=BudgetMetric.NETWORK_REQUEST,
                    requested_units=1,
                    context=BudgetContext(source_ref="operations", job_ref=str(message.job_id)),
                ),
            )
            if decision.status != BudgetDecisionStatus.RESERVED:
                raise self._failure("operations_delivery_budget_denied")
            audit.after_state = {
                **(saved_state or {}),
                "delivery_attempt": attempt,
                "delivery_fingerprint": hashlib.sha256(f"{title}\n{body}".encode()).hexdigest(),
            }
            audit.error_code, audit.updated_at = "request_started", self._clock()
        owned = self._client is None
        client = self._client or httpx.Client(timeout=30)
        try:
            FeishuWebhook(url=url, secret=None, client=client).send(
                notification_card(
                    title=title,
                    text=body,
                    reading_url=self._settings.web_base_url.rstrip("/") + "/operations",
                ),
                now=self._clock(),
            )
        except FeishuDeliveryError as error:
            with self._sessions() as session, session.begin():
                audit = session.get(OperatorAuditOperation, audit_id)
                assert audit is not None
                audit.status, audit.error_code, audit.updated_at = (
                    "unknown" if error.uncertain else "failed",
                    "result_unknown" if error.uncertain else error.code,
                    self._clock(),
                )
            raise self._failure(
                "operations_delivery_unknown" if error.uncertain else "operations_delivery_failed",
                manual=not error.uncertain,
            ) from error
        finally:
            if owned:
                client.close()
            with self._sessions() as session, session.begin():
                ResourceBudgetService(
                    session, clock=self._clock
                ).settle_budget_reservation_in_transaction(
                    owner_id=message.owner_id, reservation_id=reservation, actual_units=1
                )
        with self._sessions() as session, session.begin():
            self._guard(session, lease)
            audit = session.get(OperatorAuditOperation, audit_id)
            assert audit is not None
            audit.error_code = "delivery_saved"
            audit.after_state = {
                **audit.after_state,
                "delivered": True,
                "delivered_at": self._clock().isoformat(),
            }

    def _failure(self, code: str, *, manual: bool = True) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_INPUT,
            occurred_at=self._clock(),
            next_action="检查运营配置与审计;未知投递需人工核对目的地",
            manual_retry_allowed=manual,
        )
