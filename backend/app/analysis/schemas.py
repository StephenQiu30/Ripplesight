from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content.analysis_schemas import AnalysisObservationManifest
from content.comment_analysis_schemas import CommentAnalysisContext
from core.schemas import OutputModel


@dataclass(frozen=True, slots=True)
class EventAnnotationRef:
    owner_id: UUID
    topic_id: UUID
    topic_rule_version: int
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = ()
    annotation_id: UUID | None = None


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class AnnotationStatus(StrEnum):
    ANNOTATED = "annotated"
    UNANALYZED = "unanalyzed"


class AnnotationResultState(StrEnum):
    PENDING = "pending"
    FAILED = "failed"
    INVALID = "invalid"
    VALID = "valid"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"
    DEFERRED = "deferred"


class AnnotationDimensionResult(BaseModel):
    """Keep a validated dimension and its actual call independently of its siblings."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    state: Literal["valid", "invalid", "failed", "not_analyzed"]
    value: bool | str | tuple[str, ...] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, min_length=1, max_length=60)
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    ai_call_id: UUID

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        """Never carry an inferred value or turn malformed output into unanalysed output."""
        if (self.state == "valid") != (self.value is not None):
            raise ValueError("dimension value requires a valid outcome")
        if (self.state in {"invalid", "failed"}) != (self.error_code is not None):
            raise ValueError("dimension failures require an error code")
        if self.state != "valid" and (self.reason is not None or self.summary is not None):
            raise ValueError("non-conclusions cannot carry a reason or summary value")
        return self


class AnnotationDimensions(BaseModel):
    """Version the three independently validated results in one frozen input row."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    relevance: AnnotationDimensionResult
    sentiment: AnnotationDimensionResult
    viewpoints: AnnotationDimensionResult

    @model_validator(mode="after")
    def typed_values(self) -> Self:
        """Enforce dimension-specific types even when reading persisted JSON."""
        relevance = self.relevance
        if relevance.state == "not_analyzed":
            raise ValueError("this contract always requests relevance")
        if relevance.state == "valid" and (
            not isinstance(relevance.value, bool)
            or not relevance.reason
            or not relevance.reason.strip()
            or not relevance.summary
            or not relevance.summary.strip()
        ):
            raise ValueError("valid relevance requires a real boolean, reason and summary")
        if self.sentiment.state == "valid" and (
            not isinstance(self.sentiment.value, str)
            or self.sentiment.value not in {"positive", "neutral", "negative"}
        ):
            raise ValueError("invalid sentiment value")
        value = self.viewpoints.value
        if self.viewpoints.state == "valid" and (
            not isinstance(value, tuple)
            or not 1 <= len(value) <= 5
            or any(not item.strip() or len(item) > 200 for item in value)
        ):
            raise ValueError("invalid viewpoint value")
        if any(
            item.reason is not None or item.summary is not None
            for item in (self.sentiment, self.viewpoints)
        ):
            raise ValueError("optional dimensions have no model-provided reason or summary")
        return self


class ContentAnnotationReadView(OutputModel):
    id: UUID
    topic_id: UUID
    content_version_id: UUID
    topic_rule_version: int = Field(ge=1)
    prompt_version: str
    status: AnnotationStatus
    result_state: AnnotationResultState
    relevant: bool | None
    relevance_reason: str | None
    sentiment: Sentiment | None
    summary: str | None
    viewpoints: list[str]
    dimension_results: AnnotationDimensions | None = None
    error_code: str | None
    updated_at: datetime
    created_at: datetime | None = None


class WindowAnnotationCountView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_count: int = Field(ge=0)
    annotated_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    abnormal_count: int = Field(ge=0)


class AnalysisNeedLedgerRowView(OutputModel):
    content_version_id: UUID
    topic_id: UUID
    topic_rule_version: int = Field(ge=1)
    prompt_version: str
    source_key: str
    origin_status: Literal["candidate", "unknown"]
    started_at: datetime | None
    reason: str | None
    prompt_runtime_ids: tuple[UUID, ...]
    result_state: AnnotationResultState | None
    first_valid_at: datetime | None


