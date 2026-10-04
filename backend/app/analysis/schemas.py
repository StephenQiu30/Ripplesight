from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content.analysis_schemas import AnalysisObservationManifest
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
    error_code: str | None
    updated_at: datetime


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
        if self.input_manifest is not None and (
            set(self.input_manifest.post_observations) != set(self.content_version_ids)
            or self.prompt_items is None
            or any(item.comments and item.comment_version_ids is None for item in self.prompt_items)
            or set(self.input_manifest.comment_observations)
            != {
                identifier
                for item in self.prompt_items
                for identifier in (item.comment_version_ids or ())
            }
        ):
            raise ValueError("analysis observation manifest must match the actual prompt batch")
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
        if self.relevant and self.sentiment is None:
            raise ValueError("relevant content requires sentiment")
        if not self.relevant and self.sentiment is not None:
            raise ValueError("irrelevant content must not declare sentiment")
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
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def validate_status_fields(self) -> Self:
        if self.status is AnnotationStatus.ANNOTATED and (
            self.result_state is not AnnotationResultState.VALID
            or self.relevant is None
            or not self.relevance_reason
            or not self.relevance_reason.strip()
            or not self.summary
            or not self.summary.strip()
            or self.ai_call_id is None
            or self.error_code is not None
            or (self.relevant and self.sentiment is None)
            or (not self.relevant and self.sentiment is not None)
        ):
            raise ValueError("annotated rows require consistent structured output")
        if self.status is AnnotationStatus.UNANALYZED and (
            self.result_state is AnnotationResultState.VALID
            or self.relevant is not None
            or self.relevance_reason is not None
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
        return self
