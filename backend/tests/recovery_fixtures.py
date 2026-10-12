"""Controlled complete ledger exports for recovery contract tests."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from backups.schemas import BackupManifest
from evidence.journal_contract import (
    RecoveryCheckpoint,
    RecoveryEntry,
    RecoverySnapshot,
    entry_digest,
    genesis_digest,
)
from evidence.schemas import DeletionReason


def recovery_sample(
    manifest: BackupManifest,
    targets: Sequence[tuple[UUID, str, UUID]] = (),
    *,
    operation_id: UUID | None = None,
) -> tuple[RecoverySnapshot, RecoveryCheckpoint]:
    """Build samples, not a production authority or write receipt."""
    snapshot = RecoverySnapshot(
        format_version="ripplesight.recovery-ledger.v1",
        ledger_id=uuid4(),
        epoch=1,
        normalization_version="resource_uuid.v1",
        entries=(),
    )
    previous, entries = genesis_digest(snapshot), []
    for sequence, (owner, kind, resource) in enumerate(targets, start=1):
        entry = RecoveryEntry(
            sequence=sequence,
            operation_id=operation_id or uuid4(),
            owner_id=owner,
            action="deny_resource",
            resource_type=kind,
            resource_id=resource,
            reason=DeletionReason.AUTHORIZATION_REVOKED,
            occurred_at=datetime.now(UTC),
            previous_digest=previous,
            digest="0" * 64,
        )
        entry = entry.model_copy(update={"digest": entry_digest(entry)})
        previous = entry.digest
        entries.append(entry)
    snapshot = snapshot.model_copy(update={"entries": tuple(entries)})
    checkpoint = RecoveryCheckpoint(
        format_version="ripplesight.recovery-checkpoint.v1",
        ledger_id=snapshot.ledger_id,
        epoch=snapshot.epoch,
        normalization_version=snapshot.normalization_version,
        backup_id=manifest.backup_id,
        archive_sha256=manifest.database.archive_sha256,
        schema_sha256=manifest.database.schema_sha256,
        head_sequence=len(entries),
        head_digest=previous,
    )
    return snapshot, checkpoint
