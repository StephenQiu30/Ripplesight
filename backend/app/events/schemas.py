from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content.schemas import EventContentReadView
from core.schemas import OutputModel, PageView


@dataclass(frozen=True, slots=True)
class EventInput:
    owner_id: UUID
    topic_id: UUID
    content_id: UUID
    content_version_id: UUID
    source_key: str
    title: str
    body: str | None
    first_seen_at: datetime
    first_seen_basis: str
    matched_keywords: frozenset[str]
    representative_comment_id: UUID | None = None
    native_target_content_ids: frozenset[UUID] = frozenset()
    editorial_frame: dict[str, str | None] | None = None
    provenance_fingerprint: str | None = None
    observation_id: UUID | None = None
    observation_source_key: str | None = None
    representative_comment_observation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = ()
    annotation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EventTarget:
    event_id: UUID
    revision: int
    members: tuple[EventInput, ...]


class EventFactDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    member_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    relation: Literal[
        "root", "same_occurrence", "development", "background", "roundup", "unreviewed"
    ]
    existing_fact_id: UUID | None = None
    root_fact_id: UUID | None = None
    root_member_version_id: UUID | None = None

    @model_validator(mode="after")
    def validate_fact_relation(self) -> Self:
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("fact requires nonblank derived text")
        if len(set(self.member_version_ids)) != len(self.member_version_ids):
            raise ValueError("duplicate fact members")
        if self.relation == "same_occurrence":
            if self.existing_fact_id is None:
                raise ValueError("same occurrence requires existing fact")
        elif self.existing_fact_id is not None:
            raise ValueError("new fact cannot claim existing identity")
        if self.relation in {"development", "background"}:
            if (self.root_fact_id is None) == (self.root_member_version_id is None):
                raise ValueError("development requires exactly one direct root reference")
        elif self.root_fact_id is not None or self.root_member_version_id is not None:
            raise ValueError("only developments can have a root reference")
        return self


class EventDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    same_event: bool
    member_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    facts: list[EventFactDecision] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_complete_confirmation(self) -> Self:
        if len(set(self.member_version_ids)) != len(self.member_version_ids):
            raise ValueError("event decision has duplicate members")
        if self.same_event and (
            self.title is None
            or not self.title.strip()
            or self.summary is None
            or not self.summary.strip()
        ):
            raise ValueError("confirmed event requires title and summary")
        if self.facts:
            ids = [identity for fact in self.facts for identity in fact.member_version_ids]
            if len(ids) != len(set(ids)) or set(ids) != set(self.member_version_ids):
                raise ValueError("facts must partition the complete frozen candidate")
            if not self.same_event:
                raise ValueError("rejected event cannot confirm facts")
        return self


class EventReadView(OutputModel):
    id: UUID
    topic_id: UUID
    revision: int = Field(ge=1)
    title: str | None
    summary: str | None
    first_seen_at: datetime
    first_seen_basis: Literal["published", "discovered"]
    status: Literal["active", "merged"]
    merged_into_id: UUID | None
    redirected_from_event_id: UUID | None = None
    evidence_state: Literal["complete", "partial"]
    derived_text_available: bool
    latest_progress: str | None = None
    phase: Literal["active", "watching", "settled"] = "active"
    member_count: int = Field(ge=1)
    readable_member_count: int = Field(ge=1)
    source_counts: dict[str, int]
    created_at: datetime
    updated_at: datetime


class EventMemberReadView(OutputModel):
    id: UUID
    content_id: UUID
    content_version_id: UUID
    source_key: str
    assignment_origin: Literal["model", "manual"]
    added_revision: int = Field(ge=1)
    removed_revision: int | None = Field(ge=2)
    availability: Literal["readable", "unavailable"]
    content: EventContentReadView | None


class EventMemberPageView(PageView[EventMemberReadView]):
    event_id: UUID
    revision: int = Field(ge=1)
    current_revision: int = Field(ge=1)
    redirected_from_event_id: UUID | None = None
    evidence_state: Literal["complete", "partial"]


class EventRelatedItemView(OutputModel):
    event: EventReadView
    supporting_report_count: int = Field(ge=2, le=20)


class EventRelatedPageView(OutputModel):
    event_id: UUID
    items: list[EventRelatedItemView]
