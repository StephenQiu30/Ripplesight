"""Read-only catalogue routes use the single publication dependency and guarded DTOs."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response

from api.dependencies import PublicationServiceDependency, PublicPublicationScopeDependency
from core.schemas import ErrorView
from publication.edition_schemas import (
    PublicDailyCalendarView,
    PublicEditionCatalogueView,
    PublicEditionNavigationView,
)

router = APIRouter(prefix="/publication/catalogue/editions", tags=["公开刊物目录"])
_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "公开刊物不存在"},
    422: {"model": ErrorView, "description": "刊期、日期或分页输入无效"},
    500: {"model": ErrorView, "description": "内部异常"},
    503: {"model": ErrorView, "description": "当前读取依赖不可用"},
}


@router.get(
    "",
    operation_id="listPublicEditionCatalogue",
    response_model=PublicEditionCatalogueView,
    status_code=200,
    summary="连续分页读取当前可公开刊物历史",
    description="只列最新修订且全部冻结参考仍获许可的已完成刊物;不回退旧稿或生成报告。",
    responses=_ERRORS,
)
def catalogue(
    response: Response,
    service: PublicationServiceDependency,
    owner_id: PublicPublicationScopeDependency,
    kind: Literal["daily", "weekly", "monthly"] = "daily",
    before_key: Annotated[str | None, Query(min_length=7, max_length=10)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PublicEditionCatalogueView:
    response.headers["cache-control"] = "no-store"
    return service.edition_catalogue(
        owner_id=owner_id, kind=kind, before_key=before_key, limit=limit
    )


@router.get(
    "/{kind}/navigation/{key}",
    operation_id="getPublicEditionNavigation",
    response_model=PublicEditionNavigationView,
    status_code=200,
    summary="读取刊期及前后可公开刊物",
    description="逐刊复核当前修订、全部材料与许可;缺刊不会自动换到其他日期。",
    responses=_ERRORS,
)
def navigation(
    kind: Literal["daily", "weekly", "monthly"],
    key: Annotated[str, Path(min_length=7, max_length=10)],
    response: Response,
    service: PublicationServiceDependency,
    owner_id: PublicPublicationScopeDependency,
) -> PublicEditionNavigationView:
    response.headers["cache-control"] = "no-store"
    return service.edition_navigation(owner_id=owner_id, kind=kind, key=key)


@router.get(
    "/daily/months/{month}",
    operation_id="getPublicDailyCalendar",
    response_model=PublicDailyCalendarView,
    status_code=200,
    summary="读取指定北京月份的已公开日报日历",
    description="只列当月真实可读刊期;缺刊与撤回日保持空白,不构造标题或正文。",
    responses=_ERRORS,
)
def daily_calendar(
    month: Annotated[str, Path(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")],
    response: Response,
    service: PublicationServiceDependency,
    owner_id: PublicPublicationScopeDependency,
) -> PublicDailyCalendarView:
    response.headers["cache-control"] = "no-store"
    return service.daily_calendar(owner_id=owner_id, month=month)
