from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.application import DigestService

from ..dependencies import get_digest_service
from ..serializers import serialize_daily_digest

router = APIRouter()


@router.get("/api/digests/today", tags=["digests"])
def get_today_digest(
    service: DigestService = Depends(get_digest_service),
) -> dict[str, object]:
    digest = service.get_today_digest()
    return serialize_daily_digest(digest)
