from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from analysis.evaluation_schemas import (
    RelationBenchCasesView,
    RelationBenchGoldInput,
    RelationBenchImportInput,
    SelectBenchAcceptedView,
    SelectBenchCasesView,
    SelectBenchGoldInput,
    SelectBenchImportInput,
    SelectBenchRunView,
)
from api.dependencies import (
    NotificationOperatorServiceDependency,
    NotificationTargetServiceDependency,
    OperationsServiceDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    SelectBenchServiceDependency,
    SessionDependency,
    UserWriteScopeDependency,
)
from core.config import Settings
from core.schemas import ErrorView, PageView
from jobs.schemas import BudgetPolicyView
from notifications.schemas import (
    DeliveryResolutionInput,
    NotificationDeliveryView,
    TargetSaveInput,
    TargetView,
)
from operations.maintenance import read_maintenance_state
from operations.schemas import (
    AuditResolutionInput,
    BudgetUpdateInput,
    DictionaryInput,
    DictionaryView,
    FeedbackInput,
    FeedbackSubmissionView,
    FeedbackUpdateInput,
    FeedbackUpdateView,
    FeedbackView,
    MaintenanceAcceptedView,
    MaintenanceInput,
    MaintenanceStateView,
    OperationsHealthView,
    OperatorAuditView,
)

router = APIRouter(prefix="/operations", tags=["运营维护"])
feedback_router = APIRouter(prefix="/feedback", tags=["反馈"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView, "description": "缺少或无效的独立运营凭据"},
    403: {"model": ErrorView, "description": "运营未启用或缺少写入CSRF头"},
    404: {"model": ErrorView, "description": "记录不属于当前分区"},
    409: {"model": ErrorView, "description": "修订或操作幂等冲突"},
    422: {"model": ErrorView, "description": "输入字段无效"},
    503: {"model": ErrorView, "description": "存储或功能配置不可用"},
}


@router.get(
    "/notification-targets",
    operation_id="listOperatorNotificationTargets",
    response_model=tuple[TargetView, ...],
    status_code=status.HTTP_200_OK,
    summary="读取通知目标与订阅",
    responses=_RESPONSES,
)
def list_operator_notification_targets(
    response: Response,
    service: NotificationTargetServiceDependency,
    scope_id: OperatorScopeDependency,
) -> tuple[TargetView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list(owner_id=scope_id)


@router.put(
    "/notification-targets",
    operation_id="saveOperatorNotificationTarget",
    response_model=TargetView,
    status_code=status.HTTP_200_OK,
    summary="配置通知目标与四类订阅",
    description="独立运营授权和CSRF;修订CAS与操作幂等。默认停用;启用时间重新计时防历史回发。凭据仅环境配置。",
    responses=_RESPONSES,
)
def save_operator_notification_target(
    command: TargetSaveInput,
    response: Response,
    service: NotificationTargetServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> TargetView:
    response.headers["cache-control"] = "no-store"
    return service.save(owner_id=scope_id, command=command, now=datetime.now(UTC))


@router.get(
    "/notification-deliveries",
    operation_id="listOperatorNotificationDeliveries",
    response_model=PageView[NotificationDeliveryView],
    status_code=status.HTTP_200_OK,
    summary="分页读取通知账本与真实渠道回执",
    responses=_RESPONSES,
)
def list_operator_notification_deliveries(
    response: Response,
    service: NotificationOperatorServiceDependency,
    scope_id: OperatorScopeDependency,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PageView[NotificationDeliveryView]:
    items, after = service.list_deliveries(owner_id=scope_id, cursor=cursor, limit=limit)
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=str(after) if after else None)


@router.post(
    "/notification-deliveries/{delivery_id}/resolve",
    operation_id="resolveOperatorNotificationDelivery",
    response_model=NotificationDeliveryView,
    status_code=status.HTTP_200_OK,
    summary="人工核对未知通知结果",
    description="同事务修订CAS、审计与原Job资格。确认未送达后仅允许显式重试原任务,不会立即重送。",
    responses=_RESPONSES,
)
def resolve_operator_notification_delivery(
    delivery_id: UUID,
    command: DeliveryResolutionInput,
    response: Response,
    service: NotificationOperatorServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> NotificationDeliveryView:
    response.headers["cache-control"] = "no-store"
    return service.resolve(owner_id=scope_id, delivery_id=delivery_id, command=command)


@feedback_router.post(
    "",
    operation_id="submitFeedback",
    response_model=FeedbackSubmissionView,
    status_code=status.HTTP_201_CREATED,
    summary="提交反馈与可选私有截图",
    description="按操作ID幂等;HMAC客户端来源持久冷却60秒。截图仅运营可读,不触发外部投递。",
    responses={
        **_RESPONSES,
        429: {"model": ErrorView, "description": "反馈冷却中,响应含Retry-After"},
    },
)
def submit_feedback(
    command: FeedbackInput,
    request: Request,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: UserWriteScopeDependency,
) -> FeedbackSubmissionView:
    result = service.submit_feedback(
        owner_id=scope_id,
        command=command,
        client_ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/health",
    operation_id="getOperationsHealth",
    response_model=OperationsHealthView,
    status_code=status.HTTP_200_OK,
    summary="读取实际进程、预算与失败状态",
    responses=_RESPONSES,
)
def get_operations_health(
    response: Response, service: OperationsServiceDependency, scope_id: OperatorScopeDependency
) -> OperationsHealthView:
    response.headers["cache-control"] = "no-store"
    return service.get_health(owner_id=scope_id)


@router.get(
    "/feedback",
    operation_id="listOperatorFeedback",
    response_model=PageView[FeedbackView],
    status_code=status.HTTP_200_OK,
    summary="运营分页查看反馈",
    responses=_RESPONSES,
)
def list_operator_feedback(
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorScopeDependency,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    state: Literal["new", "reviewing", "resolved", "rejected", "deleted"] | None = None,
) -> PageView[FeedbackView]:
    items, after = service.list_feedback(
        owner_id=scope_id, cursor=cursor, limit=limit, status=state
    )
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=str(after) if after else None)


@router.patch(
    "/feedback/{feedback_id}",
    operation_id="updateOperatorFeedback",
    response_model=FeedbackUpdateView,
    status_code=status.HTTP_200_OK,
    summary="运营处理、屏蔽或删除反馈",
    responses=_RESPONSES,
)
def update_operator_feedback(
    feedback_id: UUID,
    command: FeedbackUpdateInput,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> FeedbackUpdateView:
    result = service.update_feedback(owner_id=scope_id, feedback_id=feedback_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/feedback-attachments/{attachment_id}",
    operation_id="getOperatorFeedbackAttachment",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="读取运营私有反馈截图",
    responses={
        **_RESPONSES,
        200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}, "image/gif": {}}},
    },
)
def get_operator_feedback_attachment(
    attachment_id: UUID, service: OperationsServiceDependency, scope_id: OperatorScopeDependency
) -> Response:
    data, mime = service.read_attachment(owner_id=scope_id, attachment_id=attachment_id)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "content-security-policy": "default-src 'none'",
        },
    )


