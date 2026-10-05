from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_services import freeze_ai_job_scope_in_transaction
from ai.schemas import AiCallError
from ai.services import AiService, create_ai_client
from content.editorial_reading import require_editorial_content_permission_in_transaction
from content.schemas import EventContentReadReference
from core.config import Settings
from core.errors import ApplicationError
from db.owners import list_owner_ids_in_transaction
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
)
from jobs.services import JobService, load_job_execution_configuration
from publication.schemas import FrozenPublicationReference, ReportPublicationCandidate
from reports.edition_compose import (
    compose_edition,
    edition_prompt,
    edition_prompt_version,
    render_edition,
)
from reports.edition_models import ReportEdition, ReportEditionSchedule
from reports.edition_rules import (
    DailyIssue,
    EditionKind,
    compile_daily,
    compile_period,
    daily_memory,
    due_period_key,
    next_period_key,
    period_window,
    selection_from_snapshot,
)
from reports.edition_schemas import (
    EditionContentView,
    EditionCorrectionInput,
    EditionDetailView,
    EditionRequestInput,
    EditionSummaryView,
    EditionThemeView,
)

_NAMESPACE = UUID("4d4196dc-59d7-4d07-bb6b-b2cfdb214a91")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def _entries(record: ReportEdition) -> tuple[ReportPublicationCandidate, ...]:
    return tuple(ReportPublicationCandidate.model_validate(item) for item in record.input_snapshot)


def _references(record: ReportEdition) -> tuple[FrozenPublicationReference, ...]:
    return tuple(
        FrozenPublicationReference.model_validate(
            {field: getattr(item, field) for field in FrozenPublicationReference.model_fields}
        )
        for item in _entries(record)
    )


def _valid(
    session: Session, record: ReportEdition, now: datetime, *, lock_permissions: bool = True
) -> bool:
    from publication.reading import validate_report_candidates_in_transaction

    if record.kind != "daily" and record.input_snapshot:
        for dependency in record.input_snapshot[0].get("_daily_issues", []):
            daily = session.get(ReportEdition, UUID(dependency["id"]))
            latest = session.scalar(
                select(func.max(ReportEdition.revision)).where(
                    ReportEdition.owner_id == record.owner_id,
                    ReportEdition.kind == "daily",
                    ReportEdition.period_key == dependency["key"],
                )
            )
            if (
                daily is None
                or daily.owner_id != record.owner_id
                or daily.kind != "daily"
                or daily.revision != dependency["revision"]
                or daily.revision != latest
                or daily.status != "complete"
                or not _valid(session, daily, now, lock_permissions=lock_permissions)
            ):
                return False
    references = _references(record)
    try:
        for reference in references:
            require_editorial_content_permission_in_transaction(
                session,
                owner_id=record.owner_id,
                reference=EventContentReadReference(
                    content_id=reference.content_id, content_version_id=reference.content_version_id
                ),
                now=now,
                lock_policies=lock_permissions,
            )
    except ApplicationError:
        return False
    return validate_report_candidates_in_transaction(
        session, owner_id=record.owner_id, references=references, now=now
    ).valid


