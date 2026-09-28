from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService, create_ai_client
from analysis.models import (
    AnalysisPromptActivation,
    AnalysisPromptRuntimeSession,
    ContentAnnotation,
)
from analysis.prompts import (
    ANALYSIS_OUTPUT_SCHEMA,
    ANALYSIS_PROMPT_VERSION,
    build_analysis_prompt,
    serialize_analysis_data,
)
from analysis.runtime import PromptRuntimeWindow, project_prompt_runtime_origin
from analysis.schemas import (
    AnalysisJobScope,
    AnalysisNeedLedgerRowView,
    AnalysisNeedLedgerView,
    AnalysisPromptItem,
    AnnotationOutputEnvelope,
    AnnotationOutputItem,
    AnnotationResultState,
    AnnotationStatus,
    AnnotationWrite,
    WindowAnnotationCountView,
)
from content.schemas import AnalysisPostContentView
from content.services import (
    load_post_analysis_availability_in_transaction,
    load_post_comments_for_analysis,
    load_post_versions_for_analysis,
    load_post_versions_for_analysis_scan,
)
from core.config import Settings
from jobs.coverage import CollectionDueWindowService
from jobs.execution import JobCompletion, JobExecutionFailure
from jobs.metrics import AnalysisTimingSample, summarize_analysis_timing
from jobs.models import Job
from jobs.schemas import (
    JobAcceptanceInput,
    JobFailureCategory,
    JobMessage,
    JobObservationContext,
    JobStatus,
    JobView,
)
from jobs.services import (
    JobService,
    load_content_job_contexts,
    load_job_execution_configuration,
)
from monitors.services import (
    MonitorTopicService,
    NormalizedMonitorRules,
    evaluate_monitor_rules,
    list_topic_analysis_rule_identities_in_transaction,
    load_topic_analysis_rule_timeline_in_transaction,
)

_ANALYSIS_OPERATION_NAMESPACE = UUID("16cfeef5-e41d-43a2-8212-4e21cc6f4c85")
_MAX_BATCH_ITEMS = 30
_MAX_SERIALIZED_CHARACTERS = 24_000
_MAX_BODY_CHARACTERS = 1_500
_MAX_COMMENTS_PER_POST = 50
_MAX_COLLECTION_ANALYSIS_JOBS = 100
_ANNOTATION_READ_BATCH_SIZE = 500
_MAX_SCAN_BATCHES = 20


@dataclass(frozen=True, slots=True)
class AnalysisExecutionResult:
    completion: JobCompletion
    processed_items: int


@dataclass(frozen=True, slots=True)
class AnalysisNeedOriginProjection:
    """Earliest qualifying instant; candidate does not prove uninterrupted Codex availability."""

    status: Literal["candidate", "not_required", "unknown"]
    started_at: datetime | None
    reason: str | None = None
    prompt_runtime_ids: tuple[UUID, ...] = ()


def _load_prompt_runtime_windows_in_transaction(
    session: Session, *, as_of: datetime
) -> tuple[PromptRuntimeWindow, ...]:
    return tuple(
        PromptRuntimeWindow(
            run_id=runtime.id,
            prompt_version=runtime.prompt_version,
            ai_enabled=runtime.ai_enabled,
            starts_at=runtime.started_at,
            ends_at=runtime.last_seen_at,
        )
        for runtime in session.scalars(
            select(AnalysisPromptRuntimeSession)
            .where(AnalysisPromptRuntimeSession.started_at < as_of)
            .order_by(AnalysisPromptRuntimeSession.started_at, AnalysisPromptRuntimeSession.id)
        )
    )


def _load_prompt_versions_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    end: datetime,
    cutoff_at: datetime,
    runtime_windows: Sequence[PromptRuntimeWindow],
) -> tuple[str, ...]:
    """Include known old identities even when their activation history is missing."""
    versions = {ANALYSIS_PROMPT_VERSION}
    versions.update(
        session.scalars(
            select(AnalysisPromptActivation.prompt_version).where(
                AnalysisPromptActivation.activated_at < end
            )
        )
    )
    versions.update(
        window.prompt_version
        for window in runtime_windows
        if window.ai_enabled and window.starts_at < end
    )
    versions.update(
        session.scalars(
            select(ContentAnnotation.prompt_version)
            .where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.created_at <= cutoff_at,
            )
            .distinct()
        )
    )
    versions.update(
        session.scalars(
            select(Job.scope["prompt_version"].astext)
            .where(
                Job.owner_id == owner_id,
                Job.kind == "analysis.annotate",
                Job.created_at <= cutoff_at,
                func.jsonb_typeof(Job.scope["prompt_version"]) == "string",
            )
            .distinct()
        )
    )
    return tuple(sorted(version for version in versions if version and len(version) <= 128))


