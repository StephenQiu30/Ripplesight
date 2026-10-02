"""Current licensed selection counts by ingestion cohort, for operator maintenance."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analysis.editorial_models import EditorialContentState, EditorialRun
from analysis.editorial_reading import load_editorial_publication_inputs_in_transaction


@dataclass(frozen=True, slots=True)
class SelectionWindow:
    source_key: str
    current_count: int
    previous_count: int


@dataclass(frozen=True, slots=True)
class EditorialProcessingHealth:
    failed_count: int
    waiting_over_two_hours: int
    unknown_count: int
    last_completed_at: datetime | None
    selected: tuple[SelectionWindow, ...]


def load_editorial_processing_health_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime, include_selection: bool = False
) -> EditorialProcessingHealth:
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("processing health requires aware caller transaction")
    since = now - timedelta(days=14)
    failed = int(
        session.scalar(
            select(func.count())
            .select_from(EditorialRun)
            .join(EditorialContentState, EditorialContentState.current_run_id == EditorialRun.id)
            .where(
                EditorialRun.owner_id == owner_id,
                EditorialRun.status == "failed",
                EditorialRun.updated_at >= now - timedelta(hours=3),
            )
        )
        or 0
    )
    waiting = int(
        session.scalar(
            select(func.count())
            .select_from(EditorialRun)
            .join(EditorialContentState, EditorialContentState.current_run_id == EditorialRun.id)
            .where(
                EditorialRun.owner_id == owner_id,
                EditorialRun.status.in_(["queued", "running"]),
                EditorialRun.created_at <= now - timedelta(hours=2),
            )
        )
        or 0
    )
    unknown = int(
        session.scalar(
            select(func.count())
            .select_from(EditorialRun)
            .join(EditorialContentState, EditorialContentState.current_run_id == EditorialRun.id)
            .where(EditorialRun.owner_id == owner_id, EditorialRun.status == "unknown")
        )
        or 0
    )
    last = session.scalar(
        select(func.max(EditorialRun.updated_at)).where(
            EditorialRun.owner_id == owner_id,
            EditorialRun.status == "complete",
            EditorialRun.updated_at <= now,
        )
    )
    counts: dict[str, list[int]] = {}
    after = None
    while include_selection:
        query = (
            select(EditorialContentState.content_id)
            .join(EditorialRun, EditorialRun.id == EditorialContentState.current_run_id)
            .where(EditorialContentState.owner_id == owner_id, EditorialRun.created_at >= since)
            .order_by(EditorialContentState.content_id)
            .limit(500)
        )
        if after is not None:
            query = query.where(EditorialContentState.content_id > after)
        ids = tuple(session.scalars(query))
        if not ids:
            break
        for item in load_editorial_publication_inputs_in_transaction(
            session, owner_id=owner_id, content_ids=ids, now=now
        ).values():
            # Fixed inputs, quotes and current field permission are validated by the owning reader.
            if (
                item.run.result is None
                or not item.run.result.selected
                or item.run.result.relevance != "pass"
                or item.backfill
                or not since <= item.first_received_at <= now
            ):
                continue
            pair = counts.setdefault(item.run.source_key, [0, 0])
            pair[0 if item.first_received_at >= now - timedelta(days=7) else 1] += 1
        if len(ids) < 500:
            break
        after = ids[-1]
    return EditorialProcessingHealth(
        failed,
        waiting,
        unknown,
        last,
        tuple(SelectionWindow(key, value[0], value[1]) for key, value in sorted(counts.items())),
    )
