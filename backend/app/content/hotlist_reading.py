"""ALL current admission and lifecycle checks for fixed boards, before any slicing."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from content.hotlist_material import digest, entry_payload, entry_resource_id
from content.hotlist_schemas import (
    BOARD_FIELDS,
    BOARD_REQUIRED,
    ENTRY_FIELDS,
    ENTRY_REQUIRED,
    BoardBasis,
    FixedBoard,
    FixedBoardEntry,
)
from content.models import HotlistEntryRecord, HotlistSnapshot
from evidence.admission_reading import load_current_source_admissions_in_transaction
from evidence.schemas import CleanupTargetKind, DataClass, EvidenceResourceView
from evidence.services import load_readable_resources_in_transaction
from jobs.coverage import load_hotlist_due_for_job_in_transaction
from jobs.services import load_job_execution_configuration
from sources.adapters.web_targets import normalize_public_article_url
from sources.contracts import HotlistEntry, SourceCapability


class BoardUnavailableError(ValueError):
    """A fixed board cannot prove its complete original permission or source fields."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _matches(resource: EvidenceResourceView, original: EvidenceResourceView) -> bool:
    return (
        resource.source_policy_id == original.source_policy_id
        and resource.source_policy_version == original.source_policy_version
        and resource.retention_policy_id == original.retention_policy_id
        and resource.retention_policy_version == original.retention_policy_version
        and resource.collected_at == original.collected_at
        and resource.expires_at == original.expires_at
        and resource.data_class == original.data_class == "structured"
    )


def _has_cleanup(resource: EvidenceResourceView, identifier: UUID) -> bool:
    return len(resource.cleanup_targets) == 1 and (
        resource.cleanup_targets[0].kind == CleanupTargetKind.POSTGRES_HOTLIST_SNAPSHOT
        and resource.cleanup_targets[0].reference == str(identifier)
    )


