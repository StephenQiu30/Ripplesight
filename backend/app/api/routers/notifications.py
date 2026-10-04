from typing import Any

from fastapi import APIRouter, Response

from api.dependencies import (
    ReportEmailSubscriptionServiceDependency,
    UserScopeDependency,
    UserWriteScopeDependency,
)
from core.schemas import ErrorView
from notifications.schemas import ReportEmailSubscriptionInput, ReportEmailSubscriptionView

router = APIRouter(prefix="/notifications", tags=["个人报告通知"])
_ERRORS: dict[int | str, dict[str, Any]] = {code: {"model": ErrorView} for code in (401, 500, 503)}


@router.get(
    "/email-subscription",
    operation_id="getReportEmailSubscription",
    summary="读取本人的报告邮件订阅",
    status_code=200,
    response_model=ReportEmailSubscriptionView,
    responses=_ERRORS,
)
def get_report_email_subscription(
    response: Response,
    service: ReportEmailSubscriptionServiceDependency,
    owner_id: UserScopeDependency,
) -> ReportEmailSubscriptionView:
    response.headers["cache-control"] = "private, no-store"
    return service.read(owner_id=owner_id)


@router.put(
    "/email-subscription",
    operation_id="updateReportEmailSubscription",
    summary="设置本人的报告邮件订阅",
    description="收件人为当前已验证绑定邮箱;普通会话和CSRF,无需运营令牌;修订CAS及操作幂等。",
    status_code=200,
    response_model=ReportEmailSubscriptionView,
    responses={**_ERRORS, **{code: {"model": ErrorView} for code in (403, 409, 422)}},
)
def update_report_email_subscription(
    command: ReportEmailSubscriptionInput,
    response: Response,
    service: ReportEmailSubscriptionServiceDependency,
    owner_id: UserWriteScopeDependency,
) -> ReportEmailSubscriptionView:
    response.headers["cache-control"] = "private, no-store"
    return service.save(owner_id=owner_id, command=command)
