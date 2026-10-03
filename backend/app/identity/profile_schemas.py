from typing import Literal

from pydantic import Field, field_validator

from core.schemas import InputModel


class IdentityProfileInput(InputModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class IdentityAvatarInput(InputModel):
    mime: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: str = Field(min_length=1, max_length=2796204)
