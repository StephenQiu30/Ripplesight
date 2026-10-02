from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from api.dependencies import (
    EventCorrectionServiceDependency,
    EventFactReadServiceDependency,
    EventHeatServiceDependency,
    EventReadServiceDependency,
    OperatorWriteScopeDependency,
    UserScopeDependency,
    UserWriteScopeDependency,
)
from core.schemas import ErrorView, PageView
from events.fact_schemas import EventCorrectionInput, EventCorrectionView, EventFactPageView
from events.heat_schemas import (
    AttentionSourceInput,
    AttentionSourceView,
    EventAttentionHistoryView,
    EventAttentionView,
    EventHotPageView,
)
from events.schemas import EventMemberPageView, EventReadView, EventRelatedPageView

router = APIRouter(prefix="/events", tags=["事件"])

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 数据分区冲突"},
    422: {"model": ErrorView, "description": "查询条件或分页游标无效"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}


@router.get(
    "/{event_id}/related",
    operation_id="listRelatedEvents",
    response_model=EventRelatedPageView,
    status_code=status.HTTP_200_OK,
    summary="读取有两篇独立联系证据的相关事件",
    description="固定联系报道、来源独立性及两端根事实逐项复验; 不触发关系判断或赋予正文许可。",
    responses={404: {"model": ErrorView, "description": "事件不存在"}, **_READ_RESPONSES},
)
def list_related_events(
    event_id: UUID,
    response: Response,
    service: EventReadServiceDependency,
    scope_id: UserScopeDependency,
) -> EventRelatedPageView:
    result = service.list_related(owner_id=scope_id, event_id=event_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.post(
    "/corrections",
    operation_id="correctEvent",
    response_model=EventCorrectionView,
    status_code=status.HTTP_200_OK,
    summary="人工修订事件与事实归属",
    description=(
        "按operation_id幂等和所有影响事件的expected_revisions执行合并、拆分、"
        "移动、排除、事实合并或显式重新归组; 原修订的固定正文保留。"
    ),
    responses={
        403: {"model": ErrorView, "description": "缺少Demo写入CSRF头"},
        404: {"model": ErrorView, "description": "事件不属于当前分区或成员证据不可读"},
        409: {"model": ErrorView, "description": "事件修订或幂等请求冲突"},
        **_READ_RESPONSES,
    },
)
def correct_event(
    command: EventCorrectionInput,
    response: Response,
    service: EventCorrectionServiceDependency,
    scope_id: UserWriteScopeDependency,
) -> EventCorrectionView:
    result = service.correct(owner_id=scope_id, actor_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "",
    operation_id="listEvents",
    response_model=PageView[EventReadView],
    status_code=status.HTTP_200_OK,
    summary="列出已确认事件",
    description="分页读取本地已确认且有可读固定成员版本的当前事件; 不触发采集或模型请求。",
    responses=_READ_RESPONSES,
)
def list_events(
    response: Response,
    service: EventReadServiceDependency,
    scope_id: UserScopeDependency,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    topic_id: UUID | None = None,
    source_key: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    query: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> PageView[EventReadView]:
    items, next_cursor = service.list_events(
        owner_id=scope_id,
        cursor=cursor,
        limit=limit,
        topic_id=topic_id,
        source_key=source_key,
        starts_at=starts_at,
        ends_at=ends_at,
        query=query,
    )
    response.headers["cache-control"] = "no-store"
    return PageView(items=items, next_cursor=next_cursor)


@router.get(
    "/attention-sources",
    operation_id="listEventAttentionSources",
    response_model=list[AttentionSourceView],
    status_code=status.HTTP_200_OK,
    summary="读取独立来源身份与采集时钟",
    responses=_READ_RESPONSES,
)
def list_attention_sources(
    response: Response, service: EventHeatServiceDependency, scope_id: UserScopeDependency
) -> list[AttentionSourceView]:
    result = service.list_sources(owner_id=scope_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.put(
    "/attention-sources",
    operation_id="upsertEventAttentionSource",
    response_model=AttentionSourceView,
    status_code=status.HTTP_200_OK,
    summary="配置来源角色与独立参与者身份",
    description="按来源和精确selector创建或修改身份,已有配置要求expected_revision;不触发来源采集。",
    responses={
        403: {"model": ErrorView, "description": "缺少Demo写入CSRF头"},
        409: {"model": ErrorView, "description": "来源配置修订冲突"},
        **_READ_RESPONSES,
    },
)
def upsert_attention_source(
    command: AttentionSourceInput,
    response: Response,
    service: EventHeatServiceDependency,
    scope_id: OperatorWriteScopeDependency,
) -> AttentionSourceView:
    result = service.upsert_source(owner_id=scope_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/hot",
    operation_id="listHotEvents",
    response_model=EventHotPageView,
    status_code=status.HTTP_200_OK,
    summary="读取48小时独立来源热榜",
    description="重查固定版本可读性与来源角色,至少两个独立参与者且含编辑源,返回前10;趋势缺可信基线为unknown。",
    responses=_READ_RESPONSES,
)
def list_hot_events(
    response: Response,
    service: EventHeatServiceDependency,
    scope_id: UserScopeDependency,
    topic_id: UUID | None = None,
) -> EventHotPageView:
    result = service.list_hot(owner_id=scope_id, topic_id=topic_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{event_id}",
    operation_id="getEvent",
    response_model=EventReadView,
    status_code=status.HTTP_200_OK,
    summary="读取已确认事件",
    description="读取事件当前修订; 固定成员证据部分不可读时隐藏派生标题和摘要。",
    responses={
        404: {"model": ErrorView, "description": "事件不存在或无可读成员"},
        **_READ_RESPONSES,
    },
)
def get_event(
    event_id: UUID,
    response: Response,
    service: EventReadServiceDependency,
    scope_id: UserScopeDependency,
) -> EventReadView:
    result = service.get_event(owner_id=scope_id, event_id=event_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{event_id}/members",
    operation_id="listEventMembers",
    response_model=EventMemberPageView,
    status_code=status.HTTP_200_OK,
    summary="读取事件固定版本成员",
    description=(
        "按指定事件修订读取成员固定内容版本和最后一个可读观察; "
        "代表评论单独返回最新可读评论观察, 不宣称是固定评论版本。"
    ),
    responses={
        404: {"model": ErrorView, "description": "事件不存在或所选修订无可读成员"},
        **_READ_RESPONSES,
    },
)
def list_event_members(
    event_id: UUID,
    response: Response,
    service: EventReadServiceDependency,
    scope_id: UserScopeDependency,
    revision: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EventMemberPageView:
    result = service.list_members(
        owner_id=scope_id,
        event_id=event_id,
        revision=revision,
        cursor=cursor,
        limit=limit,
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{event_id}/facts",
    operation_id="listEventFacts",
    response_model=EventFactPageView,
    status_code=status.HTTP_200_OK,
    summary="读取事件事实与直接进展",
    description="按事件修订返回事实身份、根与进展关系及固定成员版本; 不可读派生事实文本隐藏。",
    responses={
        404: {"model": ErrorView, "description": "事件或可读事实成员不存在"},
        **_READ_RESPONSES,
    },
)
def list_event_facts(
    event_id: UUID,
    response: Response,
    service: EventFactReadServiceDependency,
    scope_id: UserScopeDependency,
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> EventFactPageView:
    result = service.list_facts(owner_id=scope_id, event_id=event_id, revision=revision)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{event_id}/heat",
    operation_id="getEventHeat",
    response_model=EventAttentionView,
    status_code=status.HTTP_200_OK,
    summary="读取事件独立来源热度",
    responses={404: {"model": ErrorView, "description": "事件或可读证据不存在"}, **_READ_RESPONSES},
)
def get_event_heat(
    event_id: UUID,
    response: Response,
    service: EventHeatServiceDependency,
    scope_id: UserScopeDependency,
) -> EventAttentionView:
    result = service.get_attention(owner_id=scope_id, event_id=event_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/{event_id}/heat-history",
    operation_id="listEventHeatHistory",
    response_model=EventAttentionHistoryView,
    status_code=status.HTTP_200_OK,
    summary="读取当前事件修订的小时热度历史",
    description="读取最多7天内已有真实小时快照;每次重查固定证据与来源身份,其他修订不混入趋势。",
    responses={404: {"model": ErrorView, "description": "事件不存在"}, **_READ_RESPONSES},
)
def list_event_heat_history(
    event_id: UUID,
    response: Response,
    service: EventHeatServiceDependency,
    scope_id: UserScopeDependency,
    limit: Annotated[int, Query(ge=1, le=168)] = 48,
) -> EventAttentionHistoryView:
    result = service.list_history(owner_id=scope_id, event_id=event_id, limit=limit)
    response.headers["cache-control"] = "no-store"
    return result
