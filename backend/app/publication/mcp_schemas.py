"""The wire contract is JSON-RPC, independently from ordinary application errors."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from core.schemas import InputModel, OutputModel


class McpRequest(InputModel):
    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] | None = None

    @field_validator("id", mode="before")
    @classmethod
    def scalar_identity(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("JSON-RPC identity cannot be boolean")
        return value


class McpError(OutputModel):
    code: int
    message: str


class McpResponse(OutputModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None
    result: dict[str, Any] | None = None
    error: McpError | None = None


class LatestArguments(InputModel):
    window: Literal["24h", "7d"] = "24h"
    selected: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=4096)


class SearchArguments(InputModel):
    q: str = Field(min_length=1, max_length=200)
    window: Literal["24h", "7d"] = "7d"
    selected: bool = False
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=4096)


class HotArguments(InputModel):
    limit: int = Field(default=10, ge=1, le=50)


class StoryArguments(InputModel):
    id: UUID


class DailyArguments(InputModel):
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class CallArguments(InputModel):
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
