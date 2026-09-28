from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


@dataclass(frozen=True, slots=True)
class EventTarget:
    event_id: UUID
    revision: int
    members: tuple[EventInput, ...]


class EventDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    same_event: bool
    member_version_ids: list[UUID] = Field(min_length=2, max_length=20)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)

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
        return self
