from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Response

from api.dependencies import AlertServiceDependency, UserScopeDependency, UserWriteScopeDependency
from core.schemas import ErrorView
from notifications.alert_schemas import (
    AlertEvaluationView,
    AlertRuleInput,
    AlertRuleView,
    AlertTargetView,
)

router = APIRouter(prefix="/alerts", tags=["个人突发告警"])
_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorView} for code in (401, 403, 404, 409, 422, 500, 503)
}


@router.get(
    "",
    operation_id="listAlerts",
    response_model=list[AlertRuleView],
    status_code=200,
    responses=_ERRORS,
)
def list_alerts(
    response: Response, service: AlertServiceDependency, owner_id: UserScopeDependency
) -> list[AlertRuleView]:
    response.headers["cache-control"] = "private, no-store"
    return service.list_rules(owner_id=owner_id)


@router.get(
    "/targets",
    operation_id="listAlertTargets",
    response_model=list[AlertTargetView],
    status_code=200,
    responses=_ERRORS,
)
def list_alert_targets(
    response: Response, service: AlertServiceDependency, owner_id: UserScopeDependency
) -> list[AlertTargetView]:
    response.headers["cache-control"] = "private, no-store"
    return service.targets(owner_id=owner_id)


@router.post(
    "", operation_id="createAlert", response_model=AlertRuleView, status_code=201, responses=_ERRORS
)
def create_alert(
    command: AlertRuleInput,
    response: Response,
    service: AlertServiceDependency,
    owner_id: UserWriteScopeDependency,
) -> AlertRuleView:
    response.headers["cache-control"] = "private, no-store"
    return service.save(owner_id=owner_id, command=command)


@router.put(
    "/{rule_id}",
    operation_id="updateAlert",
    response_model=AlertRuleView,
    status_code=200,
    responses=_ERRORS,
)
def update_alert(
    rule_id: UUID,
    command: AlertRuleInput,
    response: Response,
    service: AlertServiceDependency,
    owner_id: UserWriteScopeDependency,
) -> AlertRuleView:
    response.headers["cache-control"] = "private, no-store"
    return service.save(owner_id=owner_id, rule_id=rule_id, command=command)


@router.get(
    "/{rule_id}/history",
    operation_id="listAlertHistory",
    response_model=list[AlertEvaluationView],
    status_code=200,
    responses=_ERRORS,
)
def list_alert_history(
    rule_id: UUID,
    response: Response,
    service: AlertServiceDependency,
    owner_id: UserScopeDependency,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[AlertEvaluationView]:
    response.headers["cache-control"] = "private, no-store"
    return service.history(owner_id=owner_id, rule_id=rule_id, limit=limit)
