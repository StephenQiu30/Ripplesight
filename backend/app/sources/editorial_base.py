"""Shared immutable editorial DTO base, independent of source configuration."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class EditorialContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*")
    @classmethod
    def aware_contract_time(cls, value: object) -> object:
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValueError("editorial contract time must be timezone-aware")
            return value.astimezone(UTC)
        return value
