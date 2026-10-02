"""Frozen member authorization identity for one original editorial group Job."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EditorialGroupMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: UUID
    source_key: str = Field(pattern=r"^ed_x_search_[a-f0-9]{32}$")
    configuration_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    policy_version: int = Field(ge=1)
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    handle: str = Field(pattern=r"^[A-Za-z0-9_]{1,15}$")
    cursor_json: str = Field(max_length=65_536)

    @model_validator(mode="after")
    def matching_identity(self) -> Self:
        if self.source_key != f"ed_x_search_{self.profile_id.hex}":
            raise ValueError("group member must keep its original source identity")
        value = json.loads(self.cursor_json)
        if not isinstance(value, dict):
            raise ValueError("group member cursor must be an object")
        return self


class EditorialGroupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    owner_id: UUID
    connection_id: UUID
    connection_version: int = Field(ge=1)
    participation_mode: Literal["editorial", "hot_signal", "isolated"]
    query: str = Field(min_length=1, max_length=470)
    since_id: str = Field(pattern=r"^[0-9]{1,19}$")
    scheduled_for_at: datetime | None = None
    members: tuple[EditorialGroupMember, ...] = Field(min_length=2, max_length=24)

    @model_validator(mode="after")
    def coherent_members(self) -> Self:
        if self.scheduled_for_at is not None and self.scheduled_for_at.utcoffset() is None:
            raise ValueError("group schedule must have an explicit timezone")
        if len({m.profile_id for m in self.members}) != len(self.members) or len(
            {m.handle.casefold() for m in self.members}
        ) != len(self.members):
            raise ValueError("group member identities and authors must be distinct")
        query = "(" + " OR ".join(f"from:{m.handle}" for m in self.members) + ") -is:reply"
        if self.query != query:
            raise ValueError("group query must match its frozen members")
        if len(self.model_dump_json().encode()) > 262_144:
            raise ValueError("group manifest exceeds bounded Job payload")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
