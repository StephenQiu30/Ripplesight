from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from core.schemas import InputModel, OutputModel

MediaState = Literal[
    "queued", "running", "complete", "partial", "unknown", "failed", "stale", "cancelled"
]


class MediaMirrorInput(InputModel):
    operation_id: UUID
    content_version_id: UUID
    policy_revision: int = Field(ge=1)


class MediaMirrorRunView(OutputModel):
    id: UUID
    job_id: UUID
    content_id: UUID
    content_version_id: UUID
    policy_revision: int
    status: MediaState
    candidate_count: int
    available_count: int
    unavailable_count: int
    reason: str | None
    replayed: bool


class MediaRenditionView(OutputModel):
    mode: str
    reading_url: str
    mime_type: str
    width: int | None
    height: int | None
    frame_count: int
    byte_count: int