class AnalysisNeedLedgerView(BaseModel):
    """Raw candidate IDs, never a certified Codex availability denominator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_version: Literal["analysis-candidate-v3"]
    analysis_status: Literal["not_computable"]
    start: datetime
    end: datetime
    cutoff_at: datetime
    candidate_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    matured_count: int = Field(ge=0)
    pending_observation_count: int = Field(ge=0)
    timely_valid_count: int = Field(ge=0)
    late_or_missing_count: int = Field(ge=0)
    rows: tuple[AnalysisNeedLedgerRowView, ...]


class AnalysisPromptItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_id: UUID
    content_version_id: UUID
    title: str | None = Field(default=None, max_length=2_000)
    body: str | None = Field(default=None, max_length=100_000)
    comments: tuple[str, ...] = Field(default=(), max_length=51)
    comment_version_ids: tuple[UUID, ...] | None = Field(default=None, max_length=51)
    body_truncated: bool = False
    comments_truncated: bool = False
    comment_context: CommentAnalysisContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def require_text(self) -> Self:
        if self.title is None and self.body is None:
            raise ValueError("analysis content requires title or body text")
        if any(not comment for comment in self.comments):
            raise ValueError("analysis comments must not be empty")
        if self.comment_version_ids is not None and (
            len(self.comment_version_ids) != len(self.comments)
            or len(set(self.comment_version_ids)) != len(self.comment_version_ids)
        ):
            raise ValueError("analysis comments require distinct aligned version references")
        return self


class AnalysisJobScope(BaseModel):
    """Freeze input identities, prompt contract and the single compensation index.

    Comment jobs require an exact post/target/parent context and its signed ALL
    observation manifest; post v1/v2 jobs preserve their separate legacy contract.
    Validation rejects a mismatched target, context digest or observation mapping.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: UUID
    topic_rule_version: int = Field(ge=1)
    prompt_version: str = Field(min_length=1, max_length=128)
    content_version_ids: tuple[UUID, ...] = Field(min_length=1, max_length=30)
    prompt_items: tuple[AnalysisPromptItem, ...] | None = Field(default=None, max_length=30)
    input_manifest: AnalysisObservationManifest | None = None
    retry_index: int = Field(default=0, ge=0, le=1)

    @field_validator("content_version_ids")
    @classmethod
    def require_distinct_versions(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("analysis content versions must be distinct")
        return value

    @model_validator(mode="after")
    def validate_frozen_items(self) -> Self:
        if self.prompt_items is not None and (
            tuple(sorted(item.content_version_id for item in self.prompt_items))
            != tuple(sorted(self.content_version_ids))
            or any(len(item.comments) > 50 for item in self.prompt_items)
        ):
            raise ValueError("frozen analysis items must match the content version scope")
        if self.prompt_items is not None:
            comment_mode = self.prompt_version == "analysis.comment.v1"
            if any(
                (item.comment_context is not None) != comment_mode for item in self.prompt_items
            ):
                raise ValueError("comment context requires its independent prompt version")
        if self.input_manifest is not None:
            contexts = tuple(
                item.comment_context
                for item in self.prompt_items or ()
                if item.comment_context is not None
            )
            if contexts:
                expected_posts = {
                    c.post.content_version_id: c.post.observation_id for c in contexts
                }
                expected_comments = {
                    t.content_version_id: t.observation_id
                    for c in contexts
                    for t in (c.target, *c.parents)
                }
                digest = hashlib.sha256(
                    json.dumps(
                        [c.model_dump(mode="json") for c in contexts],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                if (
                    self.input_manifest.post_observations != expected_posts
                    or self.input_manifest.comment_observations != expected_comments
                    or self.input_manifest.context_signature != digest
                    or any(
                        item.comment_context is None
                        or item.content_version_id != item.comment_context.target.content_version_id
                        or item.content_id != item.comment_context.target.content_id
                        or item.body != item.comment_context.target.text
                        or item.body_truncated != item.comment_context.target.truncated
                        or item.title is not None
                        or item.comments
                        or item.comment_version_ids not in (None, ())
                        for item in self.prompt_items or ()
                    )
                ):
                    raise ValueError("comment manifest must match its frozen context")
            elif (
                set(self.input_manifest.post_observations) != set(self.content_version_ids)
                or self.prompt_items is None
                or self.input_manifest.context_signature is not None
                or any(
                    item.comments and item.comment_version_ids is None for item in self.prompt_items
                )
                or set(self.input_manifest.comment_observations)
                != {
                    identifier
                    for item in self.prompt_items
                    for identifier in (item.comment_version_ids or ())
                }
            ):
                raise ValueError("analysis observation manifest must match the actual prompt batch")
        elif self.prompt_version == "analysis.comment.v1":
            raise ValueError("comment analysis requires exact observation inputs")
        return self

    def to_job_scope(self) -> dict[str, str | int]:
        if self.prompt_items is None:
            raise ValueError("new analysis jobs require frozen prompt items")
        result: dict[str, str | int] = {
            "topic_id": str(self.topic_id),
            "topic_rule_version": self.topic_rule_version,
            "prompt_version": self.prompt_version,
            "content_version_ids": json.dumps(
                [str(item) for item in self.content_version_ids], separators=(",", ":")
            ),
            "prompt_items": json.dumps(
                [item.model_dump(mode="json") for item in self.prompt_items],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "retry_index": self.retry_index,
        }
        if self.input_manifest is not None:
            result["input_manifest"] = self.input_manifest.model_dump_json()
        return result

    @classmethod
    def from_job_scope(cls, scope: dict[str, str | int | bool | None]) -> AnalysisJobScope:
        encoded_ids = scope.get("content_version_ids")
        if not isinstance(encoded_ids, str):
            raise ValueError("analysis scope content_version_ids must be JSON")
        try:
            content_version_ids = json.loads(encoded_ids)
        except json.JSONDecodeError as error:
            raise ValueError("analysis scope content_version_ids must be JSON") from error
        encoded_items = scope.get("prompt_items")
        if encoded_items is not None and not isinstance(encoded_items, str):
            raise ValueError("analysis scope prompt_items must be JSON")
        try:
            prompt_items = json.loads(encoded_items) if encoded_items is not None else None
        except json.JSONDecodeError as error:
            raise ValueError("analysis scope prompt_items must be JSON") from error
        encoded_manifest = scope.get("input_manifest")
        if encoded_manifest is not None and not isinstance(encoded_manifest, str):
            raise ValueError("analysis scope input_manifest must be JSON")
        try:
            manifest = json.loads(encoded_manifest) if encoded_manifest is not None else None
        except json.JSONDecodeError as error:
            raise ValueError("analysis scope input_manifest must be JSON") from error
        return cls.model_validate(
            {
                "topic_id": scope.get("topic_id"),
                "topic_rule_version": scope.get("topic_rule_version"),
                "prompt_version": scope.get("prompt_version"),
                "content_version_ids": content_version_ids,
                "prompt_items": prompt_items,
                "input_manifest": manifest,
                "retry_index": scope.get("retry_index", 0),
            }
        )


class AnnotationOutputEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[Any] = Field(max_length=30)


class AnnotationOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_version_id: UUID
    relevant: bool
    relevance_reason: str = Field(min_length=1, max_length=500)
    sentiment: Sentiment | None
    summary: str = Field(min_length=1, max_length=60)
    viewpoints: tuple[str, ...] = Field(max_length=5)

    @field_validator("relevant", mode="before")
    @classmethod
    def require_json_boolean(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("relevant must be a boolean")
        return value

    @field_validator("relevance_reason", "summary")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("annotation text must not be blank")
        return value

    @field_validator("viewpoints")
    @classmethod
    def validate_viewpoints(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("viewpoints must be short non-empty sentences")
        return value

    @model_validator(mode="after")
    def validate_sentiment_relevance(self) -> Self:
        if not self.relevant and self.sentiment is not None:
            raise ValueError("irrelevant content must not declare sentiment")
        return self


class CommentAnnotationOutputItem(BaseModel):
    """Explicit comment outcome; unknown and insufficient never carry a bool."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content_version_id: UUID
    state: Literal["valid", "insufficient", "unknown"]
    summary: str | None = Field(min_length=1, max_length=60)
    relevant: bool | None
    relevance_reason: str = Field(min_length=1, max_length=500)

    @field_validator("relevant", mode="before")
    @classmethod
    def strict_boolean(cls, value: object) -> object:
        """Reject coercions such as strings and integers."""
        if value is not None and not isinstance(value, bool):
            raise ValueError("comment relevance requires a real boolean")
        return value

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        """Require a reason and precisely one known or non-conclusive outcome."""
        if (
            not self.relevance_reason.strip()
            or ((self.state == "valid") != (self.relevant is not None))
            or ((self.state == "valid") != (self.summary is not None))
            or (self.summary is not None and not self.summary.strip())
        ):
            raise ValueError("comment outcome is inconsistent")
        return self


class AnnotationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_version_id: UUID
    relevant: bool | None = None
    relevance_reason: str | None = None
    sentiment: Sentiment | None = None
    summary: str | None = None
    viewpoints: tuple[str, ...] = Field(default=(), max_length=5)
    ai_call_id: UUID | None = None
    status: AnnotationStatus
    result_state: AnnotationResultState
    dimension_results: AnnotationDimensions | None = None
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def validate_status_fields(self) -> Self:
        if self.dimension_results is not None:
            dimensions = self.dimension_results
            if any(
                item.ai_call_id != self.ai_call_id
                for item in (dimensions.relevance, dimensions.sentiment, dimensions.viewpoints)
            ):
                raise ValueError("new dimension results require their actual common call")
            relevance = dimensions.relevance
            if (
                relevance.state != self.result_state.value
                or (relevance.value if relevance.state == "valid" else None) != self.relevant
                or relevance.reason != self.relevance_reason
                or relevance.summary != self.summary
                or relevance.error_code != self.error_code
            ):
                raise ValueError("flat relevance must project the independent result")
            valid = relevance.state == "valid"
            if self.sentiment != (
                dimensions.sentiment.value if valid else None
            ) or self.viewpoints != (
                dimensions.viewpoints.value
                if valid and isinstance(dimensions.viewpoints.value, tuple)
                else ()
            ):
                raise ValueError("flat optional values must project independent results")
        if self.status is AnnotationStatus.ANNOTATED and (
            self.result_state is not AnnotationResultState.VALID
            or self.relevant is None
            or not self.relevance_reason
            or not self.relevance_reason.strip()
            or not self.summary
            or not self.summary.strip()
            or self.ai_call_id is None
            or self.error_code is not None
            or (not self.relevant and self.sentiment is not None)
        ):
            raise ValueError("annotated rows require consistent structured output")
        if self.status is AnnotationStatus.UNANALYZED and (
            self.result_state is AnnotationResultState.VALID
            or self.relevant is not None
            or (
                self.relevance_reason is not None
                and self.result_state
                not in {AnnotationResultState.INSUFFICIENT, AnnotationResultState.UNKNOWN}
            )
            or self.sentiment is not None
            or self.summary is not None
            or self.viewpoints
        ):
            raise ValueError("unanalyzed rows cannot contain inferred output")
        if self.result_state is AnnotationResultState.PENDING and (
            self.ai_call_id is not None or self.error_code is not None
        ):
            raise ValueError("pending rows cannot claim an AI call or failure")
        if self.result_state in {AnnotationResultState.FAILED, AnnotationResultState.INVALID} and (
            self.ai_call_id is None or self.error_code is None
        ):
            raise ValueError("failed and invalid rows require an AI call and error code")
        if self.result_state in {
            AnnotationResultState.INSUFFICIENT,
            AnnotationResultState.UNKNOWN,
        } and (
            self.ai_call_id is None
            or not self.relevance_reason
            or not self.relevance_reason.strip()
            or (
                self.result_state is AnnotationResultState.INSUFFICIENT
                and self.error_code is not None
            )
        ):
            raise ValueError("insufficient and unknown require an explicit reason and AI call")
        if (
            self.result_state is AnnotationResultState.DEFERRED
            and self.error_code != "analysis_rate_limited"
        ):
            raise ValueError("deferred analysis requires a rate-limit reason")
        return self
