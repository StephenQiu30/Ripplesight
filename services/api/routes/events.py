from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.domain import SourceType

from ..dependencies import get_initialized_hotspot_event_repository
from ..errors import error_payload
from ..serializers import filter_events, paginate, serialize_hotspot_event, serialize_page_meta

router = APIRouter()


@router.get("/api/events", tags=["events"])
def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    topic: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    repository=Depends(get_initialized_hotspot_event_repository),
) -> dict[str, object]:
    events = list(repository.list_all())
    filtered = filter_events(
        events,
        source_type=source_type,
        from_date=_start_of_day(from_date),
        to_date=_end_of_day(to_date),
        topic=topic,
    )
    paged_items, meta = paginate(filtered, page=page, page_size=page_size)
    return {"items": [serialize_hotspot_event(item) for item in paged_items], "meta": serialize_page_meta(meta)}


@router.get("/api/events/{event_id}", tags=["events"])
def get_event(event_id: str, repository=Depends(get_initialized_hotspot_event_repository)) -> dict[str, object]:
    events = list(repository.list_all())
    event = next((item for item in events if item.id == event_id), None)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=error_payload(code="event_not_found", message="Hotspot event not found"),
        )
    return serialize_hotspot_event(event)


def _start_of_day(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=UTC)


def _end_of_day(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=UTC)
