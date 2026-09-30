from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from api.dependencies import (
    CommentManualRunServiceDependency,
    ContentServiceDependency,
    DemoScopeDependency,
    DemoWriteScopeDependency,
)
from content.schemas import (
    CommentManualRunInput,
    CommentRunReadinessView,
    ContentCommentView,
    ContentRecordDetailView,
    ContentRecordSummaryView,
)
from core.schemas import ErrorView, JobAcceptedView, PageView

router = APIRouter(prefix="/contents", tags=["作品资料"])

_COMMON_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
    422: {"model": ErrorView, "description": "请求参数校验失败"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "",
    operation_id="listContentRecords",
    response_model=PageView[ContentRecordSummaryView],
    status_code=status.HTTP_200_OK,
    summary="列出作品资料",
    description=(
        "按当前 Demo 分区列出具有可读观察的作品; 可按来源、发现主题、时间窗与当前标注状态筛选。"
        "时间窗使用发布时间, 缺失时回退首次发现时间; 读取不会触发来源或模型请求。"
    ),
    responses=_COMMON_READ_RESPONSES,
)
def list_content_records(
    response: Response,
    service: ContentServiceDependency,
    scope_id: DemoScopeDependency,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    topic_id: UUID | None = None,
    source_key: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    analysis_state: Literal["missing", "pending", "failed", "invalid", "valid"] | None = None,
) -> PageView[ContentRecordSummaryView]:
    items, next_cursor = service.list_contents(
        owner_id=scope_id,
        cursor=cursor,
        limit=limit,
        topic_id=topic_id,
        source_key=source_key,
        starts_at=starts_at,
        ends_at=ends_at,
        analysis_state=analysis_state,
    )
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=next_cursor)


@router.get(
    "/{content_id}",
    operation_id="getContentRecord",
    response_model=ContentRecordDetailView,
    status_code=status.HTTP_200_OK,
    summary="读取作品资料",
    description=(
        "读取当前 Demo 分区的作品身份、最新可读观察、版本/可见性历史与发现依据; 不隐式刷新。"
    ),
    responses={
        404: {"model": ErrorView, "description": "作品不存在或不可访问"},
        **_COMMON_READ_RESPONSES,
    },
)
def get_content_record(
    content_id: UUID,
    response: Response,
    service: ContentServiceDependency,
    scope_id: DemoScopeDependency,
) -> ContentRecordDetailView:
    content = service.get_content(owner_id=scope_id, content_id=content_id)
    response.headers["cache-control"] = "no-store"
    return content


@router.get(
    "/{content_id}/comments",
    operation_id="listContentComments",
    response_model=PageView[ContentCommentView],
    status_code=status.HTTP_200_OK,
    summary="分页读取作品评论",
    description="按线程根、指定根的各层回复或指定直接父节点读取本地可读评论。读取不会触发来源请求。",
    responses={
        404: {"model": ErrorView, "description": "作品或所选评论关系不存在或不可访问"},
        **_COMMON_READ_RESPONSES,
    },
)
def list_content_comments(
    content_id: UUID,
    response: Response,
    service: ContentServiceDependency,
    scope_id: DemoScopeDependency,
    root_id: UUID | None = None,
    parent_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageView[ContentCommentView]:
    items, next_cursor = service.list_comments(
        owner_id=scope_id,
        post_content_id=content_id,
        root_id=root_id,
        parent_id=parent_id,
        cursor=cursor,
        limit=limit,
    )
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=next_cursor)


@router.get(
    "/{content_id}/comment-run-readiness",
    operation_id="getContentCommentRunReadiness",
    response_model=CommentRunReadinessView,
    status_code=status.HTTP_200_OK,
    summary="读取评论复采资格",
    description="只读核对当前作品、来源、主题、预算与频次; 实际受理时重新核对。",
    responses={
        404: {"model": ErrorView, "description": "作品不存在或不可访问"},
        **_COMMON_READ_RESPONSES,
    },
)
def get_content_comment_run_readiness(
    content_id: UUID,
    response: Response,
    service: CommentManualRunServiceDependency,
    scope_id: DemoScopeDependency,
) -> CommentRunReadinessView:
    readiness = service.readiness(owner_id=scope_id, content_id=content_id)
    response.headers["cache-control"] = "no-store"
    return readiness


@router.post(
    "/{content_id}/comment-runs",
    operation_id="runContentComments",
    response_model=JobAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="复采作品评论",
    description="对当前 Demo 分区已入库且仍属于活跃主题的 HN 帖子受理一次有界评论复采。",
    responses={
        200: {"model": JobAcceptedView, "description": "同一操作标识的原 Job"},
        503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
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
    scope_id: DemoWriteScopeDependency,
) -> JobAcceptedView:
    result = service.run(owner_id=scope_id, content_id=content_id, command=payload)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["location"] = f"/api/jobs/{result.job_id}"
    response.headers["cache-control"] = "no-store"
    return JobAcceptedView(job_id=result.job_id, status="queued")
