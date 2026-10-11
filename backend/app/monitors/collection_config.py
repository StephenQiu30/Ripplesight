from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TopicCollectionConfig(BaseModel):
    """Versioned keyword-search settings; limits never override source admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    search_language: Literal["any", "zh", "en"] = "any"
    search_window_seconds: int = Field(default=86400, ge=600, le=2592000, strict=True)
    max_queries: int = Field(default=50, ge=1, le=50, strict=True)
    max_items_per_query: int = Field(default=100, ge=1, le=2000, strict=True)
    max_requests_per_query: int = Field(default=100, ge=1, le=100, strict=True)


def language_matches(language: str | None, selected: str) -> bool:
    return selected == "any" or (
        language is not None and language.lower().replace("_", "-").split("-", 1)[0] == selected
    )