def build_analysis_need_ledger_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    start: datetime,
    end: datetime,
    cutoff_at: datetime,
) -> AnalysisNeedLedgerView:
    """Enumerate observed exact-version candidates, including ones never queued."""
    if not session.in_transaction():
        raise RuntimeError("analysis ledger requires the caller's transaction")
    if (
        start.utcoffset() != timedelta(0)
        or end.utcoffset() != timedelta(0)
        or cutoff_at.utcoffset() != timedelta(0)
        or not start < end <= start + timedelta(days=31)
        or cutoff_at < end
    ):
        raise ValueError("analysis ledger needs a UTC range of at most 31 days and later cutoff")
    rows: list[AnalysisNeedLedgerRowView] = []
    timing_samples: list[AnalysisTimingSample] = []
    prompt_runtime_windows = _load_prompt_runtime_windows_in_transaction(session, as_of=end)
    prompt_versions = _load_prompt_versions_in_transaction(
        session,
        owner_id=owner_id,
        end=end,
        cutoff_at=cutoff_at,
        runtime_windows=prompt_runtime_windows,
    )
    for rule in list_topic_analysis_rule_identities_in_transaction(
        session, owner_id=owner_id, before=end
    ):
        posts = load_post_versions_for_analysis_scan(
            session,
            owner_id=owner_id,
            topic_id=rule.topic_id,
            source_keys=rule.source_keys,
            as_of=end,
        )
        if not posts:
            continue
        annotations = {
            (item.prompt_version, item.content_version_id): item
            for item in session.scalars(
                select(ContentAnnotation).where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.topic_id == rule.topic_id,
                    ContentAnnotation.topic_rule_version == rule.topic_rule_version,
                    ContentAnnotation.created_at <= cutoff_at,
                )
            )
        }
        for post in posts:
            if not evaluate_monitor_rules(rule.rules, _post_text(post)).matched:
                continue
            availability = load_post_analysis_availability_in_transaction(
                session,
                owner_id=owner_id,
                topic_id=rule.topic_id,
                content_version_id=post.content_version_id,
            )
            if availability is None:
                continue
            for prompt_version in prompt_versions:
                origin = project_analysis_need_origin_in_transaction(
                    session,
                    owner_id=owner_id,
                    topic_id=rule.topic_id,
                    topic_rule_version=rule.topic_rule_version,
                    content_version_id=post.content_version_id,
                    prompt_version=prompt_version,
                    as_of=end,
                    prompt_runtime_windows=prompt_runtime_windows,
                )
                if origin.status == "not_required" or (
                    origin.status == "candidate"
                    and (origin.started_at is None or not start <= origin.started_at < end)
                ):
                    continue
                annotation = annotations.get((prompt_version, post.content_version_id))
                first_valid_at = annotation.first_valid_at if annotation is not None else None
                inconsistent_history = (
                    origin.status == "candidate"
                    and origin.started_at is not None
                    and first_valid_at is not None
                    and first_valid_at < origin.started_at
                )
                rows.append(
                    AnalysisNeedLedgerRowView(
                        content_version_id=post.content_version_id,
                        topic_id=rule.topic_id,
                        topic_rule_version=rule.topic_rule_version,
                        prompt_version=prompt_version,
                        source_key=availability.source_key,
                        origin_status="unknown" if inconsistent_history else origin.status,
                        started_at=None if inconsistent_history else origin.started_at,
                        reason=(
                            "first_valid_precedes_need" if inconsistent_history else origin.reason
                        ),
                        prompt_runtime_ids=origin.prompt_runtime_ids,
                        result_state=annotation.result_state if annotation is not None else None,
                        first_valid_at=first_valid_at,
                    )
                )
                if (
                    origin.status == "candidate"
                    and origin.started_at is not None
                    and not inconsistent_history
                ):
                    timing_samples.append(
                        AnalysisTimingSample(
                            needed_at=origin.started_at,
                            first_valid_at=first_valid_at,
                        )
                    )
    timing = summarize_analysis_timing(timing_samples, cutoff_at=cutoff_at)
    rows.sort(
        key=lambda row: (
            str(row.topic_id),
            row.topic_rule_version,
            row.prompt_version,
            str(row.content_version_id),
        )
    )
    return AnalysisNeedLedgerView(
        metric_version="analysis-candidate-v3",
        analysis_status="not_computable",
        start=start,
        end=end,
        cutoff_at=cutoff_at,
        candidate_count=timing.sample_count,
        unknown_count=len(rows) - timing.sample_count,
        matured_count=timing.matured_count,
        pending_observation_count=timing.pending_observation_count,
        timely_valid_count=timing.timely_valid_count,
        late_or_missing_count=timing.late_or_missing_count,
        rows=tuple(rows),
    )


def project_analysis_need_origin_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    content_version_id: UUID,
    prompt_version: str,
    as_of: datetime,
    prompt_runtime_windows: Sequence[PromptRuntimeWindow] | None = None,
) -> AnalysisNeedOriginProjection:
    """Intersect exact receipt, rule/topic windows and evidenced prompt runtime."""
    if not session.in_transaction():
        raise RuntimeError("analysis need projection requires the caller's transaction")
    if as_of.tzinfo is None or topic_rule_version < 1 or not prompt_version:
        raise ValueError("analysis need projection requires aware time and valid identity")
    timeline = load_topic_analysis_rule_timeline_in_transaction(
        session,
        owner_id=owner_id,
        topic_id=topic_id,
        topic_rule_version=topic_rule_version,
    )
    if timeline is None:
        return AnalysisNeedOriginProjection("unknown", None, "topic_history_unavailable")
    activation = session.get(AnalysisPromptActivation, prompt_version)
    if activation is None:
        return AnalysisNeedOriginProjection("unknown", None, "prompt_activation_unavailable")
    availability = load_post_analysis_availability_in_transaction(
        session,
        owner_id=owner_id,
        topic_id=topic_id,
        content_version_id=content_version_id,
    )
    if (
        availability is None
        or not evaluate_monitor_rules(timeline.rules, _post_text(availability.post)).matched
    ):
        return AnalysisNeedOriginProjection("not_required", None)
    received_at = (
        availability.first_received_at
        if availability.source_key in timeline.source_keys
        else availability.first_hotlist_match_received_at
    )
    if received_at is None:
        return AnalysisNeedOriginProjection("not_required", None)
    cutoff = as_of.astimezone(UTC)
    eligible_spans: list[tuple[datetime, datetime]] = []
    for active_start, active_end in timeline.active_spans:
        start = max(received_at, timeline.starts_at, activation.activated_at, active_start)
        end = min(end for end in (timeline.ends_at, active_end, cutoff) if end is not None)
        if start < end:
            eligible_spans.append((start, end))
    if not eligible_spans:
        return AnalysisNeedOriginProjection("not_required", None)
    runtime = project_prompt_runtime_origin(
        prompt_version=prompt_version,
        eligible_spans=eligible_spans,
        runtime_windows=(
            prompt_runtime_windows
            if prompt_runtime_windows is not None
            else _load_prompt_runtime_windows_in_transaction(session, as_of=cutoff)
        ),
    )
    return AnalysisNeedOriginProjection(
        runtime.status, runtime.started_at, runtime.reason, runtime.runtime_ids
    )


def analysis_operation_id(
    *,
    topic_id: UUID,
    topic_rule_version: int,
    content_version_ids: Sequence[UUID],
    prompt_version: str,
    retry_index: int = 0,
) -> UUID:
    if (
        topic_rule_version < 1
        or not prompt_version
        or not content_version_ids
        or retry_index not in (0, 1)
    ):
        raise ValueError("analysis operation identity requires a rule, prompt and content")
    ordered_ids = sorted({str(content_version_id) for content_version_id in content_version_ids})
    if len(ordered_ids) != len(content_version_ids):
        raise ValueError("analysis operation content versions must be distinct")
    name = "\0".join((str(topic_id), str(topic_rule_version), prompt_version, *ordered_ids))
    if retry_index:
        name = f"{name}\0retry:{retry_index}"
    return uuid5(_ANALYSIS_OPERATION_NAMESPACE, name)


