from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Response, status

from api.dependencies import (
    CodexResetServiceDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    UserScopeDependency,
)
from core.schemas import ErrorView
from jobs.schemas import JobView
from monitors.codex_schemas import (
    CodexConfigurationInput,
    CodexEventReviewInput,
    CodexGapReviewInput,
    CodexPostRelinkInput,
    CodexPostReviewInput,
    CodexTickInput,
    MonitorView,
    ResetEventView,
    ResetPostView,
    ResetSnapshot,
    ResetVersionView,
    ScanGapView,
)

router = APIRouter(prefix="/codex-resets", tags=["重置公告"])
_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorView, "description": "公告读取参数无效"},
    503: {"model": ErrorView, "description": "数据库不可用或 Demo 分区冲突"},
    500: {"model": ErrorView, "description": "服务内部异常"},
}
_OPERATOR_RESPONSES = {
    **_READ_RESPONSES,
    401: {"model": ErrorView, "description": "运营凭据无效"},
    403: {"model": ErrorView, "description": "运营写入关闭或CSRF不匹配"},
    404: {"model": ErrorView, "description": "公告资源不在当前分区"},
    409: {"model": ErrorView, "description": "公告版本、幂等操作或官方来源准入冲突"},
}


@router.put(
    "/configuration",
    operation_id="configureCodexResetMonitor",
    status_code=status.HTTP_200_OK,
    response_model=MonitorView,
    summary="配置官方重置公告监控",
    description="首次仅创建关闭配置; 修改需理由、操作ID与预期修订。",
    responses=_OPERATOR_RESPONSES,
)
def configure_monitor(
    command: CodexConfigurationInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> MonitorView:
    response.headers["cache-control"] = "no-store"
    return service.save_configuration(owner_id=owner, command=command)


@router.post(
    "/monitors/{monitor_id}/ticks",
    operation_id="pollCodexResetMonitor",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobView,
    summary="人工受理一次官方公告扫描",
    responses=_OPERATOR_RESPONSES,
    description="受理唯一Job/Outbox; 不在HTTP请求中采集, 未知来源请求必须先复核。",
)
def poll_monitor(
    monitor_id: UUID,
    command: CodexTickInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> JobView:
    response.headers["cache-control"] = "no-store"
    return service.enqueue_tick(owner_id=owner, monitor_id=monitor_id, command=command)


@router.get(
    "/monitors/{monitor_id}/gaps",
    operation_id="listCodexResetScanGaps",
    status_code=status.HTTP_200_OK,
    response_model=tuple[ScanGapView, ...],
    summary="读取公告来源分页缺口",
    responses=_OPERATOR_RESPONSES,
)
def list_scan_gaps(
    monitor_id: UUID,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorScopeDependency,
) -> tuple[ScanGapView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list_gaps(owner_id=owner, monitor_id=monitor_id)


@router.post(
    "/monitors/{monitor_id}/posts/{post_id}/review",
    operation_id="reviewCodexResetPost",
    status_code=status.HTTP_200_OK,
    response_model=ResetPostView,
    summary="复核公告帖子或明确允许再次识别",
    description="未知模型请求不得自动重付; retry需理由、操作ID与帖子复核版本。",
    responses=_OPERATOR_RESPONSES,
)
def review_post(
    monitor_id: UUID,
    post_id: UUID,
    command: CodexPostReviewInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> ResetPostView:
    response.headers["cache-control"] = "no-store"
    return service.resolve_post(
        owner_id=owner,
        monitor_id=monitor_id,
        post_id=post_id,
        action=command.action,
        review=command.review,
    )


@router.post(
    "/monitors/{monitor_id}/posts/{post_id}/relink",
    operation_id="relinkCodexResetPost",
    status_code=status.HTTP_200_OK,
    response_model=ResetPostView,
    summary="审计修正公告帖子归属",
    description="来源公告与目标公告分别校验修订; 空目标仅解除现有归属, 保留原帖及审计。",
    responses=_OPERATOR_RESPONSES,
)
def relink_post(
    monitor_id: UUID,
    post_id: UUID,
    command: CodexPostRelinkInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> ResetPostView:
    response.headers["cache-control"] = "no-store"
    return service.relink_post(
        owner_id=owner,
        monitor_id=monitor_id,
        post_id=post_id,
        from_event_id=command.from_event_id,
        to_event_id=command.to_event_id,
        target_expected_revision=command.target_expected_revision,
        review=command.review,
    )


@router.post(
    "/monitors/{monitor_id}/gaps/{gap_id}/review",
    operation_id="reviewCodexResetScanGap",
    status_code=status.HTTP_200_OK,
    response_model=ScanGapView,
    summary="人工核验来源缺口或允许恢复分页",
    description="保留旧查询/token; 已换配置不能重释旧token, 确认缺口不会推进verified。",
    responses=_OPERATOR_RESPONSES,
)
def review_scan_gap(
    monitor_id: UUID,
    gap_id: UUID,
    command: CodexGapReviewInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> ScanGapView:
    response.headers["cache-control"] = "no-store"
    return service.resolve_gap(
        owner_id=owner,
        monitor_id=monitor_id,
        gap_id=gap_id,
        action=command.action,
        review=command.review,
    )


@router.patch(
    "/monitors/{monitor_id}/events/{event_id}",
    operation_id="correctCodexResetEvent",
    status_code=status.HTTP_200_OK,
    response_model=ResetEventView,
    summary="审计修改公告日期、类型、到账与撤回状态",
    description="日期必须显式填写; 预测不能自动确认到账, 人工确认保留receipt_review依据。",
    responses=_OPERATOR_RESPONSES,
)
def correct_event(
    monitor_id: UUID,
    event_id: Annotated[str, Path(min_length=1, max_length=128)],
    command: CodexEventReviewInput,
    response: Response,
    service: CodexResetServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> ResetEventView:
    response.headers["cache-control"] = "no-store"
    return service.update_event(
        owner_id=owner,
        monitor_id=monitor_id,
        event_id=event_id,
        patch=command.patch,
        review=command.review,
    )


@router.get(
    "/configuration",
    operation_id="getCodexResetConfiguration",
    response_model=MonitorView | None,
    status_code=status.HTTP_200_OK,
    summary="读取重置公告监控配置",
    description="尚未配置返回 null; 读取不创建监控, 不请求 X 或模型。",
    responses=_READ_RESPONSES,
)
def get_configuration(
    response: Response,
    service: CodexResetServiceDependency,
    scope_id: UserScopeDependency,
) -> MonitorView | None:
    result = service.get_existing_monitor(owner_id=scope_id)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/snapshot",
    operation_id="getCodexResetSnapshot",
    response_model=ResetSnapshot | None,
    status_code=status.HTTP_200_OK,
    summary="读取公告日历与健康状态",
    description="返回持久源公告与程序状态; 预测不表示确认到账, 未配置返回 null。",
    responses=_READ_RESPONSES,
)
def get_snapshot(
    response: Response,
    service: CodexResetServiceDependency,
    scope_id: UserScopeDependency,
    include_withdrawn: bool = False,
) -> ResetSnapshot | None:
    monitor = service.get_existing_monitor(owner_id=scope_id)
    result = (
        None
        if monitor is None
        else service.snapshot(
            owner_id=scope_id, monitor_id=monitor.id, include_withdrawn=include_withdrawn
        )
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/recent",
    operation_id="getRecentCodexResets",
    response_model=ResetSnapshot | None,
    status_code=status.HTTP_200_OK,
    summary="读取最近公告与确认轮次",
    description="按北京时间保留最近七日公告上下文, 未配置返回 null, 不触发扫描。",
    responses=_READ_RESPONSES,
)
def get_recent(
    response: Response,
    service: CodexResetServiceDependency,
    scope_id: UserScopeDependency,
) -> ResetSnapshot | None:
    monitor = service.get_existing_monitor(owner_id=scope_id)
    result = (
        None
        if monitor is None
        else service.snapshot(owner_id=scope_id, monitor_id=monitor.id, recent=True)
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/version",
    operation_id="getCodexResetVersion",
    response_model=ResetVersionView | None,
    status_code=status.HTTP_200_OK,
    summary="读取公告快照版本",
    description="轻量读取同一快照版本, 便于客户端刷新判断; 未配置返回 null。",
    responses=_READ_RESPONSES,
)
def get_version(
    response: Response,
    service: CodexResetServiceDependency,
    scope_id: UserScopeDependency,
) -> ResetVersionView | None:
    monitor = service.get_existing_monitor(owner_id=scope_id)
    result = (
        None if monitor is None else service.version_probe(owner_id=scope_id, monitor_id=monitor.id)
    )
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/posts",
    operation_id="listCodexResetPosts",
    response_model=list[ResetPostView],
    status_code=status.HTTP_200_OK,
    summary="读取公告源帖子",
    description="分页读取持久帖子及复核状态, 每页至多50条; 未配置为零条且配置查询为 null。",
    responses=_READ_RESPONSES,
)
def list_posts(
    response: Response,
    service: CodexResetServiceDependency,
    scope_id: UserScopeDependency,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    filter_key: Literal["all", "relevant", "pending", "review"] = "all",
) -> list[ResetPostView]:
    monitor = service.get_existing_monitor(owner_id=scope_id)
    result = (
        []
        if monitor is None
        else list(
            service.list_posts(
                owner_id=scope_id, monitor_id=monitor.id, filter_key=filter_key, page=page
            )
        )
    )
    response.headers["cache-control"] = "no-store"
    return result
