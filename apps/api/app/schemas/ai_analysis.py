from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


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
    model_name: str | None
    raw_response: dict[str, Any]
    created_at: datetime
    updated_at: datetime