def pack_prompt_batches(
    items: Sequence[AnalysisPromptItem],
) -> tuple[tuple[AnalysisPromptItem, ...], ...]:
    """Pack immutable post text first, then share remaining space across comments."""
    normalized = tuple(
        item.model_copy(
            update={
                "body": item.body[:_MAX_BODY_CHARACTERS] if item.body is not None else None,
                "comments": tuple(item.comments[:_MAX_COMMENTS_PER_POST]),
                "body_truncated": item.body_truncated
                or (item.body is not None and len(item.body) > _MAX_BODY_CHARACTERS),
                "comments_truncated": item.comments_truncated
                or len(item.comments) > _MAX_COMMENTS_PER_POST,
            }
        )
        for item in items
    )
    base_batches: list[list[AnalysisPromptItem]] = []
    current: list[AnalysisPromptItem] = []
    for item in normalized:
        without_comments = item.model_copy(
            update={
                "comments": (),
                "comments_truncated": bool(item.comments) or item.comments_truncated,
            }
        )
        candidate = [*current, without_comments]
        if current and (
            len(candidate) > _MAX_BATCH_ITEMS
            or len(serialize_analysis_data(candidate)) > _MAX_SERIALIZED_CHARACTERS
        ):
            base_batches.append(current)
            current = [without_comments]
        else:
            current = candidate
        if len(serialize_analysis_data(current)) > _MAX_SERIALIZED_CHARACTERS:
            raise ValueError("one analysis item exceeds the serialized character limit")
    if current:
        base_batches.append(current)

    source_items = {item.content_version_id: item for item in normalized}
    return tuple(_add_comments_within_limit(batch, source_items) for batch in base_batches)


def _add_comments_within_limit(
    base_batch: list[AnalysisPromptItem],
    source_items: Mapping[UUID, AnalysisPromptItem],
) -> tuple[AnalysisPromptItem, ...]:
    batch = list(base_batch)
    positions = [0] * len(batch)
    exhausted = [False] * len(batch)
    truncated_by_budget = [False] * len(batch)
    while not all(exhausted):
        changed = False
        for index, item in enumerate(batch):
            source = source_items[item.content_version_id]
            position = positions[index]
            if exhausted[index] or position >= len(source.comments):
                exhausted[index] = True
                continue
            comment = source.comments[position]
            candidate_item = item.model_copy(update={"comments": (*item.comments, comment)})
            candidate_batch = [*batch[:index], candidate_item, *batch[index + 1 :]]
            if len(serialize_analysis_data(candidate_batch)) <= _MAX_SERIALIZED_CHARACTERS:
                batch = candidate_batch
                positions[index] += 1
                changed = True
                continue
            prefix = _largest_comment_prefix(batch, index=index, comment=comment)
            if prefix:
                batch[index] = item.model_copy(update={"comments": (*item.comments, prefix)})
                changed = True
            truncated_by_budget[index] = True
            exhausted[index] = True
        if not changed:
            break
    return tuple(
        item.model_copy(
            update={
                "comments_truncated": source_items[item.content_version_id].comments_truncated
                or truncated_by_budget[index]
                or positions[index] < len(source_items[item.content_version_id].comments)
            }
        )
        for index, item in enumerate(batch)
    )


def _largest_comment_prefix(
    batch: Sequence[AnalysisPromptItem],
    *,
    index: int,
    comment: str,
) -> str:
    low, high = 0, len(comment)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate_item = batch[index].model_copy(
            update={"comments": (*batch[index].comments, comment[:midpoint])}
        )
        candidate = [*batch[:index], candidate_item, *batch[index + 1 :]]
        if len(serialize_analysis_data(candidate)) <= _MAX_SERIALIZED_CHARACTERS:
            low = midpoint
        else:
            high = midpoint - 1
    return comment[:low]


def resolve_annotation_results(
    *,
    expected_content_version_ids: Sequence[UUID],
    raw_items: Sequence[Any],
    ai_call_id: UUID,
    retry_index: int = 0,
) -> tuple[AnnotationWrite, ...]:
    if retry_index not in (0, 1):
        raise ValueError("analysis retry index must be zero or one")
    grouped: dict[UUID, list[Any]] = {}
    expected = set(expected_content_version_ids)
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            continue
        raw_id = raw_item.get("content_version_id")
        try:
            content_version_id = UUID(str(raw_id))
        except (TypeError, ValueError):
            continue
        if content_version_id in expected:
            grouped.setdefault(content_version_id, []).append(dict(raw_item))

    resolved: list[AnnotationWrite] = []
    for content_version_id in expected_content_version_ids:
        candidates = grouped.get(content_version_id, [])
        if len(candidates) == 1:
            try:
                output = AnnotationOutputItem.model_validate(candidates[0])
            except ValidationError:
                output = None
            if output is not None and output.content_version_id == content_version_id:
                resolved.append(
                    AnnotationWrite(
                        content_version_id=content_version_id,
                        relevant=output.relevant,
                        relevance_reason=output.relevance_reason,
                        sentiment=output.sentiment,
                        summary=output.summary,
                        viewpoints=output.viewpoints,
                        ai_call_id=ai_call_id,
                        status=AnnotationStatus.ANNOTATED,
                        result_state=AnnotationResultState.VALID,
                    )
                )
                continue
        error_code = (
            "analysis_output_missing"
            if not candidates
            else "analysis_output_duplicate"
            if len(candidates) > 1
            else "analysis_output_invalid"
        )
        resolved.append(
            AnnotationWrite(
                content_version_id=content_version_id,
                ai_call_id=ai_call_id,
                status=AnnotationStatus.UNANALYZED,
                result_state=(
                    AnnotationResultState.FAILED
                    if retry_index == 1
                    else AnnotationResultState.INVALID
                ),
                error_code=("analysis_invalid_exhausted" if retry_index == 1 else error_code),
            )
        )
    return tuple(resolved)


def analysis_failure(error: AiCallError, *, now: datetime) -> JobExecutionFailure:
    if now.tzinfo is None:
        raise ValueError("analysis failure time must be timezone-aware")
    if error.code is AiFailureCode.RATE_LIMITED:
        budget_delayed = error.retry_at is not None
        return JobExecutionFailure(
            error_code="analysis_rate_limited",
            category=JobFailureCategory.RATE_LIMITED,
            occurred_at=now,
            next_action=(
                "等待每日分析预算窗口恢复后自动重试"
                if budget_delayed
                else "等待模型限流恢复后自动重试"
            ),
            retry_at=max(error.retry_at, now + timedelta(seconds=60))
            if error.retry_at is not None
            else now + timedelta(seconds=60),
            max_attempts=100 if budget_delayed else 3,
        )
    category = (
        JobFailureCategory.INVALID_RESPONSE
        if error.code is AiFailureCode.INVALID_OUTPUT
        else JobFailureCategory.TRANSIENT
    )
    return JobExecutionFailure(
        error_code=f"analysis_{error.code.value}",
        category=category,
        occurred_at=now,
        next_action="检查本机 Codex app-server 状态与结构化输出后手动重试",
        manual_retry_allowed=True,
    )


