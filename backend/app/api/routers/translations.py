from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response

from analysis.translation_schemas import TranslationRequestInput, TranslationRunView
from api.dependencies import (
    DemoScopeDependency,
    DemoWriteScopeDependency,
    TranslationServiceDependency,
)
from core.schemas import ErrorView

router = APIRouter(prefix="/translations", tags=["全文翻译"])
_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "正文或译文不存在"},
    422: {"model": ErrorView, "description": "输入无效"},
    503: {"model": ErrorView, "description": "依赖不可用"},
    500: {"model": ErrorView, "description": "内部异常"},
}


@router.post(
    "/contents/{content_id}",
    operation_id="requestContentTranslation",
    response_model=TranslationRunView,
    status_code=202,
    summary="受理固定全文许可版本的分批翻译",
    responses={
        **_ERRORS,
        403: {"model": ErrorView, "description": "缺少写入安全头"},
        409: {"model": ErrorView, "description": "翻译未启用或译文版本冲突"},
    },
)
def request_translation(
    content_id: UUID,
    command: TranslationRequestInput,
    response: Response,
    service: TranslationServiceDependency,
    owner: DemoWriteScopeDependency,
) -> TranslationRunView:
    response.headers["cache-control"] = "no-store"
    return service.request(owner_id=owner, content_id=content_id, command=command)


@router.get(
    "/{run_id}",
    operation_id="getContentTranslation",
    response_model=TranslationRunView,
    status_code=200,
    summary="复核固定正文和当前许可后读取译文",
    responses=_ERRORS,
)
def get_translation(
    run_id: UUID,
    response: Response,
    service: TranslationServiceDependency,
    owner: DemoScopeDependency,
) -> TranslationRunView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner, run_id=run_id)
