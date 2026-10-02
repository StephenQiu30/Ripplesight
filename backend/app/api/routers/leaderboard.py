from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Response, status

from api.dependencies import LeaderboardReadServiceDependency
from core.schemas import ErrorView
from leaderboard.schemas import (
    BoardKey,
    BoardView,
    ModelDetailView,
    RulesView,
    SourceDetailView,
    SourcesView,
)

router = APIRouter(prefix="/leaderboard", tags=["模型榜"])

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "模型、来源或榜单不存在"},
    422: {"model": ErrorView, "description": "输入条件无效"},
    503: {"model": ErrorView, "description": "数据库不可用或尚无有效发布榜单"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "/boards/{board}",
    operation_id="getLeaderboardBoard",
    response_model=BoardView,
    status_code=status.HTTP_200_OK,
    summary="读取已发布模型榜",
    description="读取最近有效轮次; 筛选保留完整榜单原排名, 不触发抓取或重新计算。",
    responses=_READ_RESPONSES,
)
def get_board(
    board: BoardKey,
    response: Response,
    service: LeaderboardReadServiceDependency,
    domestic: bool = False,
    open_weights: bool = False,
) -> BoardView:
    result = service.board(board, domestic=domestic, open_weights=open_weights)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/models/{slug}",
    operation_id="getLeaderboardModel",
    response_model=ModelDetailView,
    status_code=status.HTTP_200_OK,
    summary="读取模型证据与对比",
    description="查看公开评测、缺项、官方价格、排名稳定性及相邻模型逐项对比。",
    responses=_READ_RESPONSES,
)
def get_model(
    slug: Annotated[str, Path(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")],
    response: Response,
    service: LeaderboardReadServiceDependency,
) -> ModelDetailView:
    result = service.model(slug)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/sources",
    operation_id="listLeaderboardSources",
    response_model=SourcesView,
    status_code=status.HTTP_200_OK,
    summary="读取榜单来源覆盖",
    description="列出来源、运营机构、权重和当前采集状态; 无发布轮次时仍可查看方法注册表。",
    responses={key: value for key, value in _READ_RESPONSES.items() if key != 404},
)
def list_sources(response: Response, service: LeaderboardReadServiceDependency) -> SourcesView:
    result = service.sources()
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/sources/{source_key}",
    operation_id="getLeaderboardSource",
    response_model=SourceDetailView,
    status_code=status.HTTP_200_OK,
    summary="读取评测来源明细",
    description="读取原始分数、配置选择依据、许可、更新时间与排除原因。",
    responses=_READ_RESPONSES,
)
def get_source(
    source_key: Annotated[
        str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    ],
    response: Response,
    service: LeaderboardReadServiceDependency,
) -> SourceDetailView:
    result = service.source(source_key)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/rules",
    operation_id="getLeaderboardRules",
    response_model=RulesView,
    status_code=status.HTTP_200_OK,
    summary="读取模型榜计算规则",
    description="读取算法版本、预算权重、锚点、配置政策和历史证据沿用期限。",
    responses={key: value for key, value in _READ_RESPONSES.items() if key != 404},
)
def get_rules(response: Response, service: LeaderboardReadServiceDependency) -> RulesView:
    result = service.rules()
    response.headers["cache-control"] = "no-store"
    return result