class AnalysisService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_prompt_activation_in_transaction(
        self, *, prompt_version: str, activated_at: datetime
    ) -> bool:
        """Keep the first enabled scheduler start for this prompt version."""
        if not self._session.in_transaction():
            raise RuntimeError("prompt activation requires the caller's transaction")
        if not 0 < len(prompt_version) <= 128 or activated_at.tzinfo is None:
            raise ValueError("prompt activation requires a version and aware time")
        inserted = self._session.scalar(
            insert(AnalysisPromptActivation)
            .values(prompt_version=prompt_version, activated_at=activated_at.astimezone(UTC))
            .on_conflict_do_nothing(index_elements=["prompt_version"])
            .returning(AnalysisPromptActivation.prompt_version)
        )
        return inserted is not None

    def start_prompt_runtime_in_transaction(
        self,
        *,
        run_id: UUID,
        prompt_version: str,
        ai_enabled: bool,
        started_at: datetime,
    ) -> bool:
        """Atomically record this scheduler run and its first enabled prompt use."""
        if not self._session.in_transaction():
            raise RuntimeError("prompt runtime start requires the caller's transaction")
        if not 0 < len(prompt_version) <= 128 or started_at.tzinfo is None:
            raise ValueError("prompt runtime start requires a version and aware time")
        utc_start = started_at.astimezone(UTC)
        inserted = self._session.scalar(
            insert(AnalysisPromptRuntimeSession)
            .values(
                id=run_id,
                prompt_version=prompt_version,
                ai_enabled=ai_enabled,
                started_at=utc_start,
                last_seen_at=utc_start,
                stopped_at=None,
            )
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(AnalysisPromptRuntimeSession.id)
        )
        if inserted is None:
            existing = self._session.get(AnalysisPromptRuntimeSession, run_id)
            if (
                existing is None
                or existing.prompt_version != prompt_version
                or existing.ai_enabled != ai_enabled
                or existing.started_at != utc_start
            ):
                raise ValueError("prompt runtime run ID conflicts with another configuration")
            return False
        if ai_enabled:
            self.record_prompt_activation_in_transaction(
                prompt_version=prompt_version, activated_at=utc_start
            )
        return True

    def heartbeat_prompt_runtime_in_transaction(
        self, *, run_id: UUID, observed_at: datetime
    ) -> bool:
        """Extend only a live scheduler run's confirmed configuration interval."""
        if not self._session.in_transaction():
            raise RuntimeError("prompt runtime heartbeat requires the caller's transaction")
        if observed_at.tzinfo is None:
            raise ValueError("prompt runtime heartbeat requires aware time")
        runtime = self._session.get(AnalysisPromptRuntimeSession, run_id, with_for_update=True)
        if runtime is None:
            raise LookupError("prompt runtime session is missing")
        utc_seen = observed_at.astimezone(UTC)
        if runtime.stopped_at is not None or utc_seen < runtime.last_seen_at:
            raise ValueError("prompt runtime heartbeat is stopped or out of order")
        if utc_seen == runtime.last_seen_at:
            return False
        runtime.last_seen_at = utc_seen
        return True

    def stop_prompt_runtime_in_transaction(self, *, run_id: UUID, stopped_at: datetime) -> bool:
        """Close a normally exiting run without inventing a crash end time."""
        if not self._session.in_transaction():
            raise RuntimeError("prompt runtime stop requires the caller's transaction")
        if stopped_at.tzinfo is None:
            raise ValueError("prompt runtime stop requires aware time")
        runtime = self._session.get(AnalysisPromptRuntimeSession, run_id, with_for_update=True)
        if runtime is None:
            raise LookupError("prompt runtime session is missing")
        utc_stop = stopped_at.astimezone(UTC)
        if runtime.stopped_at is not None:
            if runtime.stopped_at != utc_stop:
                raise ValueError("prompt runtime session already stopped at another time")
            return False
        if utc_stop < runtime.last_seen_at:
            raise ValueError("prompt runtime stop precedes last heartbeat")
        runtime.last_seen_at = utc_stop
        runtime.stopped_at = utc_stop
        return True

    def collection_analysis_counts_in_transaction(
        self,
        *,
        owner_id: UUID,
        targets_by_job: Mapping[UUID, tuple[UUID, int, tuple[UUID, ...]]],
    ) -> dict[UUID, WindowAnnotationCountView | None]:
        """Count frozen analysis targets for a bounded page of collection jobs.

        A missing or conflicting prompt identity is unknown, not a pending zero.
        Every target version must have a persisted annotation or analysis Job scope
        identifying the same prompt version before its Job can be counted.
        The caller must supply a complete, proven target set; an empty tuple is
        treated as a confirmed zero only under that contract.
        """
        if not self._session.in_transaction():
            raise RuntimeError("collection analysis reads require the caller's transaction")
        if len(targets_by_job) > _MAX_COLLECTION_ANALYSIS_JOBS:
            raise ValueError("collection analysis reads allow at most 100 jobs")
        if not targets_by_job:
            return {}

        contexts = load_content_job_contexts(
            self._session, owner_id=owner_id, job_ids=set(targets_by_job)
        )
        zero = WindowAnnotationCountView(
            total_count=0,
            annotated_count=0,
            pending_count=0,
            failed_count=0,
            abnormal_count=0,
        )
        result: dict[UUID, WindowAnnotationCountView | None] = {
            job_id: None for job_id in targets_by_job
        }
        known: dict[UUID, tuple[UUID, int, set[UUID]]] = {}
        targets_by_scope: dict[tuple[UUID, int], set[UUID]] = {}
        for job_id, (topic_id, rule_version, version_ids) in targets_by_job.items():
            if len(set(version_ids)) != len(version_ids):
                raise ValueError("collection analysis content versions must be distinct")
            context = contexts.get(job_id)
            if context is None or rule_version < 1:
                continue
            if context.configuration_ref.startswith("topic:") and (
                context.configuration_ref != f"topic:{topic_id}"
                or context.configuration_version != rule_version
            ):
                continue
            if not version_ids:
                result[job_id] = zero
                continue
            versions = set(version_ids)
            known[job_id] = (topic_id, rule_version, versions)
            targets_by_scope.setdefault((topic_id, rule_version), set()).update(versions)
        if not known:
            return result

        prompt_by_target: dict[tuple[UUID, int, UUID], set[str]] = {}
        annotation_states: dict[tuple[UUID, int, str, UUID], str] = {}
        all_versions = sorted(
            {version for versions in targets_by_scope.values() for version in versions},
            key=str,
        )
        topic_ids = {topic_id for topic_id, _ in targets_by_scope}
        rule_versions = {rule_version for _, rule_version in targets_by_scope}
        for start in range(0, len(all_versions), _ANNOTATION_READ_BATCH_SIZE):
            batch = all_versions[start : start + _ANNOTATION_READ_BATCH_SIZE]
            rows = self._session.execute(
                select(
                    ContentAnnotation.topic_id,
                    ContentAnnotation.topic_rule_version,
                    ContentAnnotation.content_version_id,
                    ContentAnnotation.prompt_version,
                    ContentAnnotation.result_state,
                ).where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.topic_id.in_(topic_ids),
                    ContentAnnotation.topic_rule_version.in_(rule_versions),
                    ContentAnnotation.content_version_id.in_(batch),
                )
            ).all()
            for topic_id, rule_version, version_id, prompt_version, state in rows:
                if version_id not in targets_by_scope.get((topic_id, rule_version), ()):
                    continue
                prompt_by_target.setdefault((topic_id, rule_version, version_id), set()).add(
                    prompt_version
                )
                annotation_states[(topic_id, rule_version, prompt_version, version_id)] = state

        failed_targets: set[tuple[UUID, int, str, UUID]] = set()
        invalid_scopes: set[tuple[UUID, int]] = set()
        # The jobs domain owns its ORM; read its owner-scoped DTOs once for the page.
        analysis_jobs = CollectionDueWindowService(self._session).list_analysis_jobs_in_transaction(
            owner_id=owner_id, topic_ids=topic_ids
        )
        for job in analysis_jobs:
            raw_topic = job.scope.get("topic_id")
            raw_rule = job.scope.get("topic_rule_version")
            if not isinstance(raw_rule, int) or isinstance(raw_rule, bool):
                continue
            try:
                scope_key = (UUID(str(raw_topic)), raw_rule)
            except ValueError:
                continue
            candidate_versions = targets_by_scope.get(scope_key)
            if candidate_versions is None:
                continue
            try:
                scope = AnalysisJobScope.from_job_scope(job.scope)
            except (TypeError, ValueError, ValidationError):
                invalid_scopes.add(scope_key)
                continue
            matched = candidate_versions.intersection(scope.content_version_ids)
            for version_id in matched:
                prompt_by_target.setdefault((*scope_key, version_id), set()).add(
                    scope.prompt_version
                )
                if job.status in {
                    JobStatus.FAILED,
                    JobStatus.PARTIALLY_SUCCEEDED,
                    JobStatus.CANCELLED,
                }:
                    failed_targets.add((*scope_key, scope.prompt_version, version_id))

        for job_id, (topic_id, rule_version, versions) in known.items():
            scope_key = (topic_id, rule_version)
            if scope_key in invalid_scopes:
                continue
            prompts = {
                prompt
                for version_id in versions
                for prompt in prompt_by_target.get((topic_id, rule_version, version_id), ())
            }
            if len(prompts) != 1 or any(
                len(prompt_by_target.get((topic_id, rule_version, version_id), ())) != 1
                for version_id in versions
            ):
                continue
            prompt_version = prompts.pop()
            annotated = abnormal = failed = 0
            for version_id in versions:
                target = (topic_id, rule_version, prompt_version, version_id)
                state = annotation_states.get(target)
                if state == AnnotationResultState.VALID.value:
                    annotated += 1
                elif state == AnnotationResultState.INVALID.value:
                    abnormal += 1
                elif state == AnnotationResultState.FAILED.value or target in failed_targets:
                    failed += 1
            result[job_id] = WindowAnnotationCountView(
                total_count=len(versions),
                annotated_count=annotated,
                pending_count=len(versions) - annotated - abnormal - failed,
                failed_count=failed,
                abnormal_count=abnormal,
            )
        return result

    def window_annotation_counts_in_transaction(
        self,
        *,
        owner_id: UUID,
        topic_id: UUID,
        topic_rule_version: int,
        prompt_version: str,
        content_version_ids: tuple[UUID, ...],
    ) -> WindowAnnotationCountView:
        """Separate missing annotations, failed jobs and malformed model output."""
        if not self._session.in_transaction():
            raise RuntimeError("annotation count reads require the caller's transaction")
        if len(set(content_version_ids)) != len(content_version_ids):
            raise ValueError("content version identities must be distinct")
        if not content_version_ids:
            return WindowAnnotationCountView(
                total_count=0,
                annotated_count=0,
                pending_count=0,
                failed_count=0,
                abnormal_count=0,
            )
        annotations = self._session.scalars(
            select(ContentAnnotation).where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.topic_rule_version == topic_rule_version,
                ContentAnnotation.prompt_version == prompt_version,
                ContentAnnotation.content_version_id.in_(content_version_ids),
            )
        ).all()
        annotated = {
            row.content_version_id
            for row in annotations
            if row.result_state == AnnotationResultState.VALID.value
        }
        abnormal = {
            row.content_version_id
            for row in annotations
            if row.result_state == AnnotationResultState.INVALID.value
        }
        row_failed = {
            row.content_version_id
            for row in annotations
            if row.result_state == AnnotationResultState.FAILED.value
        }
        row_pending = {
            row.content_version_id
            for row in annotations
            if row.result_state == AnnotationResultState.PENDING.value
        }
        failed: set[UUID] = set()
        for job in CollectionDueWindowService(self._session).list_analysis_jobs_in_transaction(
            owner_id=owner_id
        ):
            if job.status not in {
                JobStatus.FAILED,
                JobStatus.PARTIALLY_SUCCEEDED,
                JobStatus.CANCELLED,
            }:
                continue
            scope = AnalysisJobScope.from_job_scope(job.scope)
            if (
                scope.topic_id == topic_id
                and scope.topic_rule_version == topic_rule_version
                and scope.prompt_version == prompt_version
            ):
                failed.update(set(scope.content_version_ids) & set(content_version_ids))
        failed.update(row_failed)
        failed.difference_update(annotated | abnormal | row_pending)
        pending = set(content_version_ids) - annotated - abnormal - failed
        return WindowAnnotationCountView(
            total_count=len(content_version_ids),
            annotated_count=len(annotated),
            pending_count=len(pending),
            failed_count=len(failed),
            abnormal_count=len(abnormal),
        )

    def enqueue_due_batches_in_transaction(
        self,
        *,
        owner_id: UUID,
        topic_id: UUID,
        now: datetime,
    ) -> tuple[JobView, ...]:
        """Accept due topic batches inside the scheduler-owned transaction."""
        if not self._session.in_transaction():
            raise RuntimeError("analysis scanning requires the caller's transaction")
        if now.tzinfo is None:
            raise ValueError("analysis scan time must be timezone-aware")
        rule_version, rules, source_keys = MonitorTopicService(
            self._session
        ).get_current_topic_rules_and_sources_in_transaction(owner_id=owner_id, topic_id=topic_id)
        candidates = load_post_versions_for_analysis_scan(
            self._session,
            owner_id=owner_id,
            topic_id=topic_id,
            source_keys=source_keys,
        )
        matched = tuple(
            item for item in candidates if evaluate_monitor_rules(rules, _post_text(item)).matched
        )
        if not matched:
            return ()
        annotations: dict[UUID, str] = {}
        for start in range(0, len(matched), _ANNOTATION_READ_BATCH_SIZE):
            version_ids = tuple(
                item.content_version_id
                for item in matched[start : start + _ANNOTATION_READ_BATCH_SIZE]
            )
            annotations.update(
                {
                    row.content_version_id: row.result_state
                    for row in self._session.scalars(
                        select(ContentAnnotation).where(
                            ContentAnnotation.owner_id == owner_id,
                            ContentAnnotation.topic_id == topic_id,
                            ContentAnnotation.topic_rule_version == rule_version,
                            ContentAnnotation.prompt_version == ANALYSIS_PROMPT_VERSION,
                            ContentAnnotation.content_version_id.in_(version_ids),
                        )
                    )
                }
            )
        jobs_by_version: dict[UUID, list[tuple[JobStatus, int, bool]]] = {}
        for job in CollectionDueWindowService(self._session).list_analysis_jobs_in_transaction(
            owner_id=owner_id, topic_ids={topic_id}
        ):
            try:
                scope = AnalysisJobScope.from_job_scope(job.scope)
            except (TypeError, ValueError, ValidationError):
                continue
            if (
                scope.topic_id != topic_id
                or scope.topic_rule_version != rule_version
                or scope.prompt_version != ANALYSIS_PROMPT_VERSION
            ):
                continue
            for version_id in scope.content_version_ids:
                jobs_by_version.setdefault(version_id, []).append(
                    (job.status, scope.retry_index, scope.prompt_items is not None)
                )

        fresh: list[AnalysisPostContentView] = []
        retry: list[AnalysisPostContentView] = []
        terminal = {
            JobStatus.SUCCEEDED,
            JobStatus.PARTIALLY_SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
        for item in matched:
            state = annotations.get(item.content_version_id)
            attempts = jobs_by_version.get(item.content_version_id, [])
            if state in {AnnotationResultState.VALID.value, AnnotationResultState.FAILED.value}:
                continue
            if state == AnnotationResultState.INVALID.value:
                if any(index == 1 for _, index, _ in attempts) or any(
                    status not in terminal for status, _, _ in attempts
                ):
                    continue
                retry.append(item)
            elif (
                attempts
                and all(status in terminal for status, _, _ in attempts)
                and any(not frozen for _, _, frozen in attempts)
                and not any(index == 1 for _, index, _ in attempts)
            ):
                # Old Jobs cannot recover their unfrozen comments. Admit a distinct
                # replacement only after their terminal failure; never reinterpret them.
                retry.append(item)
            elif not attempts:
                fresh.append(item)

        due = tuple([*retry, *fresh])
        if not due:
            return ()
        comments = load_post_comments_for_analysis(
            self._session,
            owner_id=owner_id,
            post_content_ids={item.content_id for item in due},
            limit_per_post=51,
        )
        prompt_items = {
            item.content_version_id: _prompt_item(
                item, comments=tuple(comment.text for comment in comments.get(item.content_id, ()))
            )
            for item in due
        }
        accepted: list[JobView] = []
        planned = [
            (batch, 1)
            for item in retry
            for batch in pack_prompt_batches((prompt_items[item.content_version_id],))
        ]
        planned.extend(
            (batch, 0)
            for batch in pack_prompt_batches(
                tuple(prompt_items[item.content_version_id] for item in fresh)
            )
        )
        job_service = JobService(self._session, clock=lambda: now)
        for batch, retry_index in planned[:_MAX_SCAN_BATCHES]:
            content_version_ids = tuple(
                sorted((item.content_version_id for item in batch), key=str)
            )
            operation_id = analysis_operation_id(
                topic_id=topic_id,
                topic_rule_version=rule_version,
                content_version_ids=content_version_ids,
                prompt_version=ANALYSIS_PROMPT_VERSION,
                retry_index=retry_index,
            )
            if job_service.operation_exists_in_transaction(
                owner_id=owner_id, kind="analysis.annotate", operation_id=operation_id
            ):
                continue
            accepted.append(
                job_service.accept_in_transaction(
                    owner_id=owner_id,
                    command=JobAcceptanceInput(
                        operation_id=operation_id,
                        kind="analysis.annotate",
                        observation=JobObservationContext(
                            configuration_ref=f"topic:{topic_id}",
                            configuration_version=rule_version,
                        ),
                        scope=AnalysisJobScope(
                            topic_id=topic_id,
                            topic_rule_version=rule_version,
                            prompt_version=ANALYSIS_PROMPT_VERSION,
                            content_version_ids=content_version_ids,
                            prompt_items=batch,
                            retry_index=retry_index,
                        ).to_job_scope(),
                    ),
                )
            )
        return tuple(accepted)

    def missing_content_version_ids_in_transaction(
        self,
        *,
        owner_id: UUID,
        topic_id: UUID,
        topic_rule_version: int,
        prompt_version: str,
        content_version_ids: Sequence[UUID],
    ) -> tuple[UUID, ...]:
        if not self._session.in_transaction():
            raise RuntimeError("analysis reads require the caller's transaction")
        existing = set(
            self._session.scalars(
                select(ContentAnnotation.content_version_id).where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.topic_id == topic_id,
                    ContentAnnotation.topic_rule_version == topic_rule_version,
                    ContentAnnotation.prompt_version == prompt_version,
                    ContentAnnotation.content_version_id.in_(content_version_ids),
                    ContentAnnotation.result_state == AnnotationResultState.VALID.value,
                )
            )
        )
        return tuple(item for item in content_version_ids if item not in existing)

    def persist_results_in_transaction(
        self,
        *,
        owner_id: UUID,
        topic_id: UUID,
        topic_rule_version: int,
        prompt_version: str,
        posts: Mapping[UUID, AnalysisPostContentView],
        results: Sequence[AnnotationWrite],
        created_at: datetime,
    ) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("analysis writes require the caller's transaction")
        if created_at.tzinfo is None:
            raise ValueError("analysis creation time must be timezone-aware")
        for result in results:
            post = posts.get(result.content_version_id)
            if post is None:
                raise ValueError("analysis result references an unfrozen content version")
            self._session.execute(
                insert(ContentAnnotation)
                .values(
                    id=uuid4(),
                    owner_id=owner_id,
                    content_id=post.content_id,
                    content_version_id=result.content_version_id,
                    topic_id=topic_id,
                    topic_rule_version=topic_rule_version,
                    prompt_version=prompt_version,
                    relevant=result.relevant,
                    relevance_reason=result.relevance_reason,
                    sentiment=result.sentiment.value if result.sentiment is not None else None,
                    summary=result.summary,
                    viewpoints=list(result.viewpoints),
                    ai_call_id=result.ai_call_id,
                    status=result.status.value,
                    result_state=result.result_state.value,
                    error_code=result.error_code,
                    diagnostic_history=[],
                    first_valid_at=(
                        created_at if result.result_state is AnnotationResultState.VALID else None
                    ),
                    created_at=created_at,
                    updated_at=created_at,
                )
                .on_conflict_do_nothing(
                    constraint="content_annotations_owner_version_topic_rule_prompt_key"
                )
            )
            current = self._session.scalar(
                select(ContentAnnotation)
                .where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.content_version_id == result.content_version_id,
                    ContentAnnotation.topic_id == topic_id,
                    ContentAnnotation.topic_rule_version == topic_rule_version,
                    ContentAnnotation.prompt_version == prompt_version,
                )
                .with_for_update()
            )
            if current is None:
                raise RuntimeError("annotation insertion did not produce a row")
            if (
                current.ai_call_id == result.ai_call_id
                and current.result_state == result.result_state.value
            ):
                continue
            diagnostic = {
                "result_state": result.result_state.value,
                "error_code": result.error_code,
                "ai_call_id": str(result.ai_call_id) if result.ai_call_id else None,
                "recorded_at": created_at.astimezone(UTC).isoformat(),
            }
            history = list(current.diagnostic_history)
            if current.result_state == AnnotationResultState.VALID.value:
                if result.result_state is not AnnotationResultState.VALID and not any(
                    entry.get("ai_call_id") == diagnostic["ai_call_id"]
                    and entry.get("result_state") == diagnostic["result_state"]
                    for entry in history
                ):
                    current.diagnostic_history = [*history, diagnostic]
                    current.updated_at = max(current.updated_at, created_at)
                continue
            if result.result_state is AnnotationResultState.PENDING:
                continue
            if (
                created_at < current.updated_at
                and result.result_state is not AnnotationResultState.VALID
            ):
                if not any(
                    entry.get("ai_call_id") == diagnostic["ai_call_id"]
                    and entry.get("result_state") == diagnostic["result_state"]
                    for entry in history
                ):
                    current.diagnostic_history = [*history, diagnostic]
                continue
            previous = {
                "result_state": current.result_state,
                "error_code": current.error_code,
                "ai_call_id": str(current.ai_call_id) if current.ai_call_id else None,
                "recorded_at": current.updated_at.astimezone(UTC).isoformat(),
            }
            if current.result_state != AnnotationResultState.PENDING.value and not any(
                entry.get("ai_call_id") == previous["ai_call_id"]
                and entry.get("result_state") == previous["result_state"]
                for entry in history
            ):
                history.append(previous)
            current.diagnostic_history = history
            current.status = result.status.value
            current.result_state = result.result_state.value
            current.error_code = result.error_code
            current.ai_call_id = result.ai_call_id
            current.relevant = result.relevant
            current.relevance_reason = result.relevance_reason
            current.sentiment = result.sentiment.value if result.sentiment else None
            current.summary = result.summary
            current.viewpoints = list(result.viewpoints)
            if result.result_state is AnnotationResultState.VALID:
                current.first_valid_at = created_at
            current.updated_at = max(current.updated_at, created_at)


