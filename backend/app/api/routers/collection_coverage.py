from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from api.dependencies import CollectionCoverageServiceDependency, UserScopeDependency
from core.schemas import ErrorView, PageView
from jobs.schemas import CollectionCoverageMetricsView, CollectionCoverageView
from sources.contracts import SourceCapability

router = APIRouter(prefix="/collection-coverage", tags=["采集覆盖"])

_READ_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
    404: {"model": ErrorView, "description": "到期窗口不存在或不可访问"},
    422: {"model": ErrorView, "description": "查询时间或游标无效"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}
_METRICS_ERROR_RESPONSES = {
    code: response for code, response in _READ_ERROR_RESPONSES.items() if code != 404
}


@router.get(
    "",
    operation_id="listCollectionCoverage",
    response_model=PageView[CollectionCoverageView],
    status_code=status.HTTP_200_OK,
    summary="按来源与时间查询采集覆盖",
    description="从当前 Demo 分区可访问来源的持久到期窗口分页读取任务、内容、分析与预算事实。",
    responses=_READ_ERROR_RESPONSES,
)
def list_collection_coverage(
    response: Response,
    service: CollectionCoverageServiceDependency,
    scope_id: UserScopeDependency,
    start: Annotated[
        datetime,
        Query(description="UTC 到期范围起点 (包含)", examples=["2026-09-27T00:00:00Z"]),
    ],
    end: Annotated[
        datetime,
        Query(
            description="UTC 到期范围终点 (不包含); 最多比起点晚 31 天",
            examples=["2026-09-28T00:00:00Z"],
        ),
    ],
    source_key: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = None,
    capability: SourceCapability | None = None,
    topic_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[
        str | None,
        Query(min_length=44, max_length=44, description="上一页返回的不透明游标"),
    ] = None,
) -> PageView[CollectionCoverageView]:
    try:
        items, next_cursor = service.list_coverage(
            owner_id=scope_id,
            start=start,
            end=end,
            source_key=source_key,
            capability=capability,
            topic_id=topic_id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as error:
        raise HTTPException(status_code=422) from error
    response.headers["cache-control"] = "no-store"
    return PageView(items=list(items), next_cursor=next_cursor)


@router.get(
    "/metrics",
    operation_id="getCollectionCoverageMetrics",
    response_model=CollectionCoverageMetricsView,
    status_code=status.HTTP_200_OK,
    summary="复算逐来源采集时效与热榜桶",
    description=(
        "按当前可访问来源及 UTC 到期窗复算采集指标。"
        "分析时效与热榜相位冻结尚无足够持久事实时显式标为未验证。"
    ),
    responses=_METRICS_ERROR_RESPONSES,
)
def get_collection_coverage_metrics(
    response: Response,
    service: CollectionCoverageServiceDependency,
    scope_id: UserScopeDependency,
    start: Annotated[datetime, Query(description="UTC 到期范围起点 (包含)")],
    end: Annotated[datetime, Query(description="UTC 到期范围终点 (不包含); 最多 31 天")],
    source_key: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = None,
    capability: SourceCapability | None = None,
    topic_id: UUID | None = None,
) -> CollectionCoverageMetricsView:
    try:
        result = service.get_metrics(
            owner_id=scope_id,
            start=start,
            end=end,
            source_key=source_key,
            capability=capability,
            topic_id=topic_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422) from error
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{window_id}",
    operation_id="getCollectionCoverage",
    response_model=CollectionCoverageView,
    status_code=status.HTTP_200_OK,
    summary="读取单个采集覆盖窗口",
    description="按当前 Demo 分区和当前可访问来源读取窗口及其持久事实。",
    responses=_READ_ERROR_RESPONSES,
)
def get_collection_coverage(
    window_id: UUID,
    response: Response,
    service: CollectionCoverageServiceDependency,
    scope_id: UserScopeDependency,
) -> CollectionCoverageView:
    view = service.get_coverage(owner_id=scope_id, window_id=window_id)
    response.headers["cache-control"] = "no-store"
    return view
