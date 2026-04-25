from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SearchCreate(BaseModel):
    query: str = Field(min_length=1)
    source_types: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchResultRead(BaseModel):
    title: str
    url: str
    source_id: int
    source_name: str
    source_type: str
    author: str | None
    published_at: datetime | None
    snippet: str | None
    relevance_score: float
    relevance_reason: str
    keyword_mentioned: bool
    importance: str
    summary: str
    status: str
    raw_payload: dict[str, Any]


class SearchRead(BaseModel):
    query: str
    items: list[SearchResultRead]
    errors: list[str]
