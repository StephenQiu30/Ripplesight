from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status

from api.dependencies import (
    DemoScopeDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    PublicationServiceDependency,
)
from core.schemas import ErrorView
from publication.group_schemas import (
    PublicDevelopmentsPage,
    PublicFactReportsPage,
    PublicReadingFilters,
    PublicTimelinePage,
)
from publication.schemas import (
    Category,
    PublicationOverrideInput,
    PublicEditionView,
    PublicItemDetailView,
    PublicItemsPage,
    PublicStoriesPage,
    PublicStoryView,
    PublishResultView,
    RepublishInput,
    RepublishRunView,
    SelectedChangesPage,
    SelectedSnapshotView,
    SourcePolicyInput,
    SourcePolicyView,
)
from publication.topic_schemas import PublicTopicDirectoryView, PublicTopicPageView

router = APIRouter(prefix="/publication", tags=["公开发布"])
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorView, "description": "过滤或分页输入无效"},
    503: {"model": ErrorView, "description": "数据库或检索容量暂不可用"},
    500: {"model": ErrorView, "description": "读取内部异常"},
}
_DETAIL_ERRORS = {
    **_READ_ERRORS,
    404: {"model": ErrorView, "description": "材料已不可公开或不存在"},
}
_SYNC_ERRORS = {
    **_READ_ERRORS,
    409: {"model": ErrorView, "description": "精选同步epoch已更换,需重新获取快照"},
}
_OPERATOR_ERRORS = {
    **_DETAIL_ERRORS,
    401: {"model": ErrorView, "description": "操作员令牌缺失或无效"},
    403: {"model": ErrorView, "description": "缺少写入头或操作员入口停用"},
    409: {"model": ErrorView, "description": "修订或幂等操作冲突"},
}
_GROUP_ERRORS = {
    **_DETAIL_ERRORS,
    409: {"model": ErrorView, "description": "当前报道成员或许可修订已变化,需重新读取分组"},
}


def _reading_headers(response: Response) -> None:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"


def _reading_filters(
    window: Literal["24h", "7d"] = "24h",
    channel: Literal["all", "news", "x", "firstParty"] = "all",
    category: Category | None = None,
    source_key: Annotated[str | None, Query(max_length=64)] = None,
    tag: Annotated[str | None, Query(max_length=128)] = None,
    topic: Annotated[str | None, Query(max_length=64)] = None,
) -> PublicReadingFilters:
    return PublicReadingFilters(
        window=window,
        channel=channel,
        category=category,
        source_key=source_key,
        tag=tag,
        topic=topic,
    )


ReadingFiltersDependency = Annotated[PublicReadingFilters, Depends(_reading_filters)]


