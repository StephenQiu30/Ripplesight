"""Fixed-version original representation DTOs; metadata never grants a license."""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sources.editorial_schemas import public_url


class EditorialRenderedMedia(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    url: str = Field(max_length=2048)
    kind: Literal["image", "video", "audio", "unknown"] = "unknown"
    alt: str | None = Field(default=None, max_length=512)
    origin: Literal["body", "attachment"] = "body"

    @field_validator("url")
    @classmethod
    def bounded_public_url(cls, value: str) -> str:
        return public_url(value)


class EditorialRenderedRepresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    body_format: Literal["text", "html", "markdown"]
    body: str = Field(max_length=500_000)
    media: tuple[EditorialRenderedMedia, ...] = Field(default=(), max_length=64)
    representation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("media")
    @classmethod
    def bounded_media_size(
        cls, value: tuple[EditorialRenderedMedia, ...]
    ) -> tuple[EditorialRenderedMedia, ...]:
        if (
            len(
                json.dumps(
                    [item.model_dump(mode="json") for item in value], ensure_ascii=False
                ).encode()
            )
            > 65536
        ):
            raise ValueError("rendered media JSON exceeds its limit")
        return value


class EditorialRenderedView(EditorialRenderedRepresentation):
    content_id: UUID
    content_version_id: UUID
