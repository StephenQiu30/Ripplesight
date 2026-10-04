from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from api.dependencies import (
    SourceConnectionServiceDependency,
    UserScopeDependency,
)
from connections.catalog import list_public_platform_catalog
from connections.catalog_schemas import PublicPlatformCatalogView
from connections.schemas import SourcePlatformView
from core.schemas import ErrorView, PageView

router = APIRouter(prefix="/source-capabilities", tags=["来源能力"])

_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
    422: {"model": ErrorView, "description": "请求参数校验失败"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "/public-platforms",
    operation_id="listPublicPlatformCatalog",
    response_model=PageView[PublicPlatformCatalogView],
    status_code=status.HTTP_200_OK,
    summary="列出七平台免费入口候选",
    description=(
        "返回固定RSSHub源码核验的七平台入口、能力与阻断原因。"
        "资料声明、执行准入、真实试点和产品可用分别标记。"
        "不读取来源凭据。不创建连接或任务。不访问平台或本机采集服务。"
    ),
    responses={
        401: {"model": ErrorView, "description": "会话无效或已撤销"},
        503: {"model": ErrorView, "description": "账户会话存储不可用"},
        500: {"model": ErrorView, "description": "服务内部异常"},
    },
)
def list_public_platforms(
    response: Response,
    _scope_id: UserScopeDependency,
) -> PageView[PublicPlatformCatalogView]:
    response.headers["cache-control"] = "private, no-store"
    return PageView(items=list_public_platform_catalog(), next_cursor=None)


@router.get(
    "",
    operation_id="listSourceCapabilities",
    response_model=PageView[SourcePlatformView],
    status_code=status.HTTP_200_OK,
    summary="列出来源能力",
    description="按当前账户返回已实现来源目录、连接版本及手动/定时入口的持久状态。",
    responses=_RESPONSES,
)
def list_source_capabilities(
    response: Response,
    service: SourceConnectionServiceDependency,
    scope_id: UserScopeDependency,
) -> PageView[SourcePlatformView]:
    response.headers["cache-control"] = "no-store"
    return PageView(
        items=service.list_platforms(owner_id=scope_id),
        next_cursor=None,
    )
