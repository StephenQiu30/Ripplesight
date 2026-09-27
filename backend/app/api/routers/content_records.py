from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from api.dependencies import (
    AuthenticatedIdentityDependency,
    CommentManualRunServiceDependency,
    ContentServiceDependency,
    CsrfProtectedIdentityDependency,
)
from content.schemas import CommentManualRunInput, ContentRecordDetailView, ContentRecordSummaryView
from core.schemas import ErrorView, JobAcceptedView, PageView

router = APIRouter(prefix="/contents", tags=["作品资料"])

_COMMON_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView, "description": "会话无效或已过期"},
    422: {"model": ErrorView, "description": "请求参数校验失败"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "",
    operation_id="listContentRecords",
    response_model=PageView[ContentRecordSummaryView],
    status_code=status.HTTP_200_OK,
    summary="列出作品资料",
    description="按当前 owner 列出具有可读观察的作品及当前来源状态; 读取不会触发来源请求。",
    responses=_COMMON_READ_RESPONSES,
)
def list_content_records(
    response: Response,
    service: ContentServiceDependency,
    identity: AuthenticatedIdentityDependency,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageView[ContentRecordSummaryView]:
    items, next_cursor = service.list_contents(
        owner_id=identity.view.user.id,
        cursor=cursor,
        limit=limit,
    )
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=next_cursor)


@router.get(
    "/{content_id}",
    operation_id="getContentRecord",
    response_model=ContentRecordDetailView,
    status_code=status.HTTP_200_OK,
    summary="读取作品资料",
    description="读取当前 owner 的作品身份、最新可读观察、版本/可见性历史与发现依据; 不隐式刷新。",
    responses={
        404: {"model": ErrorView, "description": "作品不存在或不可访问"},
        **_COMMON_READ_RESPONSES,
    },
)
def get_content_record(
    content_id: UUID,
    response: Response,
    service: ContentServiceDependency,
    identity: AuthenticatedIdentityDependency,
) -> ContentRecordDetailView:
    content = service.get_content(owner_id=identity.view.user.id, content_id=content_id)
    response.headers["cache-control"] = "no-store"
    return content


@router.post(
    "/{content_id}/comment-runs",
    operation_id="runContentComments",
    response_model=JobAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="复采作品评论",
    description="对当前 owner 已入库且仍属于活跃主题的 HN 帖子受理一次有界评论复采。",
    responses={
        200: {"model": JobAcceptedView, "description": "同一操作标识的原 Job"},
        401: {"model": ErrorView, "description": "会话无效或已过期"},
        403: {"model": ErrorView, "description": "请求安全校验失败"},
        404: {"model": ErrorView, "description": "作品不存在或不可访问"},
        409: {"model": ErrorView, "description": "来源能力、频次或预算不允许复采"},
        422: {"model": ErrorView, "description": "请求参数校验失败"},
        500: {"model": ErrorView, "description": "服务内部异常"},
    },
)
def run_content_comments(
    content_id: UUID,
    payload: CommentManualRunInput,
    response: Response,
    service: CommentManualRunServiceDependency,
    identity: CsrfProtectedIdentityDependency,
) -> JobAcceptedView:
    result = service.run(owner_id=identity.view.user.id, content_id=content_id, command=payload)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["location"] = f"/api/jobs/{result.job_id}"
    response.headers["cache-control"] = "no-store"
    return JobAcceptedView(job_id=result.job_id, status="queued")
