from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from api.dependencies import EditionServiceDependency, UserScopeDependency, UserWriteScopeDependency
from core.schemas import ErrorView
from reports.edition_rules import EditionKind
from reports.edition_schemas import (
    EditionCorrectionInput,
    EditionDetailView,
    EditionRequestInput,
    EditionSummaryView,
)

router = APIRouter(prefix="/editions", tags=["日周月刊"])
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "刊期不存在"},
    422: {"model": ErrorView, "description": "输入校验失败"},
    500: {"model": ErrorView, "description": "内部异常"},
    503: {"model": ErrorView, "description": "数据库或Demo分区不可用"},
}
_WRITE_ERRORS = {
    **_READ_ERRORS,
    403: {"model": ErrorView, "description": "缺少写入安全头"},
    409: {"model": ErrorView, "description": "刊期版本冲突或材料许可变更"},
}


@router.get(
    "",
    operation_id="listReportEditions",
    response_model=list[EditionSummaryView],
    status_code=status.HTTP_200_OK,
    responses=_READ_ERRORS,
    summary="按日周月读取最新刊期修订",
)
def list_editions(
    response: Response,
    service: EditionServiceDependency,
    owner: UserScopeDependency,
    kind: EditionKind = "daily",
    before_key: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> tuple[EditionSummaryView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list(owner_id=owner, kind=kind, before_key=before_key, limit=limit)


@router.post(
    "",
    operation_id="requestReportEdition",
    response_model=EditionDetailView,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_WRITE_ERRORS,
    summary="接受完整自然刊期的冻结编选任务",
)
def request_edition(
    command: EditionRequestInput,
    response: Response,
    service: EditionServiceDependency,
    owner: UserWriteScopeDependency,
) -> EditionDetailView:
    response.headers["cache-control"] = "no-store"
    return service.request(owner_id=owner, actor_id=owner, command=command)


@router.get(
    "/{edition_id}",
    operation_id="getReportEdition",
    response_model=EditionDetailView,
    status_code=status.HTTP_200_OK,
    responses=_READ_ERRORS,
    summary="复核全部材料许可后读取刊期正文",
)
def get_edition(
    edition_id: UUID,
    response: Response,
    service: EditionServiceDependency,
    owner: UserScopeDependency,
) -> EditionDetailView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner, edition_id=edition_id)


@router.get(
    "/{edition_id}/revisions",
    operation_id="listReportEditionRevisions",
    response_model=list[EditionSummaryView],
    status_code=status.HTTP_200_OK,
    responses=_READ_ERRORS,
    summary="读取逐刊历史修订与当前可读状态",
)
def list_revisions(
    edition_id: UUID,
    response: Response,
    service: EditionServiceDependency,
    owner: UserScopeDependency,
    limit: int = Query(default=50, ge=1, le=100),
) -> tuple[EditionSummaryView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.revisions(owner_id=owner, edition_id=edition_id, limit=limit)


@router.post(
    "/{edition_id}/corrections",
    operation_id="correctReportEdition",
    response_model=EditionDetailView,
    status_code=status.HTTP_200_OK,
    responses=_WRITE_ERRORS,
    summary="以版本校验保存人工修订并保留旧稿",
)
def correct_edition(
    edition_id: UUID,
    command: EditionCorrectionInput,
    response: Response,
    service: EditionServiceDependency,
    owner: UserWriteScopeDependency,
) -> EditionDetailView:
    response.headers["cache-control"] = "no-store"
    return service.correct(owner_id=owner, actor_id=owner, edition_id=edition_id, command=command)
