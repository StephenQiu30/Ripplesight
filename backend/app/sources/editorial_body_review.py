"""Frozen, non-secret references for an operator-reviewed local body extraction."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from sources.editorial_base import EditorialContract


class EditorialBodyReview(EditorialContract):
    read_reference: str = Field(min_length=1, max_length=128)
    save_reference: str = Field(min_length=1, max_length=128)
    fee_reference: str = Field(min_length=1, max_length=128)
    egress_reference: str = Field(min_length=1, max_length=128)
    request_bound_reference: str = Field(min_length=1, max_length=128)
    deployment_reference: str = Field(min_length=1, max_length=128)
    component_revision: Literal["firecrawl/2.11.162"] = "firecrawl/2.11.162"
    reviewed_at: datetime
    expires_at: datetime

    @field_validator(
        "read_reference",
        "save_reference",
        "fee_reference",
        "egress_reference",
        "request_bound_reference",
        "deployment_reference",
    )
    @classmethod
    def safe_reference(cls, value: str) -> str:
        if not value.strip() or "?" in value or any(ord(char) < 32 for char in value):
            raise ValueError("review references must not contain credentials or controls")
        return value

    @model_validator(mode="after")
    def bounded_review(self) -> Self:
        if self.reviewed_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValueError("body review requires aware times")
        if not 0 < (self.expires_at - self.reviewed_at).total_seconds() <= 90 * 86400:
            raise ValueError("body review must expire within 90 days")
        return self
