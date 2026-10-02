from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from core.schemas import InputModel, OutputModel

TranslationState = Literal[
    "not_requested", "queued", "running", "complete", "partial", "unknown", "failed", "stale"
]


class TranslationRequestInput(InputModel):
    operation_id: UUID
    content_version_id: UUID
    policy_revision: int = Field(ge=1)
    expected_revision: int = Field(default=0, ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class TranslationReadView(OutputModel):
    body_html: str | None = None
    status: TranslationState = "not_requested"
    revision: int | None = None
    reason: str = "not_requested"
    complete: bool = False
    translated_segments: int = 0
    total_segments: int = 0


class TranslationRunView(TranslationReadView):
    id: UUID
    content_id: UUID
    content_version_id: UUID
    policy_revision: int
    job_id: UUID
    created_at: datetime
