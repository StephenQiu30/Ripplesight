"""Bounded, persistent scan orchestration over official source-domain contracts.

AIHOT monitor/scan.ts semantic port; MIT notice in THIRD_PARTY_NOTICES.md.
No provider, credentials, model SDK or delivery transport is created here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.errors import ApplicationError
from monitors.codex_models import CodexResetScanGap
from monitors.codex_schemas import ContextPost, ResetPostInput, ScanAuthorization, ScanResult
from monitors.codex_services import CodexResetService
from monitors.codex_time import aware
from sources.contracts import (
    SearchRequest,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceSort,
)


class ResetSource(Protocol):
    def fetch_page(self, request: SearchRequest) -> SourcePage: ...


class ResetContextSource(Protocol):
    def context_for(self, post: SourcePost, *, max_reply_depth: int) -> tuple[ContextPost, ...]: ...


class CodexResetScanService:
    def __init__(
        self,
        session: Session,
        *,
        source: ResetSource | None = None,
        context_source: ResetContextSource | None = None,
        clock: Callable[[], datetime] | None = None,
        execution_guard: Callable[[Session], bool] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self._session = session
        self._source = source
        self._context_source = context_source
        self._clock = clock or (lambda: datetime.now(UTC))
        self._execution_guard = execution_guard
        self._cancelled = cancelled or (lambda: False)
        self._service = CodexResetService(
            session, clock=self._clock, execution_guard=execution_guard
        )

    def collect(
        self,
        *,
        owner_id: UUID,
        monitor_id: UUID,
        authorization: ScanAuthorization | None = None,
        lookback_hours: int | None = None,
        force: bool = False,
    ) -> ScanResult:
        if lookback_hours is not None and not 1 <= lookback_hours <= 168:
            raise ApplicationError("invalid_codex_input")
        with self._session.begin():
            monitor = self._service._monitor(owner_id, monitor_id)
            configuration = self._service._configuration(monitor)
            if self._cancelled() or (
                self._execution_guard is not None and not self._execution_guard(self._session)
            ):
                return ScanResult(status="blocked", reason="execution_not_current")
            if not monitor.enabled:
                return ScanResult(status="blocked", reason="monitor_disabled")
            if authorization is None or not authorization.allowed:
                return ScanResult(status="blocked", reason="source_authorization_required")
            if (
                self._source is None
                or configuration.connection_id is None
                or configuration.author_external_id is None
            ):
                return ScanResult(status="blocked", reason="official_source_unavailable")
            now = aware(self._clock())
            every = (
                configuration.hot_interval_seconds
                if monitor.hot_until and monitor.hot_until > now
                else configuration.normal_interval_seconds
            )
            if (
                not force
                and lookback_hours is None
                and monitor.last_attempt_at
                and now - monitor.last_attempt_at < timedelta(seconds=every - 30)
            ):
                return ScanResult(status="skipped", reason="not_due")
        bind = self._session.get_bind()
        if not isinstance(bind, Engine):
            raise RuntimeError("Codex scan requires an engine-owned session")
        # Session advisory lock survives commits, while network calls hold no SQL transaction.
        with bind.connect() as lock_connection:
            acquired = lock_connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": f"codex-reset:{owner_id}:{monitor_id}"},
            )
            lock_connection.commit()
            if not acquired:
                return ScanResult(status="skipped", reason="overlapping_scan")
            try:
                return self._collect_locked(owner_id, monitor_id, lookback_hours)
            finally:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": f"codex-reset:{owner_id}:{monitor_id}"},
                )
                lock_connection.commit()

    def _collect_locked(
        self, owner_id: UUID, monitor_id: UUID, lookback_hours: int | None
    ) -> ScanResult:
        now = aware(self._clock())
        with self._session.begin():
            monitor = self._service._monitor(owner_id, monitor_id, lock=True)
            if not monitor.enabled:
                return ScanResult(status="blocked", reason="monitor_disabled")
            if self._cancelled() or (
                self._execution_guard is not None and not self._execution_guard(self._session)
            ):
                return ScanResult(status="blocked", reason="execution_not_current")
            configuration = self._service._configuration(monitor)
            unknown_gaps = self._session.scalars(
                select(CodexResetScanGap)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state != "complete",
                    CodexResetScanGap.failure_code.in_(
                        ("source_request_running", "source_unknown", "context_unknown")
                    ),
                )
                .with_for_update()
            ).all()
            if unknown_gaps:
                for abandoned in unknown_gaps:
                    abandoned.state, abandoned.failure_code = "held", "source_unknown"
                    abandoned.updated_at = now
                return ScanResult(
                    status="blocked", reason="source_unknown", backlog=len(unknown_gaps)
                )
            monitor.last_attempt_at = now
            gap = CodexResetScanGap(
                id=uuid4(),
                owner_id=owner_id,
                monitor_id=monitor_id,
                configuration_version=monitor.configuration_version,
                query=f"from:{configuration.author}",
                stop_at_id=None if lookback_hours else monitor.since_id,
                starts_at=now - timedelta(hours=lookback_hours or 168),
                ends_at=now,
                state="pending",
                created_at=now,
                updated_at=now,
            )
            self._session.add(gap)
            self._session.flush()
            fresh_id = gap.id
        stored = pages = 0
        reason: str | None = None
        for _ in range(configuration.max_pages):
            added, state, failure = self._read_page(owner_id, monitor_id, fresh_id)
            stored += added
            pages += 1
            if state != "pending":
                reason = failure
                break
        with self._session.begin():
            older = self._session.scalars(
                select(CodexResetScanGap.id)
                .where(
                    CodexResetScanGap.owner_id == owner_id,
                    CodexResetScanGap.monitor_id == monitor_id,
                    CodexResetScanGap.state == "pending",
                )
                .order_by(CodexResetScanGap.created_at, CodexResetScanGap.id)
                .limit(configuration.max_pages)
            ).all()
        budget = configuration.max_pages
        for gap_id in older:
            while budget:
                added, state, failure = self._read_page(owner_id, monitor_id, gap_id)
                stored += added
                pages += 1
                budget -= 1
                if state != "pending":
                    reason = reason or failure
                    break
            if not budget:
                break
        with self._session.begin():
            monitor = self._service._monitor(owner_id, monitor_id, lock=True)
            backlog = (
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
            # Collected records a successful bounded collection, never a verified interpretation.
            if (
                reason is None
                and monitor.enabled
                and not self._cancelled()
                and (self._execution_guard is None or self._execution_guard(self._session))
            ):
                monitor.last_collected_at = now
        return ScanResult(
            status="partial" if reason or backlog else "collected",
            reason=reason,
            stored=stored,
            pages=pages,
            backlog=int(backlog),
        )

    def _read_page(
        self, owner_id: UUID, monitor_id: UUID, gap_id: UUID
    ) -> tuple[int, str, str | None]:
        if self._cancelled():
            self._hold_gap(owner_id, monitor_id, gap_id, "cancelled")
            return 0, "held", "cancelled"
        with self._session.begin():
            monitor = self._service._monitor(owner_id, monitor_id)
            configuration = self._service._configuration(monitor)
            gap = self._session.get(CodexResetScanGap, gap_id)
            if gap is None or gap.owner_id != owner_id or gap.monitor_id != monitor_id:
                raise ApplicationError("resource_not_found")
            if not monitor.enabled or gap.configuration_version != monitor.configuration_version:
                return 0, "held", "configuration_changed"
            if self._execution_guard is not None and not self._execution_guard(self._session):
                return 0, "held", "execution_not_current"
            request = SearchRequest(
                source_key="x",
                query=gap.query,
                page_size=100,
                page_token=gap.next_token,
                starts_at=aware(gap.starts_at) if gap.starts_at else None,
                ends_at=aware(gap.ends_at) if gap.ends_at else None,
                sort=SourceSort.LATEST,
            )
            expected_scan_revision = monitor.scan_revision
            stop_at = gap.stop_at_id
            gap.failure_code = "source_request_running"
            gap.updated_at = aware(self._clock())
        if self._source is None:
            return 0, "held", "official_source_unavailable"
        try:
            page = self._source.fetch_page(request)
        except Exception as error:
            source_failure = (
                "source_unknown" if getattr(error, "unknown", False) else "source_failed"
            )
            self._hold_gap(owner_id, monitor_id, gap_id, source_failure)
            return 0, "held", source_failure
        if page.source_key != "x" or page.capability != SourceCapability.SEARCH:
            self._hold_gap(owner_id, monitor_id, gap_id, "source_protocol_error")
            return 0, "held", "source_protocol_error"
        converted: list[ResetPostInput] = []
        observed_ids: list[str] = []
        reached_known = False
        context_error: str | None = None
        for item in page.items:
            if not isinstance(item, SourcePost) or not re_valid_id(item.external_id):
                context_error = "source_protocol_error"
                break
            observed_ids.append(item.external_id)
            if stop_at and int(item.external_id) <= int(stop_at):
                reached_known = True
                continue
            if item.repost_external_id:
                continue
            if (
                item.author_external_id != configuration.author_external_id
                or item.published_at is None
                or not item.text
                or item.text_scope != "full"
                or (request.starts_at is not None and item.published_at < request.starts_at)
                or (request.ends_at is not None and item.published_at > request.ends_at)
            ):
                context_error = "source_evidence_incomplete"
                break
            context: tuple[ContextPost, ...] = ()
            if item.parent_external_id or item.quote_external_id:
                if self._context_source is None:
                    context_error = "context_unavailable"
                    break
                try:
                    context = self._context_source.context_for(item, max_reply_depth=2)
                    ids = {(c.relation, c.id) for c in context}
                    if (
                        len(context) > 4
                        or (
                            item.parent_external_id
                            and ("reply", item.parent_external_id) not in ids
                        )
                        or (item.quote_external_id and ("quote", item.quote_external_id) not in ids)
                    ):
                        raise ValueError("incomplete context")
                except Exception as error:
                    context_error = (
                        "context_unknown"
                        if getattr(error, "unknown", False)
                        else "context_unavailable"
                    )
                    break
            converted.append(
                ResetPostInput(
                    external_id=item.external_id,
                    published_at=item.published_at,
                    text=item.text,
                    url=f"https://x.com/thsottiaux/status/{item.external_id}",
                    context=context,
                    origin="lookback" if stop_at is None else "live",
                )
            )
        failure = context_error or (
            page.stop_reason.value
            if page.state in {SourcePageState.PARTIAL, SourcePageState.STOPPED} and page.stop_reason
            else None
        )
        next_token = None if reached_known else page.next_page_token
        if request.page_token is not None and next_token == request.page_token:
            failure = "cursor_loop"
        if page.state == SourcePageState.MORE and not next_token and not reached_known:
            failure = "source_protocol_error"
        try:
            with self._session.begin():
                monitor = self._service._monitor(owner_id, monitor_id, lock=True)
                gap = self._session.get(CodexResetScanGap, gap_id)
                if gap is None:
                    raise ApplicationError("resource_not_found")
                if (
                    not monitor.enabled
                    or monitor.configuration_version != gap.configuration_version
                    or monitor.scan_revision != expected_scan_revision
                    or self._cancelled()
                    or (
                        self._execution_guard is not None
                        and not self._execution_guard(self._session)
                    )
                ):
                    gap.state, gap.failure_code = "held", "configuration_changed"
                    return 0, "held", "configuration_changed"
                stored = sum(self._service._store_post(monitor, p) for p in converted)
                # Stored evidence and its exact cursor transition are one transaction.
                self._session.flush()
                if observed_ids and not failure:
                    gap.before_id = min(
                        [*observed_ids, *([gap.before_id] if gap.before_id else [])], key=int
                    )
                    if gap.stop_at_id is not None or monitor.since_id is None:
                        monitor.since_id = max(
                            [*observed_ids, *([monitor.since_id] if monitor.since_id else [])],
                            key=int,
                        )
                gap.state = "held" if failure else "pending" if next_token else "complete"
                gap.failure_code = failure
                if not failure:
                    gap.next_token = next_token
                gap.updated_at = aware(self._clock())
                monitor.scan_revision += 1
                return stored, gap.state, failure
        except ApplicationError:
            self._hold_gap(owner_id, monitor_id, gap_id, "source_evidence_changed")
            return 0, "held", "source_evidence_changed"

    def _hold_gap(self, owner_id: UUID, monitor_id: UUID, gap_id: UUID, code: str) -> None:
        with self._session.begin():
            self._service._monitor(owner_id, monitor_id, lock=True)
            if self._execution_guard is not None and not self._execution_guard(self._session):
                return
            gap = self._session.get(CodexResetScanGap, gap_id)
            if gap:
                gap.state, gap.failure_code, gap.updated_at = "held", code, aware(self._clock())


def re_valid_id(value: str) -> bool:
    return value.isascii() and value.isdigit() and 1 <= len(value) <= 19
