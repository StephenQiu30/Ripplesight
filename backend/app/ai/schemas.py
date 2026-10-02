from __future__ import annotations

import base64
import hashlib
import io
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AiImageInput(BaseModel):
    """One admitted raster image. Binary input is never part of public DTOs or repr."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    body: bytes = Field(min_length=1, max_length=4_000_000, exclude=True, repr=False)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]

    @model_validator(mode="after")
    def validate_pixels(self) -> Self:
        expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
        try:
            with Image.open(io.BytesIO(self.body)) as image:
                if (
                    image.format != expected[self.content_type]
                    or image.width * image.height > 16_000_000
                ):
                    raise ValueError("unsupported bounded AI image")
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError):
            raise ValueError("unsupported bounded AI image") from None
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def input_tokens_cap(self) -> int:
        # The allowance covers decoded pixels rather than only compressed bytes.
        with Image.open(io.BytesIO(self.body)) as image:
            return max(len(self.body), image.width * image.height) + 4096

    @property
    def data_url(self) -> str:
        return f"data:{self.content_type};base64," + base64.b64encode(self.body).decode("ascii")


class AiFailureCode(StrEnum):
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    FAILED = "failed"


class AiCallStatus(StrEnum):
    RUNNING = "running"
    UNKNOWN = "unknown"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AiTokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_output_tokens: int = Field(default=0, ge=0)


class AiCompletion(BaseModel):
    """A structured model answer; `output` already matches the requested JSON Schema."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    call_id: UUID | None = None
    output: dict[str, Any]
    usage: AiTokenUsage
    duration_ms: int = Field(ge=0)
    usage_reported: bool = True
    cost_currency: str | None = Field(default=None, pattern=r"^(USD|CNY)$")
    cost_actual_micros: int | None = Field(default=None, ge=0)


class SavedAiCallView(BaseModel):
    """Original AI ledger identity for saved-stage validation, without model output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    provider: str
    model: str
    model_key: str | None
    routing_version: int | None
    routing_hash: str | None
    status: AiCallStatus
    input_fingerprint: str


class AiCallError(Exception):
    def __init__(
        self,
        code: AiFailureCode,
        detail: str = "",
        *,
        call_id: UUID | None = None,
        retry_at: datetime | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.call_id = call_id
        self.retry_at = retry_at
        self.outcome_unknown = outcome_unknown
        # Upstream text may echo prompt content; keep it short and out of logs by default.
        self.detail = detail[:500]
