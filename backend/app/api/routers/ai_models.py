"""Operator-only capability model choices and original call usage, with no read side effects."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from ai.capability_schemas import (
    AiCostCircuitAckInput,
    AiModelConfigurationView,
    AiModelOverview,
    AiModelSwitchInput,
)
from api.dependencies import (
    AiCapabilityServiceDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
)
from core.schemas import ErrorView

router = APIRouter(prefix="/ai/models", tags=["模型配置"])
_READ: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView, "description": "运营令牌缺失或无效"},
    403: {"model": ErrorView, "description": "运营读取关闭"},
    422: {"model": ErrorView, "description": "模型配置或有界参数无效"},
    503: {"model": ErrorView, "description": "持久库或保护模型catalog不可用"},
    500: {"model": ErrorView, "description": "模型配置读取内部错误"},
}


@router.get(
    "/configuration",
    operation_id="getAiModelConfiguration",
    response_model=AiModelConfigurationView,
    status_code=200,
    summary="读取11能力当前模型与保护catalog选择",
    responses=_READ,
    description="admin→环境→默认,仅展示配置来源与server声明能力;不返回凭据、不调用模型。",
)
def get_configuration(
    response: Response,
    service: AiCapabilityServiceDependency,
    owner_id: OperatorScopeDependency,
) -> AiModelConfigurationView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner_id)


@router.get(
    "/overview",
    operation_id="getAiModelOverview",
    response_model=AiModelOverview,
    status_code=200,
    summary="读取原AiCall用途费用统计与模型切换审计",
    responses=_READ,
    description="仅原模型账本,独立币种不换算;估计与供应商actual/cap分列,未知原调用不重复请求。",
)
def get_overview(
    response: Response,
    service: AiCapabilityServiceDependency,
    owner_id: OperatorScopeDependency,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> AiModelOverview:
    response.headers["cache-control"] = "no-store"
    return service.overview(owner_id=owner_id, days=days)


@router.put(
    "/configuration",
    operation_id="switchAiCapabilityModel",
    response_model=AiModelConfigurationView,
    status_code=200,
    summary="按版本和原因切换单个能力模型",
    responses={
        **_READ,
        409: {"model": ErrorView, "description": "模型配置版本或操作幂等发生冲突"},
    },
    description="原运营审计与append-only模型配置版本同事务;null清admin覆盖,仅影响之后受理的任务。",
)
def switch_configuration(
    command: AiModelSwitchInput,
    response: Response,
    service: AiCapabilityServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> AiModelConfigurationView:
    response.headers["cache-control"] = "no-store"
    return service.switch(owner_id=owner_id, command=command)


@router.post(
    "/cost-circuits/acknowledgments",
    operation_id="acknowledgeAiCostCircuit",
    response_model=AiModelConfigurationView,
    status_code=200,
    summary="人工复核一条模型超额收费并按版本恢复",
    responses={**_READ, 409: {"model": ErrorView, "description": "模型配置版本或操作幂等冲突"}},
)
def acknowledge_cost_circuit(
    command: AiCostCircuitAckInput,
    response: Response,
    service: AiCapabilityServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> AiModelConfigurationView:
    response.headers["cache-control"] = "no-store"
    return service.acknowledge_cost_circuit(owner_id=owner_id, command=command)