def read_board_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    snapshot_id: UUID,
    now: datetime,
) -> FixedBoard:
    """Reject an entire board if even one frozen field or position lacks current permission.

    This provider never calls observation readers or public policy readers. It is
    also the leaf gate for observations originally derived from this board.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("board read requires an aware caller transaction")
    row = session.scalar(
        select(HotlistSnapshot)
        .where(HotlistSnapshot.owner_id == owner_id, HotlistSnapshot.id == snapshot_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise BoardUnavailableError("lifecycle_unavailable")
    if row.provenance is None:
        raise BoardUnavailableError("provenance_unknown")
    try:
        basis = BoardBasis.model_validate_json(json.dumps(row.provenance))
    except (ValidationError, TypeError, ValueError) as error:
        raise BoardUnavailableError("invalid") from error
    due = load_hotlist_due_for_job_in_transaction(
        session,
        owner_id=owner_id,
        job_id=row.job_id,
        source_key=row.source_key,
        operation_id=row.operation_id,
    )
    configuration = load_job_execution_configuration(session, job_id=row.job_id)
    if configuration is None or (
        configuration.owner_id != owner_id
        or configuration.operation_id != row.operation_id
        or configuration.kind != "source.hotlist"
        or configuration.observation.source_key != row.source_key
        or configuration.observation.source_capability is not SourceCapability.HOTLIST
        or configuration.scope.get("connection_id") != str(basis.connection_id)
        or configuration.scope.get("connection_version") != basis.connection_version
        or configuration.scope.get("interval_seconds") != basis.interval_seconds
    ):
        raise BoardUnavailableError("invalid")
    if (
        (basis.owner_id, basis.snapshot_id, basis.source_key, basis.job_id, basis.operation_id)
        != (row.owner_id, row.id, row.source_key, row.job_id, row.operation_id)
        or basis.due_at != due.due_at
        or not 0 <= row.entry_count <= 100
        or basis.source_entry_count < row.entry_count
        or basis.truncated != (basis.source_entry_count > row.entry_count)
        or basis.board_state != ("complete" if row.entry_count else "empty")
        or len(basis.entries) != row.entry_count
        or not BOARD_REQUIRED.issubset(basis.fields)
        or not set(basis.fields).issubset(BOARD_FIELDS)
        or len(basis.fields) != len(set(basis.fields))
        or not basis.due_at <= row.observed_at <= basis.received_at <= now
        or (basis.source_updated_at is not None and basis.source_updated_at > row.observed_at)
    ):
        raise BoardUnavailableError("invalid")
    serialized = basis.model_dump(mode="json", exclude={"digest"})
    serialized.update(
        observed_at=row.observed_at.astimezone(UTC).isoformat(), entry_count=row.entry_count
    )
    if digest(serialized) != basis.digest:
        raise BoardUnavailableError("invalid")
    resources = load_readable_resources_in_transaction(
        session, owner_id=owner_id, resource_type="hotlist_snapshot", resource_ids={row.id}, now=now
    )
    original = resources.get(row.id)
    entry_resources = load_readable_resources_in_transaction(
        session,
        owner_id=owner_id,
        resource_type="hotlist_entry",
        resource_ids={entry_resource_id(row.id, i) for i in range(1, row.entry_count + 1)},
        now=now,
    )
    if original is None or len(entry_resources) != row.entry_count:
        raise BoardUnavailableError("lifecycle_unavailable")
    admission = load_current_source_admissions_in_transaction(
        session,
        owner_id=owner_id,
        source_contexts={(row.source_key, SourceCapability.HOTLIST)},
        data_class=DataClass.STRUCTURED,
        now=now,
    ).get((row.source_key, SourceCapability.HOTLIST))
    if admission is None or (
        admission.policy_id != original.source_policy_id
        or admission.policy_version != original.source_policy_version
        or admission.retention_policy_id != original.retention_policy_id
        or admission.retention_policy_version != original.retention_policy_version
        or original.collected_at != row.observed_at
        or original.expires_at != row.observed_at + timedelta(days=admission.effective_days)
        or not _has_cleanup(original, row.id)
        or not set(basis.fields).issubset(admission.field_purposes)
    ):
        raise BoardUnavailableError("source_unavailable")
    rows = list(
        session.scalars(
            select(HotlistEntryRecord)
            .where(
                HotlistEntryRecord.owner_id == owner_id, HotlistEntryRecord.snapshot_id == row.id
            )
            .order_by(HotlistEntryRecord.rank)
            .limit(101)
        )
    )
    if len(rows) != row.entry_count:
        raise BoardUnavailableError("invalid")
    items = []
    for position, (entry, proof) in enumerate(zip(rows, basis.entries, strict=True), 1):
        if (
            entry.rank != position
            or proof.rank != position
            or not ENTRY_REQUIRED.issubset(proof.fields)
            or not set(proof.fields).issubset(ENTRY_FIELDS)
            or len(proof.fields) != len(set(proof.fields))
        ):
            raise BoardUnavailableError("invalid")
        original_entry = entry_resources[entry_resource_id(row.id, position)]
        if not _matches(original_entry, original) or not _has_cleanup(original_entry, row.id):
            raise BoardUnavailableError("lifecycle_unavailable")
        try:
            normalize_public_article_url(entry.url)
            item = HotlistEntry(
                rank=entry.rank,
                title=entry.title,
                url=entry.url,
                summary=entry.summary,
                heat=entry.heat,
                published_at=entry.published_at,
                native_id=proof.native_id,
                native_rank=proof.native_rank,
                heat_unit=proof.heat_unit,
            )
            if item.published_at is not None and (
                item.published_at.utcoffset() is None or item.published_at > row.observed_at
            ):
                raise ValueError("entry publication time must be aware and observed")
            payload = entry_payload(item)
            current = admission.admit(collected_at=row.observed_at, payload=payload, now=now)
        except ValueError as error:
            raise BoardUnavailableError("invalid") from error
        if (
            set(payload) != set(proof.fields)
            or dict(current.fields) != payload
            or digest(payload) != proof.digest
            or current.expires_at != original_entry.expires_at
        ):
            raise BoardUnavailableError("source_unavailable")
        items.append(FixedBoardEntry(**item.model_dump(), fields=proof.fields))
    return FixedBoard(
        snapshot_id=row.id,
        source_key=row.source_key,
        job_id=row.job_id,
        operation_id=row.operation_id,
        observed_at=row.observed_at,
        due_at=due.due_at,
        received_at=basis.received_at,
        source_updated_at=basis.source_updated_at,
        source_entry_count=basis.source_entry_count,
        truncated=basis.truncated,
        adapter_version=basis.adapter_version,
        connection_id=basis.connection_id,
        connection_version=basis.connection_version,
        interval_seconds=basis.interval_seconds,
        source_policy_version=original.source_policy_version,
        retention_policy_version=original.retention_policy_version,
        expires_at=original.expires_at,
        fields=basis.fields,
        items=items,
    )


def latest_board_id_in_transaction(
    session: Session, *, owner_id: UUID, source_key: str
) -> UUID | None:
    """Choose latest before validating; a failed proof never falls back to an older board."""
    return session.scalar(
        select(HotlistSnapshot.id)
        .where(HotlistSnapshot.owner_id == owner_id, HotlistSnapshot.source_key == source_key)
        .order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc())
        .limit(1)
    )


def previous_board_id_in_transaction(
    session: Session, *, owner_id: UUID, board: FixedBoard
) -> UUID | None:
    """Find the immediate prior snapshot only; the caller must validate it completely."""
    return session.scalar(
        select(HotlistSnapshot.id)
        .where(
            HotlistSnapshot.owner_id == owner_id,
            HotlistSnapshot.source_key == board.source_key,
            HotlistSnapshot.observed_at < board.observed_at,
        )
        .order_by(HotlistSnapshot.observed_at.desc(), HotlistSnapshot.id.desc())
        .limit(1)
    )


def readable_hotlist_jobs_in_transaction(
    session: Session, *, owner_id: UUID, source_jobs: set[tuple[UUID, str]], now: datetime
) -> set[UUID]:
    """Current raw-board dependency gate for hotlist-derived observations."""
    if not session.in_transaction() or len(source_jobs) > 20000:
        raise ValueError("bounded board dependency read required")
    readable = set()
    for job_id, source in source_jobs:
        identifier = session.scalar(
            select(HotlistSnapshot.id).where(
                HotlistSnapshot.owner_id == owner_id,
                HotlistSnapshot.job_id == job_id,
                HotlistSnapshot.source_key == source,
            )
        )
        if identifier is None:
            continue
        try:
            read_board_in_transaction(session, owner_id=owner_id, snapshot_id=identifier, now=now)
        except BoardUnavailableError:
            continue
        readable.add(job_id)
    return readable


def compare_boards_in_transaction(
    session: Session, *, owner_id: UUID, board: FixedBoard, now: datetime
) -> tuple[str, dict[str, int]]:
    """Compare only adjacent fully authorized boards and unambiguous URL identities."""
    identifier = previous_board_id_in_transaction(session, owner_id=owner_id, board=board)
    if identifier is None:
        return "no_baseline", {}
    try:
        previous = read_board_in_transaction(
            session, owner_id=owner_id, snapshot_id=identifier, now=now
        )
    except BoardUnavailableError:
        return "unavailable", {}
    if (
        board.connection_id,
        board.connection_version,
        board.adapter_version,
        board.source_policy_version,
        board.retention_policy_version,
        board.fields,
    ) != (
        previous.connection_id,
        previous.connection_version,
        previous.adapter_version,
        previous.source_policy_version,
        previous.retention_policy_version,
        previous.fields,
    ):
        return "source_changed", {}
    if (
        board.truncated
        or previous.truncated
        or board.interval_seconds != previous.interval_seconds
        or board.due_at - previous.due_at != timedelta(seconds=board.interval_seconds)
    ):
        return "gap", {}
    ranks = {}
    prior_urls = [normalize_public_article_url(item.url) for item in previous.items]
    current_urls = [normalize_public_article_url(item.url) for item in board.items]
    for item, url in zip(previous.items, prior_urls, strict=True):
        if prior_urls.count(url) == 1 and current_urls.count(url) == 1:
            ranks[url] = item.rank
    return "comparable", ranks
