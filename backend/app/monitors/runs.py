from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connections.schemas import SourceEntryPoint
from connections.services import (
    load_applied_source_presets_in_transaction,
    load_execution_policy_in_transaction,
)
from content.discovery import plan_single_keyword_discovery
from content.schemas import KeywordDiscoveryRunInput
from core.config import Settings
from core.errors import ApplicationError
from evidence.services import load_source_access_readiness
from jobs.models import Job
from jobs.schemas import BudgetMetric, BudgetScopeKind, BudgetWindowUsageView, JobAcceptanceInput
from jobs.services import (
    JobService,
    ResourceBudgetService,
    try_lock_source_collection_in_transaction,
)
from monitors.models import MonitorTopic, MonitorTopicVersion
from monitors.schemas import (
    MonitorTopicRunInput,
    MonitorTopicRunSourceView,
    MonitorTopicRunView,
    MonitorTopicStatus,
)
from monitors.services import normalize_monitor_rules, scheduled_collection_queries
from sources.contracts import SourceCapability


@dataclass(frozen=True, slots=True)
class MonitorTopicRunResult:
    view: MonitorTopicRunView
    replayed: bool


class MonitorTopicRunService:
    """Accept an owner-scoped manual search request as one durable operation."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(
        self, *, owner_id: UUID, topic_id: UUID, command: MonitorTopicRunInput
    ) -> MonitorTopicRunResult:
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("manual run time must be timezone-aware")
        now = now.astimezone(UTC)
        requested = tuple(sorted(command.source_keys))
        request_sources = ",".join(requested)
        self._session.rollback()
        with self._session.begin():
            # Serialize retries even before the first Job exists. A collision only
            # delays an unrelated request; it cannot give that request access.
            lock_key = int.from_bytes(command.operation_id.bytes[:8], "big", signed=True)
            self._session.scalar(select(func.pg_advisory_xact_lock(lock_key)))
            existing = self._existing_jobs(owner_id=owner_id, operation_id=command.operation_id)
            if existing:
                return MonitorTopicRunResult(
                    view=self._replayed_view(
                        topic_id=topic_id,
                        operation_id=command.operation_id,
                        request_sources=request_sources,
                        jobs=existing,
                    ),
                    replayed=True,
                )

            topic = self._session.scalar(
                select(MonitorTopic)
                .where(MonitorTopic.owner_id == owner_id, MonitorTopic.id == topic_id)
                .with_for_update()
            )
            if topic is None:
                raise ApplicationError("resource_not_found")
            version = self._session.get(MonitorTopicVersion, (topic.id, topic.current_version))
            if version is None:
                raise RuntimeError("monitor topic current version is missing")
            if not set(requested).issubset(set(version.source_keys)):
                raise ApplicationError("invalid_topic_source_selection")
            if topic.status != MonitorTopicStatus.ACTIVE.value:
                raise ApplicationError("topic_not_ready")

            applied = load_applied_source_presets_in_transaction(
                self._session, owner_id=owner_id, source_keys=requested
            )
            readiness = load_source_access_readiness(self._session, owner_id=owner_id, now=now)
            budgets = ResourceBudgetService(self._session, clock=lambda: now).budget_usage_snapshot(
                owner_id=owner_id
            )
            rules = normalize_monitor_rules(
                match_any=version.match_any,
                match_all=version.match_all,
                exclude=version.exclude,
            )
            queries = scheduled_collection_queries(rules)
            planned: list[tuple[str, tuple[JobAcceptanceInput, ...]]] = []
            skipped: dict[str, str] = {}
            for source_key in requested:
                preset = applied.get(source_key)
                if (
                    preset is None
                    or SourceCapability.SEARCH not in preset.capabilities
                    or not readiness.get((source_key, SourceCapability.SEARCH), False)
                    or (source_key == "bilibili" and not self._settings.mediacrawler_enabled)
                ):
                    skipped[source_key] = "source_unavailable"
                    continue
                policy = load_execution_policy_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    connection_id=preset.connection_id,
                    connection_version=preset.connection_version,
                )
                if not policy.enabled:
                    skipped[source_key] = "source_unavailable"
                    continue
                if policy.quiet_at(now):
                    skipped[source_key] = "quiet"
                    continue
                if not self._has_budget(budgets, source_key):
                    skipped[source_key] = "budget"
                    continue
                if policy.min_interval_seconds and (
                    not try_lock_source_collection_in_transaction(
                        self._session,
                        owner_id=owner_id,
                        source_key=source_key,
                    )
                    or self._recent_source_job(
                        owner_id=owner_id,
                        source_key=source_key,
                        since=now - timedelta(seconds=policy.min_interval_seconds),
                    )
                ):
                    skipped[source_key] = "rate_limited"
                    continue

                source_queries = queries[: policy.max_queries]
                interval = max(topic.collection_interval_seconds, policy.min_interval_seconds)
                starts_at = now - timedelta(
                    seconds=interval + self._settings.collection_lookback_seconds
                )
                source_jobs: list[JobAcceptanceInput] = []
                for index, query in enumerate(source_queries):
                    is_bilibili = source_key == "bilibili"
                    run = KeywordDiscoveryRunInput(
                        run_id=uuid5(command.operation_id, f"{topic_id}:{source_key}:{index}"),
                        configuration_ref=f"topic:{topic_id}",
                        configuration_version=version.version,
                        source_key=source_key,
                        connection_id=preset.connection_id,
                        connection_version=preset.connection_version,
                        primary_query=query,
                        starts_at=starts_at,
                        ends_at=now,
                        page_size=min(policy.max_items_per_query, 5 if is_bilibili else 100),
                        latest_max_pages=1 if is_bilibili else 3,
                        latest_max_requests=min(policy.max_requests, 26 if is_bilibili else 3),
                        top_max_pages=1,
                        top_max_requests=1,
                        max_seconds=min(policy.max_seconds, 220 if is_bilibili else 90),
                        entry_point=SourceEntryPoint.MANUAL,
                    )
                    planned_job = plan_single_keyword_discovery(run)
                    source_jobs.append(
                        planned_job.model_copy(
                            update={
                                "scope": {
                                    **planned_job.scope,
                                    "manual_request_id": str(command.operation_id),
                                    "manual_source_keys": request_sources,
                                    "manual_query_index": index,
                                }
                            }
                        )
                    )
                planned.append((source_key, tuple(source_jobs)))

            if not planned:
                raise ApplicationError("topic_not_ready")
            skip_snapshot = ",".join(f"{key}:{reason}" for key, reason in sorted(skipped.items()))
            accepted: dict[str, list[UUID]] = {key: [] for key in requested}
            job_service = JobService(self._session, clock=lambda: now)
            for source_key, commands in planned:
                for job in commands:
                    scope = {**job.scope, "manual_skips": skip_snapshot}
                    accepted_job = job_service.accept_in_transaction(
                        owner_id=owner_id, command=job.model_copy(update={"scope": scope})
                    )
                    accepted[source_key].append(accepted_job.id)
            return MonitorTopicRunResult(
                view=MonitorTopicRunView(
                    operation_id=command.operation_id,
                    topic_id=topic_id,
                    topic_version=version.version,
                    sources=[
                        MonitorTopicRunSourceView(
                            source_key=key,
                            job_ids=accepted[key],
                            skip_reason=skipped.get(key),
                        )
                        for key in requested
                    ],
                ),
                replayed=False,
            )

    def _existing_jobs(self, *, owner_id: UUID, operation_id: UUID) -> tuple[Job, ...]:
        return tuple(
            self._session.scalars(
                select(Job)
                .where(
                    Job.owner_id == owner_id,
                    Job.kind == "keyword.search",
                    Job.scope["manual_request_id"].astext == str(operation_id),
                )
                .order_by(Job.source_key, Job.id)
            )
        )

    @staticmethod
    def _replayed_view(
        *, topic_id: UUID, operation_id: UUID, request_sources: str, jobs: tuple[Job, ...]
    ) -> MonitorTopicRunView:
        first = jobs[0]
        if (
            first.configuration_ref != f"topic:{topic_id}"
            or first.scope.get("manual_source_keys") != request_sources
        ):
            raise ApplicationError("idempotency_conflict")
        grouped: dict[str, list[Job]] = {key: [] for key in request_sources.split(",")}
        for job in jobs:
            if (
                job.configuration_ref != first.configuration_ref
                or job.configuration_version != first.configuration_version
                or job.scope.get("manual_source_keys") != request_sources
                or job.source_key not in grouped
            ):
                raise ApplicationError("idempotency_conflict")
            assert job.source_key is not None
            grouped[job.source_key].append(job)
        skip_snapshot = first.scope.get("manual_skips")
        skipped = (
            dict(item.split(":", 1) for item in skip_snapshot.split(","))
            if isinstance(skip_snapshot, str) and skip_snapshot
            else {}
        )
        return MonitorTopicRunView(
            operation_id=operation_id,
            topic_id=topic_id,
            topic_version=first.configuration_version,
            sources=[
                MonitorTopicRunSourceView(
                    source_key=key,
                    job_ids=[
                        job.id
                        for job in sorted(
                            grouped[key],
                            key=lambda item: str(item.scope["manual_query_index"]),
                        )
                    ],
                    skip_reason=skipped.get(key),
                )
                for key in grouped
            ],
        )

    def _recent_source_job(self, *, owner_id: UUID, source_key: str, since: datetime) -> bool:
        return (
            self._session.scalar(
                select(Job.id)
                .where(
                    Job.owner_id == owner_id,
                    Job.source_key == source_key,
                    Job.kind == "keyword.search",
                    Job.created_at > since,
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def _has_budget(budgets: tuple[BudgetWindowUsageView, ...], source_key: str) -> bool:
        relevant = [
            budget
            for budget in budgets
            if budget.metric is BudgetMetric.NETWORK_REQUEST
            and (
                budget.scope_kind is BudgetScopeKind.GLOBAL
                or (
                    budget.scope_kind is BudgetScopeKind.SOURCE
                    and budget.scope_reference == source_key
                )
            )
        ]
        return {BudgetScopeKind.GLOBAL, BudgetScopeKind.SOURCE}.issubset(
            {budget.scope_kind for budget in relevant}
        ) and all(
            budget.enabled and budget.remaining_units is not None and budget.remaining_units > 0
            for budget in relevant
        )
