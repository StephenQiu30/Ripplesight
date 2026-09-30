from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from api.dependencies import DemoScopeDependency, HotlistServiceDependency
from content.schemas import HotlistSnapshotSummaryView, HotlistSnapshotView, HotlistSourceView
from core.schemas import ErrorView, PageView

router = APIRouter(prefix="/hotlists", tags=["热榜"])

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
    422: {"model": ErrorView, "description": "请求参数校验失败"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "/sources",
    operation_id="listHotlistSources",
    response_model=PageView[HotlistSourceView],
    status_code=status.HTTP_200_OK,
    summary="列出已应用热榜来源",
    description="仅列出当前 Demo 分区已应用的热榜来源及最近快照时间。读取不会访问 RSSHub。",
    responses=_READ_RESPONSES,
)
def list_hotlist_sources(
    response: Response,
    service: HotlistServiceDependency,
    scope_id: DemoScopeDependency,
) -> PageView[HotlistSourceView]:
    items = service.list_sources(owner_id=scope_id)
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=None)


@router.get(
    "/{source_key}/snapshots",
    operation_id="listHotlistSnapshots",
    response_model=PageView[HotlistSnapshotSummaryView],
    status_code=status.HTTP_200_OK,
    summary="列出热榜历史快照",
    description="按观察时间和快照 ID 倒序读取当前 Demo 分区的持久快照。游标限定同一来源。",
    responses={404: {"model": ErrorView, "description": "热榜来源未应用"}, **_READ_RESPONSES},
)
def list_hotlist_snapshots(
    source_key: Annotated[
        str, Path(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    ],
    response: Response,
    service: HotlistServiceDependency,
    scope_id: DemoScopeDependency,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageView[HotlistSnapshotSummaryView]:
    try:
        items, next_cursor = service.list_history(
            owner_id=scope_id,
            source_key=source_key,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=422) from error
    response.headers["cache-control"] = "no-store"
    return PageView(items=list(items), next_cursor=next_cursor)


@router.get(
    "/{source_key}/snapshots/{snapshot_id}",
    operation_id="getHistoricalHotlistSnapshot",
    response_model=HotlistSnapshotView,
    status_code=status.HTTP_200_OK,
    summary="读取指定热榜历史快照",
    description="固定快照 ID 按原始榜位分页。排名与同来源前一成功快照比较。",
    responses={404: {"model": ErrorView, "description": "来源或快照不存在"}, **_READ_RESPONSES},
)
def get_historical_hotlist_snapshot(
    source_key: Annotated[
        str, Path(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    ],
    snapshot_id: UUID,
    response: Response,
    service: HotlistServiceDependency,
    scope_id: DemoScopeDependency,
    cursor: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HotlistSnapshotView:
    snapshot = service.get_historical(
        owner_id=scope_id,
        source_key=source_key,
        snapshot_id=snapshot_id,
        cursor=cursor,
        limit=limit,
    )
    response.headers["cache-control"] = "no-store"
    return snapshot


@router.get(
    "/{source_key}",
    operation_id="getHotlistSnapshot",
    response_model=HotlistSnapshotView,
    status_code=status.HTTP_200_OK,
    summary="读取最新热榜快照",
    description="读取当前 Demo 分区最近一次快照及与上次快照的排名变化。按排名游标分页。",
    responses={
        404: {"model": ErrorView, "description": "来源未应用或尚无快照"},
        **_READ_RESPONSES,
    },
)
def get_hotlist_snapshot(
    source_key: Annotated[
        str, Path(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    ],
    response: Response,
    service: HotlistServiceDependency,
    scope_id: DemoScopeDependency,
    cursor: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HotlistSnapshotView:
    snapshot = service.get_latest(
        owner_id=scope_id,
        source_key=source_key,
        cursor=cursor,
        limit=limit,
    )
    response.headers["cache-control"] = "no-store"
    return snapshot
