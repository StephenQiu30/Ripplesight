from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.application import SourceGovernanceService

from ..dependencies import get_governance_service
from ..serializers import (
    paginate,
    serialize_keyword_rule,
    serialize_monitored_account,
    serialize_page_meta,
    serialize_source_config,
)

router = APIRouter()


@router.get("/api/sources", tags=["sources"])
def list_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    enabled: bool | None = Query(default=None),
    service: SourceGovernanceService = Depends(get_governance_service),
) -> dict[str, object]:
    items = service.list_sources(enabled=enabled)
    paged_items, meta = paginate(items, page=page, page_size=page_size)
    return {"items": [serialize_source_config(item) for item in paged_items], "meta": serialize_page_meta(meta)}


@router.get("/api/x/keywords", tags=["x-config"])
def list_keyword_rules(
    service: SourceGovernanceService = Depends(get_governance_service),
) -> dict[str, object]:
    items = service.list_keyword_rules(enabled=None)
    return {
        "items": [serialize_keyword_rule(item) for item in items],
        "meta": serialize_page_meta(paginate(items, page=1, page_size=len(items) or 1)[1]),
    }


@router.get("/api/x/accounts", tags=["x-config"])
def list_monitored_accounts(
    service: SourceGovernanceService = Depends(get_governance_service),
) -> dict[str, object]:
    items = service.list_monitored_accounts(enabled=None)
    return {
        "items": [serialize_monitored_account(item) for item in items],
        "meta": serialize_page_meta(paginate(items, page=1, page_size=len(items) or 1)[1]),
    }
