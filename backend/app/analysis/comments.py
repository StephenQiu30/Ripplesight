"""Accept bounded independent relevance jobs for already collected comments."""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ai.analysis_reading import load_legacy_analysis_call_job_in_transaction
from ai.capability_services import freeze_ai_job_scope_in_transaction
from analysis.models import CommentAnalysisScanCursor, ContentAnnotation
from analysis.prompts import COMMENT_ANALYSIS_PROMPT_VERSION, serialize_analysis_data
from analysis.reads import analysis_scope_inputs_readable_in_transaction
from analysis.schemas import (
    AnalysisJobScope,
    AnalysisPromptItem,
    AnnotationResultState,
    AnnotationStatus,
    AnnotationWrite,
)
from analysis.services import AnalysisService, analysis_operation_id
from content.analysis_inputs import freeze_analysis_observation_inputs_in_transaction
from content.comment_analysis import (
    load_comment_analysis_page_in_transaction,
    load_comment_analysis_post_page_in_transaction,
)
from content.comment_analysis_schemas import CommentAnalysisContext, CommentContextText
from content.schemas import AnalysisPostContentView
from core.config import Settings
from jobs.schemas import JobAcceptanceInput, JobObservationContext, JobStatus, JobView
from jobs.services import (
    JobService,
    load_job_cancellation_state_in_transaction,
    load_job_execution_configuration,
)
from monitors.services import MonitorTopicService, evaluate_monitor_rules


