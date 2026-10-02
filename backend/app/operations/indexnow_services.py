"""One fenced IndexNow POST per original job attempt, with no secondary delivery ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from jobs.execution import ExecutionLease, JobCompletion, JobExecutionFailure, JobExecutionService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    BudgetScopeKind,
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import JobService, ResourceBudgetService, load_job_execution_configuration
from operations.indexnow_receipts import load_changed_receipt_paths_in_transaction
from operations.indexnow_schemas import IndexNowManifest, IndexNowReceiptCursor
from operations.models import OperatorAuditOperation
from operations.services import accept_audit_in_transaction
from publication.indexnow_reading import (
    load_indexable_changes_in_transaction,
    read_indexable_path_eligibilities_in_transaction,
    revalidate_indexable_paths_in_transaction,
)
from publication.indexnow_schemas import IndexableChangeCursor

_NAMESPACE = UUID("51d577b5-2b5a-4f81-84a1-90b085bb27d1")
_COMPONENT = "operations.indexnow"


def _configuration_fingerprint(settings: Settings) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "base_url": settings.web_base_url,
                "key_hash": hashlib.sha256(
                    settings.indexnow_key.get_secret_value().encode()
                ).hexdigest()
                if settings.indexnow_key
                else None,
                "external": settings.indexnow_external_requests_enabled,
                "indexing": settings.publication_indexing_enabled,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def enqueue_due_indexnow_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime, settings: Settings
) -> int:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("IndexNow scheduling requires an aware caller transaction")
    if not settings.indexnow_enabled:
        return 0
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"indexnow:{owner_id}"},
    )
    previous = session.scalar(
        select(OperatorAuditOperation)
        .where(
            OperatorAuditOperation.owner_id == owner_id,
            OperatorAuditOperation.action == "indexnow.submit",
        )
        .order_by(OperatorAuditOperation.created_at.desc(), OperatorAuditOperation.id.desc())
        .limit(1)
    )
    if previous is not None and previous.status != "succeeded":
        return 0
    raw_after = previous.after_state.get("next_cursor") if previous else None
    after = (
        IndexableChangeCursor.model_validate(raw_after)
        if raw_after
        else IndexableChangeCursor(
            changed_at=now - timedelta(days=1),
            content_id=UUID(int=0),
            revision=0,
        )
    )
    changes = load_indexable_changes_in_transaction(
        session, owner_id=owner_id, after=after, until=now
    )
    slot = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    raw_receipt = previous.after_state.get("next_receipt_cursor") if previous else None
    receipt_after = (
        IndexNowReceiptCursor.model_validate(raw_receipt)
        if raw_receipt
        and previous
        and previous.after_state.get("receipt_cycle") == slot.date().isoformat()
        else None
    )
    capacity = min(500, 1500 - len(changes.paths))
    receipt_paths, next_receipt, receipt_examined = (
        load_changed_receipt_paths_in_transaction(
            session, owner_id=owner_id, after=receipt_after, until=now, limit=capacity
        )
        if capacity
        else ([], receipt_after, 0)
    )
    operation = uuid5(
        _NAMESPACE,
        f"{owner_id}:{slot}:{after.model_dump_json()}:"
        f"{receipt_after.model_dump_json() if receipt_after else ''}:"
        f"{_configuration_fingerprint(settings)}",
    )
    payload = {
        "configuration_fingerprint": _configuration_fingerprint(settings),
        "paths": sorted(set(changes.paths + receipt_paths)),
        "next_cursor": changes.next_cursor.model_dump(mode="json"),
        "examined": changes.examined + receipt_examined,
        "next_receipt_cursor": next_receipt.model_dump(mode="json") if next_receipt else None,
        "receipt_cycle": slot.date().isoformat(),
    }
    audit, replayed = accept_audit_in_transaction(
        session,
        owner_id=owner_id,
        operation_id=operation,
        action="indexnow.submit",
        target_ref="public-site",
        reason="indexnow.daily.changed_urls",
        payload=payload,
        now=now,
    )
    if replayed:
        return 0
    job = JobService(session, clock=lambda: now).accept_in_transaction(
        owner_id=owner_id,
        command=JobAcceptanceInput(
            operation_id=operation,
            kind="publication.indexnow",
            observation=JobObservationContext(
                configuration_ref="indexnow:site", configuration_version=1
            ),
            scope={"audit_id": str(audit.id), "manifest_json": json.dumps(payload)},
        ),
    )
    audit.job_id = job.id
    audit.after_state = {"stage": "queued"}
    return 1


class IndexNowExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.sessions, self.settings, self.client = sessions, settings, client
        self.clock = clock or (lambda: datetime.now(UTC))

    def _execution(self, session: Session) -> JobExecutionService:
        return JobExecutionService(
            session, lease_seconds=self.settings.job_lease_seconds, clock=self.clock
        )

    def _failure(self, code: str, *, unknown: bool = False) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.CONFIGURATION_UNAVAILABLE
            if not unknown
            else JobFailureCategory.TRANSIENT,
            occurred_at=self.clock(),
            manual_retry_allowed=not unknown,
            next_action="核对IndexNow接收状态后运营确认" if unknown else "核对配置与预算后显式重试",
        )

    def execute(self, message: JobMessage, lease: ExecutionLease) -> JobCompletion:
        attempt_id: UUID | None = None
        with self.sessions.begin() as session:
            execution = self._execution(session)
            lease = execution.require_current_lease_in_transaction(lease)
            job = load_job_execution_configuration(session, job_id=message.job_id)
            if (
                job is None
                or job.owner_id != message.owner_id
                or job.operation_id != message.operation_id
                or job.kind != "publication.indexnow"
            ):
                raise self._failure("indexnow_configuration_changed")
            audit = session.scalar(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.owner_id == message.owner_id,
                    OperatorAuditOperation.id == UUID(str(job.scope["audit_id"])),
                    OperatorAuditOperation.job_id == message.job_id,
                )
                .with_for_update()
            )
            if audit is None:
                raise self._failure("indexnow_configuration_changed")
            manifest = IndexNowManifest.model_validate_json(str(job.scope["manifest_json"]))
            if audit.status == "succeeded":
                return JobCompletion(JobStatus.SUCCEEDED)
            stage = audit.after_state.get("stage")
            if (
                stage == "sending"
                and audit.after_state.get("operator_confirmation") != "not_delivered"
            ):
                audit.status, audit.error_code, audit.updated_at = (
                    "unknown",
                    "indexnow_submission_unknown",
                    self.clock(),
                )
                ResourceBudgetService(
                    session, clock=self.clock
                ).recover_abandoned_attempts_in_transaction(
                    owner_id=message.owner_id,
                    operation_id=message.operation_id,
                    component_key=_COMPONENT,
                    stage="submit",
                    finished_at=self.clock(),
                )
                unknown = True
            else:
                unknown = False
            if not unknown:
                if not self.settings.indexnow_enabled or (
                    manifest.configuration_fingerprint != _configuration_fingerprint(self.settings)
                ):
                    raise self._failure("indexnow_configuration_changed")
                paths = revalidate_indexable_paths_in_transaction(
                    session,
                    owner_id=message.owner_id,
                    paths=manifest.paths,
                    now=self.clock(),
                )
                summary = {
                    "next_cursor": manifest.next_cursor.model_dump(mode="json"),
                    "examined": manifest.examined,
                    "urls": len(paths),
                    "next_receipt_cursor": manifest.next_receipt_cursor.model_dump(mode="json")
                    if manifest.next_receipt_cursor
                    else None,
                    "receipt_cycle": manifest.receipt_cycle.isoformat()
                    if manifest.receipt_cycle
                    else None,
                }
                if not paths or not self.settings.indexnow_external_requests_enabled:
                    audit.status, audit.updated_at = "succeeded", self.clock()
                    audit.after_state = {**summary, "stage": "empty" if not paths else "disabled"}
                    return JobCompletion(JobStatus.SUCCEEDED)
                budgets = ResourceBudgetService(session, clock=self.clock)
                policies = budgets.budget_usage_snapshot(owner_id=message.owner_id)
                if not any(
                    policy.metric is BudgetMetric.NETWORK_REQUEST
                    and policy.enabled
                    and policy.scope_kind is BudgetScopeKind.SOURCE
                    and policy.scope_reference == "indexnow"
                    for policy in policies
                ):
                    raise self._failure("indexnow_budget_unavailable")
                count = execution.current_request_count_in_transaction(
                    lease, owner_id=message.owner_id, operation_id=message.operation_id
                )
                attempt_id = uuid5(message.operation_id, f"indexnow.http:{count + 1}")
                decision = budgets.reserve_budget_in_transaction(
                    owner_id=message.owner_id,
                    command=BudgetReservationInput(
                        reservation_id=attempt_id,
                        operation_id=message.operation_id,
                        metric=BudgetMetric.NETWORK_REQUEST,
                        requested_units=1,
                        context=BudgetContext(
                            source_ref="indexnow", job_ref="publication.indexnow"
                        ),
                    ),
                )
                if decision.status != BudgetDecisionStatus.RESERVED:
                    raise self._failure("indexnow_budget_unavailable")
                budgets.begin_attempt_in_transaction(
                    owner_id=message.owner_id,
                    command=UsageAttemptInput(
                        attempt_id=attempt_id,
                        operation_id=message.operation_id,
                        component_key=_COMPONENT,
                        usage_kind=UsageKind.NETWORK_REQUEST,
                        stage="submit",
                        started_at=self.clock(),
                    ),
                )
                lease, allowed = execution.begin_request_in_transaction(lease)
                if not allowed:
                    raise self._failure("indexnow_configuration_changed")
                audit.after_state = {
                    **summary,
                    "stage": "sending",
                    "attempt_id": str(attempt_id),
                    "eligibilities": read_indexable_path_eligibilities_in_transaction(
                        session, owner_id=message.owner_id, paths=paths, now=self.clock()
                    ),
                }
                audit.updated_at = self.clock()
        if unknown:
            raise self._failure("indexnow_submission_unknown", unknown=True)
        assert attempt_id is not None and self.settings.indexnow_key is not None
        status: int | None = None
        error_code: str | None = None
        try:
            with (
                (
                    httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
                    if self.client is None
                    else _borrow(self.client)
                ) as client,
                client.stream(
                    "POST",
                    "https://api.indexnow.org/indexnow",
                    json={
                        "host": urlsplit(self.settings.web_base_url).netloc,
                        "key": self.settings.indexnow_key.get_secret_value(),
                        "keyLocation": f"{self.settings.web_base_url}/hotkey-indexnow-key.txt",
                        "urlList": [f"{self.settings.web_base_url}{path}" for path in paths],
                    },
                    timeout=30,
                    follow_redirects=False,
                ) as response,
            ):
                # Status is the receipt; no provider body is loaded.
                status = response.status_code
        except httpx.HTTPError:
            error_code = "indexnow_submission_unknown"
        with self.sessions.begin() as session:
            # Save an already-returned receipt even if cancellation arrived during I/O.
            self._execution(session).require_current_lease_allowing_cancel_in_transaction(lease)
            audit = session.scalar(
                select(OperatorAuditOperation)
                .where(
                    OperatorAuditOperation.owner_id == message.owner_id,
                    OperatorAuditOperation.operation_id == message.operation_id,
                )
                .with_for_update()
            )
            assert audit is not None
            budgets = ResourceBudgetService(session, clock=self.clock)
            budgets.settle_budget_reservation_in_transaction(
                owner_id=message.owner_id, reservation_id=attempt_id, actual_units=1
            )
            budgets.finish_attempt_in_transaction(
                owner_id=message.owner_id,
                attempt_id=attempt_id,
                outcome=UsageOutcome.SUCCEEDED if status in {200, 202} else UsageOutcome.FAILED,
                finished_at=self.clock(),
            )
            audit.status = (
                "succeeded" if status in {200, 202} else "unknown" if status is None else "failed"
            )
            audit.error_code = (
                error_code
                if status is None
                else None
                if status in {200, 202}
                else "indexnow_submission_rejected"
            )
            audit.after_state = {
                **audit.after_state,
                "http_status": status,
                "stage": "accepted"
                if status == 200
                else "key_validation_pending"
                if status == 202
                else "sending"
                if status is None
                else "rejected",
            }
            audit.updated_at = self.clock()
        if status not in {200, 202}:
            raise self._failure(
                error_code or "indexnow_submission_rejected", unknown=status is None
            )
        return JobCompletion(JobStatus.SUCCEEDED)


@contextmanager
def _borrow(client: httpx.Client) -> Iterator[httpx.Client]:
    yield client
