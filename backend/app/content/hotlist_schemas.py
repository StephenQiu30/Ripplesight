"""Pure fixed-board admission and read contracts; no publication or ORM dependencies."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BOARD_REQUIRED = frozenset(
    {
        "observed_at",
        "received_at",
        "board_state",
        "entry_count",
        "source_entry_count",
        "truncated",
        "adapter_version",
    }
)
ENTRY_REQUIRED = frozenset({"rank", "title", "canonical_url"})
BOARD_FIELDS = BOARD_REQUIRED | {"source_updated_at"}
ENTRY_FIELDS = ENTRY_REQUIRED | {
    "summary",
    "heat",
    "published_at",
    "native_id",
    "native_rank",
    "heat_unit",
}
HOTLIST_REQUIRED = BOARD_REQUIRED | ENTRY_REQUIRED


class BoardEntryBasis(BaseModel):
    """Field-level admitted identity and checksum without a second copy of text."""

    model_config = ConfigDict(extra="forbid", strict=True)
    rank: int = Field(ge=1, le=100)
    fields: list[str]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    native_id: str | None = Field(default=None, max_length=512)
    native_rank: int | None = Field(default=None, ge=1, le=10000)
    heat_unit: str | None = Field(default=None, max_length=100)


class BoardBasis(BaseModel):
    """Frozen context and metadata protected by the board's checksum."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    owner_id: UUID
    snapshot_id: UUID
    source_key: str
    job_id: UUID
    operation_id: UUID
    connection_id: UUID
    connection_version: int = Field(ge=1)
    due_at: datetime
    interval_seconds: int = Field(ge=600, le=86400)
    received_at: datetime
    source_updated_at: datetime | None
    source_entry_count: int = Field(ge=0)
    truncated: bool
    adapter_version: str
    board_state: Literal["complete", "empty"]
    fields: list[str]
    entries: list[BoardEntryBasis] = Field(max_length=100)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("due_at", "received_at", "source_updated_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        """Reject corrupt naive provenance before ordering times."""
        if value is not None and value.utcoffset() is None:
            raise ValueError("board times must be timezone aware")
        return value


class FixedBoardEntry(BaseModel):
    """Raw fields admitted for one current-readable feed position."""

    rank: int
    title: str
    url: str
    summary: str | None = None
    heat: str | None = None
    published_at: datetime | None = None
    native_id: str | None = Field(default=None, max_length=512)
    native_rank: int | None = None
    heat_unit: str | None = Field(default=None, max_length=100)
    fields: list[str]


class FixedBoard(BaseModel):
    """Complete authorized board, used by private reads and public projection."""

    snapshot_id: UUID
    source_key: str
    job_id: UUID
    operation_id: UUID
    observed_at: datetime
    due_at: datetime
    received_at: datetime
    source_updated_at: datetime | None
    source_entry_count: int
    truncated: bool
    adapter_version: str
    connection_id: UUID
    connection_version: int
    interval_seconds: int
    source_policy_version: int
    retention_policy_version: int
    expires_at: datetime
    fields: list[str]
    items: list[FixedBoardEntry]
