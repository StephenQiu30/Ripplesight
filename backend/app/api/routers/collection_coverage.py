from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from api.dependencies import (
    AuthenticatedIdentityDependency,
    CollectionCoverageServiceDependency,
)
from core.schemas import ErrorView, PageView
from jobs.schemas import CollectionCoverageView
from sources.contracts import SourceCapability

router = APIRouter(prefix="/collection-coverage", tags=["采集覆盖"])

_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView, "description": "会话无效或已过期"},
    404: {"model": ErrorView, "description": "窗口不存在或不可访问"},
    422: {"model": ErrorView, "description": "时间范围或游标无效"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "",
    operation_id="listCollectionCoverage",
    response_model=PageView[CollectionCoverageView],
    status_code=status.HTTP_200_OK,
    summary="列出采集覆盖窗口",
    description="按到期点倒序查询当前 owner 的持久采集事实。读取不访问来源站点。",
    responses=_READ_ERRORS,
)
def list_collection_coverage(
    response: Response,
    service: CollectionCoverageServiceDependency,
    identity: AuthenticatedIdentityDependency,
    start: datetime,
    end: datetime,
    source_key: Annotated[
        str | None, Query(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    ] = None,
    capability: SourceCapability | None = None,
    topic_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
) -> PageView[CollectionCoverageView]:
    if (
        start.utcoffset() != timedelta(0)
        or end.utcoffset() != timedelta(0)
        or start >= end
        or end - start > timedelta(days=31)
    ):
        raise HTTPException(status_code=422, detail="无效的 UTC 时间范围")
    try:
        items, next_cursor = service.list_coverage(
            owner_id=identity.view.user.id,
            start=start,
            end=end,
            source_key=source_key,
            capability=capability,
            topic_id=topic_id,
            limit=limit,
            cursor=cursor,
            cursor_key=identity.csrf_digest,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="无效的覆盖查询游标") from error
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=next_cursor)


@router.get(
    "/{window_id}",
    operation_id="getCollectionCoverage",
    response_model=CollectionCoverageView,
    status_code=status.HTTP_200_OK,
    summary="读取采集覆盖窗口",
    description="按当前 owner 读取指定到期窗的执行、内容、分析和预算事实。",
    responses=_READ_ERRORS,
)
def get_collection_coverage(
    window_id: UUID,
    response: Response,
    service: CollectionCoverageServiceDependency,
    identity: AuthenticatedIdentityDependency,
) -> CollectionCoverageView:
    try:
        item = service.get_coverage(owner_id=identity.view.user.id, window_id=window_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="覆盖窗口不存在") from error
    response.headers["cache-control"] = "no-store"
    return item
