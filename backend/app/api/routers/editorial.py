from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from analysis.editorial_schemas import (
    EditorialOverrideInput,
    EditorialRunInput,
    EditorialRunView,
    EditorialSourceInput,
    EditorialSourceView,
)
from api.dependencies import (
    DemoScopeDependency,
    EditorialServiceDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
)
from core.schemas import ErrorView

router = APIRouter(prefix="/editorial", tags=["编辑分析"])
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "分析不存在或固定材料不可读"},
    422: {"model": ErrorView, "description": "参数校验失败"},
    500: {"model": ErrorView, "description": "内部异常"},
    503: {"model": ErrorView, "description": "数据库或 Demo 分区不可用"},
}
_WRITE_ERRORS = {
    **_READ_ERRORS,
    401: {"model": ErrorView, "description": "缺少独立运营访问凭据"},
    403: {"model": ErrorView, "description": "缺少写入安全校验头"},
    409: {"model": ErrorView, "description": "版本冲突、来源停用或操作标识已使用"},
}


@router.get(
    "/sources",
    operation_id="listEditorialSources",
    response_model=list[EditorialSourceView],
    status_code=status.HTTP_200_OK,
    responses=_READ_ERRORS,
    summary="读取来源的编辑分析配置",
)
def list_sources(
    response: Response, service: EditorialServiceDependency, owner: DemoScopeDependency
) -> list[EditorialSourceView]:
    response.headers["cache-control"] = "no-store"
    return service.list_sources(owner_id=owner)


@router.put(
    "/sources/{source_key}",
    operation_id="saveEditorialSource",
    response_model=EditorialSourceView,
    status_code=status.HTTP_200_OK,
    responses=_WRITE_ERRORS,
    summary="按版本保存来源分级、主体和编辑开关",
)
def save_source(
    source_key: str,
    command: EditorialSourceInput,
    response: Response,
    service: EditorialServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialSourceView:
    response.headers["cache-control"] = "no-store"
    return service.save_source(owner_id=owner, source_key=source_key, command=command)


@router.get(
    "/contents/{content_id}",
    operation_id="getCurrentEditorialRun",
    response_model=EditorialRunView,
    responses={
        **_READ_ERRORS,
        401: {"model": ErrorView, "description": "缺少独立运营访问凭据"},
        403: {"model": ErrorView, "description": "维护入口尚未启用"},
    },
    status_code=status.HTTP_200_OK,
    summary="读取作品当前编辑分析与人工覆盖版本",
)
def get_current_run(
    content_id: UUID,
    response: Response,
    service: EditorialServiceDependency,
    owner: OperatorScopeDependency,
) -> EditorialRunView:
    response.headers["cache-control"] = "no-store"
    return service.get_current_run(owner_id=owner, content_id=content_id)


@router.post(
    "/contents/{content_id}/runs",
    operation_id="requestEditorialRun",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EditorialRunView,
    responses=_WRITE_ERRORS,
    summary="受理固定正文版本的全链路编辑分析",
    description="受理与现有 Job/Outbox 同事务, 不在 HTTP 请求中调用模型。",
)
def request_run(
    content_id: UUID,
    source_key: str,
    command: EditorialRunInput,
    response: Response,
    service: EditorialServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialRunView:
    response.headers["cache-control"] = "no-store"
    return service.request_run(
        owner_id=owner, content_id=content_id, source_key=source_key, command=command
    )


@router.get(
    "/runs/{run_id}",
    operation_id="getEditorialRun",
    response_model=EditorialRunView,
    responses=_READ_ERRORS,
    status_code=status.HTTP_200_OK,
    summary="读取分析结果并复核固定材料的可读权限",
)
def get_run(
    run_id: UUID,
    response: Response,
    service: EditorialServiceDependency,
    owner: DemoScopeDependency,
) -> EditorialRunView:
    response.headers["cache-control"] = "no-store"
    return service.get_run(owner_id=owner, run_id=run_id)


@router.post(
    "/runs/{run_id}/corrections",
    operation_id="correctEditorialRun",
    response_model=EditorialRunView,
    responses={
        **_WRITE_ERRORS,
        401: {"model": ErrorView, "description": "缺少独立运营访问凭据"},
    },
    status_code=status.HTTP_200_OK,
    summary="按人工版本纠正或清除精选、标题摘要、分类推荐理由、标签与静默覆盖",
)
def override(
    run_id: UUID,
    command: EditorialOverrideInput,
    response: Response,
    service: EditorialServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialRunView:
    response.headers["cache-control"] = "no-store"
    return service.override(owner_id=owner, run_id=run_id, command=command)
