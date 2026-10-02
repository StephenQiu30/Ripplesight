from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from core.schemas import InputModel, OutputModel


class ContactImageInput(InputModel):
    mime: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data_base64: str = Field(min_length=1, max_length=2796204)


class SiteConfigurationInput(InputModel):
    operation_id: UUID
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)
    contact_enabled: bool = False
    contact_title: str = Field(default="联系", min_length=1, max_length=100)
    contact_text: str = Field(default="", max_length=4000)
    contact_url: str | None = Field(default=None, max_length=1000)
    wechat_qr_action: Literal["keep", "replace", "clear"] = "keep"
    wechat_image: ContactImageInput | None = None
    feishu_qr_action: Literal["keep", "replace", "clear"] = "keep"
    feishu_image: ContactImageInput | None = None

    @field_validator("reason", "contact_title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a nonblank value is required")
        return value.strip()

    @field_validator("contact_url")
    @classmethod
    def public_link(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("contact URL requires HTTP(S) without credentials")
        return value

    @model_validator(mode="after")
    def image_action(self) -> Self:
        if (self.wechat_qr_action == "replace") != (self.wechat_image is not None):
            raise ValueError("only replace accepts an image, and replace needs an image")
        if (self.feishu_qr_action == "replace") != (self.feishu_image is not None):
            raise ValueError("only replace accepts a Feishu image, and replace needs an image")
        if self.contact_enabled and not (self.contact_text or self.contact_url):
            raise ValueError("enabled contact needs text or a link")
        return self


class SiteConfigurationView(OutputModel):
    revision: int
    contact_enabled: bool
    contact_title: str
    contact_text: str
    contact_url: str | None
    wechat_qr_url: str | None
    feishu_qr_url: str | None
    updated_at: datetime | None


class PublicContactView(OutputModel):
    enabled: bool
    title: str | None
    text: str | None
    url: str | None
    wechat_qr_url: str | None
    feishu_qr_url: str | None
    revision: int


class PublicSiteFeatures(OutputModel):
    editorial_analysis: bool
    model_leaderboard: bool
    codex_monitor: bool
    notifications: bool
    smtp: bool
    media_mirror: bool
    feedback: bool
    external_indexing: bool


class PublicSiteMetaView(OutputModel):
    name: str
    version: str
    environment: str
    description: str
    public_base_url: str
    robots_index: bool = False
    features: PublicSiteFeatures
