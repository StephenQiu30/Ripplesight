"""Persistent Codex announcement use case, ported from AIHOT monitor/* and admin/monitor.ts.

The source is MIT licensed; see LICENSE. Ripplesight keeps its own
transactions, AiService receipts, Kafka jobs and official X authorization.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from functools import partial
from itertools import pairwise
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ai.capability_services import freeze_ai_job_scope_in_transaction
from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService
from connections.editorial_services import require_official_x_connection_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import (
    RetentionPolicyUnavailableError,
    SourceAccessPolicyService,
    SourceAccessUnavailableError,
)
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobView
from jobs.services import JobService
from monitors.codex_models import (
    CodexResetEvent,
    CodexResetEventPost,
    CodexResetMonitor,
    CodexResetMonitorVersion,
    CodexResetPost,
    CodexResetRecognition,
    CodexResetReview,
    CodexResetScanGap,
)
from monitors.codex_recognize import RECOGNIZE_PROMPT_VERSION, recognize
from monitors.codex_schemas import (
    AppliedRecognition,
    CalendarMark,
    CodexConfigurationInput,
    CodexOperationalHealth,
    CodexTickInput,
    ContextPost,
    EventPatch,
    MonitorConfiguration,
    MonitorView,
    NotificationIntent,
    OutageView,
    PresentationStatus,
    Proposition,
    Recognition,
    RecognitionInput,
    ResetEventPost,
    ResetEventView,
    ResetHealth,
    ResetPostInput,
    ResetPostView,
    ResetSnapshot,
    ResetStatistics,
    ResetVersionView,
    ReviewInput,
    ScanGapView,
    Schedule,
)
from monitors.codex_time import (
    BEIJING,
    HOUR,
    aware,
    estimate_for,
    manual_schedule,
    resolve_stated_time,
    schedule_from,
)
from operations.services import (
    accept_audit_in_transaction,
    complete_audit_in_transaction,
    load_completed_audit_in_transaction,
)
from sources.contracts import SourceCapability

HOT_WINDOW = 8 * HOUR
OUTAGE_WINDOW = 18 * HOUR
LIKELY_AFTER = 6 * HOUR
STATED_COUNT = re.compile(
    r"\b(twice|thrice)\b|\b(two|three|four|five|[2-5])\s+(?:(?:banked|manual)\s+)?(?:times|resets?)\b|\b[2-5]\s*x\b",
    re.I,
)
ANOTHER = re.compile(r"\b(another|again|second|one more|twice|2nd)\b", re.I)
HEDGED = re.compile(r"\b(about|around|approximately|roughly|shortly|soon|or so)\b|~|-ish\b", re.I)


def _fingerprint(value: Any) -> bytes:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).digest()


def _loose(value: str) -> str:
    value = re.sub(r"https?://\S+", " ", unicodedata.normalize("NFKC", value).lower())
    return (
        " " + re.sub(r"\s+", " ", "".join(c if c.isalnum() else " " for c in value)).strip() + " "
    )


def quoted_in_post(excerpt: str, post: str) -> bool:
    parts = [_loose(part) for part in re.split(r"…|\.\.\.", excerpt)]
    parts = [part for part in parts if part.strip()]
    return bool(parts) and all(part in _loose(post) for part in parts)


def validated_propositions(
    rec: Recognition, post: str
) -> tuple[list[Proposition], list[Proposition]]:
    accepted, held = [], []
    for p in rec.propositions:
        if not p.real or not p.excerpt.strip():
            continue
        if not rec.relevant or rec.needs_review or not quoted_in_post(p.excerpt, post):
            held.append(p)
        else:
            accepted.append(
                p.model_copy(update={"count": 1})
                if p.count > 1 and not STATED_COUNT.search(p.excerpt)
                else p
            )
    return accepted, held


def presentation_status(event: ResetEventView, now: datetime) -> PresentationStatus:
    if event.withdrawn:
        return "withdrawn"
    if event.status == "confirmed":
        return "confirmed"
    window = event.estimate or event.schedule
    if window and aware(now) >= window.ends_at:
        return (
            "expired_unconfirmed"
            if aware(now) < window.ends_at + LIKELY_AFTER
            else "likely_completed"
        )
    return "in_progress" if event.in_progress else "announced"


def _title(event: ResetEventView, shown: PresentationStatus) -> str:
    credit = event.kind == "reset_credit"
    if shown == "withdrawn":
        return "重置卡预告已撤回" if credit else "重置预告已撤回"
    if not event.kind_explicit and event.confirmation_basis != "receipt_review":
        if event.status == "confirmed":
            return "Tibo 确认重置(形式未明确)"
        if shown == "likely_completed":
            return "预告重置可能已生效(形式未明确,未确认)"
        if shown == "in_progress":
            return "重置进行中(形式未明确)"
        return "Tibo 预告重置(形式未明确)"
    if event.status == "confirmed":
        if event.confirmation_basis == "receipt_review":
            return "重置卡已人工核实到账" if credit else "额度重置已人工核实到账"
        return (
            "重置卡已发放"
            if credit
            else "Codex 额度重置已完成"
            if event.kind_explicit
            else "Tibo 确认重置"
        )
    if shown == "likely_completed":
        return "重置卡应已发放(未确认)" if credit else "额度应已重置(未确认)"
    if shown == "in_progress":
        return "重置卡正在发放" if credit else "额度重置进行中"
    return "Tibo 预告将发放重置卡" if credit else "Tibo 预告将重置额度"


type CodexNotificationAdmission = Callable[
    [Session, UUID, UUID, tuple[NotificationIntent, ...]], int
]


class CodexResetService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        ai: AiService | None = None,
        clock: Callable[[], datetime] | None = None,
        execution_guard: Callable[[Session], bool] | None = None,
        notification_sink: CodexNotificationAdmission | None = None,
    ) -> None:
        self.settings = settings
        self._session = session
        self._ai = ai
        self._clock = clock or (lambda: datetime.now(UTC))
        self._execution_guard = execution_guard
        self._notification_sink = notification_sink

    def _monitor(
        self, owner_id: UUID, monitor_id: UUID, *, lock: bool = False
    ) -> CodexResetMonitor:
        stmt = select(CodexResetMonitor).where(
            CodexResetMonitor.owner_id == owner_id, CodexResetMonitor.id == monitor_id
        )
        row = self._session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise ApplicationError("resource_not_found")
        return row

    def _configuration(self, monitor: CodexResetMonitor) -> MonitorConfiguration:
        row = self._session.get(
            CodexResetMonitorVersion, (monitor.owner_id, monitor.id, monitor.configuration_version)
        )
        if row is None:
            raise RuntimeError("missing immutable Codex monitor configuration")
        return MonitorConfiguration.model_validate(row.configuration)

    def _monitor_view(self, monitor: CodexResetMonitor) -> MonitorView:
        return MonitorView(
            id=monitor.id,
            enabled=monitor.enabled,
            revision=monitor.revision,
            configuration_version=monitor.configuration_version,
            configuration=self._configuration(monitor),
        )

    def create_monitor(
        self, *, owner_id: UUID, configuration: MonitorConfiguration | None = None
    ) -> MonitorView:
        with self._session.begin():
            return self.create_monitor_in_transaction(
                owner_id=owner_id, configuration=configuration
            )

    def create_monitor_in_transaction(
        self, *, owner_id: UUID, configuration: MonitorConfiguration | None = None
    ) -> MonitorView:
        if not self._session.in_transaction():
            raise RuntimeError("Codex creation requires caller transaction")
        now = aware(self._clock())
        existing = self._session.scalar(
            select(CodexResetMonitor).where(CodexResetMonitor.owner_id == owner_id)
        )
        if existing is not None:
            return self._monitor_view(existing)
        monitor = CodexResetMonitor(
            id=uuid4(),
            owner_id=owner_id,
            enabled=False,
            revision=1,
            configuration_version=1,
            projection_epoch=1,
            scan_revision=1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(monitor)
        self._session.flush()
        self._session.add(
            CodexResetMonitorVersion(
                owner_id=owner_id,
                monitor_id=monitor.id,
                version=1,
                configuration=(configuration or MonitorConfiguration()).model_dump(mode="json"),
                created_at=now,
            )
        )
        self._session.flush()
        return self._monitor_view(monitor)

    def get_monitor(self, *, owner_id: UUID, monitor_id: UUID) -> MonitorView:
        with self._session.begin():
            return self._monitor_view(self._monitor(owner_id, monitor_id))

    def get_existing_monitor(self, *, owner_id: UUID) -> MonitorView | None:
        """A read must never configure or create an announcement monitor."""
        with self._session.begin():
            row = self._session.scalar(
                select(CodexResetMonitor).where(CodexResetMonitor.owner_id == owner_id)
            )
            return self._monitor_view(row) if row else None

    def configure(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        expected_revision: int,
        enabled: bool,
        configuration: MonitorConfiguration | None = None,
    ) -> MonitorView:
        with self._session.begin():
            return self.configure_in_transaction(
                owner_id=owner_id,
                monitor_id=monitor_id,
                expected_revision=expected_revision,
                enabled=enabled,
                configuration=configuration,
            )

    def configure_in_transaction(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        expected_revision: int,
        enabled: bool,
        configuration: MonitorConfiguration | None = None,
    ) -> MonitorView:
        if not self._session.in_transaction():
            raise RuntimeError("Codex configuration requires caller transaction")
        monitor = self._monitor(owner_id, monitor_id, lock=True)
        if monitor.revision != expected_revision:
            raise ApplicationError("codex_version_conflict")
        if configuration is not None and configuration != self._configuration(monitor):
            monitor.configuration_version += 1
            self._session.add(
                CodexResetMonitorVersion(
                    owner_id=owner_id,
                    monitor_id=monitor_id,
                    version=monitor.configuration_version,
                    configuration=configuration.model_dump(mode="json"),
                    created_at=aware(self._clock()),
                )
            )
            # A new configuration holds old gaps instead of reinterpreting their page tokens.
            for gap in self._session.scalars(
                select(CodexResetScanGap).where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state == "pending",
                )
            ).all():
                gap.state, gap.failure_code = "held", "configuration_changed"
        monitor.enabled = enabled
        monitor.revision += 1
        monitor.projection_epoch += 1
        monitor.scan_revision += 1
        monitor.updated_at = aware(self._clock())
        self._session.flush()
        return self._monitor_view(monitor)

    def save_configuration(
        self, *, owner_id: UUID, command: CodexConfigurationInput
    ) -> MonitorView:
        self._session.rollback()
        with self._session.begin():
            return self.save_configuration_in_transaction(owner_id=owner_id, command=command)

    def save_configuration_in_transaction(
        self, *, owner_id: UUID, command: CodexConfigurationInput
    ) -> MonitorView:
        if not self._session.in_transaction():
            raise RuntimeError("Codex operator configuration requires caller transaction")
        now = aware(self._clock())
        accept_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            action="codex_reset.configure",
            target_ref="codex-reset-monitor",
            reason=command.reason,
            payload=command.model_dump(mode="json"),
            now=now,
            before_state={"revision": command.expected_revision},
        )
        replay = load_completed_audit_in_transaction(
            self._session, owner_id=owner_id, operation_id=command.operation_id
        )
        if replay is not None:
            return MonitorView.model_validate(replay)
        existing = self._session.scalar(
            select(CodexResetMonitor)
            .where(CodexResetMonitor.owner_id == owner_id)
            .with_for_update()
        )
        if existing is None:
            if command.expected_revision != 0 or command.enabled:
                raise ApplicationError("invalid_codex_input")
            result = self.create_monitor_in_transaction(
                owner_id=owner_id, configuration=command.configuration
            )
        else:
            if command.enabled:
                c = command.configuration
                if (
                    c.connection_id is None
                    or c.connection_version is None
                    or c.author_external_id is None
                ):
                    raise ApplicationError("invalid_codex_input")
                require_official_x_connection_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    connection_id=c.connection_id,
                    connection_version=c.connection_version,
                    now=now,
                )
            result = self.configure_in_transaction(
                owner_id=owner_id,
                monitor_id=existing.id,
                expected_revision=command.expected_revision,
                enabled=command.enabled,
                configuration=command.configuration,
            )
        complete_audit_in_transaction(
            self._session,
            owner_id=owner_id,
            operation_id=command.operation_id,
            after_state=result.model_dump(mode="json"),
            now=now,
        )
        return result

    def enqueue_tick(self, *, owner_id: UUID, monitor_id: UUID, command: CodexTickInput) -> JobView:
        self._session.rollback()
        with self._session.begin():
            return self.enqueue_tick_in_transaction(
                owner_id=owner_id, monitor_id=monitor_id, command=command, audited=True
            )

    def enqueue_tick_in_transaction(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        command: CodexTickInput,
        audited: bool = False,
        scheduled_for_at: datetime | None = None,
    ) -> JobView:
        if not self._session.in_transaction():
            raise RuntimeError("Codex Job admission requires caller transaction")
        monitor = self._monitor(owner_id, monitor_id, lock=True)
        now = aware(self._clock())
        if audited:
            accept_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                action="codex_reset.tick",
                target_ref=f"codex-reset-monitor:{monitor_id}",
                reason=command.reason,
                payload=command.model_dump(mode="json"),
                now=now,
                before_state={"revision": monitor.revision},
            )
            frozen = load_completed_audit_in_transaction(
                self._session, owner_id=owner_id, operation_id=command.operation_id
            )
            if frozen is not None:
                return JobView.model_validate(frozen)
        if not monitor.enabled or monitor.revision != command.expected_revision:
            raise ApplicationError("codex_version_conflict")
        if (
            self._session.scalar(
                select(CodexResetScanGap.id)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state != "complete",
                    CodexResetScanGap.failure_code.in_(
                        ("source_request_running", "source_unknown", "context_unknown")
                    ),
                )
                .limit(1)
            )
            is not None
        ):
            raise ApplicationError("codex_source_unavailable")
        c = self._configuration(monitor)
        if c.connection_id is None or c.connection_version is None or c.author_external_id is None:
            raise ApplicationError("invalid_codex_input")
        require_official_x_connection_in_transaction(
            self._session,
            owner_id=owner_id,
            connection_id=c.connection_id,
            connection_version=c.connection_version,
            now=now,
        )
        result = JobService(self._session, clock=self._clock).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=command.operation_id,
                kind="monitor.codex_reset.tick",
                observation=JobObservationContext(
                    configuration_ref=f"codex-reset:{monitor_id}",
                    configuration_version=monitor.configuration_version,
                    source_key="x",
                    source_capability=SourceCapability.SEARCH,
                ),
                scheduled_for_at=scheduled_for_at,
                scope={
                    **freeze_ai_job_scope_in_transaction(
                        self._session, owner_id=owner_id, settings=self.settings
                    ),
                    "monitor_id": str(monitor_id),
                    "revision": monitor.revision,
                    "lookback_hours": command.lookback_hours,
                    "force": audited,
                },
            ),
        )
        if audited:
            complete_audit_in_transaction(
                self._session,
                owner_id=owner_id,
                operation_id=command.operation_id,
                after_state=result.model_dump(mode="json"),
                now=now,
            )
        return result

    def _store_post(self, monitor: CodexResetMonitor, source: ResetPostInput) -> bool:
        raw = source.model_dump(mode="json")
        # Collection origin/receipt identity can differ across overlapping lookbacks.
        fingerprint = _fingerprint(
            source.model_dump(mode="json", exclude={"origin", "source_receipt_ref"})
        )
        row = self._session.scalar(
            select(CodexResetPost).where(
                CodexResetPost.owner_id == monitor.owner_id,
                CodexResetPost.monitor_id == monitor.id,
                CodexResetPost.external_id == source.external_id,
            )
        )
        if row is not None:
            if row.input_fingerprint != fingerprint:
                raise ApplicationError(
                    "codex_version_conflict", context={"reason": "source_evidence_changed"}
                )
            return False
        self._session.add(
            CodexResetPost(
                id=uuid4(),
                owner_id=monitor.owner_id,
                monitor_id=monitor.id,
                configuration_version=monitor.configuration_version,
                external_id=source.external_id,
                published_at=aware(source.published_at),
                source_input=raw,
                input_fingerprint=fingerprint,
                context=[c.model_dump(mode="json") for c in source.context],
                needs_review=False,
                reviewed=False,
                skipped=False,
                review_version=1,
                failure_count=0,
                collected_at=aware(self._clock()),
            )
        )
        monitor.history_from = min(monitor.history_from or source.published_at, source.published_at)
        return True

    def store_posts(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        posts: tuple[ResetPostInput, ...],
        expected_configuration_version: int,
    ) -> int:
        if len(posts) > 100:
            raise ApplicationError("invalid_codex_input")
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            if monitor.configuration_version != expected_configuration_version:
                raise ApplicationError("codex_version_conflict")
            stored = sum(
                self._store_post(monitor, p)
                for p in sorted(posts, key=lambda p: (p.published_at, int(p.external_id)))
            )
            self._session.flush()
            return stored

    def _event_view(
        self, row: CodexResetEvent, *, now: datetime, posts: tuple[ResetEventPost, ...] = ()
    ) -> ResetEventView:
        event = ResetEventView.model_validate(
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "revision": row.revision,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "withdrawn": row.withdrawn,
                "in_progress": row.in_progress,
                "kind_explicit": row.kind_explicit,
                "time_inferred": row.time_inferred,
                "confirmed_at": row.confirmed_at,
                "occurred_on": row.occurred_on,
                "confirmation_basis": row.confirmation_basis,
                "schedule": row.schedule,
                "estimate": row.estimate,
                "scope": row.scope,
                "reported_at": row.reported_at,
                "posts": posts,
            }
        )
        shown = presentation_status(event, now)
        return event.model_copy(
            update={"presentation_status": shown, "title": _title(event, shown)}
        )

    def prepare_next(self, *, owner_id: UUID, monitor_id: UUID) -> RecognitionInput | None:
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id)
            if not monitor.enabled:
                raise ApplicationError("codex_monitor_disabled")
            if self._execution_guard is not None and not self._execution_guard(self._session):
                return None
            if self._session.scalar(
                select(CodexResetScanGap.id)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state != "complete",
                    func.coalesce(CodexResetScanGap.failure_code, "")
                    != "operator_acknowledged_gap",
                )
                .limit(1)
            ):
                return None
            post = self._session.scalar(
                select(CodexResetPost)
                .where(
                    CodexResetPost.owner_id == owner_id,
                    CodexResetPost.monitor_id == monitor_id,
                    CodexResetPost.processed_at.is_(None),
                )
                .order_by(
                    CodexResetPost.published_at,
                    func.length(CodexResetPost.external_id),
                    CodexResetPost.external_id,
                )
                .limit(1)
            )
            if post is None:
                return None
            rows = self._session.scalars(
                select(CodexResetEvent)
                .where(
                    CodexResetEvent.owner_id == owner_id,
                    CodexResetEvent.monitor_id == monitor_id,
                    CodexResetEvent.withdrawn.is_(False),
                    CodexResetEvent.created_at >= post.published_at - 72 * HOUR,
                    CodexResetEvent.created_at <= post.published_at + 48 * HOUR,
                )
                .order_by(CodexResetEvent.created_at.desc())
                .limit(8)
            ).all()
            return RecognitionInput(
                owner_id=owner_id,
                monitor_id=monitor_id,
                post_id=post.id,
                configuration_version=monitor.configuration_version,
                projection_epoch=monitor.projection_epoch,
                review_version=post.review_version,
                input_fingerprint=post.input_fingerprint.hex(),
                post=ResetPostInput.model_validate(post.source_input),
                open_events=tuple(
                    self._event_view(
                        e,
                        now=aware(self._clock()),
                        posts=self._first_event_post(owner_id, monitor_id, e.id),
                    )
                    for e in rows
                ),
            )

    def _first_event_post(
        self, owner_id: UUID, monitor_id: UUID, event_id: str
    ) -> tuple[ResetEventPost, ...]:
        linked = self._session.execute(
            select(CodexResetEventPost, CodexResetPost)
            .join(CodexResetPost, CodexResetPost.id == CodexResetEventPost.post_id)
            .where(
                CodexResetEventPost.owner_id == owner_id,
                CodexResetEventPost.monitor_id == monitor_id,
                CodexResetEventPost.event_id == event_id,
            )
            .order_by(CodexResetPost.published_at, CodexResetPost.external_id)
            .limit(1)
        ).first()
        if linked is None:
            return ()
        link, p = linked
        return (
            ResetEventPost.model_validate(
                {
                    "post_id": p.id,
                    "external_id": p.external_id,
                    "published_at": p.published_at,
                    "action": link.action,
                    "stage": link.stage,
                    "excerpt": link.excerpt,
                    "excerpt_zh": link.excerpt_zh,
                    "original_text": p.source_input["text"],
                    "translation_zh": p.translation_zh,
                    "url": p.source_input["url"],
                    "context": p.context,
                }
            ),
        )

    def _recognition_admission_in_transaction(
        self, prepared: RecognitionInput, attempt_id: UUID | None
    ) -> None:
        """Recheck the exact source and review context inside the AI reserve transaction."""
        if not self._session.in_transaction():
            raise RuntimeError("recognition admission requires caller transaction")
        monitor = self._monitor(prepared.owner_id, prepared.monitor_id, lock=True)
        post = self._session.get(CodexResetPost, prepared.post_id, with_for_update=True)
        attempt = self._attempt(prepared, attempt_id) if attempt_id else None
        if (
            post is None
            or post.owner_id != prepared.owner_id
            or post.monitor_id != prepared.monitor_id
            or post.processed_at is not None
            or post.review_version != prepared.review_version
            or post.input_fingerprint.hex() != prepared.input_fingerprint
            or not monitor.enabled
            or monitor.configuration_version != prepared.configuration_version
            or monitor.projection_epoch != prepared.projection_epoch
            or (attempt is not None and attempt.status != "running")
            or (self._execution_guard is not None and not self._execution_guard(self._session))
        ):
            raise AiCallError(AiFailureCode.UNAVAILABLE, "recognition input changed")
        configuration = self._configuration(monitor)
        if configuration.connection_id is None or configuration.connection_version is None:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "official source is not configured")
        current_events = self._session.scalars(
            select(CodexResetEvent)
            .where(
                CodexResetEvent.owner_id == prepared.owner_id,
                CodexResetEvent.monitor_id == prepared.monitor_id,
                CodexResetEvent.withdrawn.is_(False),
                CodexResetEvent.created_at >= post.published_at - 72 * HOUR,
                CodexResetEvent.created_at <= post.published_at + 48 * HOUR,
            )
            .order_by(CodexResetEvent.created_at.desc())
            .limit(8)
            .with_for_update()
        ).all()
        if [(e.id, e.revision) for e in current_events] != [
            (e.id, e.revision) for e in prepared.open_events
        ]:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "recognition event context changed")
        now = aware(self._clock())
        try:
            require_official_x_connection_in_transaction(
                self._session,
                owner_id=prepared.owner_id,
                connection_id=configuration.connection_id,
                connection_version=configuration.connection_version,
                now=now,
            )
            materials = [(prepared.post.text, prepared.post.published_at)]
            materials.extend(
                (c.original_text, c.published_at or prepared.post.published_at)
                for c in prepared.post.context
            )
            materials.extend(
                (p.original_text, p.published_at)
                for event in prepared.open_events
                for p in event.posts
            )
            policy = SourceAccessPolicyService(self._session, clock=lambda: now)
            for body, observed_at in materials:
                permission = policy.admit_payload_in_transaction(
                    owner_id=prepared.owner_id,
                    source_key="x",
                    capability=SourceCapability.SEARCH,
                    data_class=DataClass.STRUCTURED,
                    collected_at=observed_at,
                    payload={"body": body},
                )
                if permission.fields.get("body") != body:
                    raise AiCallError(
                        AiFailureCode.UNAVAILABLE, "recognition text permission changed"
                    )
        except (
            ApplicationError,
            SourceAccessUnavailableError,
            RetentionPolicyUnavailableError,
        ) as error:
            raise AiCallError(
                AiFailureCode.UNAVAILABLE, "recognition source permission changed"
            ) from error

    def _recognition_admission(
        self, session: Session, *, prepared: RecognitionInput, attempt_id: UUID
    ) -> None:
        CodexResetService(
            session,
            settings=self.settings,
            clock=self._clock,
            execution_guard=self._execution_guard,
        )._recognition_admission_in_transaction(prepared, attempt_id)

    def process_pending(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        limit: int = 20,
        job_id: UUID | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        if not 1 <= limit <= 20:
            raise ApplicationError("invalid_codex_input")
        processed = failed = enqueued = 0
        for _ in range(limit):
            if cancelled and cancelled():
                break
            prepared = self.prepare_next(owner_id=owner_id, monitor_id=monitor_id)
            if prepared is None:
                break
            attempt_id = None
            try:
                attempt_id = self.begin_recognition(prepared=prepared, job_id=job_id)
                if attempt_id is None:
                    break
                if self._ai is None:
                    raise AiCallError(AiFailureCode.UNAVAILABLE)
                caller = self._ai.with_admission_guard(
                    partial(self._recognition_admission, prepared=prepared, attempt_id=attempt_id)
                )
                recognition, call_id = recognize(caller, prepared, job_id=job_id)
                applied = self.apply_recognition(
                    prepared=prepared,
                    recognition=recognition,
                    ai_call_id=call_id,
                    attempt_id=attempt_id,
                )
                if applied.status == "stale":
                    break
                processed += int(applied.status != "duplicate")
                enqueued += applied.notifications_enqueued
            except AiCallError as error:
                self.record_failure(
                    prepared=prepared,
                    code=error.code.value,
                    ai_call_id=error.call_id,
                    attempt_id=attempt_id,
                )
                failed += 1
                break
        return {"processed": processed, "failed": failed, "notifications_enqueued": enqueued}

    @staticmethod
    def _new_recognition(
        prepared: RecognitionInput,
        *,
        recognition_id: UUID,
        status: str,
        recognition: dict[str, Any],
        created_at: datetime,
        prompt_version: str = RECOGNIZE_PROMPT_VERSION,
    ) -> CodexResetRecognition:
        return CodexResetRecognition(
            id=recognition_id,
            owner_id=prepared.owner_id,
            monitor_id=prepared.monitor_id,
            post_id=prepared.post_id,
            configuration_version=prepared.configuration_version,
            projection_epoch=prepared.projection_epoch,
            review_version=prepared.review_version,
            input_fingerprint=bytes.fromhex(prepared.input_fingerprint),
            prompt_version=prompt_version,
            ai_call_id=None,
            status=status,
            recognition=recognition,
            held=[],
            notifications=[],
            created_at=created_at,
        )

    def _attempt(self, prepared: RecognitionInput, attempt_id: UUID) -> CodexResetRecognition:
        row = self._session.get(CodexResetRecognition, attempt_id)
        if (
            row is None
            or row.owner_id != prepared.owner_id
            or row.monitor_id != prepared.monitor_id
            or row.post_id != prepared.post_id
            or row.review_version != prepared.review_version
            or row.input_fingerprint.hex() != prepared.input_fingerprint
        ):
            raise ApplicationError("codex_version_conflict")
        return row

    def begin_recognition(
        self, *, prepared: RecognitionInput, job_id: UUID | None = None
    ) -> UUID | None:
        """Persist the model boundary before calling AiService; an interrupted call is unknown."""
        with self._session.begin():
            monitor = self._monitor(prepared.owner_id, prepared.monitor_id, lock=True)
            post = self._session.get(CodexResetPost, prepared.post_id)
            if (
                post is None
                or post.owner_id != prepared.owner_id
                or post.monitor_id != prepared.monitor_id
                or post.processed_at is not None
                or post.review_version != prepared.review_version
                or not monitor.enabled
                or monitor.configuration_version != prepared.configuration_version
                or monitor.projection_epoch != prepared.projection_epoch
                or (self._execution_guard is not None and not self._execution_guard(self._session))
            ):
                return None
            prior = self._session.scalars(
                select(CodexResetRecognition).where(
                    CodexResetRecognition.owner_id == prepared.owner_id,
                    CodexResetRecognition.monitor_id == prepared.monitor_id,
                    CodexResetRecognition.post_id == prepared.post_id,
                    CodexResetRecognition.review_version == prepared.review_version,
                    CodexResetRecognition.status.in_(("running", "unknown", "failed", "stale")),
                )
            ).all()
            uncertain = next(
                (row for row in prior if row.status in {"running", "unknown"} or row.ai_call_id),
                None,
            )
            if uncertain:
                if uncertain.status == "running":
                    uncertain.status = "unknown"
                    uncertain.recognition = {
                        **uncertain.recognition,
                        "status": "unknown",
                        "failure_code": "recognition_interrupted",
                    }
                    post.failure_code = "recognition_interrupted"
                    post.failure_count += 1
                post.needs_review = True
                post.reviewed = False
                monitor.updated_at = aware(self._clock())
                return None
            row = self._new_recognition(
                prepared,
                recognition_id=uuid4(),
                status="running",
                recognition={"status": "running", "job_id": str(job_id) if job_id else None},
                created_at=aware(self._clock()),
            )
            self._session.add(row)
            return row.id

    def record_failure(
        self,
        *,
        prepared: RecognitionInput,
        code: str,
        ai_call_id: UUID | None = None,
        attempt_id: UUID | None = None,
    ) -> None:
        with self._session.begin():
            monitor = self._monitor(prepared.owner_id, prepared.monitor_id, lock=True)
            row = self._session.get(CodexResetPost, prepared.post_id)
            if (
                row is not None
                and row.owner_id == prepared.owner_id
                and row.monitor_id == prepared.monitor_id
                and row.processed_at is None
                and row.review_version == prepared.review_version
                and monitor.enabled
                and monitor.configuration_version == prepared.configuration_version
                and monitor.projection_epoch == prepared.projection_epoch
                and (self._execution_guard is None or self._execution_guard(self._session))
            ):
                row.failure_count += 1
                row.failure_code = code[:64]
                if ai_call_id is not None:
                    row.needs_review = True
                    row.reviewed = False
                monitor.updated_at = aware(self._clock())
            attempt = (
                self._attempt(prepared, attempt_id)
                if attempt_id
                else self._new_recognition(
                    prepared,
                    recognition_id=uuid4(),
                    status="failed",
                    recognition={},
                    created_at=aware(self._clock()),
                )
            )
            attempt.status = "unknown" if ai_call_id is not None else "failed"
            attempt.ai_call_id = ai_call_id
            attempt.recognition = {"status": attempt.status, "failure_code": code[:64]}
            self._session.add(attempt)

    def _target(
        self, monitor: CodexResetMonitor, p: Proposition, posted_at: datetime
    ) -> CodexResetEvent | None:
        rows = self._session.scalars(
            select(CodexResetEvent)
            .where(
                CodexResetEvent.owner_id == monitor.owner_id,
                CodexResetEvent.monitor_id == monitor.id,
                CodexResetEvent.kind == p.kind,
                CodexResetEvent.withdrawn.is_(False),
            )
            .order_by(CodexResetEvent.created_at.desc(), CodexResetEvent.id)
            .with_for_update()
        ).all()

        def is_open(e: CodexResetEvent, grace: timedelta) -> bool:
            base = (
                Schedule.model_validate(e.schedule).ends_at
                if e.schedule
                else e.created_at + 24 * HOUR
            )
            return e.created_at <= posted_at <= base + grace

        if p.relates_to:
            e = next((e for e in rows if e.id == p.relates_to), None)
            if e and (
                e.status == "confirmed"
                or is_open(e, 12 * HOUR if p.action == "announce" else 48 * HOUR)
            ):
                return e
            return None
        if p.action == "announce":
            # A catch-up can find a promise after completion; add evidence without downgrade.
            for e in reversed(rows):
                if e.status == "confirmed" and posted_at < e.created_at <= posted_at + 48 * HOUR:
                    existing = self._session.scalar(
                        select(CodexResetEventPost.post_id)
                        .where(
                            CodexResetEventPost.owner_id == monitor.owner_id,
                            CodexResetEventPost.monitor_id == monitor.id,
                            CodexResetEventPost.event_id == e.id,
                            CodexResetEventPost.action == "announce",
                        )
                        .limit(1)
                    )
                    if existing is None:
                        return e
            return None
        for e in rows[:5]:
            receipt_only = (
                p.action == "confirm"
                and e.confirmation_basis == "receipt_review"
                and e.confirmed_at is None
            )
            if (e.status == "announced" or receipt_only) and is_open(e, 12 * HOUR):
                return e
        return None

    @staticmethod
    def _schedule(p: Proposition, posted_at: datetime) -> Schedule | None:
        words = p.stated_time
        if (
            words
            and words.precision == "approximate"
            and words.relative_hours
            and not HEDGED.search(p.excerpt)
        ):
            words = words.model_copy(update={"precision": "deadline"})
        stated = resolve_stated_time(words, posted_at) if words else None
        return schedule_from(stated) if stated else None

    def _create_event(
        self,
        monitor: CodexResetMonitor,
        post: CodexResetPost,
        p: Proposition,
        index: int,
        nth: int,
        schedule: Schedule | None,
    ) -> CodexResetEvent:
        confirmed = p.action == "confirm"
        prefix = "banked" if p.kind == "reset_credit" else "reset"
        event_id = f"{prefix}-{post.external_id}-{index + 1}-{nth}"
        e = CodexResetEvent(
            owner_id=monitor.owner_id,
            monitor_id=monitor.id,
            id=event_id,
            kind=p.kind,
            status="confirmed" if confirmed else "announced",
            revision=1,
            manual_version=0,
            withdrawn=False,
            in_progress=p.action == "progress",
            kind_explicit=p.kind_explicit,
            time_inferred=p.time_inferred,
            scope=p.scope.model_dump(mode="json"),
            schedule=schedule.model_dump(mode="json") if schedule else None,
            estimate=None
            if confirmed
            else estimate_for(schedule, post.published_at, p.expected_landing).model_dump(
                mode="json"
            ),
            reported_at=post.published_at if p.action == "progress" else None,
            confirmed_at=post.published_at if confirmed else None,
            confirmation_basis="source_post" if confirmed else None,
            created_at=post.published_at,
            updated_at=post.published_at,
        )
        self._session.add(e)
        self._session.flush()
        return e

    def _link(
        self, monitor: CodexResetMonitor, e: CodexResetEvent, post: CodexResetPost, p: Proposition
    ) -> None:
        key = (monitor.owner_id, monitor.id, e.id, post.id)
        link = self._session.get(CodexResetEventPost, key)
        stage = {
            "announce": "发卡预告" if p.kind == "reset_credit" else "预告",
            "progress": "进展",
            "confirm": "确认发卡" if p.kind == "reset_credit" else "确认完成",
            "amend": "补充说明",
            "withdraw": "撤回",
        }[p.action]
        if link is None:
            self._session.add(
                CodexResetEventPost(
                    owner_id=monitor.owner_id,
                    monitor_id=monitor.id,
                    event_id=e.id,
                    post_id=post.id,
                    action=p.action,
                    stage=stage,
                    excerpt=p.excerpt,
                    excerpt_zh=p.excerpt_zh,
                )
            )
        else:
            link.action, link.stage, link.excerpt, link.excerpt_zh = (
                p.action,
                stage,
                p.excerpt,
                p.excerpt_zh,
            )

    def apply_recognition(
        self,
        *,
        prepared: RecognitionInput,
        recognition: Recognition,
        ai_call_id: UUID | None = None,
        prompt_version: str = RECOGNIZE_PROMPT_VERSION,
        attempt_id: UUID | None = None,
    ) -> AppliedRecognition:
        now = aware(self._clock())
        if not 1 <= len(prompt_version) <= 128:
            raise ApplicationError("invalid_codex_input")
        with self._session.begin():
            monitor = self._monitor(prepared.owner_id, prepared.monitor_id, lock=True)
            post = self._session.scalar(
                select(CodexResetPost)
                .where(
                    CodexResetPost.owner_id == prepared.owner_id,
                    CodexResetPost.monitor_id == prepared.monitor_id,
                    CodexResetPost.id == prepared.post_id,
                )
                .with_for_update()
            )
            if post is None:
                raise ApplicationError("resource_not_found")
            if post.processed_at is not None:
                if attempt_id:
                    attempt = self._attempt(prepared, attempt_id)
                    attempt.status = "stale"
                    attempt.ai_call_id = ai_call_id
                    attempt.recognition = recognition.model_dump(mode="json")
                return AppliedRecognition(status="duplicate")
            stale = (
                not monitor.enabled
                or monitor.configuration_version != prepared.configuration_version
                or monitor.projection_epoch != prepared.projection_epoch
                or post.review_version != prepared.review_version
                or post.input_fingerprint.hex() != prepared.input_fingerprint
                or (self._execution_guard is not None and not self._execution_guard(self._session))
            )
            if ai_call_id is not None and not stale:
                try:
                    self._recognition_admission_in_transaction(prepared, attempt_id)
                except AiCallError:
                    stale = True
                    post.needs_review = True
                    post.reviewed = False
                    post.failure_code = "recognition_source_changed"
                    monitor.updated_at = now
            accepted, held = validated_propositions(recognition, str(post.source_input["text"]))
            event_ids: list[str] = []
            notifications: list[NotificationIntent] = []
            if not stale:
                created_here: dict[str, tuple[str, Schedule | None]] = {}
                for index, p in enumerate(accepted):
                    try:
                        schedule = self._schedule(p, post.published_at)
                    except ValueError:
                        held.append(p)
                        continue
                    here = created_here.get(p.kind)
                    if (
                        here
                        and not p.relates_to
                        and p.count == 1
                        and p.action in {"announce", "progress"}
                        and not ANOTHER.search(p.excerpt)
                        and (schedule is None or schedule == here[1])
                    ):
                        continue
                    if p.relates_to and p.relates_to not in {e.id for e in prepared.open_events}:
                        held.append(p)
                        continue
                    target = self._target(monitor, p, post.published_at)
                    if (
                        target
                        and target.manual_version > 0
                        and not (
                            p.action == "confirm" and target.confirmation_basis == "receipt_review"
                        )
                    ):
                        held.append(p)
                        continue
                    events: list[CodexResetEvent] = []
                    action: Literal["announce", "confirm", "amend", "withdraw"] | None = None
                    if target is None:
                        if p.action in {"amend", "withdraw"} or p.relates_to:
                            held.append(p)
                            continue
                        for nth in range(1, p.count + 1):
                            events.append(
                                self._create_event(monitor, post, p, index, nth, schedule)
                            )
                        created_here[p.kind] = (events[0].id, schedule)
                        action = "confirm" if p.action == "confirm" else "announce"
                    else:
                        events = [target]
                        old = self._event_view(target, now=now)
                        if p.action == "announce":
                            if target.status == "announced" and schedule:
                                target.schedule = schedule.model_dump(mode="json")
                                target.estimate = estimate_for(
                                    schedule, post.published_at, p.expected_landing
                                ).model_dump(mode="json")
                                action = "amend" if old.schedule != schedule else None
                            elif target.status == "confirmed":
                                target.created_at = min(target.created_at, post.published_at)
                                if target.schedule is None and schedule:
                                    target.schedule = schedule.model_dump(mode="json")
                        elif p.action == "progress" and target.status == "announced":
                            target.in_progress, target.reported_at = True, post.published_at
                            if schedule:
                                target.schedule = schedule.model_dump(mode="json")
                                target.estimate = estimate_for(
                                    schedule, post.published_at, p.expected_landing
                                ).model_dump(mode="json")
                        elif p.action == "confirm":
                            if (
                                target.status == "confirmed"
                                and target.confirmed_at
                                and post.published_at - target.confirmed_at > 6 * HOUR
                            ):
                                events = [self._create_event(monitor, post, p, index, 1, schedule)]
                                action = "confirm"
                            else:
                                action = "confirm" if target.status == "announced" else None
                                target.status, target.estimate, target.in_progress = (
                                    "confirmed",
                                    None,
                                    False,
                                )
                                target.confirmed_at = min(
                                    target.confirmed_at or post.published_at, post.published_at
                                )
                                target.confirmation_basis = "source_post"
                        elif p.action == "amend":
                            scope_known = p.scope.audience_source is not None or bool(p.scope.plans)
                            if scope_known:
                                target.scope = p.scope.model_dump(mode="json")
                            if schedule and target.status == "announced":
                                target.schedule = schedule.model_dump(mode="json")
                                target.estimate = estimate_for(
                                    schedule, post.published_at, p.expected_landing
                                ).model_dump(mode="json")
                            if target.status == "announced" and (
                                (old.schedule != schedule and schedule is not None)
                                or (scope_known and old.scope != p.scope)
                            ):
                                action = "amend"
                        elif p.action == "withdraw":
                            target.withdrawn = True
                            action = "withdraw" if target.status == "announced" else None
                        target.revision += 1
                        target.updated_at = max(target.updated_at, post.published_at)
                    for event in events:
                        self._link(monitor, event, post, p)
                        if event.id not in event_ids:
                            event_ids.append(event.id)
                        if action:
                            notifications.append(
                                NotificationIntent(
                                    post_id=post.id,
                                    event_id=event.id,
                                    action=action,
                                    content_at=post.published_at,
                                    dedupe_key=f"codex:{post.external_id}:{event.id}:{action}",
                                )
                            )
                translations = {c.id: c.text_zh for c in recognition.context_zh}
                post.context = [
                    dict(c, text_zh=translations.get(str(c["id"]), c.get("text_zh")))
                    for c in post.context
                ]
                if recognition.relevant:
                    post.translation_zh = recognition.translation_zh
                post.needs_review = recognition.needs_review or bool(held)
                post.processed_at, post.failure_code = now, None
                if event_ids:
                    post.activity = {
                        "kind": "event_update",
                        "event_ids": event_ids,
                        "action": next(
                            (p.action for p in accepted if p.action != "progress"), None
                        ),
                        "status_changed": True,
                    }
                elif recognition.relevant and not held and not recognition.needs_review:
                    post.activity = {
                        "kind": "related",
                        "event_ids": [],
                        "action": None,
                        "status_changed": False,
                    }
                if recognition.relevant and not recognition.needs_review and not held:
                    self._apply_outage(monitor, post, recognition, notifications)
                if (
                    recognition.relevant
                    and not recognition.needs_review
                    and not held
                    and (
                        recognition.outage == "outage"
                        or any(n.action == "announce" for n in notifications)
                    )
                ):
                    monitor.hot_until = max(
                        monitor.hot_until or post.published_at, post.published_at + HOT_WINDOW
                    )
                monitor.projection_epoch += 1
                monitor.updated_at = now
            status: Literal["applied", "held", "stale"] = (
                "stale" if stale else "held" if held or recognition.needs_review else "applied"
            )
            attempt = (
                self._attempt(prepared, attempt_id)
                if attempt_id
                else self._new_recognition(
                    prepared,
                    recognition_id=uuid4(),
                    status=status,
                    recognition={},
                    created_at=now,
                    prompt_version=prompt_version,
                )
            )
            attempt.status = status
            attempt.ai_call_id = ai_call_id
            attempt.recognition = recognition.model_dump(mode="json")
            attempt.held = [p.model_dump(mode="json") for p in held]
            attempt.notifications = [n.model_dump(mode="json") for n in notifications]
            self._session.add(attempt)
            self._session.flush()
            enqueued = (
                self._notification_sink(
                    self._session, monitor.owner_id, monitor.id, tuple(notifications)
                )
                if notifications and self._notification_sink and not stale
                else 0
            )
            return AppliedRecognition(
                status=status,
                event_ids=tuple(event_ids),
                notifications=tuple(notifications),
                notifications_enqueued=enqueued,
            )

    def _apply_outage(
        self,
        monitor: CodexResetMonitor,
        post: CodexResetPost,
        rec: Recognition,
        notifications: list[NotificationIntent],
    ) -> None:
        if rec.outage == "outage":
            post.outage = {"kind": "outage", "recovered_at": None, "reset_event_id": None}
        previous = self._session.scalar(
            select(CodexResetPost)
            .where(
                CodexResetPost.owner_id == monitor.owner_id,
                CodexResetPost.monitor_id == monitor.id,
                CodexResetPost.id != post.id,
                CodexResetPost.outage.is_not(None),
                CodexResetPost.published_at >= post.published_at - OUTAGE_WINDOW,
                CodexResetPost.published_at <= post.published_at,
            )
            .order_by(CodexResetPost.published_at.desc())
            .limit(1)
        )
        if previous and previous.outage:
            patch = dict(previous.outage)
            if rec.outage == "recovery" and not patch.get("recovered_at"):
                patch["recovered_at"] = post.published_at.isoformat()
            announced = next((n for n in notifications if n.action == "announce"), None)
            if announced and not patch.get("reset_event_id"):
                patch["reset_event_id"] = announced.event_id
            previous.outage = patch

    def _post_view(self, row: CodexResetPost, event_ids: tuple[str, ...] = ()) -> ResetPostView:
        return ResetPostView(
            id=row.id,
            external_id=row.external_id,
            published_at=row.published_at,
            text=str(row.source_input["text"]),
            translation_zh=row.translation_zh,
            url=str(row.source_input["url"]),
            context=tuple(ContextPost.model_validate(c) for c in row.context),
            processed_at=row.processed_at,
            needs_review=row.needs_review,
            reviewed=row.reviewed,
            review_version=row.review_version,
            failure_count=row.failure_count,
            failure_code=row.failure_code,
            event_ids=event_ids,
        )

    def list_posts(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        filter_key: Literal["all", "relevant", "pending", "review"] = "review",
        page: int = 1,
    ) -> tuple[ResetPostView, ...]:
        if not 1 <= page <= 1000:
            raise ApplicationError("invalid_codex_input")
        with self._session.begin():
            self._monitor(owner_id, monitor_id)
            stmt = select(CodexResetPost).where(
                CodexResetPost.owner_id == owner_id, CodexResetPost.monitor_id == monitor_id
            )
            if filter_key == "review":
                stmt = stmt.where(
                    CodexResetPost.needs_review.is_(True), CodexResetPost.reviewed.is_(False)
                )
            elif filter_key == "pending":
                stmt = stmt.where(CodexResetPost.processed_at.is_(None))
            elif filter_key == "relevant":
                stmt = stmt.where(CodexResetPost.activity.is_not(None))
            rows = self._session.scalars(
                stmt.order_by(CodexResetPost.published_at.desc(), CodexResetPost.external_id.desc())
                .limit(50)
                .offset((page - 1) * 50)
            ).all()
            return tuple(
                self._post_view(row, tuple((row.activity or {}).get("event_ids", [])))
                for row in rows
            )

    def _existing_review(
        self, monitor: CodexResetMonitor, review: ReviewInput, fingerprint: bytes
    ) -> CodexResetReview | None:
        row = self._session.scalar(
            select(CodexResetReview).where(
                CodexResetReview.owner_id == monitor.owner_id,
                CodexResetReview.monitor_id == monitor.id,
                CodexResetReview.operation_id == review.operation_id,
            )
        )
        if row is not None and row.input_fingerprint != fingerprint:
            raise ApplicationError(
                "codex_version_conflict", context={"reason": "operation_id_reused"}
            )
        return row

    @staticmethod
    def _gap_view(row: CodexResetScanGap, monitor: CodexResetMonitor) -> ScanGapView:
        return ScanGapView(
            id=row.id,
            configuration_version=row.configuration_version,
            monitor_revision=monitor.revision,
            query=row.query,
            has_resume_token=row.next_token is not None,
            stop_at_id=row.stop_at_id,
            before_id=row.before_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            state=row.state,
            failure_code=row.failure_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_gaps(self, *, owner_id: UUID, monitor_id: UUID) -> tuple[ScanGapView, ...]:
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id)
            rows = self._session.scalars(
                select(CodexResetScanGap)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state != "complete",
                )
                .order_by(CodexResetScanGap.created_at, CodexResetScanGap.id)
                .limit(100)
            ).all()
            return tuple(self._gap_view(row, monitor) for row in rows)

    def resolve_gap(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        gap_id: UUID,
        action: Literal["retry", "acknowledge"],
        review: ReviewInput,
    ) -> ScanGapView:
        fingerprint = _fingerprint(
            {"gap_id": str(gap_id), "action": action, "review": review.model_dump(mode="json")}
        )
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            existing = self._existing_review(monitor, review, fingerprint)
            if existing:
                return ScanGapView.model_validate(existing.after)
            row = self._session.get(CodexResetScanGap, gap_id)
            if row is None or row.owner_id != owner_id or row.monitor_id != monitor_id:
                raise ApplicationError("resource_not_found")
            if monitor.revision != review.expected_revision or row.state == "complete":
                raise ApplicationError("codex_version_conflict")
            if action == "retry" and row.configuration_version != monitor.configuration_version:
                raise ApplicationError("codex_version_conflict")
            before = self._gap_view(row, monitor).model_dump(mode="json")
            row.state = "pending" if action == "retry" else "held"
            row.failure_code = None if action == "retry" else "operator_acknowledged_gap"
            row.updated_at = aware(self._clock())
            monitor.revision += 1
            monitor.scan_revision += 1
            # Acknowledgement allows known posts to proceed but never proves missing coverage.
            monitor.last_verified_at = None
            after = self._gap_view(row, monitor)
            self._save_review(
                monitor,
                review,
                fingerprint,
                entity_kind="gap",
                entity_id=str(gap_id),
                action=action,
                before=before,
                after=after.model_dump(mode="json"),
            )
            return after

    def _save_review(
        self,
        monitor: CodexResetMonitor,
        review: ReviewInput,
        fingerprint: bytes,
        *,
        entity_kind: str,
        entity_id: str,
        action: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        accept_audit_in_transaction(
            self._session,
            owner_id=monitor.owner_id,
            operation_id=review.operation_id,
            action=f"codex_reset.{entity_kind}.{action}",
            target_ref=f"codex-reset:{monitor.id}:{entity_kind}:{entity_id}",
            reason=review.reason,
            payload={"input_fingerprint": fingerprint.hex()},
            now=aware(self._clock()),
            before_state=before,
        )
        self._session.add(
            CodexResetReview(
                id=uuid4(),
                owner_id=monitor.owner_id,
                monitor_id=monitor.id,
                operation_id=review.operation_id,
                input_fingerprint=fingerprint,
                entity_kind=entity_kind,
                entity_id=entity_id,
                action=action,
                actor=review.actor,
                reason=review.reason,
                before=before,
                after=after,
                created_at=aware(self._clock()),
            )
        )
        monitor.projection_epoch += 1
        monitor.updated_at = aware(self._clock())
        complete_audit_in_transaction(
            self._session,
            owner_id=monitor.owner_id,
            operation_id=review.operation_id,
            after_state=after,
            now=aware(self._clock()),
        )

    def resolve_post(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        post_id: UUID,
        action: Literal["skip", "reviewed", "retry"],
        review: ReviewInput,
    ) -> ResetPostView:
        fingerprint = _fingerprint(
            {"entity_id": str(post_id), "action": action, "review": review.model_dump(mode="json")}
        )
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            existing = self._existing_review(monitor, review, fingerprint)
            if existing:
                return ResetPostView.model_validate(existing.after)
            row = self._session.scalar(
                select(CodexResetPost)
                .where(
                    CodexResetPost.id == post_id,
                    CodexResetPost.owner_id == owner_id,
                    CodexResetPost.monitor_id == monitor_id,
                )
                .with_for_update()
            )
            if row is None:
                raise ApplicationError("resource_not_found")
            if row.review_version != review.expected_revision or (
                action in {"skip", "retry"} and row.processed_at is not None
            ):
                raise ApplicationError("codex_version_conflict")
            if action == "reviewed" and row.processed_at is None:
                raise ApplicationError("invalid_codex_input")
            if action == "retry" and not row.needs_review:
                raise ApplicationError("invalid_codex_input")
            before = self._post_view(row).model_dump(mode="json")
            if action == "skip":
                row.processed_at, row.skipped, row.needs_review = aware(self._clock()), True, False
                row.failure_code = None
            if action == "retry":
                row.failure_code, row.needs_review, row.reviewed = None, False, False
                monitor.projection_epoch += 1
                monitor.updated_at = aware(self._clock())
            else:
                row.reviewed = True
            row.review_version += 1
            after = self._post_view(row)
            self._save_review(
                monitor,
                review,
                fingerprint,
                entity_kind="post",
                entity_id=str(post_id),
                action=action,
                before=before,
                after=after.model_dump(mode="json"),
            )
            return after

    def update_event(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        event_id: str,
        patch: EventPatch,
        review: ReviewInput,
    ) -> ResetEventView:
        fingerprint = _fingerprint(
            {
                "entity_id": event_id,
                "patch": patch.model_dump(mode="json", exclude_unset=True),
                "review": review.model_dump(mode="json"),
            }
        )
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            existing = self._existing_review(monitor, review, fingerprint)
            if existing:
                return ResetEventView.model_validate(existing.after)
            row = self._session.get(CodexResetEvent, (owner_id, monitor_id, event_id))
            if row is None:
                raise ApplicationError("resource_not_found")
            if row.revision != review.expected_revision:
                raise ApplicationError("codex_version_conflict")
            now = aware(self._clock())
            before = self._event_view(row, now=now).model_dump(mode="json")
            fields = patch.model_fields_set
            if patch.kind:
                row.kind, row.kind_explicit = patch.kind, True
            if patch.status:
                row.status, row.in_progress = patch.status, False
                if patch.status == "announced":
                    row.confirmed_at, row.occurred_on, row.confirmation_basis = None, None, None
            if "schedule" in fields:
                if patch.schedule is not None:
                    start, end = aware(patch.schedule.starts_at), aware(patch.schedule.ends_at)
                    if end < start:
                        raise ApplicationError("invalid_codex_input")
                    row.schedule = manual_schedule(patch.schedule).model_dump(mode="json")
                else:
                    row.schedule = None
            if patch.scope is not None:
                row.scope = patch.scope.model_dump(mode="json")
            if "confirmed_at" in fields and row.status == "confirmed":
                row.confirmed_at = aware(patch.confirmed_at) if patch.confirmed_at else None
            if "occurred_on" in fields and row.status == "confirmed":
                row.occurred_on = patch.occurred_on
            if (
                "confirmation_basis" in fields
                and row.status == "confirmed"
                and row.confirmation_basis != "source_post"
            ):
                if patch.confirmation_basis == "source_post":
                    raise ApplicationError("invalid_codex_input")
                # An account review cannot replace an existing official confirmation.
                row.confirmation_basis = patch.confirmation_basis
            if row.status == "confirmed" and row.confirmation_basis is None:
                row.confirmation_basis = "receipt_review"
            if row.status == "confirmed":
                row.estimate = None
            elif "schedule" in fields or patch.status == "announced":
                row.estimate = estimate_for(
                    Schedule.model_validate(row.schedule) if row.schedule else None, row.created_at
                ).model_dump(mode="json")
            if patch.withdrawn is not None:
                row.withdrawn = patch.withdrawn
            row.revision += 1
            row.manual_version += 1
            row.updated_at = now
            after = self._event_view(row, now=now)
            self._save_review(
                monitor,
                review,
                fingerprint,
                entity_kind="event",
                entity_id=event_id,
                action="update",
                before=before,
                after=after.model_dump(mode="json"),
            )
            return after

    def review_receipt(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        event_id: str,
        review: ReviewInput,
        occurred_on: date | None = None,
    ) -> ResetEventView:
        return self.update_event(
            owner_id=owner_id,
            monitor_id=monitor_id,
            event_id=event_id,
            review=review,
            patch=EventPatch(
                status="confirmed", confirmation_basis="receipt_review", occurred_on=occurred_on
            ),
        )

    def relink_post(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        post_id: UUID,
        from_event_id: str,
        to_event_id: str | None,
        target_expected_revision: int | None,
        review: ReviewInput,
    ) -> ResetPostView:
        fingerprint = _fingerprint(
            {
                "post_id": str(post_id),
                "from": from_event_id,
                "to": to_event_id,
                "target_revision": target_expected_revision,
                "review": review.model_dump(mode="json"),
            }
        )
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            existing = self._existing_review(monitor, review, fingerprint)
            if existing:
                return ResetPostView.model_validate(existing.after)
            source = self._session.get(CodexResetEvent, (owner_id, monitor_id, from_event_id))
            target = (
                self._session.get(CodexResetEvent, (owner_id, monitor_id, to_event_id))
                if to_event_id
                else None
            )
            link = self._session.get(
                CodexResetEventPost, (owner_id, monitor_id, from_event_id, post_id)
            )
            post = self._session.get(CodexResetPost, post_id)
            if (
                source is None
                or link is None
                or post is None
                or post.owner_id != owner_id
                or post.monitor_id != monitor_id
                or (to_event_id and target is None)
            ):
                raise ApplicationError("resource_not_found")
            if source.revision != review.expected_revision or (
                target and target.revision != target_expected_revision
            ):
                raise ApplicationError("codex_version_conflict")
            before = self._post_view(
                post, tuple((post.activity or {}).get("event_ids", []))
            ).model_dump(mode="json")
            if to_event_id != from_event_id:
                if (
                    target
                    and self._session.get(
                        CodexResetEventPost, (owner_id, monitor_id, target.id, post_id)
                    )
                    is None
                ):
                    self._session.add(
                        CodexResetEventPost(
                            owner_id=owner_id,
                            monitor_id=monitor_id,
                            event_id=target.id,
                            post_id=post_id,
                            action=link.action,
                            stage=link.stage,
                            excerpt=link.excerpt,
                            excerpt_zh=link.excerpt_zh,
                        )
                    )
                self._session.delete(link)
                self._session.flush()
                ids = tuple(
                    self._session.scalars(
                        select(CodexResetEventPost.event_id)
                        .where(
                            CodexResetEventPost.owner_id == owner_id,
                            CodexResetEventPost.monitor_id == monitor_id,
                            CodexResetEventPost.post_id == post_id,
                        )
                        .order_by(CodexResetEventPost.event_id)
                    ).all()
                )
                post.activity = dict(post.activity or {}, event_ids=list(ids))
                for event in (source, target):
                    if event:
                        event.revision += 1
                        event.manual_version += 1
                        event.updated_at = aware(self._clock())
            after = self._post_view(post, tuple((post.activity or {}).get("event_ids", [])))
            self._save_review(
                monitor,
                review,
                fingerprint,
                entity_kind="post",
                entity_id=str(post_id),
                action="relink",
                before=before,
                after=after.model_dump(mode="json"),
            )
            return after

    def notification_intents(
        self, *, owner_id: UUID, monitor_id: UUID, now: datetime | None = None
    ) -> tuple[NotificationIntent, ...]:
        current = aware(now or self._clock())
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id)
            if not monitor.enabled:
                return ()
            rows = self._session.scalars(
                select(CodexResetRecognition)
                .join(CodexResetPost, CodexResetPost.id == CodexResetRecognition.post_id)
                .where(
                    CodexResetRecognition.owner_id == owner_id,
                    CodexResetRecognition.monitor_id == monitor_id,
                    CodexResetRecognition.status.in_(("applied", "held")),
                    CodexResetPost.published_at > current - 36 * HOUR,
                )
                .order_by(CodexResetPost.published_at, CodexResetPost.external_id)
            ).all()
            return tuple(
                NotificationIntent.model_validate(intent)
                for row in rows
                for intent in row.notifications
            )

    def enqueue_pending_notifications(self, *, owner_id: UUID, monitor_id: UUID) -> int:
        """Replay persisted intents through the same idempotent notification ledger.

        A previous tick can have committed its recognition while no target was
        available. Recovery reads that receipt and never repeats recognition.
        """
        if self._notification_sink is None:
            return 0
        current = aware(self._clock())
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            if not monitor.enabled or (
                self._execution_guard is not None and not self._execution_guard(self._session)
            ):
                return 0
            rows = self._session.scalars(
                select(CodexResetRecognition)
                .join(CodexResetPost, CodexResetPost.id == CodexResetRecognition.post_id)
                .where(
                    CodexResetRecognition.owner_id == owner_id,
                    CodexResetRecognition.monitor_id == monitor_id,
                    CodexResetRecognition.status.in_(("applied", "held")),
                    CodexResetPost.published_at > current - 36 * HOUR,
                )
                .order_by(CodexResetPost.published_at, CodexResetPost.external_id)
            )
            accepted = 0
            for row in rows:
                intents = tuple(
                    NotificationIntent.model_validate(item) for item in row.notifications
                )
                for offset in range(0, len(intents), 20):
                    if self._execution_guard is not None and not self._execution_guard(
                        self._session
                    ):
                        raise ApplicationError("codex_version_conflict")
                    accepted += self._notification_sink(
                        self._session, owner_id, monitor_id, intents[offset : offset + 20]
                    )
            return accepted

    def verify_if_complete(
        self, *, owner_id: UUID, monitor_id: UUID, collected_at: datetime
    ) -> bool:
        with self._session.begin():
            monitor = self._monitor(owner_id, monitor_id, lock=True)
            pending, review, gaps = self._counts(owner_id, monitor_id)
            complete = (
                monitor.enabled
                and monitor.last_collected_at is not None
                and monitor.last_collected_at >= aware(collected_at)
                and not (pending or review or gaps)
                and (self._execution_guard is None or self._execution_guard(self._session))
            )
            if complete:
                monitor.last_verified_at = aware(collected_at)
            return complete

    def _counts(self, owner_id: UUID, monitor_id: UUID) -> tuple[int, int, int]:
        counts = self._session.execute(
            select(
                func.count().filter(CodexResetPost.processed_at.is_(None)),
                func.count().filter(
                    CodexResetPost.needs_review.is_(True), CodexResetPost.reviewed.is_(False)
                ),
            ).where(CodexResetPost.owner_id == owner_id, CodexResetPost.monitor_id == monitor_id)
        ).one()
        gaps = (
            self._session.scalar(
                select(func.count())
                .select_from(CodexResetScanGap)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state != "complete",
                )
            )
            or 0
        )
        return int(counts[0]), int(counts[1]), int(gaps)

    def snapshot(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        recent: bool = False,
        include_withdrawn: bool = False,
        now: datetime | None = None,
    ) -> ResetSnapshot:
        current = aware(now or self._clock())
        today = current.astimezone(BEIJING).date()
        cutoff = (
            datetime.combine(today - timedelta(days=7), datetime.min.time(), BEIJING).astimezone(
                UTC
            )
            if recent
            else None
        )
        with self._session.begin():
            # All writes take the monitor lock; SHARE gives one coherent committed projection.
            monitor = self._session.scalar(
                select(CodexResetMonitor)
                .where(CodexResetMonitor.owner_id == owner_id, CodexResetMonitor.id == monitor_id)
                .with_for_update(read=True)
            )
            if monitor is None:
                raise ApplicationError("resource_not_found")
            pending, review, gaps = self._counts(owner_id, monitor_id)
            verified = monitor.last_verified_at
            age = current - verified if verified else None
            health_status = (
                "unknown"
                if age is None
                else "attention"
                if gaps or review or age > 3 * HOUR
                else "delayed"
                if pending or age > timedelta(minutes=40)
                else "healthy"
            )
            health = ResetHealth.model_validate(
                {
                    "status": health_status,
                    "enabled": monitor.enabled,
                    "last_attempt_at": monitor.last_attempt_at,
                    "last_collected_at": monitor.last_collected_at,
                    "last_verified_at": verified,
                    "pending_count": pending,
                    "review_count": review,
                    "held_window_count": gaps,
                }
            )
            event_rows = self._session.scalars(
                select(CodexResetEvent)
                .where(
                    CodexResetEvent.owner_id == owner_id, CodexResetEvent.monitor_id == monitor_id
                )
                .order_by(CodexResetEvent.updated_at.desc(), CodexResetEvent.id)
            ).all()
            posts = {
                p.id: p
                for p in self._session.scalars(
                    select(CodexResetPost).where(
                        CodexResetPost.owner_id == owner_id, CodexResetPost.monitor_id == monitor_id
                    )
                ).all()
            }
            links = self._session.scalars(
                select(CodexResetEventPost).where(
                    CodexResetEventPost.owner_id == owner_id,
                    CodexResetEventPost.monitor_id == monitor_id,
                )
            ).all()
            by_event: dict[str, list[ResetEventPost]] = {}
            for link in links:
                p = posts[link.post_id]
                by_event.setdefault(link.event_id, []).append(
                    ResetEventPost.model_validate(
                        {
                            "post_id": p.id,
                            "external_id": p.external_id,
                            "published_at": p.published_at,
                            "action": link.action,
                            "stage": link.stage,
                            "excerpt": link.excerpt,
                            "excerpt_zh": link.excerpt_zh,
                            "original_text": p.source_input["text"],
                            "translation_zh": p.translation_zh,
                            "url": p.source_input["url"],
                            "context": p.context,
                        }
                    )
                )
            events = []
            for row in event_rows:
                if row.withdrawn and not include_withdrawn:
                    continue
                event = self._event_view(
                    row,
                    now=current,
                    posts=tuple(
                        sorted(
                            by_event.get(row.id, []),
                            key=lambda p: (p.published_at, int(p.external_id)),
                            reverse=True,
                        )
                    ),
                )
                if (
                    cutoff is None
                    or event.updated_at >= cutoff
                    or event.presentation_status
                    in {"announced", "in_progress", "expired_unconfirmed"}
                ):
                    events.append(event)
            activities = tuple(
                self._post_view(p, tuple((p.activity or {}).get("event_ids", [])))
                for p in sorted(
                    posts.values(), key=lambda p: (p.published_at, int(p.external_id)), reverse=True
                )
                if p.activity and (cutoff is None or p.published_at >= cutoff)
            )
            outage_post = next(
                (
                    p
                    for p in sorted(
                        posts.values(), key=lambda p: (p.published_at, p.external_id), reverse=True
                    )
                    if p.outage and current - OUTAGE_WINDOW <= p.published_at <= current
                ),
                None,
            )
            outage = (
                OutageView.model_validate(
                    {
                        "post_id": outage_post.id,
                        "published_at": outage_post.published_at,
                        "original_text": outage_post.source_input["text"],
                        "translation_zh": outage_post.translation_zh,
                        "recovered_at": (outage_post.outage or {}).get("recovered_at"),
                        "reset_event_id": (outage_post.outage or {}).get("reset_event_id"),
                        "url": outage_post.source_input["url"],
                    }
                )
                if outage_post
                else None
            )
            return self._build_snapshot(
                current=current,
                health=health,
                history_from=monitor.history_from,
                events=tuple(events),
                activities=activities,
                outage=outage,
            )

    def version_probe(
        self, *, owner_id: UUID, monitor_id: UUID, now: datetime | None = None
    ) -> ResetVersionView:
        current = aware(now or self._clock())
        with self._session.begin():
            monitor = self._session.scalar(
                select(CodexResetMonitor)
                .where(CodexResetMonitor.owner_id == owner_id, CodexResetMonitor.id == monitor_id)
                .with_for_update(read=True)
            )
            if monitor is None:
                raise ApplicationError("resource_not_found")
            pending, review, gaps = self._counts(owner_id, monitor_id)
            verified = monitor.last_verified_at
            age = current - verified if verified else None
            status = (
                "unknown"
                if age is None
                else "attention"
                if gaps or review or age > 3 * HOUR
                else "delayed"
                if pending or age > timedelta(minutes=40)
                else "healthy"
            )
            health = ResetHealth.model_validate(
                {
                    "status": status,
                    "enabled": monitor.enabled,
                    "last_attempt_at": monitor.last_attempt_at,
                    "last_collected_at": monitor.last_collected_at,
                    "last_verified_at": verified,
                    "pending_count": pending,
                    "review_count": review,
                    "held_window_count": gaps,
                }
            )
            rows = self._session.scalars(
                select(CodexResetEvent)
                .where(
                    CodexResetEvent.owner_id == owner_id,
                    CodexResetEvent.monitor_id == monitor_id,
                    CodexResetEvent.withdrawn.is_(False),
                )
                .order_by(CodexResetEvent.updated_at.desc(), CodexResetEvent.id)
            ).all()
            events = tuple(self._event_view(row, now=current) for row in rows)
            outage_post = self._session.scalar(
                select(CodexResetPost)
                .where(
                    CodexResetPost.owner_id == owner_id,
                    CodexResetPost.monitor_id == monitor_id,
                    CodexResetPost.outage.is_not(None),
                    CodexResetPost.published_at >= current - OUTAGE_WINDOW,
                    CodexResetPost.published_at <= current,
                )
                .order_by(CodexResetPost.published_at.desc(), CodexResetPost.external_id.desc())
                .limit(1)
            )
            outage = (
                OutageView.model_validate(
                    {
                        "post_id": outage_post.id,
                        "published_at": outage_post.published_at,
                        "original_text": outage_post.source_input["text"],
                        "translation_zh": outage_post.translation_zh,
                        "recovered_at": (outage_post.outage or {}).get("recovered_at"),
                        "reset_event_id": (outage_post.outage or {}).get("reset_event_id"),
                        "url": outage_post.source_input["url"],
                    }
                )
                if outage_post
                else None
            )
            return ResetVersionView(
                version=self._version(events, outage, health),
                checked_at=verified,
                today=current.astimezone(BEIJING).date(),
            )

    @staticmethod
    def _version(
        events: tuple[ResetEventView, ...], outage: OutageView | None, health: ResetHealth
    ) -> str:
        return _fingerprint(
            {
                "events": [(e.id, e.revision, e.presentation_status) for e in events],
                "outage": outage.model_dump(mode="json") if outage else None,
                "health": [
                    health.status,
                    health.pending_count,
                    health.review_count,
                    health.held_window_count,
                ],
            }
        )[:8].hex()

    @staticmethod
    def _build_snapshot(
        *,
        current: datetime,
        health: ResetHealth,
        history_from: datetime | None,
        events: tuple[ResetEventView, ...],
        activities: tuple[ResetPostView, ...],
        outage: OutageView | None,
    ) -> ResetSnapshot:
        today = current.astimezone(BEIJING).date()
        calendar: list[CalendarMark] = []
        rounds: list[datetime] = []
        landed: list[tuple[datetime, ResetEventView]] = []
        for e in events:
            if e.withdrawn:
                continue
            state: Literal["confirmed", "likely", "pending"] = (
                "confirmed"
                if e.status == "confirmed"
                else "likely"
                if e.presentation_status == "likely_completed"
                else "pending"
            )
            window = e.estimate or e.schedule
            moment = (
                datetime.combine(e.occurred_on, datetime.min.time(), BEIJING) + 12 * HOUR
                if e.occurred_on
                else e.confirmed_at or (window.starts_at if window else e.created_at)
            )
            day = moment.astimezone(BEIJING).date()
            label = (
                "待生效"
                if state == "pending"
                else "发重置卡"
                if e.kind == "reset_credit"
                else "额度重置"
                if e.kind_explicit
                else "重置确认"
            )
            calendar.append(
                CalendarMark(date=day, event_id=e.id, kind=e.kind, state=state, label=label)
            )
            if state != "pending":
                landed.append((moment, e))
                if e.kind == "direct_reset" and current - timedelta(days=90) <= moment <= current:
                    rounds.append(moment)
        rounds.sort()
        intervals = [(b - a).total_seconds() / 86400 for a, b in pairwise(rounds)]
        in_window = [
            m
            for m in calendar
            if m.state != "pending" and today - timedelta(days=90) < m.date <= today
        ]
        reset_days = [
            m.date
            for m in calendar
            if m.kind == "direct_reset" and m.state == "confirmed" and m.date <= today
        ]
        stats = ResetStatistics(
            resets_90=sum(m.kind == "direct_reset" for m in in_window),
            credits_90=sum(m.kind == "reset_credit" for m in in_window),
            median_interval_days=round(statistics.median(intervals), 1) if intervals else None,
            last_reset_date=max(reset_days) if reset_days else None,
        )
        version = CodexResetService._version(events, outage, health)
        return ResetSnapshot(
            today=today,
            checked_at=health.last_verified_at,
            history_from=history_from,
            events=events,
            activities=activities,
            monitor=health,
            outage=outage,
            calendar=tuple(calendar),
            statistics=stats,
            current=next(
                (
                    e
                    for e in events
                    if e.presentation_status in {"announced", "in_progress", "expired_unconfirmed"}
                ),
                None,
            ),
            last_landed=max(landed, key=lambda pair: pair[0])[1] if landed else None,
            confirm_minutes=tuple(
                e.confirmed_at.astimezone(BEIJING).hour * 60
                + e.confirmed_at.astimezone(BEIJING).minute
                for e in events
                if e.kind == "direct_reset"
                and e.confirmed_at
                and e.confirmation_basis == "source_post"
            ),
            version=version,
        )


def read_codex_operational_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> CodexOperationalHealth:
    """Metadata only; never creates configuration or reads a provider on GET."""
    if not session.in_transaction():
        raise RuntimeError("Codex operational health requires the caller transaction")
    monitor = session.scalar(
        select(CodexResetMonitor).where(CodexResetMonitor.owner_id == owner_id)
    )
    if monitor is None:
        return CodexOperationalHealth(configured=False, enabled=False)
    base = (
        CodexResetPost.owner_id == owner_id,
        CodexResetPost.monitor_id == monitor.id,
        CodexResetPost.configuration_version == monitor.configuration_version,
        CodexResetPost.skipped.is_(False),
    )
    oldest = session.scalar(
        select(func.min(CodexResetPost.collected_at)).where(
            *base,
            CodexResetPost.processed_at.is_(None),
            CodexResetPost.collected_at <= aware(now) - timedelta(hours=1),
        )
    )
    held = session.scalar(
        select(func.count())
        .select_from(CodexResetPost)
        .where(
            *base,
            CodexResetPost.needs_review.is_(True),
            CodexResetPost.reviewed.is_(False),
            or_(
                and_(
                    CodexResetPost.processed_at > aware(now) - timedelta(hours=48),
                    CodexResetPost.processed_at <= aware(now),
                ),
                and_(
                    CodexResetPost.processed_at.is_(None),
                    CodexResetPost.collected_at > aware(now) - timedelta(hours=48),
                    CodexResetPost.collected_at <= aware(now),
                ),
            ),
        )
    )
    return CodexOperationalHealth(
        configured=True,
        enabled=monitor.enabled,
        monitor_id=monitor.id,
        stuck_oldest_collected_at=oldest,
        held_unreviewed_count=held or 0,
    )
