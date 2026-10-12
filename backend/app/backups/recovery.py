"""Validate a complete restrictive ledger against an independently supplied pin.

This exchange format supports disposable rehearsals only. Neither a hash chain
nor a caller-supplied checkpoint proves the existence of a production authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backups.schemas import BackupManifest
from evidence.schemas import DeletionReason

_MAX_BYTES = 16 * 1024 * 1024
_DIGEST = r"^[0-9a-f]{64}$"


class RecoveryLedgerError(RuntimeError):
    """An input cannot establish the narrowly requested replay proof."""


class RecoveryEntry(BaseModel):
    """A minimal resource denial, with no content or authentication authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sequence: int = Field(ge=1, le=10000)
    operation_id: UUID
    owner_id: UUID
    action: Literal["deny_resource"]
    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    resource_id: UUID
    reason: DeletionReason
    occurred_at: datetime
    previous_digest: str = Field(pattern=_DIGEST)
    digest: str = Field(pattern=_DIGEST)

    @field_validator("occurred_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        """Normalize equivalent aware timestamps before canonical hashing."""
        if value.utcoffset() is None:
            raise ValueError("ledger times must be aware")
        return value.astimezone(UTC)


class RecoverySnapshot(BaseModel):
    """A complete genesis-to-head export, never its own trust anchor."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal["ripplesight.recovery-ledger.v1"]
    ledger_id: UUID
    epoch: int = Field(ge=1)
    normalization_version: Literal["resource_uuid.v1"]
    entries: tuple[RecoveryEntry, ...] = Field(max_length=10000)


class RecoveryCheckpoint(BaseModel):
    """An external pin binding a specific candidate and ledger high water mark."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal["ripplesight.recovery-checkpoint.v1"]
    ledger_id: UUID
    epoch: int = Field(ge=1)
    normalization_version: Literal["resource_uuid.v1"]
    backup_id: UUID
    archive_sha256: str = Field(pattern=_DIGEST)
    schema_sha256: str = Field(pattern=_DIGEST)
    head_sequence: int = Field(ge=0, le=10000)
    head_digest: str = Field(pattern=_DIGEST)


@dataclass(frozen=True)
class VerifiedRecovery:
    """Validated inputs for one isolated, finite replay; never a release token."""

    snapshot: RecoverySnapshot
    checkpoint: RecoveryCheckpoint


def _digest(domain: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(domain.encode("ascii") + b"\0" + encoded.encode("ascii")).hexdigest()


def genesis_digest(snapshot: RecoverySnapshot) -> str:
    """Bind the first record to its ledger identity and normalization epoch."""
    return _digest(
        "ripplesight.recovery.genesis.v1",
        {
            "ledger_id": str(snapshot.ledger_id),
            "epoch": snapshot.epoch,
            "normalization_version": snapshot.normalization_version,
        },
    )


def entry_digest(entry: RecoveryEntry) -> str:
    """Hash only the versioned canonical entry payload, excluding its digest."""
    payload = entry.model_dump(mode="json", exclude={"digest"})
    payload["occurred_at"] = (
        entry.occurred_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    return _digest("ripplesight.recovery.entry.v1", payload)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("duplicate JSON key")
        values[key] = value
    return values


def _parse_json[T: BaseModel](data: bytes | str, model: type[T]) -> T:
    encoded = data.encode("utf-8") if isinstance(data, str) else data
    if len(encoded) > _MAX_BYTES:
        raise ValueError("recovery input is too large")
    json.loads(encoded, object_pairs_hook=_unique_pairs)
    return model.model_validate_json(encoded)


def _read_snapshot(path: Path) -> bytes:
    # O_NONBLOCK prevents a swapped FIFO from blocking before the fstat check.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        status = os.fstat(handle.fileno())
        if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
            raise RecoveryLedgerError("recovery snapshot requires a private regular file")
        if status.st_size > _MAX_BYTES:
            raise RecoveryLedgerError("recovery snapshot is too large")
        data = handle.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise RecoveryLedgerError("recovery snapshot is too large")
        return data


def verify_recovery_inputs(
    *, snapshot_path: Path, checkpoint_json: str, manifest: BackupManifest
) -> VerifiedRecovery:
    """Reject malformed, incomplete or wrongly bound inputs before creating a DB.

    The caller obtains the checkpoint independently of both the candidate and
    export. This validates that claim, not the caller's authority or freshness.
    """
    try:
        snapshot = _parse_json(_read_snapshot(snapshot_path), RecoverySnapshot)
        checkpoint = _parse_json(checkpoint_json, RecoveryCheckpoint)
    except (OSError, ValueError) as error:
        # Pydantic errors may contain submitted data; never propagate them to CLI.
        raise RecoveryLedgerError("recovery inputs are invalid or unavailable") from error
    if (
        checkpoint.ledger_id != snapshot.ledger_id
        or checkpoint.epoch != snapshot.epoch
        or checkpoint.normalization_version != snapshot.normalization_version
        or checkpoint.backup_id != manifest.backup_id
        or checkpoint.archive_sha256 != manifest.database.archive_sha256
        or checkpoint.schema_sha256 != manifest.database.schema_sha256
    ):
        raise RecoveryLedgerError("recovery checkpoint does not bind this candidate and ledger")
    previous = genesis_digest(snapshot)
    operations: set[tuple[UUID, UUID]] = set()
    for sequence, entry in enumerate(snapshot.entries, start=1):
        operation = (entry.owner_id, entry.operation_id)
        if (
            entry.sequence != sequence
            or entry.previous_digest != previous
            or entry.digest != entry_digest(entry)
            or operation in operations
        ):
            raise RecoveryLedgerError("recovery ledger is discontinuous or inconsistent")
        operations.add(operation)
        previous = entry.digest
    if checkpoint.head_sequence != len(snapshot.entries) or checkpoint.head_digest != previous:
        raise RecoveryLedgerError("recovery ledger does not reach the independent checkpoint")
    return VerifiedRecovery(snapshot, checkpoint)