def comment_context_signature(context: CommentAnalysisContext) -> str:
    """Bind parent-chain completeness and truncated text in addition to observations."""
    return hashlib.sha256(
        json.dumps(
            [context.model_dump(mode="json")],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def fit_comment_context(context: CommentAnalysisContext) -> CommentAnalysisContext:
    """Bound escaped JSON before acceptance while explicitly marking shortened text.

    Returns:
        A context whose actual serialized input fits the executor's 24k budget.

    Raises:
        ValueError: Even the smallest allowed text cannot fit the input budget.
    """
    limit = 1500
    while limit >= 1:

        def shorten(item: CommentContextText, bound: int = limit) -> CommentContextText:
            return item.model_copy(
                update={
                    "text": item.text[:bound],
                    "truncated": item.truncated or len(item.text) > bound,
                }
            )

        fitted = context.model_copy(
            update={
                "post": shorten(context.post),
                "target": shorten(context.target),
                "parents": tuple(shorten(p) for p in context.parents),
            }
        )
        item = AnalysisPromptItem(
            content_id=fitted.target.content_id,
            content_version_id=fitted.target.content_version_id,
            body=fitted.target.text,
            body_truncated=fitted.target.truncated,
            comment_context=fitted,
        )
        if len(serialize_analysis_data((item,))) <= 24000:
            return fitted
        limit //= 2
    raise ValueError("comment context cannot fit the serialized budget")


class CommentAnalysisService:
    """Page comments without keyword filtering; accept at most twenty independent jobs."""

    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings

    def enqueue_due_in_transaction(
        self, *, owner_id: UUID, topic_id: UUID, now: datetime
    ) -> tuple[JobView, ...]:
        """Freeze new contexts and one bounded invalid-output compensation.

        Returns:
            New jobs; settled contexts are skipped so later pages remain reachable.

        Raises:
            RuntimeError: The caller has no transaction or a naive clock.
        """
        if not self._session.in_transaction() or now.utcoffset() is None:
            raise RuntimeError("comment analysis requires an aware caller transaction")
        rule_version, rules, source_keys = MonitorTopicService(
            self._session
        ).get_current_topic_rules_and_sources_in_transaction(
            owner_id=owner_id,
            topic_id=topic_id,
        )
        self._session.execute(
            insert(CommentAnalysisScanCursor)
            .values(
                owner_id=owner_id,
                topic_id=topic_id,
                topic_rule_version=rule_version,
                after_post_version_id=None,
                after_comment_id=None,
                after_invalid_annotation_id=None,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        cursor = self._session.get(
            CommentAnalysisScanCursor, (owner_id, topic_id), with_for_update=True
        )
        if cursor is None:
            raise RuntimeError("comment scan cursor was not inserted")
        if cursor.topic_rule_version != rule_version:
            cursor.topic_rule_version = rule_version
            cursor.after_post_version_id = cursor.after_comment_id = None
            cursor.after_invalid_annotation_id = None
        cursor.updated_at = now
        posts, last_raw_post, exhausted = load_comment_analysis_post_page_in_transaction(
            self._session,
            owner_id=owner_id,
            topic_id=topic_id,
            topic_rule_version=rule_version,
            source_keys=source_keys,
            now=now,
            after=cursor.after_post_version_id,
            resume=cursor.after_comment_id is not None,
        )
        accepted: list[JobView] = []
        service = JobService(self._session, clock=lambda: now)
        # Advance even over cancelled/unreadable jobs so they cannot starve later rows.
        invalid_query = select(ContentAnnotation).where(
            ContentAnnotation.owner_id == owner_id,
            ContentAnnotation.topic_id == topic_id,
            ContentAnnotation.topic_rule_version == rule_version,
            ContentAnnotation.prompt_version == COMMENT_ANALYSIS_PROMPT_VERSION,
            ContentAnnotation.result_state == AnnotationResultState.INVALID.value,
        )
        if cursor.after_invalid_annotation_id is not None:
            invalid_query = invalid_query.where(
                ContentAnnotation.id > cursor.after_invalid_annotation_id
            )
        invalid_rows = self._session.scalars(
            invalid_query.order_by(ContentAnnotation.id).limit(20)
        ).all()
        cursor.after_invalid_annotation_id = (
            invalid_rows[-1].id if len(invalid_rows) == 20 else None
        )
        for row in invalid_rows:
            if row.ai_call_id is None:
                continue
            job_id = load_legacy_analysis_call_job_in_transaction(
                self._session,
                owner_id=owner_id,
                ai_call_id=row.ai_call_id,
                prompt_version=COMMENT_ANALYSIS_PROMPT_VERSION,
            )
            job = load_job_execution_configuration(self._session, job_id=job_id) if job_id else None
            state = (
                load_job_cancellation_state_in_transaction(
                    self._session, owner_id=owner_id, job_id=job_id
                )
                if job_id
                else None
            )
            if (
                job is None
                or state is None
                or state.requested_at is not None
                or state.status
                not in {
                    JobStatus.SUCCEEDED,
                    JobStatus.PARTIALLY_SUCCEEDED,
                    JobStatus.FAILED,
                }
            ):
                continue
            try:
                scope = AnalysisJobScope.from_job_scope(job.scope)
            except (ValueError, ValidationError):
                continue
            if (
                scope.topic_rule_version != rule_version
                or scope.retry_index != 0
                or scope.input_manifest is None
                or not analysis_scope_inputs_readable_in_transaction(
                    self._session, owner_id=owner_id, scope=scope, now=now
                )
            ):
                continue
            result = self._accept(
                service,
                owner_id=owner_id,
                scope=scope.model_copy(update={"retry_index": 1}),
                frozen_ai=job.scope,
                now=now,
            )
            if result is not None:
                accepted.append(result)
                if len(accepted) == 20:
                    return tuple(accepted)
        scanned = 0
        initial_post, initial_comment = cursor.after_post_version_id, cursor.after_comment_id
        for post in posts:
            if not evaluate_monitor_rules(
                rules, "\n".join(p for p in (post.title, post.body) if p)
            ).matched:
                continue
            after = initial_comment if post.content_version_id == initial_post else None
            while True:
                contexts, after = load_comment_analysis_page_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    post=post,
                    now=now,
                    after=after,
                )
                scanned += 50
                for context in contexts:
                    context = fit_comment_context(context)
                    manifest = freeze_analysis_observation_inputs_in_transaction(
                        self._session,
                        owner_id=owner_id,
                        post_observations={
                            context.post.content_version_id: context.post.observation_id
                        },
                        comment_observations={
                            t.content_version_id: t.observation_id
                            for t in (context.target, *context.parents)
                        },
                        context_signature=comment_context_signature(context),
                        now=now,
                    )
                    item = AnalysisPromptItem(
                        content_id=context.target.content_id,
                        content_version_id=context.target.content_version_id,
                        body=context.target.text,
                        body_truncated=context.target.truncated,
                        comment_context=context,
                    )
                    scope = AnalysisJobScope(
                        topic_id=topic_id,
                        topic_rule_version=rule_version,
                        prompt_version=COMMENT_ANALYSIS_PROMPT_VERSION,
                        content_version_ids=(item.content_version_id,),
                        prompt_items=(item,),
                        input_manifest=manifest,
                    )
                    result = self._accept(service, owner_id=owner_id, scope=scope, now=now)
                    if result is not None:
                        accepted.append(result)
                        if len(accepted) == 20:
                            cursor.after_post_version_id = post.content_version_id
                            cursor.after_comment_id = context.target.content_id
                            return tuple(accepted)
                cursor.after_post_version_id = post.content_version_id
                cursor.after_comment_id = after
                if scanned >= 500:
                    return tuple(accepted)
                if after is None:
                    break
        cursor.after_post_version_id = None if exhausted else last_raw_post
        cursor.after_comment_id = None
        return tuple(accepted)

    def _accept(
        self,
        service: JobService,
        *,
        owner_id: UUID,
        scope: AnalysisJobScope,
        now: datetime,
        frozen_ai: dict[str, str | int | bool | None] | None = None,
    ) -> JobView | None:
        if scope.input_manifest is None:
            raise ValueError("comment analysis requires a frozen manifest")
        operation = analysis_operation_id(
            topic_id=scope.topic_id,
            topic_rule_version=scope.topic_rule_version,
            content_version_ids=scope.content_version_ids,
            prompt_version=scope.prompt_version,
            retry_index=scope.retry_index,
            input_signature=scope.input_manifest.signature,
        )
        if service.operation_exists_in_transaction(
            owner_id=owner_id, kind="analysis.annotate", operation_id=operation
        ):
            return None
        ai_scope: Mapping[str, str | int | bool | None]
        if frozen_ai is None:
            ai_scope = freeze_ai_job_scope_in_transaction(
                self._session, owner_id=owner_id, settings=self._settings
            )
        else:
            # Model configuration and provider identity are accepted once, including compensation.
            ai_scope = {key: value for key, value in frozen_ai.items() if key.startswith("ai_")}
        accepted = service.accept_in_transaction(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=operation,
                kind="analysis.annotate",
                observation=JobObservationContext(
                    configuration_ref=f"topic:{scope.topic_id}",
                    configuration_version=scope.topic_rule_version,
                ),
                scope={**scope.to_job_scope(), **ai_scope},
            ),
        )
        AnalysisService(self._session).persist_results_in_transaction(
            owner_id=owner_id,
            topic_id=scope.topic_id,
            topic_rule_version=scope.topic_rule_version,
            prompt_version=scope.prompt_version,
            input_manifest=scope.input_manifest,
            created_at=now,
            posts={
                item.content_version_id: AnalysisPostContentView(
                    content_id=item.content_id,
                    content_version_id=item.content_version_id,
                    title=None,
                    body=item.body,
                    observation_id=item.comment_context.target.observation_id,
                )
                for item in scope.prompt_items or ()
                if item.comment_context is not None
            },
            results=tuple(
                AnnotationWrite(
                    content_version_id=identifier,
                    status=AnnotationStatus.UNANALYZED,
                    result_state=AnnotationResultState.PENDING,
                )
                for identifier in scope.content_version_ids
            ),
        )
        return accepted