@router.get(
    "/timeline",
    operation_id="getPublicReadingTimeline",
    response_model=PublicTimelinePage,
    status_code=200,
    summary="按事件与事实折叠的精选阅读时间线",
    responses=_READ_ERRORS,
)
def reading_timeline(
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    filters: ReadingFiltersDependency,
    limit: Annotated[int, Query(ge=1, le=40)] = 20,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> PublicTimelinePage:
    _reading_headers(response)
    return service.timeline(owner_id=owner_id, filters=filters, limit=limit, cursor=cursor)


@router.get(
    "/facts/{fact_id}/reports",
    operation_id="getPublicFactReports",
    response_model=PublicFactReportsPage,
    status_code=200,
    summary="同事实的当前公开报道及修订分页",
    responses=_GROUP_ERRORS,
)
def fact_reports(
    fact_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    filters: ReadingFiltersDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    revision: Annotated[str | None, Query(max_length=64)] = None,
) -> PublicFactReportsPage:
    _reading_headers(response)
    return service.fact_reports(
        owner_id=owner_id,
        fact_id=fact_id,
        filters=filters,
        limit=limit,
        cursor=cursor,
        revision=revision,
    )


@router.get(
    "/stories/{event_id}/developments",
    operation_id="getPublicStoryDevelopments",
    response_model=PublicDevelopmentsPage,
    status_code=200,
    summary="故事中的独立发生事实和精选进展",
    responses=_GROUP_ERRORS,
)
def developments(
    event_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    filters: ReadingFiltersDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    revision: Annotated[str | None, Query(max_length=64)] = None,
) -> PublicDevelopmentsPage:
    _reading_headers(response)
    return service.developments(
        owner_id=owner_id,
        event_id=event_id,
        filters=filters,
        limit=limit,
        cursor=cursor,
        revision=revision,
    )


@router.get(
    "/topics",
    operation_id="getPublicTopicDirectory",
    response_model=PublicTopicDirectoryView,
    status_code=200,
    summary="公开行业专题目录与当前许可统计",
    responses=_READ_ERRORS,
)
def topic_directory(
    response: Response, service: PublicationServiceDependency, owner_id: DemoScopeDependency
) -> PublicTopicDirectoryView:
    _reading_headers(response)
    return service.topic_directory(owner_id=owner_id)


@router.get(
    "/topics/{slug}",
    operation_id="getPublicTopicPage",
    response_model=PublicTopicPageView,
    status_code=200,
    summary="公开专题固定二十条分页",
    responses=_DETAIL_ERRORS,
)
def topic_page(
    slug: Annotated[str, Path(min_length=1, max_length=64)],
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
) -> PublicTopicPageView:
    _reading_headers(response)
    return service.topic_page(owner_id=owner_id, slug=slug, page=page)


@router.get(
    "/items",
    operation_id="listPublicItems",
    response_model=PublicItemsPage,
    status_code=status.HTTP_200_OK,
    summary="读取公开资讯",
    description="24小时或7天原生窗口;所有出口复验相同固定版本和许可。GET不采集或调用模型。",
    responses=_READ_ERRORS,
)
def list_items(
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    window: Literal["24h", "7d"] = "24h",
    mode: Literal["selected", "all"] = "selected",
    by: Literal["timeline", "published"] = "timeline",
    category: Category | None = None,
    channel: Literal["news", "x", "firstParty"] | None = None,
    source_key: Annotated[str | None, Query(max_length=64)] = None,
    tag: Annotated[str | None, Query(max_length=128)] = None,
    topic: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    search_order: Literal["relevance", "time"] = "relevance",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> PublicItemsPage:
    _reading_headers(response)
    return service.items(
        owner_id=owner_id,
        window=window,
        mode=mode,
        by=by,
        category=category,
        channel=channel,
        source_key=source_key,
        tag=tag,
        topic=topic,
        q=q,
        search_order=search_order,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/editions/{kind}/{key}",
    operation_id="getPublicEdition",
    response_model=PublicEditionView,
    status_code=200,
    summary="读取当前可公开刊期与完整引用",
    description="日周月刊只读出口;当前修订及全部冻结参考逐次复验,不回退旧修订或生成报告。",
    responses=_DETAIL_ERRORS,
)
def public_edition(
    kind: Literal["daily", "weekly", "monthly"],
    key: Annotated[str, Path(min_length=7, max_length=10)],
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
) -> PublicEditionView:
    _reading_headers(response)
    return service.edition(owner_id=owner_id, kind=kind, key=key)


@router.get(
    "/items/{content_id}/site",
    operation_id="getSitePublicationItem",
    response_model=PublicItemDetailView,
    status_code=200,
    summary="读取站内发布正文",
    description="站内全文许可与再分发许可分别判断;摘要模式不含正文、理由和归组信息。",
    responses=_DETAIL_ERRORS,
)
def site_item(
    content_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
) -> PublicItemDetailView:
    _reading_headers(response)
    return service.detail(owner_id=owner_id, content_id=content_id)


@router.get(
    "/items/{content_id}",
    operation_id="getPublicPublicationItem",
    response_model=PublicItemDetailView,
    status_code=200,
    summary="读取可再分发的发布详情",
    description="仅有明确再分发许可时包含正文;其余保留摘要和站内入口。",
    responses=_DETAIL_ERRORS,
)
def public_item(
    content_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
) -> PublicItemDetailView:
    _reading_headers(response)
    return service.detail(owner_id=owner_id, content_id=content_id, redistribute=True)


@router.get(
    "/selected/snapshot",
    operation_id="getSelectedPublicationSnapshot",
    response_model=SelectedSnapshotView,
    status_code=200,
    summary="读取全量精选同步快照",
    description="全量快照不限于7天;水位不能越过仍等待公开的条目。",
    responses=_SYNC_ERRORS,
)
def snapshot(
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> SelectedSnapshotView:
    _reading_headers(response)
    return service.selected_snapshot(owner_id=owner_id, limit=limit, cursor=cursor)


@router.get(
    "/selected/changes",
    operation_id="getSelectedPublicationChanges",
    response_model=SelectedChangesPage,
    status_code=200,
    summary="读取精选增量修订",
    description="保留每个序号;已限制/撤回的历史upsert只输出remove,防离线重放泄漏。",
    responses=_SYNC_ERRORS,
)
def changes(
    epoch: UUID,
    since: Annotated[int, Query(ge=0)],
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> SelectedChangesPage:
    _reading_headers(response)
    return service.selected_changes(owner_id=owner_id, epoch=epoch, since=since, limit=limit)


@router.get(
    "/hot",
    operation_id="getPublicHotStories",
    response_model=PublicStoriesPage,
    status_code=200,
    summary="读取公开事件热榜",
    description="48小时来源热度排序,至少两个参与方且含编辑来源;全部固定材料必须可公开。",
    responses=_READ_ERRORS,
)
def hot(
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PublicStoriesPage:
    _reading_headers(response)
    return service.hot(owner_id=owner_id, limit=limit)


@router.get(
    "/stories/{event_id}",
    operation_id="getPublicStory",
    response_model=PublicStoryView,
    status_code=200,
    summary="读取公开事件故事",
    description="事件摘要与直接进展按全部固定成员许可复验,不从不可公开成员保留派生文本。",
    responses=_DETAIL_ERRORS,
)
def story(
    event_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: DemoScopeDependency,
) -> PublicStoryView:
    _reading_headers(response)
    return service.story(owner_id=owner_id, event_id=event_id)


@router.get(
    "/policies",
    operation_id="listPublicationPolicies",
    response_model=list[SourcePolicyView],
    status_code=200,
    summary="读取公开来源许可策略",
    responses={**_READ_ERRORS, 401: _OPERATOR_ERRORS[401], 403: _OPERATOR_ERRORS[403]},
)
def policies(
    response: Response, service: PublicationServiceDependency, owner_id: OperatorScopeDependency
) -> list[SourcePolicyView]:
    _reading_headers(response)
    return service.policies(owner_id=owner_id)


@router.put(
    "/sources/{source_key}/policy",
    operation_id="savePublicationSourcePolicy",
    response_model=SourcePolicyView,
    status_code=200,
    summary="修订来源公开许可",
    description="操作员令牌及写入头必需;默认关闭全文/再分发/索引许可,留存不可变修订回执。",
    responses=_OPERATOR_ERRORS,
)
def save_policy(
    source_key: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")],
    command: SourcePolicyInput,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> SourcePolicyView:
    _reading_headers(response)
    return service.save_policy(owner_id=owner_id, source_key=source_key, command=command)


@router.put(
    "/items/{content_id}/override",
    operation_id="overridePublication",
    response_model=PublishResultView,
    status_code=200,
    summary="人工调整公开范围与索引",
    description="明确预期修订,支持公开/摘要/撤回及SEO索引/排除;修改留审计回执。",
    responses=_OPERATOR_ERRORS,
)
def override(
    content_id: UUID,
    command: PublicationOverrideInput,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> PublishResultView:
    _reading_headers(response)
    return service.override(owner_id=owner_id, content_id=content_id, command=command)


@router.post(
    "/sources/{source_key}/republish",
    operation_id="republishPublicationSource",
    response_model=RepublishRunView,
    status_code=202,
    summary="受理来源公开投影重建",
    description="既有jobs/Outbox原子受理,分批持久游标且支持取消/恢复,不重新请求来源或模型。",
    responses=_OPERATOR_ERRORS,
)
def republish(
    source_key: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")],
    command: RepublishInput,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> RepublishRunView:
    _reading_headers(response)
    return service.republish(owner_id=owner_id, source_key=source_key, command=command)


@router.get(
    "/republish/{run_id}",
    operation_id="getPublicationRepublishRun",
    response_model=RepublishRunView,
    status_code=200,
    summary="读取公开投影重建进度",
    responses={**_DETAIL_ERRORS, 401: _OPERATOR_ERRORS[401], 403: _OPERATOR_ERRORS[403]},
)
def republish_status(
    run_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: OperatorScopeDependency,
) -> RepublishRunView:
    _reading_headers(response)
    return service.republish_status(owner_id=owner_id, run_id=run_id)