@router.get(
    "/audit",
    operation_id="listOperatorAudit",
    response_model=PageView[OperatorAuditView],
    status_code=status.HTTP_200_OK,
    summary="查看运营操作审计",
    responses=_RESPONSES,
)
def list_operator_audit(
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorScopeDependency,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PageView[OperatorAuditView]:
    items, after = service.list_audit(owner_id=scope_id, cursor=cursor, limit=limit)
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=str(after) if after else None)


@router.post(
    "/audit/{audit_id}/resolve-delivery",
    operation_id="resolveOperatorDelivery",
    response_model=OperatorAuditView,
    status_code=status.HTTP_200_OK,
    summary="按目的地实际证据人工核对未知运营投递",
    responses=_RESPONSES,
)
def resolve_operator_delivery(
    audit_id: UUID,
    command: AuditResolutionInput,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> OperatorAuditView:
    result = service.resolve_delivery(owner_id=scope_id, audit_id=audit_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/dictionaries",
    operation_id="listOperatorDictionaries",
    response_model=list[DictionaryView],
    status_code=status.HTTP_200_OK,
    summary="读取当前词典版本",
    responses=_RESPONSES,
)
def list_operator_dictionaries(
    response: Response, service: OperationsServiceDependency, scope_id: OperatorScopeDependency
) -> list[DictionaryView]:
    response.headers["cache-control"] = "no-store"
    return service.list_dictionaries(owner_id=scope_id)


@router.put(
    "/dictionaries",
    operation_id="saveOperatorDictionary",
    response_model=DictionaryView,
    status_code=status.HTTP_200_OK,
    summary="保存可复验的词典新版本",
    responses=_RESPONSES,
)
def save_operator_dictionary(
    command: DictionaryInput,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> DictionaryView:
    result = service.save_dictionary(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.put(
    "/budgets",
    operation_id="updateOperatorBudget",
    response_model=BudgetPolicyView,
    status_code=status.HTTP_200_OK,
    summary="按账本政策版本修改预算",
    responses=_RESPONSES,
)
def update_operator_budget(
    command: BudgetUpdateInput,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> BudgetPolicyView:
    result = service.update_budget(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/maintenance",
    operation_id="getOperatorMaintenance",
    response_model=MaintenanceStateView,
    status_code=status.HTTP_200_OK,
    summary="读取实际维护计划与执行证据",
    responses=_RESPONSES,
)
def get_operator_maintenance(
    request: Request,
    response: Response,
    session: SessionDependency,
    scope_id: OperatorScopeDependency,
) -> MaintenanceStateView:
    settings: Settings = request.app.state.settings
    result = read_maintenance_state(
        session, owner_id=scope_id, settings=settings, now=datetime.now(UTC)
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.post(
    "/maintenance",
    operation_id="runOperatorMaintenance",
    response_model=MaintenanceAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="接受有界维护任务",
    description="仅固定配置和备份ID;不允许请求提供库URL或文件路径。实际任务经原Job/Outbox与Worker执行。",
    responses=_RESPONSES,
)
def run_operator_maintenance(
    command: MaintenanceInput,
    response: Response,
    service: OperationsServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> MaintenanceAcceptedView:
    result = service.enqueue_maintenance(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.post(
    "/selectbench-runs",
    operation_id="runOperatorSelectBench",
    response_model=SelectBenchAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="以生产筛选链路排队黄金集模型评测",
    description="运营写权限;开关默认关闭。固定分组与seed抽样,每case/model原Job,生产预筛及两次独立评分,统一预算与未知响应不重付。",
    responses=_RESPONSES,
)
def run_operator_selectbench(
    command: SelectBenchGoldInput,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> SelectBenchAcceptedView:
    result = service.queue_gold(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.post(
    "/selectbench-relation-runs",
    operation_id="runOperatorRelationBench",
    response_model=SelectBenchAcceptedView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="以生产关系提示词排队固定报道对评测",
    responses=_RESPONSES,
)
def run_operator_relation_bench(
    command: RelationBenchGoldInput,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> SelectBenchAcceptedView:
    response.headers["cache-control"] = "no-store"
    return service.queue_relation_gold(owner_id=scope_id, command=command)


@router.post(
    "/selectbench-relations",
    operation_id="importOperatorRelationBench",
    response_model=SelectBenchRunView,
    status_code=status.HTTP_201_CREATED,
    summary="导入同批报道对与各模型关系预测并复算指标",
    responses=_RESPONSES,
)
def import_operator_relation_bench(
    command: RelationBenchImportInput,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> SelectBenchRunView:
    response.headers["cache-control"] = "no-store"
    return service.import_relation_report(owner_id=scope_id, command=command)


@router.get(
    "/selectbench/{run_id}/relations",
    operation_id="getOperatorRelationBench",
    response_model=RelationBenchCasesView,
    status_code=status.HTTP_200_OK,
    summary="逐条比较关系误判、错误和模型分歧",
    responses=_RESPONSES,
)
def get_operator_relation_bench(
    run_id: UUID,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorScopeDependency,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=400)] = 100,
    disagree: bool = False,
    errors: bool = False,
) -> RelationBenchCasesView:
    response.headers["cache-control"] = "no-store"
    return service.get_relation_cases(
        owner_id=scope_id,
        run_id=run_id,
        cursor=cursor,
        limit=limit,
        disagree=disagree,
        errors=errors,
    )


@router.post(
    "/selectbench",
    operation_id="importOperatorSelectBench",
    response_model=SelectBenchRunView,
    status_code=status.HTTP_201_CREATED,
    summary="导入同批黄金集并复算评测指标",
    responses=_RESPONSES,
)
def import_operator_selectbench(
    command: SelectBenchImportInput,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> SelectBenchRunView:
    result = service.import_report(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/selectbench",
    operation_id="listOperatorSelectBench",
    response_model=list[SelectBenchRunView],
    status_code=status.HTTP_200_OK,
    summary="列出可核对的模型评测运行",
    responses=_RESPONSES,
)
def list_operator_selectbench(
    response: Response, service: SelectBenchServiceDependency, scope_id: OperatorScopeDependency
) -> list[SelectBenchRunView]:
    response.headers["cache-control"] = "no-store"
    return service.list_runs(owner_id=scope_id)


@router.get(
    "/selectbench/{run_id}",
    operation_id="getOperatorSelectBench",
    response_model=SelectBenchCasesView,
    status_code=status.HTTP_200_OK,
    summary="按误判、分层或模型分歧逐条对比",
    responses=_RESPONSES,
)
def get_operator_selectbench(
    run_id: UUID,
    response: Response,
    service: SelectBenchServiceDependency,
    scope_id: OperatorScopeDependency,
    model: Annotated[str | None, Query(max_length=200)] = None,
    outcome: Literal["tp", "fp", "tn", "fn", "either", "error"] | None = None,
    stratum: Annotated[str | None, Query(max_length=128)] = None,
    disagree: bool = False,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=400)] = 100,
) -> SelectBenchCasesView:
    response.headers["cache-control"] = "no-store"
    return service.get_cases(
        owner_id=scope_id,
        run_id=run_id,
        model=model,
        outcome=outcome,
        stratum=stratum,
        disagree=disagree,
        cursor=cursor,
        limit=limit,
    )
