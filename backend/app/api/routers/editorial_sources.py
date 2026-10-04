"""Typed operator source configuration and dedicated-token external ingestion."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response, status

from api.dependencies import (
    EditorialSourcePreviewServiceDependency,
    EditorialSourceServiceDependency,
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    SourceIconReadingServiceDependency,
    SourceIconServiceDependency,
    UserScopeDependency,
    UserWriteScopeDependency,
)
from connections.editorial_body_schemas import EditorialBodyApprovalInput, EditorialBodyApprovalView
from connections.editorial_schemas import (
    EditorialGroupBacklogReviewInput,
    EditorialGroupBacklogReviewResult,
    EditorialGroupBacklogView,
    EditorialPollInput,
    EditorialProfileInput,
    EditorialRsshubApprovalInput,
    EditorialRsshubApprovalView,
    EditorialRunReviewInput,
    ExternalEditorialInput,
    ExternalIngressReceipt,
)
from core.schemas import ErrorView
from jobs.schemas import JobView
from sources.editorial_preview_schemas import (
    EditorialPreviewJobView,
    EditorialPreviewReviewInput,
    EditorialPreviewReviewView,
    EditorialRemotePreviewInput,
    EditorialSamplePreviewInput,
    EditorialSourcePreviewView,
)
from sources.editorial_schemas import EditorialProfileView, EditorialRunResult
from sources.icons_schemas import SourceIconRefreshInput, SourceIconView

router = APIRouter(prefix="/editorial-sources", tags=["编辑来源"])
_READ: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView, "description": "运营凭据缺失或无效"},
    403: {"model": ErrorView, "description": "运营配置关闭"},
    404: {"model": ErrorView, "description": "来源不在当前分区"},
    422: {"model": ErrorView, "description": "参数无效"},
    503: {"model": ErrorView, "description": "持久库不可用"},
    500: {"model": ErrorView, "description": "内部错误"},
}
_WRITE = {**_READ, 409: {"model": ErrorView, "description": "来源配置版本、操作幂等或准入发生冲突"}}


@router.post(
    "/{profile_id}/body-approval",
    operation_id="approveEditorialBodyExtraction",
    response_model=EditorialBodyApprovalView,
    status_code=status.HTTP_200_OK,
    summary="批准固定来源的本机正文补全声明",
    description="审批绑定配置版本、原帖读取保存用途、零费用和固定出口证据; 不启用来源或发起请求。",
    responses=_WRITE,
)
def approve_body_extraction(
    profile_id: UUID,
    command: EditorialBodyApprovalInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialBodyApprovalView:
    response.headers["cache-control"] = "no-store"
    return service.approve_body(owner_id=owner, profile_id=profile_id, command=command)


@router.post(
    "/preview/sample",
    operation_id="previewEditorialSourceSample",
    status_code=status.HTTP_200_OK,
    response_model=EditorialSourcePreviewView,
    summary="本地解析给定来源样本",
    description=(
        "按严格RSS、网页或JSON配置解析最多1MB给定样本; 最多返回20条元数据摘要, 不外采、不正式入库。"
    ),
    responses=_WRITE,
)
def preview_sample(
    command: EditorialSamplePreviewInput,
    response: Response,
    service: EditorialSourcePreviewServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialSourcePreviewView:
    response.headers["cache-control"] = "no-store"
    return service.preview_sample(owner_id=owner, command=command)


@router.post(
    "/{profile_id}/previews",
    operation_id="previewStoredEditorialSource",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobView,
    summary="按当前来源修订受理一次远端试抓",
    description=(
        "原Job与预算冻结当前修订、连接和许可; "
        "仅试抓RSS、网页、JSON或官方X首批, 不写内容或来源水位。未知请求阻断再次受理。"
    ),
    responses=_WRITE,
)
def preview_stored_source(
    profile_id: UUID,
    command: EditorialRemotePreviewInput,
    response: Response,
    service: EditorialSourcePreviewServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> JobView:
    response.headers["cache-control"] = "no-store"
    return service.enqueue(owner_id=owner, profile_id=profile_id, command=command)


@router.get(
    "/previews/{job_id}",
    operation_id="getEditorialSourcePreview",
    status_code=status.HTTP_200_OK,
    response_model=EditorialPreviewJobView,
    summary="读取原试抓任务及有界结果",
    description=(
        "纯读取原Job和审计冻结结果; 返回条数、耗时、请求数及最多20条标题URL时间摘要, 无GET外采。"
    ),
    responses={**_READ, 409: _WRITE[409]},
)
def get_preview(
    job_id: UUID,
    response: Response,
    service: EditorialSourcePreviewServiceDependency,
    owner: OperatorScopeDependency,
) -> EditorialPreviewJobView:
    response.headers["cache-control"] = "no-store"
    return service.read(owner_id=owner, job_id=job_id)


@router.post(
    "/previews/{job_id}/review",
    operation_id="reviewEditorialSourcePreview",
    status_code=status.HTTP_200_OK,
    response_model=EditorialPreviewReviewView,
    summary="人工核对原未知试抓并允许新的显式受理",
    description=(
        "要求原试抓操作ID、当前来源修订、复核操作ID与理由。"
        "保留原unknown结果和保守预算回执, 不发HTTP、不重发原Job。"
    ),
    responses=_WRITE,
)
def review_preview(
    job_id: UUID,
    command: EditorialPreviewReviewInput,
    response: Response,
    service: EditorialSourcePreviewServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialPreviewReviewView:
    response.headers["cache-control"] = "no-store"
    return service.review(owner_id=owner, job_id=job_id, command=command)


@router.get(
    "/groups/backlogs",
    operation_id="listEditorialSourceGroupBacklogs",
    status_code=status.HTTP_200_OK,
    response_model=tuple[EditorialGroupBacklogView, ...],
    summary="读取原成员固定的官方 X 分组积压",
    description="仅运营读取; 不请求外部、不推进水位。返回全部原成员当前版本以供人工CAS复核。",
    responses=_READ,
)
def list_group_backlogs(
    response: Response, service: EditorialSourceServiceDependency, owner: OperatorScopeDependency
) -> tuple[EditorialGroupBacklogView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list_group_backlogs(owner_id=owner)


@router.post(
    "/groups/backlogs/review",
    operation_id="reviewEditorialSourceGroupBacklog",
    status_code=status.HTTP_200_OK,
    response_model=EditorialGroupBacklogReviewResult,
    summary="人工按全部原成员版本重建官方 X 分组积压",
    description=(
        "必须显式操作ID、理由、操作者和全部原成员CAS。清旧分页令牌并退回原水位, "
        "保留旧成功时钟、同事务审计; 仅重新受理到期采集, 不在HTTP请求中调用外部。"
    ),
    responses=_WRITE,
)
def review_group_backlog(
    command: EditorialGroupBacklogReviewInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialGroupBacklogReviewResult:
    response.headers["cache-control"] = "no-store"
    return service.review_group_backlog(owner_id=owner, command=command)


@router.get(
    "",
    operation_id="listEditorialSourceProfiles",
    status_code=status.HTTP_200_OK,
    response_model=tuple[EditorialProfileView, ...],
    summary="读取六类型编辑来源配置与健康",
    description="仅运营读取。无配置返回空列表, 不创建来源、不请求外部。",
    responses=_READ,
)
def list_profiles(
    response: Response, service: EditorialSourceServiceDependency, owner: OperatorScopeDependency
) -> tuple[EditorialProfileView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list_profiles(owner_id=owner)


@router.get(
    "/{profile_id}",
    operation_id="getEditorialSourceProfile",
    status_code=status.HTTP_200_OK,
    response_model=EditorialProfileView,
    summary="读取一个来源的固定配置版本",
    responses=_READ,
)
def get_profile(
    profile_id: UUID,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorScopeDependency,
) -> EditorialProfileView:
    response.headers["cache-control"] = "no-store"
    return service.get_profile(owner_id=owner, profile_id=profile_id)


@router.post(
    "",
    operation_id="createEditorialSourceProfile",
    response_model=EditorialProfileView,
    status_code=status.HTTP_201_CREATED,
    summary="创建关闭状态的编辑来源",
    description=(
        "必须先创建关闭配置, 再通过原Evidence批准来源及保留策略后启用。密钥只由服务端引用。"
    ),
    responses=_WRITE,
)
def create_profile(
    command: EditorialProfileInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialProfileView:
    response.headers["cache-control"] = "no-store"
    return service.save_profile(owner_id=owner, command=command)


@router.put(
    "/{profile_id}",
    operation_id="updateEditorialSourceProfile",
    status_code=status.HTTP_200_OK,
    response_model=EditorialProfileView,
    summary="按预期版本修改来源配置与启用状态",
    description="配置版本不可变; 未知外部请求须复核后才能更换配置。",
    responses=_WRITE,
)
def update_profile(
    profile_id: UUID,
    command: EditorialProfileInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialProfileView:
    response.headers["cache-control"] = "no-store"
    return service.save_profile(owner_id=owner, profile_id=profile_id, command=command)


@router.post(
    "/{profile_id}/rsshub-approval",
    operation_id="approveEditorialRsshubSource",
    status_code=status.HTTP_200_OK,
    response_model=EditorialRsshubApprovalView,
    summary="按固定配置和证据审批本机RSSHub入口",
    description=(
        "运营CSRF写权限、独立操作ID和当前修订/配置SHA核验。"
        "将用途、下游出口、缓存、费用和风控停止证据绑定原组件政策; "
        "不启用来源、不批准数据许可、不发HTTP。"
    ),
    responses=_WRITE,
)
def approve_rsshub_source(
    profile_id: UUID,
    command: EditorialRsshubApprovalInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialRsshubApprovalView:
    response.headers["cache-control"] = "no-store"
    return service.approve_rsshub(owner_id=owner, profile_id=profile_id, command=command)


@router.get(
    "/{profile_id}/runs",
    operation_id="listEditorialSourceRuns",
    status_code=status.HTTP_200_OK,
    response_model=tuple[EditorialRunResult, ...],
    summary="读取来源摄入与恢复状态",
    responses=_READ,
)
def list_runs(
    profile_id: UUID,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorScopeDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> tuple[EditorialRunResult, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list_runs(owner_id=owner, profile_id=profile_id, limit=limit)


@router.post(
    "/{profile_id}/runs",
    operation_id="pollEditorialSource",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobView,
    summary="人工受理一次来源采集",
    description="受理原Job与Outbox; 不在HTTP请求采集。未知请求需先人工复核。",
    responses=_WRITE,
)
def poll_source(
    profile_id: UUID,
    command: EditorialPollInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> JobView:
    response.headers["cache-control"] = "no-store"
    return service.enqueue_poll(owner_id=owner, profile_id=profile_id, command=command)


@router.post(
    "/{profile_id}/runs/{run_id}/review",
    operation_id="reviewEditorialSourceRun",
    status_code=status.HTTP_200_OK,
    response_model=EditorialRunResult,
    summary="人工核验未知请求或解除已知失败",
    description="需要理由、操作ID、操作者和预期来源修订; 保留旧未知结果审计, 不自动重投。",
    responses=_WRITE,
)
def review_run(
    profile_id: UUID,
    run_id: UUID,
    command: EditorialRunReviewInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> EditorialRunResult:
    response.headers["cache-control"] = "no-store"
    return service.review_run(owner_id=owner, profile_id=profile_id, run_id=run_id, command=command)


@router.post(
    "/{profile_id}/ingest",
    operation_id="ingestExternalEditorialSource",
    response_model=ExternalIngressReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    summary="接收专属令牌外部来源材料",
    description=(
        "令牌与来源绑定, 默认关闭。最多50项/4MiB, 同分区实际peer跨来源10次/滚动60秒; "
        "许可只从当前分区Evidence批准版本读取, "
        "材料经原Job+Outbox接收, 返回逐项回执且可GET进度。非法raw不持久, 部分拒绝不推进成功时钟。"
    ),
    responses={
        **_WRITE,
        401: {"model": ErrorView, "description": "外部来源令牌缺失或无效"},
        403: {"model": ErrorView, "description": "外部来源令牌未配置或CSRF无效"},
        429: {"model": ErrorView, "description": "实际peer滚动准入超限, Retry-After后再试"},
    },
)
def external_ingest(
    profile_id: UUID,
    command: ExternalEditorialInput,
    response: Response,
    request: Request,
    service: EditorialSourceServiceDependency,
    owner: UserWriteScopeDependency,
    token: Annotated[str | None, Header(alias="X-HotKey-Source-Token", max_length=4096)] = None,
) -> ExternalIngressReceipt:
    service.verify_external_token(owner_id=owner, profile_id=profile_id, token=token)
    response.headers["cache-control"] = "no-store"
    return service.accept_ingress(
        owner_id=owner,
        profile_id=profile_id,
        command=command,
        peer_ip=request.client.host if request.client else None,
    )


@router.get(
    "/{profile_id}/ingest/{run_id}",
    operation_id="getExternalEditorialIngressReceipt",
    response_model=ExternalIngressReceipt,
    status_code=status.HTTP_200_OK,
    summary="读取专属令牌外部摄入的固定逐项回执",
    description="同来源令牌与owner校验,只读原Job/SourceRun,不返回材料正文、IP或密钥,不触发重试。",
    responses={
        **_READ,
        401: {"model": ErrorView, "description": "外部来源令牌缺失或无效"},
        403: {"model": ErrorView, "description": "外部来源令牌未配置"},
    },
)
def external_receipt(
    profile_id: UUID,
    run_id: UUID,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: UserScopeDependency,
    token: Annotated[str | None, Header(alias="X-HotKey-Source-Token", max_length=4096)] = None,
) -> ExternalIngressReceipt:
    service.verify_external_token(owner_id=owner, profile_id=profile_id, token=token)
    response.headers["cache-control"] = "no-store"
    return service.get_ingress_receipt(owner_id=owner, profile_id=profile_id, run_id=run_id)


@router.get(
    "/{profile_id}/icon",
    operation_id="getEditorialSourceIcon",
    status_code=status.HTTP_200_OK,
    response_model=SourceIconView,
    summary="读取独立MEDIA许可的来源图标缓存状态",
    description="仅读取当前来源版本和Evidence,不采外源。撤权、保留许可失效与旧版本不返回图像。",
    responses=_READ,
)
def get_icon(
    profile_id: UUID,
    response: Response,
    service: SourceIconServiceDependency,
    owner: OperatorScopeDependency,
) -> SourceIconView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner, profile_id=profile_id)


@router.post(
    "/{profile_id}/icon/refresh",
    operation_id="refreshEditorialSourceIcon",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobView,
    summary="按来源版本和理由受理图标采集",
    description="原Job/Outbox和同事务运营审计,真实外采默认关闭;unknown必须显式人工retry_unknown。",
    responses=_WRITE,
)
def refresh_icon(
    profile_id: UUID,
    command: SourceIconRefreshInput,
    response: Response,
    service: SourceIconServiceDependency,
    owner: OperatorWriteScopeDependency,
) -> JobView:
    response.headers["cache-control"] = "no-store"
    return service.refresh(owner_id=owner, profile_id=profile_id, command=command)


@router.get(
    "/{profile_id}/icon/{mode}",
    operation_id="readEditorialSourceIcon",
    status_code=status.HTTP_200_OK,
    response_model=None,
    response_class=Response,
    summary="读取当前许可的48或96尺寸来源图标",
    description="仅读既有MinIO对象,哈希验证且读前后重新核许可,从不在GET采集。",
    responses=_READ,
)
def read_icon(
    profile_id: UUID,
    mode: Literal["avatar-48", "avatar-96"],
    service: SourceIconReadingServiceDependency,
    owner: OperatorScopeDependency,
) -> Response:
    found = service.read(owner_id=owner, profile_id=profile_id, mode=mode)
    return Response(
        found.body,
        media_type=found.mime_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "ETag": f'"{found.sha256}"',
        },
    )
