from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TopicIdeaRead(BaseModel):
    title: str
    angle: str = ""
    format: str = ""
    rationale: str = ""


class AiAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotspot_id: int
    is_real: bool | None
    relevance_score: Decimal
    relevance_reason: str | None
    keyword_mentioned: bool
    importance: str
    summary: str | None
    quick_understanding: list[str] = Field(default_factory=list)
    topic_ideas: list[TopicIdeaRead] = Field(default_factory=list)
    model_name: str | None
    raw_response: dict[str, Any]
    created_at: datetime
    updated_at: datetime
