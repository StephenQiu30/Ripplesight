from datetime import date, datetime
from uuid import UUID

from pydantic import Field, field_validator

from core.schemas import InputModel
from publication.indexnow_schemas import IndexableChangeCursor, canonical_indexnow_path


class IndexNowReceiptCursor(InputModel):
    created_at: datetime
    audit_id: UUID
    path: str

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("receipt cursor requires timezone")
        return value

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return canonical_indexnow_path(value)


class IndexNowManifest(InputModel):
    configuration_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    paths: list[str] = Field(max_length=1500)
    next_cursor: IndexableChangeCursor
    examined: int = Field(ge=0, le=2000)
    next_receipt_cursor: IndexNowReceiptCursor | None = None
    receipt_cycle: date | None = None

    @field_validator("paths")
    @classmethod
    def canonical_paths(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate IndexNow paths")
        for value in values:
            canonical_indexnow_path(value)
        return values
