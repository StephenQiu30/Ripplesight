from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.schemas import OutputModel
from events.heat_schemas import EventAttentionView

type FactRelation = Literal["root", "development", "background", "roundup", "unreviewed"]
type VerdictRelation = Literal["SAME_OCCURRENCE", "SAME_STORY", "UNRELATED", "ROUNDUP"]


@dataclass(frozen=True, slots=True)
class FactRelationCandidate:
    fact_id: UUID
    event_id: UUID
    revision: int
    story_root: bool
    recall_score: float


@dataclass(frozen=True, slots=True)
class FactVerdict:
    fact_id: UUID
    relation: VerdictRelation | None
    confidence: float | None
    note: str
    state: Literal["valid", "missing", "invalid"]


@dataclass(frozen=True, slots=True)
class FactRelationChoice:
    kind: Literal[
        "same_occurrence",
        "development",
        "new_story",
        "roundup",
        "unreviewed",
        "signal",
        "signal_unmatched",
        "mention",
    ]
    target_fact_id: UUID | None = None
    target_event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EventPublicationGrouping:
    topic_id: UUID
    event_id: UUID
    event_revision: int
    fact_id: UUID
    root_fact_id: UUID | None
    fact_revision: int
    grouped_at: datetime
    role: Literal["primary", "report"]
    relation: FactRelation = "unreviewed"
    frame: dict[str, object] | None = None
    assignment_origin: Literal["model", "manual", "legacy"] = "legacy"


@dataclass(frozen=True, slots=True)
class StoryIndexingChange:
    event_id: UUID
    changed_at: datetime
    eligible_story: bool


class EventCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    kind: Literal["merge", "split", "move", "detach", "merge_facts", "regroup"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_revisions: dict[UUID, int] = Field(min_length=1, max_length=20)
    target_event_id: UUID | None = None
    content_ids: list[UUID] = Field(default_factory=list, max_length=200)
    fact_ids: list[UUID] = Field(default_factory=list, max_length=20)
    target_fact_id: UUID | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        if not self.reason.strip() or any(value < 1 for value in self.expected_revisions.values()):
            raise ValueError("correction needs a reason and positive expected revisions")
        if len(set(self.content_ids)) != len(self.content_ids):
            raise ValueError("duplicate correction content")
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("duplicate correction fact")
        if self.kind == "merge":
            if (
                len(self.expected_revisions) < 2
                or self.target_event_id not in self.expected_revisions
            ):
                raise ValueError("merge needs all source and target event revisions")
        elif self.kind == "move":
            if (
                len(self.expected_revisions) != 2
                or self.target_event_id not in self.expected_revisions
            ):
                raise ValueError("move needs source and target revisions")
        elif len(self.expected_revisions) != 1:
            raise ValueError("single event correction requires one expected revision")
        if self.kind in {"split", "move", "detach", "regroup"} and not self.content_ids:
            raise ValueError("member correction needs content identities")
        if self.kind == "merge_facts" and (
            len(self.fact_ids) < 2 or self.target_fact_id not in self.fact_ids
        ):
            raise ValueError("fact merge requires a target within the fact identities")
        if self.kind != "merge_facts" and (self.fact_ids or self.target_fact_id is not None):
            raise ValueError("fact identities are only valid for fact merge")
        if self.kind not in {"merge", "move"} and self.target_event_id is not None:
            raise ValueError("target event is only valid for merge or move")
        if self.kind in {"merge", "merge_facts"} and self.content_ids:
            raise ValueError("merge operates on complete event or fact identities")
        return self


class EventCorrectionView(OutputModel):
    operation_id: UUID
    kind: str
    event_revisions: dict[UUID, int]
    target_event_id: UUID | None
    affected_content_ids: list[UUID]
    created_fact_ids: list[UUID]
    replayed: bool = False


class EventFactMemberView(OutputModel):
    content_id: UUID
    content_version_id: UUID
    event_member_id: UUID
    role: Literal["primary", "report", "mention"]
    assignment_origin: Literal["model", "manual", "legacy"]
    availability: Literal["readable", "unavailable"]


class EventFactConditionView(OutputModel):
    quote: str = Field(min_length=1, max_length=400)


class EventFactView(OutputModel):
    id: UUID
    revision: int
    relation: FactRelation
    root_fact_id: UUID | None
    title: str | None
    summary: str | None
    evidence: str | None = Field(default=None, max_length=600)
    conditions: list[EventFactConditionView] = Field(default_factory=list, max_length=4)
    first_seen_at: datetime
    first_seen_basis: Literal["published", "discovered"]
    evidence_state: Literal["complete", "partial"]
    members: list[EventFactMemberView]


class EventMaterialChange(BaseModel):
    """One applied member classification, with derived reasons gated at read time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_member_id: UUID
    content_version_id: UUID
    fact_id: UUID
    kind: Literal["new_fact", "supplement", "repeat", "unknown"]
    reason: str | None = Field(default=None, max_length=2000)
    unavailable: bool = False

    @model_validator(mode="after")
    def validate_explanation(self) -> Self:
        """Keep classified evidence explainable and withdrawn conclusions hidden."""
        if self.kind in {"supplement", "repeat"} and (
            self.reason is None or not self.reason.strip()
        ):
            raise ValueError("classified evidence requires a reason")
        if self.unavailable and (self.kind != "unknown" or self.reason is not None):
            raise ValueError("unavailable evidence cannot retain a conclusion")
        return self


class EventRevisionDeltaReceipt(BaseModel):
    """Immutable result of one atomic automatic grouping revision, not a time bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["fact_delta_v1"]
    event_id: UUID
    baseline_event_revision: int = Field(ge=0, strict=True)
    event_revision: int = Field(ge=1, strict=True)
    material_changes: list[EventMaterialChange] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_revision_and_members(self) -> Self:
        """Verify the explicit baseline and an exclusive fixed-member partition."""
        if self.event_revision != self.baseline_event_revision + 1:
            raise ValueError("applied revision must follow its frozen baseline")
        for identities in (
            [item.event_member_id for item in self.material_changes],
            [item.content_version_id for item in self.material_changes],
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("applied material identities must be unique")
        return self


class EventRevisionDeltaView(EventRevisionDeltaReceipt):
    """Compute counts from the permission-gated material partition, never model numbers."""

    new_fact_count: int = Field(ge=0)
    material_count: int = Field(ge=1)
    new_fact_material_count: int = Field(ge=0)
    supplement_count: int = Field(ge=0)
    repeat_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)

    @classmethod
    def from_receipt(cls, receipt: EventRevisionDeltaReceipt) -> Self:
        """Compute distinct facts and exclusive material counts from a gated receipt."""
        changes = receipt.material_changes
        return cls(
            **receipt.model_dump(),
            new_fact_count=len({item.fact_id for item in changes if item.kind == "new_fact"}),
            material_count=len(changes),
            new_fact_material_count=sum(item.kind == "new_fact" for item in changes),
            supplement_count=sum(item.kind == "supplement" for item in changes),
            repeat_count=sum(item.kind == "repeat" for item in changes),
            unknown_count=sum(item.kind == "unknown" for item in changes),
        )


class EventFactPageView(OutputModel):
    """Read fixed event facts and an optional verifiable automatic revision delta."""

    event_id: UUID
    event_revision: int
    facts: list[EventFactView]
    delta_state: Literal["available", "not_recorded", "invalid", "ambiguous", "unavailable"] = (
        "not_recorded"
    )
    delta: EventRevisionDeltaView | None = None


@dataclass(frozen=True, slots=True)
class EventPublicationMemberReference:
    content_id: UUID
    content_version_id: UUID
    representative_comment_id: UUID | None
    observation_id: UUID | None = None
    source_key: str | None = None
    input_observation_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class EventPublicationStoryView:
    event_id: UUID
    topic_id: UUID
    revision: int
    title: str
    summary: str
    latest_progress: str | None
    phase: Literal["active", "watching", "settled"]
    first_seen_at: datetime
    members: tuple[EventPublicationMemberReference, ...]
    heat: float | None = None
    attention: EventAttentionView | None = None
    narrative_input_observation_ids: tuple[UUID, ...] = ()