class AnalysisAnnotateExecutor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, message: JobMessage) -> AnalysisExecutionResult:
        scope, rules, posts, items = self._load_execution(message)
        if not items:
            return AnalysisExecutionResult(
                completion=JobCompletion(status=JobStatus.SUCCEEDED),
                processed_items=len(scope.content_version_ids),
            )
        if (
            len(items) > _MAX_BATCH_ITEMS
            or len(serialize_analysis_data(items)) > _MAX_SERIALIZED_CHARACTERS
            or any(len(item.body or "") > _MAX_BODY_CHARACTERS for item in items)
            or any(len(item.comments) > _MAX_COMMENTS_PER_POST for item in items)
        ):
            raise self._configuration_failure("analysis_batch_scope_invalid")
        try:
            client = create_ai_client(self._settings)
        except AiCallError as error:
            raise analysis_failure(error, now=self._clock()) from error
        try:
            try:
                with self._sessions() as session:
                    completion = AiService(session, client, clock=self._clock).complete(
                        owner_id=message.owner_id,
                        job_id=message.job_id,
                        purpose="analysis.annotate",
                        prompt_version=scope.prompt_version,
                        prompt=build_analysis_prompt(
                            items=items,
                            match_any=rules.match_any,
                            match_all=rules.match_all,
                            exclude=rules.exclude,
                        ),
                        output_schema=ANALYSIS_OUTPUT_SCHEMA,
                    )
            except AiCallError as error:
                self._persist_results(
                    message=message,
                    scope=scope,
                    posts=posts,
                    results=tuple(
                        AnnotationWrite(
                            content_version_id=item.content_version_id,
                            ai_call_id=error.call_id,
                            status=AnnotationStatus.UNANALYZED,
                            result_state=(
                                AnnotationResultState.FAILED
                                if error.call_id is not None
                                else AnnotationResultState.PENDING
                            ),
                            error_code=(
                                f"analysis_{error.code.value}"
                                if error.call_id is not None
                                else None
                            ),
                        )
                        for item in items
                    ),
                )
                raise analysis_failure(error, now=self._clock()) from error
            if completion.call_id is None:
                raise self._configuration_failure("analysis_ai_call_missing")
            try:
                envelope = AnnotationOutputEnvelope.model_validate(completion.output)
            except ValidationError as error:
                self._persist_results(
                    message=message,
                    scope=scope,
                    posts=posts,
                    results=tuple(
                        AnnotationWrite(
                            content_version_id=item.content_version_id,
                            ai_call_id=completion.call_id,
                            status=AnnotationStatus.UNANALYZED,
                            result_state=(
                                AnnotationResultState.FAILED
                                if scope.retry_index == 1
                                else AnnotationResultState.INVALID
                            ),
                            error_code=(
                                "analysis_invalid_exhausted"
                                if scope.retry_index == 1
                                else "analysis_output_envelope_invalid"
                            ),
                        )
                        for item in items
                    ),
                )
                raise JobExecutionFailure(
                    error_code="analysis_invalid_output",
                    category=JobFailureCategory.INVALID_RESPONSE,
                    occurred_at=self._clock(),
                    next_action="检查模型批量输出对象后手动重试",
                    manual_retry_allowed=True,
                ) from error
            results = resolve_annotation_results(
                expected_content_version_ids=tuple(item.content_version_id for item in items),
                raw_items=envelope.items,
                ai_call_id=completion.call_id,
                retry_index=scope.retry_index,
            )
            self._persist_results(message=message, scope=scope, posts=posts, results=results)
            invalid_count = sum(result.status is AnnotationStatus.UNANALYZED for result in results)
            job_completion = (
                JobCompletion(status=JobStatus.SUCCEEDED)
                if invalid_count == 0
                else JobCompletion(
                    status=JobStatus.PARTIALLY_SUCCEEDED,
                    failure=JobExecutionFailure(
                        error_code="analysis_items_invalid",
                        category=JobFailureCategory.INVALID_RESPONSE,
                        occurred_at=self._clock(),
                        next_action=(
                            "检查最终无效条目的模型输出后人工处理"
                            if scope.retry_index == 1
                            else "由分析补偿流程重试无效条目"
                        ),
                        manual_retry_allowed=scope.retry_index == 1,
                    ),
                )
            )
            return AnalysisExecutionResult(
                completion=job_completion,
                processed_items=len(scope.content_version_ids),
            )
        finally:
            client.close()

    def _persist_results(
        self,
        *,
        message: JobMessage,
        scope: AnalysisJobScope,
        posts: Mapping[UUID, AnalysisPostContentView],
        results: Sequence[AnnotationWrite],
    ) -> None:
        with self._sessions() as session, session.begin():
            AnalysisService(session).persist_results_in_transaction(
                owner_id=message.owner_id,
                topic_id=scope.topic_id,
                topic_rule_version=scope.topic_rule_version,
                prompt_version=scope.prompt_version,
                posts=posts,
                results=results,
                created_at=self._clock(),
            )

    def _load_execution(
        self,
        message: JobMessage,
    ) -> tuple[
        AnalysisJobScope,
        NormalizedMonitorRules,
        dict[UUID, AnalysisPostContentView],
        tuple[AnalysisPromptItem, ...],
    ]:
        with self._sessions() as session, session.begin():
            configuration = load_job_execution_configuration(session, job_id=message.job_id)
            if configuration is None:
                raise self._configuration_failure("analysis_job_missing")
            try:
                scope = AnalysisJobScope.from_job_scope(configuration.scope)
            except (TypeError, ValueError, ValidationError) as error:
                raise self._configuration_failure("analysis_scope_invalid") from error
            expected_operation_id = analysis_operation_id(
                topic_id=scope.topic_id,
                topic_rule_version=scope.topic_rule_version,
                content_version_ids=scope.content_version_ids,
                prompt_version=scope.prompt_version,
                retry_index=scope.retry_index,
            )
            if (
                configuration.owner_id != message.owner_id
                or configuration.operation_id != message.operation_id
                or configuration.operation_id != expected_operation_id
                or configuration.kind != "analysis.annotate"
                or configuration.observation.configuration_ref != f"topic:{scope.topic_id}"
                or configuration.observation.configuration_version != scope.topic_rule_version
                or configuration.observation.source_key is not None
                or scope.prompt_version != ANALYSIS_PROMPT_VERSION
                or tuple(sorted(scope.content_version_ids, key=str)) != scope.content_version_ids
            ):
                raise self._configuration_failure("analysis_scope_mismatch")
            if scope.prompt_items is None:
                raise self._configuration_failure("analysis_frozen_input_missing")
            rules = MonitorTopicService(session).get_topic_rules_in_transaction(
                owner_id=message.owner_id,
                topic_id=scope.topic_id,
                version=scope.topic_rule_version,
            )
            missing_ids = AnalysisService(session).missing_content_version_ids_in_transaction(
                owner_id=message.owner_id,
                topic_id=scope.topic_id,
                topic_rule_version=scope.topic_rule_version,
                prompt_version=scope.prompt_version,
                content_version_ids=scope.content_version_ids,
            )
            loaded_posts = load_post_versions_for_analysis(
                session,
                owner_id=message.owner_id,
                content_version_ids=set(missing_ids),
            )
            posts = {item.content_version_id: item for item in loaded_posts}
            if len(posts) != len(missing_ids):
                raise self._configuration_failure("analysis_content_missing")
            frozen = {item.content_version_id: item for item in scope.prompt_items}
            items = tuple(frozen[content_version_id] for content_version_id in missing_ids)
            for item in items:
                post = posts[item.content_version_id]
                frozen_body = post.body[:_MAX_BODY_CHARACTERS] if post.body is not None else None
                if (
                    item.content_id != post.content_id
                    or item.title != post.title
                    or item.body != frozen_body
                    or item.body_truncated
                    != (post.body is not None and len(post.body) > _MAX_BODY_CHARACTERS)
                ):
                    raise self._configuration_failure("analysis_frozen_content_mismatch")
        return scope, rules, posts, items

    def _configuration_failure(self, code: str) -> JobExecutionFailure:
        return JobExecutionFailure(
            error_code=code,
            category=JobFailureCategory.CONFIGURATION_UNAVAILABLE,
            occurred_at=self._clock(),
            next_action="重新扫描并受理与当前主题和内容版本一致的分析任务",
            manual_retry_allowed=True,
        )


def _post_text(post: AnalysisPostContentView) -> str:
    return "\n".join(part for part in (post.title, post.body) if part)


def _prompt_item(
    post: AnalysisPostContentView,
    *,
    comments: tuple[str, ...],
) -> AnalysisPromptItem:
    return AnalysisPromptItem(
        content_id=post.content_id,
        content_version_id=post.content_version_id,
        title=post.title,
        body=post.body[:_MAX_BODY_CHARACTERS] if post.body is not None else None,
        comments=comments[: _MAX_COMMENTS_PER_POST + 1],
        body_truncated=post.body is not None and len(post.body) > _MAX_BODY_CHARACTERS,
        comments_truncated=len(comments) > _MAX_COMMENTS_PER_POST,
    )
