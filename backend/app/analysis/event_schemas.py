"""Completed editorial inputs exposed to events without analysis ORM coupling."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EditorialEventInput:
    owner_id: UUID
    content_id: UUID
    content_version_id: UUID
    source_key: str
    title: str
    summary: str | None
    raw_title: str
    raw_body: str
    first_seen_at: datetime
    first_seen_basis: str
    selected: bool
    fact_frame: dict[str, object] | None
    provenance_fingerprint: str
    scope: Literal["single", "composite", "unknown"] = "unknown"
    observation_id: UUID | None = None
    input_observation_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class EditorialEventInputPage:
    items: tuple[EditorialEventInput, ...]
    next_after: tuple[UUID, UUID] | None
