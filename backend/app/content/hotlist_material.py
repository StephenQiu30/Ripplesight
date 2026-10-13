"""Atomic minimization, provenance and lifecycle registration of whole feed snapshots."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from content.hotlist_schemas import BOARD_REQUIRED, ENTRY_REQUIRED, BoardBasis, BoardEntryBasis
from content.models import HotlistEntryRecord, HotlistSnapshot
from evidence.schemas import CleanupTargetKind, CleanupTargetSpec, DataClass
from evidence.services import LifecycleService, SourceAccessPolicyService
from sources.contracts import HotlistEntry, HotlistPage, SourceCapability


def digest(value: object) -> str:
    """Hash the canonical JSON value, never its display formatting."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def entry_resource_id(snapshot_id: UUID, rank: int) -> UUID:
    """Bind an immutable feed position to its original board identity."""
    return uuid5(snapshot_id, str(rank))


def entry_payload(entry: HotlistEntry) -> dict[str, object]:
    """Use the same scalar fields for admission, stored row and checksum."""
    if entry.published_at is not None:
        entry = entry.model_copy(update={"published_at": entry.published_at.astimezone(UTC)})
    payload: dict[str, object] = entry.model_dump(mode="json", exclude_none=True)
    payload["canonical_url"] = payload.pop("url")
    return payload


def persist_board_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    job_id: UUID,
    operation_id: UUID,
    connection_id: UUID,
    connection_version: int,
    due_at: datetime,
    interval_seconds: int,
    page: HotlistPage,
    now: datetime,
) -> tuple[HotlistSnapshot, tuple[HotlistEntry, ...]]:
    """Save only admitted source fields and register every position before deriving content."""
    policy = SourceAccessPolicyService(session, clock=lambda: now)
    lifecycle = LifecycleService(session, clock=lambda: now)
    identifier = uuid4()
    target = [
        CleanupTargetSpec(
            kind=CleanupTargetKind.POSTGRES_HOTLIST_SNAPSHOT, reference=str(identifier)
        )
    ]
    board_payload: dict[str, object] = {
        "observed_at": page.observed_at.astimezone(UTC).isoformat(),
        "received_at": now.isoformat(),
        "board_state": page.state.value,
        "entry_count": len(page.items),
        "source_entry_count": page.source_entry_count
        if page.source_entry_count is not None
        else len(page.items),
        "truncated": page.truncated,
        "adapter_version": page.adapter_version,
    }
    if page.source_updated_at is not None:
        board_payload["source_updated_at"] = page.source_updated_at.isoformat()
    board_admission = policy.admit_payload_in_transaction(
        owner_id=owner_id,
        source_key=page.source_key,
        capability=SourceCapability.HOTLIST,
        data_class=DataClass.STRUCTURED,
        collected_at=page.observed_at,
        payload=board_payload,
    )
    if not BOARD_REQUIRED.issubset(board_admission.fields):
        raise ValueError("whole hotlist metadata is not admitted")
    lifecycle.track_resource_in_transaction(
        owner_id=owner_id,
        resource_type="hotlist_snapshot",
        resource_id=identifier,
        admission=board_admission,
        cleanup_targets=target,
    )
    snapshot = HotlistSnapshot(
        id=identifier,
        owner_id=owner_id,
        source_key=page.source_key,
        job_id=job_id,
        operation_id=operation_id,
        observed_at=page.observed_at,
        entry_count=len(page.items),
    )
    session.add(snapshot)
    session.flush()
    bases = []
    minimized = []
    for original in page.items:
        if original.published_at is not None and (
            original.published_at.utcoffset() is None or original.published_at > page.observed_at
        ):
            raise ValueError("entry publication time must be aware and observed")
        admission = policy.admit_payload_in_transaction(
            owner_id=owner_id,
            source_key=page.source_key,
            capability=SourceCapability.HOTLIST,
            data_class=DataClass.STRUCTURED,
            collected_at=page.observed_at,
            payload=entry_payload(original),
        )
        if not ENTRY_REQUIRED.issubset(admission.fields):
            raise ValueError("hotlist entry required fields are not admitted")
        fields = dict(admission.fields)
        fields["url"] = fields.pop("canonical_url")
        item = HotlistEntry.model_validate_json(json.dumps(fields))
        minimized.append(item)
        bases.append(
            BoardEntryBasis(
                rank=item.rank,
                fields=sorted(admission.fields),
                digest=digest(entry_payload(item)),
                native_id=item.native_id,
                native_rank=item.native_rank,
                heat_unit=item.heat_unit,
            )
        )
        session.add(
            HotlistEntryRecord(
                snapshot_id=identifier,
                rank=item.rank,
                owner_id=owner_id,
                title=item.title,
                url=item.url,
                summary=item.summary,
                heat=item.heat,
                published_at=item.published_at,
                content_id=None,
                matched_topic_names=[],
                matched_topic_ids=[],
            )
        )
        lifecycle.track_resource_in_transaction(
            owner_id=owner_id,
            resource_type="hotlist_entry",
            resource_id=entry_resource_id(identifier, item.rank),
            admission=admission,
            cleanup_targets=target,
        )
    basis = BoardBasis(
        owner_id=owner_id,
        snapshot_id=identifier,
        source_key=page.source_key,
        job_id=job_id,
        operation_id=operation_id,
        connection_id=connection_id,
        connection_version=connection_version,
        due_at=due_at,
        interval_seconds=interval_seconds,
        received_at=now,
        source_updated_at=page.source_updated_at
        if "source_updated_at" in board_admission.fields
        else None,
        source_entry_count=page.source_entry_count
        if page.source_entry_count is not None
        else len(page.items),
        truncated=page.truncated,
        adapter_version=page.adapter_version,
        board_state="complete" if page.items else "empty",
        fields=sorted(board_admission.fields),
        entries=bases,
        digest="0" * 64,
    )
    serialized = basis.model_dump(mode="json", exclude={"digest"})
    serialized["observed_at"] = page.observed_at.astimezone(UTC).isoformat()
    serialized["entry_count"] = len(page.items)
    basis.digest = digest(serialized)
    snapshot.provenance = basis.model_dump(mode="json")
    session.flush()
    return snapshot, tuple(minimized)