class EditionService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.session, self.clock = session, clock or (lambda: datetime.now(UTC))

    def _lock(self, owner: UUID, key: str) -> None:
        self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(f"edition:{owner}:{key}", 0)))
        )

    def _latest(self, owner: UUID, kind: str, key: str) -> ReportEdition | None:
        return self.session.scalar(
            select(ReportEdition)
            .where(
                ReportEdition.owner_id == owner,
                ReportEdition.kind == kind,
                ReportEdition.period_key == key,
            )
            .order_by(ReportEdition.revision.desc())
            .limit(1)
        )

    def _daily_issues(
        self,
        owner: UUID,
        *,
        start: datetime | None,
        end: datetime,
        now: datetime,
    ) -> tuple[tuple[DailyIssue, ...], list[dict[str, Any]]]:
        latest = select(ReportEdition.period_key, func.max(ReportEdition.revision).label("rev"))
        latest = latest.where(ReportEdition.owner_id == owner, ReportEdition.kind == "daily")
        versions = latest.group_by(ReportEdition.period_key).subquery()
        query = (
            select(ReportEdition)
            .join(
                versions,
                (ReportEdition.period_key == versions.c.period_key)
                & (ReportEdition.revision == versions.c.rev),
            )
            .where(
                ReportEdition.owner_id == owner,
                ReportEdition.kind == "daily",
                ReportEdition.status == "complete",
                ReportEdition.window_start < end,
            )
        )
        if start is not None:
            query = query.where(ReportEdition.window_start >= start)
        else:
            query = query.limit(7)
        rows = self.session.scalars(query.order_by(ReportEdition.period_key.desc()))
        issues, dependencies = [], []
        for row in rows:
            if row.status != "complete" or (
                start is not None and not _valid(self.session, row, now)
            ):
                continue
            content = EditionContentView.model_validate(row.content)
            selection = selection_from_snapshot(row.input_snapshot)
            carried = {id for section in content.sections for id in section.content_ids}
            issues.append(
                DailyIssue(
                    row.period_key,
                    selection,
                    tuple(
                        s.primary.content_id
                        for s in selection.main
                        if s.primary.content_id in carried
                    ),
                    tuple(content.highlights),
                )
            )
            dependencies.append(
                {"id": str(row.id), "key": row.period_key, "revision": row.revision}
            )
            if start is None and len(issues) == 7:
                break
        return tuple(issues), dependencies

    def _record(self, owner: UUID, id: UUID, *, lock: bool = False) -> ReportEdition:
        query = select(ReportEdition).where(ReportEdition.owner_id == owner, ReportEdition.id == id)
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise ApplicationError("resource_not_found")
        return row

    def _view(self, record: ReportEdition) -> EditionDetailView:
        from jobs.services import load_job_cancellation_state_in_transaction

        job = (
            load_job_cancellation_state_in_transaction(
                self.session, owner_id=record.owner_id, job_id=record.job_id
            )
            if record.job_id is not None
            else None
        )
        cancelled = bool(
            job and job.requested_at is not None and record.status in {"queued", "running"}
        )
        valid = record.status == "complete" and _valid(
            self.session, record, self.clock(), lock_permissions=False
        )
        content = EditionContentView.model_validate(record.content) if valid else None
        latest = self._latest(record.owner_id, record.kind, record.period_key)
        return EditionDetailView(
            id=record.id,
            kind=record.kind,
            key=record.period_key,
            revision=record.revision,
            status="failed"
            if cancelled
            else "stale"
            if record.status == "complete" and not valid
            else record.status,
            generator=record.generator,
            window_start=record.window_start,
            window_end=record.window_end,
            title=content.title if content else None,
            valid=valid,
            failure_code="edition_cancelled"
            if cancelled
            else "edition_input_withdrawn"
            if record.status == "complete" and not valid
            else record.failure_code,
            created_at=record.created_at,
            job_id=record.job_id,
            content=content,
            body_markdown=record.body_markdown if valid else None,
            ai_call_id=record.ai_call_id,
            reason=record.reason,
            historical_revision=bool(latest and latest.revision != record.revision),
        )

    def get(self, *, owner_id: UUID, edition_id: UUID) -> EditionDetailView:
        self.session.rollback()
        with self.session.begin():
            self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            return self._view(self._record(owner_id, edition_id))

    def list(
        self, *, owner_id: UUID, kind: EditionKind, before_key: str | None = None, limit: int = 20
    ) -> tuple[EditionSummaryView, ...]:
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_edition_input")
        if before_key is not None:
            try:
                period_window(kind, before_key)
            except ValueError as error:
                raise ApplicationError("invalid_edition_input") from error
        self.session.rollback()
        with self.session.begin():
            self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            newer = select(ReportEdition.period_key, func.max(ReportEdition.revision).label("rev"))
            newer = newer.where(ReportEdition.owner_id == owner_id, ReportEdition.kind == kind)
            newer_versions = newer.group_by(ReportEdition.period_key).subquery()
            query = (
                select(ReportEdition)
                .join(
                    newer_versions,
                    (ReportEdition.period_key == newer_versions.c.period_key)
                    & (ReportEdition.revision == newer_versions.c.rev),
                )
                .where(ReportEdition.owner_id == owner_id, ReportEdition.kind == kind)
            )
            if before_key is not None:
                query = query.where(ReportEdition.period_key < before_key)
            rows = self.session.scalars(
                query.order_by(ReportEdition.period_key.desc()).limit(limit)
            )
            return tuple(EditionSummaryView.model_validate(self._view(row)) for row in rows)

    def request(
        self, *, owner_id: UUID, actor_id: UUID, command: EditionRequestInput
    ) -> EditionDetailView:
        self.session.rollback()
        with self.session.begin():
            return self.request_in_transaction(
                owner_id=owner_id, actor_id=actor_id, command=command
            )

    def revisions(
        self, *, owner_id: UUID, edition_id: UUID, limit: int = 50
    ) -> tuple[EditionSummaryView, ...]:
        if not 1 <= limit <= 100:
            raise ApplicationError("invalid_edition_input")
        self.session.rollback()
        with self.session.begin():
            self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            record = self._record(owner_id, edition_id)
            rows = self.session.scalars(
                select(ReportEdition)
                .where(
                    ReportEdition.owner_id == owner_id,
                    ReportEdition.kind == record.kind,
                    ReportEdition.period_key == record.period_key,
                )
                .order_by(ReportEdition.revision.desc())
                .limit(limit)
            )
            return tuple(EditionSummaryView.model_validate(self._view(row)) for row in rows)

    def request_in_transaction(
        self, *, owner_id: UUID, actor_id: UUID, command: EditionRequestInput
    ) -> EditionDetailView:
        from events.heat import load_edition_attention_inputs_in_transaction
        from publication.reading import (
            list_report_candidates_in_transaction,
            report_candidate_authorities_in_transaction,
        )

        if not self.session.in_transaction():
            raise RuntimeError("edition admission requires caller transaction")
        self._lock(owner_id, str(command.operation_id))
        request_hash = _hash(command.model_dump(mode="json"))
        existing = self.session.scalar(
            select(ReportEdition).where(
                ReportEdition.owner_id == owner_id,
                ReportEdition.operation_id == command.operation_id,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_hash:
                raise ApplicationError("idempotency_conflict")
            return self._view(existing)
        self._lock(owner_id, f"{command.kind}:{command.key}")
        latest = self._latest(owner_id, command.kind, command.key)
        if (latest.revision if latest else 0) != command.expected_revision:
            raise ApplicationError("edition_revision_conflict")
        now = self.clock()
        start, end = period_window(command.kind, command.key)
        if end > now:
            raise ApplicationError("invalid_edition_input")
        daily_count = 0
        dependencies: list[dict[str, Any]] = []
        if command.kind == "daily":
            candidates = tuple(
                list_report_candidates_in_transaction(
                    self.session, owner_id=owner_id, start=start, end=end, now=now
                )
            )
            issues, _ = self._daily_issues(owner_id, start=None, end=start, now=now)
            covered, previous_events = daily_memory(issues, command.key)
            authorities = report_candidate_authorities_in_transaction(
                self.session, owner_id=owner_id, entries=candidates, now=now
            )
            attention = load_edition_attention_inputs_in_transaction(
                self.session,
                owner_id=owner_id,
                references=tuple(
                    EventContentReadReference(
                        content_id=e.content_id,
                        content_version_id=e.content_version_id,
                        observation_id=e.observation_id,
                        input_observation_ids=e.input_observation_ids,
                    )
                    for e in candidates
                ),
                event_ids=tuple({e.event_id for e in candidates if e.event_id}),
                start=start,
                end=end,
                now=now,
            )
            selection = compile_daily(
                candidates,
                covered=covered,
                previous_events=previous_events,
                authorities={id: (rank, action) for id, (rank, action, _) in authorities.items()},
                participants={
                    **{id: p for id, (_, _, p) in authorities.items()},
                    **attention.participants,
                },
                fact_sources=attention.fact_sources,
                event_participants=attention.event_participants,
            )
        else:
            issues, dependencies = self._daily_issues(owner_id, start=start, end=end, now=now)
            daily_count = len(issues)
            selection = compile_period(command.kind, issues)
        if not selection.entries:
            raise ApplicationError("edition_input_unavailable")
        id, revision = uuid4(), command.expected_revision + 1
        job = JobService(self.session, clock=self.clock).accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=command.operation_id,
                kind="report.edition",
                observation=JobObservationContext(
                    configuration_ref=f"edition:{id}", configuration_version=revision
                ),
                scope={
                    "edition_id": str(id),
                    "kind": command.kind,
                    "key": command.key,
                    **freeze_ai_job_scope_in_transaction(
                        self.session, owner_id=owner_id, settings=self.settings
                    ),
                },
            ),
        )
        snapshot = selection.snapshot()
        if dependencies:
            snapshot[0]["_daily_issues"] = dependencies
        record = ReportEdition(
            id=id,
            owner_id=owner_id,
            operation_id=command.operation_id,
            actor_id=actor_id,
            kind=command.kind,
            period_key=command.key,
            revision=revision,
            window_start=start,
            window_end=end,
            cutoff_at=now,
            job_id=job.id,
            prompt_version=edition_prompt_version(),
            input_fingerprint=_hash(snapshot),
            request_fingerprint=request_hash,
            input_snapshot=snapshot,
            repeats_suppressed=selection.repeats_suppressed,
            daily_editions_covered=daily_count,
            status="queued",
            generator="template",
            content=None,
            body_markdown=None,
            ai_call_id=None,
            failure_code=None,
            reason=command.reason,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()
        if not _valid(self.session, record, now):
            raise ApplicationError("edition_input_unavailable")
        return self._view(record)

    def correct(
        self, *, owner_id: UUID, actor_id: UUID, edition_id: UUID, command: EditionCorrectionInput
    ) -> EditionDetailView:
        request_hash = _hash({"edition_id": edition_id, **command.model_dump(mode="json")})
        self.session.rollback()
        with self.session.begin():
            self._lock(owner_id, str(command.operation_id))
            replay = self.session.scalar(
                select(ReportEdition).where(
                    ReportEdition.owner_id == owner_id,
                    ReportEdition.operation_id == command.operation_id,
                )
            )
            if replay is not None:
                if replay.request_fingerprint != request_hash:
                    raise ApplicationError("idempotency_conflict")
                return self._view(replay)
            prior = self._record(owner_id, edition_id)
            self._lock(owner_id, f"{prior.kind}:{prior.period_key}")
            latest = self._latest(owner_id, prior.kind, prior.period_key)
            if (
                latest is None
                or latest.id != prior.id
                or latest.revision != command.expected_revision
            ):
                raise ApplicationError("edition_revision_conflict")
            if prior.status != "complete" or not _valid(self.session, prior, self.clock()):
                raise ApplicationError("edition_input_unavailable")
            content = EditionContentView.model_validate(prior.content)
            allowed = {entry.content_id for entry in content.entries}
            if not set(command.highlights) <= allowed or any(
                not theme.content_ids or not set(theme.content_ids) <= allowed
                for theme in command.themes
            ):
                raise ApplicationError("invalid_edition_input")
            content.title, content.lead, content.highlights, content.themes = (
                command.title,
                command.lead,
                command.highlights,
                [EditionThemeView.model_validate(theme.model_dump()) for theme in command.themes],
            )
            now = self.clock()
            record = ReportEdition(
                id=uuid4(),
                owner_id=owner_id,
                operation_id=command.operation_id,
                actor_id=actor_id,
                kind=prior.kind,
                period_key=prior.period_key,
                revision=prior.revision + 1,
                window_start=prior.window_start,
                window_end=prior.window_end,
                cutoff_at=prior.cutoff_at,
                job_id=None,
                prompt_version=prior.prompt_version,
                input_fingerprint=prior.input_fingerprint,
                request_fingerprint=request_hash,
                input_snapshot=prior.input_snapshot,
                repeats_suppressed=prior.repeats_suppressed,
                daily_editions_covered=prior.daily_editions_covered,
                status="complete",
                generator="manual",
                content=content.model_dump(mode="json"),
                body_markdown=render_edition(
                    content, selection_from_snapshot(prior.input_snapshot)
                ),
                ai_call_id=None,
                failure_code=None,
                reason=command.reason,
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)
            self.session.flush()
            return self._view(record)

    def enqueue_due_in_transaction(self, *, now: datetime, limit: int = 8) -> int:
        if not self.session.in_transaction() or not 1 <= limit <= 100:
            raise ValueError("edition scheduling requires a bounded caller transaction")
        accepted = 0
        for owner in list_owner_ids_in_transaction(self.session):
            if accepted >= limit:
                break
            accepted += self._enqueue_owner_due_in_transaction(
                owner=owner, now=now, limit=limit - accepted
            )
        return accepted

    def _enqueue_owner_due_in_transaction(self, *, owner: UUID, now: datetime, limit: int) -> int:
        accepted = 0
        kinds: tuple[EditionKind, ...] = ("daily", "weekly", "monthly")
        for kind in kinds:
            due = due_period_key(kind, now)
            self._lock(owner, f"schedule:{kind}")
            first_key = self.session.scalar(
                select(func.min(ReportEdition.period_key)).where(
                    ReportEdition.owner_id == owner, ReportEdition.kind == kind
                )
            )
            schedule = self.session.get(ReportEditionSchedule, (owner, kind))
            if schedule is None:
                schedule = ReportEditionSchedule(
                    owner_id=owner,
                    kind=kind,
                    first_period_key=first_key or due,
                    scan_after_key=None,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(schedule)
                self.session.flush()
            # Check the newest due period first, independently of old empty gaps.
            key = due
            tried: set[str] = set()
            previous = schedule.scan_after_key
            catchup = next_period_key(kind, previous) if previous else schedule.first_period_key
            considered = 0
            while accepted < limit and considered < 100:
                if key > due:
                    schedule.scan_after_key = None
                    break
                if key in tried:
                    key = next_period_key(kind, key)
                    continue
                tried.add(key)
                considered += 1
                if self._latest(owner, kind, key) is None:
                    try:
                        with self.session.begin_nested():
                            self.request_in_transaction(
                                owner_id=owner,
                                actor_id=owner,
                                command=EditionRequestInput(
                                    operation_id=uuid5(_NAMESPACE, f"{owner}:{kind}:{key}"),
                                    kind=kind,
                                    key=key,
                                    expected_revision=0,
                                    reason="scheduled",
                                ),
                            )
                            accepted += 1
                    except ApplicationError as error:
                        if error.code != "edition_input_unavailable":
                            raise
                if key == due and considered == 1:
                    key = catchup
                else:
                    schedule.scan_after_key = key
                    key = next_period_key(kind, key)
                schedule.updated_at = now
        return accepted


class EditionExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def _failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.INVALID_RESPONSE,
            occurred_at=self.clock(),
            next_action="核对刊期固定材料、模型回执和修订, 用新操作人工恢复。",
        )

    def _ai_guard(
        self, session: Session, message: JobMessage, lease: ExecutionLease, edition_id: UUID
    ) -> None:
        JobExecutionService(
            session, lease_seconds=self.settings.job_lease_seconds, clock=self.clock
        ).require_current_operation_in_transaction(
            lease, owner_id=message.owner_id, operation_id=message.operation_id
        )
        service = EditionService(session, settings=self.settings, clock=self.clock)
        record = service._record(message.owner_id, edition_id, lock=True)
        latest = service._latest(message.owner_id, record.kind, record.period_key)
        if (
            record.job_id != message.job_id
            or record.prompt_version != edition_prompt_version()
            or record.status != "running"
            or record.generator != "model"
            or latest is None
            or latest.id != record.id
            or not _valid(session, record, self.clock())
        ):
            raise self._failure("edition_input_withdrawn")
        try:
            for reference in _references(record):
                require_editorial_content_permission_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    reference=EventContentReadReference(
                        content_id=reference.content_id,
                        content_version_id=reference.content_version_id,
                    ),
                    now=self.clock(),
                )
        except ApplicationError as error:
            raise self._failure("edition_input_withdrawn") from error

    def execute(
        self, message: JobMessage, lease: ExecutionLease, *, ai: AiService | None = None
    ) -> JobCompletion:
        with self.sessions() as session:
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                configuration is None
                or configuration.kind != "report.edition"
                or configuration.observation.configuration_ref != message.configuration_ref
                or configuration.observation.configuration_version != message.configuration_version
                or (
                    configuration.owner_id != message.owner_id
                    or configuration.operation_id != message.operation_id
                )
            ):
                raise self._failure("edition_scope_invalid")
            id = UUID(str(configuration.scope["edition_id"]))
        client = None
        if ai is None and self.settings.ai_enabled and configuration.scope["kind"] != "daily":
            client = create_ai_client(self.settings)
        try:
            with self.sessions.begin() as session:
                JobExecutionService(
                    session, lease_seconds=self.settings.job_lease_seconds, clock=self.clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=message.owner_id, operation_id=message.operation_id
                )
                service = EditionService(session, settings=self.settings, clock=self.clock)
                record = service._record(message.owner_id, id, lock=True)
                if record.job_id != message.job_id:
                    raise self._failure("edition_stale_scope")
                if record.status == "complete":
                    if not _valid(session, record, self.clock()):
                        raise self._failure("edition_input_withdrawn")
                    return JobCompletion(status=JobStatus.SUCCEEDED)
                if record.prompt_version != edition_prompt_version():
                    raise self._failure("edition_stale_scope")
                if record.status in {"unknown", "failed", "stale"}:
                    raise self._failure(record.failure_code or "edition_requires_review")
                use_model = record.kind != "daily" and (
                    record.generator == "model"
                    if record.status == "running"
                    else ai is not None or client is not None
                )
                if record.status == "running" and use_model:
                    record.status, record.failure_code = "unknown", "edition_result_unknown"
                    unknown = True
                else:
                    unknown = False
                    if not _valid(session, record, self.clock()):
                        raise self._failure("edition_input_withdrawn")
                    record.status, record.updated_at = "running", self.clock()
                    record.generator = "model" if use_model else "template"
                selection = selection_from_snapshot(record.input_snapshot)
                kind, key = cast(EditionKind, record.kind), record.period_key
                repeats, covered = record.repeats_suppressed, record.daily_editions_covered
            if unknown:
                raise self._failure("edition_result_unknown")
            response_id, output = None, None
            failure = None
            try:
                if use_model:
                    system, prompt, output_type = edition_prompt(kind, key, selection)
                    with self.sessions() as session:
                        caller = ai
                        if caller is None:
                            assert client is not None
                            caller = AiService(
                                session,
                                client,
                                clock=self.clock,
                                settings=self.settings,
                                guard=lambda current: JobExecutionService(
                                    current,
                                    lease_seconds=self.settings.job_lease_seconds,
                                    clock=self.clock,
                                ).require_current_operation_in_transaction(
                                    lease,
                                    owner_id=message.owner_id,
                                    operation_id=message.operation_id,
                                ),
                                execution_epoch=lease.epoch,
                            )
                        caller = caller.with_admission_guard(
                            lambda current: self._ai_guard(current, message, lease, id),
                            execution_epoch=lease.epoch,
                        )
                        response = caller.complete(
                            owner_id=message.owner_id,
                            job_id=message.job_id,
                            purpose=f"report.edition.{kind}",
                            prompt_version=edition_prompt_version(),
                            prompt=prompt,
                            instructions=system,
                            output_schema=output_type.model_json_schema(),
                        )
                    response_id, output = response.call_id, response.output
                    if response_id is None:
                        raise self._failure("edition_call_evidence_missing")
                content = compose_edition(
                    kind,
                    key,
                    selection,
                    model_output=output,
                    repeats_suppressed=repeats,
                    daily_editions_covered=covered,
                )
            except AiCallError as error:
                response_id, failure = error.call_id, f"edition_{error.code.value}"
                content = None
            except JobExecutionFailure as error:
                content, failure = None, error.error_code
            except (ValidationError, ValueError):
                content, failure = None, "edition_invalid_output"
            # Save the unique call receipt even when the lease or source changes after the call.
            with self.sessions.begin() as session:
                record = EditionService(session, settings=self.settings, clock=self.clock)._record(
                    message.owner_id, id, lock=True
                )
                record.ai_call_id = response_id
            with self.sessions.begin() as session:
                JobExecutionService(
                    session, lease_seconds=self.settings.job_lease_seconds, clock=self.clock
                ).require_current_operation_in_transaction(
                    lease, owner_id=message.owner_id, operation_id=message.operation_id
                )
                service = EditionService(session, settings=self.settings, clock=self.clock)
                record = service._record(message.owner_id, id, lock=True)
                if failure is not None:
                    record.status = "unknown" if failure == "edition_timeout" else "failed"
                    record.failure_code, record.updated_at = failure, self.clock()
                else:
                    latest = service._latest(message.owner_id, kind, key)
                    if (
                        latest is None
                        or latest.id != record.id
                        or not _valid(session, record, self.clock())
                    ):
                        record.status, record.failure_code = "stale", "edition_input_changed"
                        failure = "edition_input_changed"
                    else:
                        assert content is not None
                        record.content, record.body_markdown = (
                            content.model_dump(mode="json"),
                            render_edition(content, selection),
                        )
                        record.status, record.failure_code, record.updated_at = (
                            "complete",
                            None,
                            self.clock(),
                        )
                        record.generator = "model" if output is not None else "template"
            if failure:
                raise self._failure(failure)
            return JobCompletion(status=JobStatus.SUCCEEDED)
        finally:
            if client is not None:
                client.close()
