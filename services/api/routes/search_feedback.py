from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from backend.core.application import FeedbackService, SearchService

from ..dependencies import get_feedback_service, get_search_service
from ..schemas import FeedbackSubmission
from ..serializers import (
    paginate,
    serialize_feedback_record,
    serialize_hotspot_event,
    serialize_page_meta,
)

router = APIRouter()


@router.get("/api/search", tags=["search"])
def search_events(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    items = service.search_events(q)
    paged_items, meta = paginate(items, page=page, page_size=page_size)
    return {"items": [serialize_hotspot_event(item) for item in paged_items], "meta": serialize_page_meta(meta)}


@router.post("/api/feedback", tags=["feedback"], status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackSubmission,
    service: FeedbackService = Depends(get_feedback_service),
) -> dict[str, object]:
    feedback = service.submit_feedback(
        target_type=payload.target_type,
        target_id=payload.target_id,
        feedback_type=payload.feedback_type,
        comment=payload.comment,
    )
    return serialize_feedback_record(feedback)
