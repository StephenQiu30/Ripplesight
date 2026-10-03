from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Response, status

from api.dependencies import (
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    PublicContactScopeDependency,
    PublicPublicationScopeDependency,
    PublicSiteReadingServiceDependency,
    SiteConfigurationServiceDependency,
    SourceIconReadingServiceDependency,
)
from core.schemas import ErrorView
from operations.site_schemas import (
    PublicContactView,
    PublicSiteMetaView,
    SiteConfigurationInput,
    SiteConfigurationView,
)
from publication.site_schemas import PublicSiteStatisticsView

router = APIRouter(tags=["站点资料"])
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "当前未公开该资料"},
    422: {"model": ErrorView, "description": "输入无效"},
    503: {"model": ErrorView, "description": "读取依赖暂不可用"},
}
_WRITE_ERRORS = {
    **_READ_ERRORS,
    401: {"model": ErrorView, "description": "运营凭据无效"},
    403: {"model": ErrorView, "description": "运营关闭或写入头缺失"},
    409: {"model": ErrorView, "description": "配置版本或操作幂等冲突"},
}


def _headers(response: Response) -> None:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"


@router.get(
    "/site/meta",
    operation_id="getPublicSiteMeta",
    response_model=PublicSiteMetaView,
    status_code=status.HTTP_200_OK,
    summary="站点信息与实际部署开关",
    responses=_READ_ERRORS,
)
def site_meta(
    response: Response, service: SiteConfigurationServiceDependency
) -> PublicSiteMetaView:
    _headers(response)
    return service.meta()


@router.get(
    "/site/stats",
    operation_id="getPublicSiteStatistics",
    response_model=PublicSiteStatisticsView,
    status_code=status.HTTP_200_OK,
    summary="当前许可范围内的公开资料统计",
    responses=_READ_ERRORS,
)
def site_statistics(
    response: Response,
    service: PublicSiteReadingServiceDependency,
    owner_id: PublicPublicationScopeDependency,
) -> PublicSiteStatisticsView:
    _headers(response)
    return service.statistics(owner_id=owner_id)


@router.get(
    "/site/contact",
    operation_id="getPublicContact",
    response_model=PublicContactView,
    status_code=status.HTTP_200_OK,
    summary="已启用的公开联系资料",
    responses=_READ_ERRORS,
)
def site_contact(
    response: Response,
    service: SiteConfigurationServiceDependency,
    owner_id: PublicContactScopeDependency,
) -> PublicContactView:
    _headers(response)
    return service.contact(owner_id=owner_id)


@router.get(
    "/site/contact/qr/{sha256}.png",
    operation_id="getPublicContactImage",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="当前启用且哈希匹配的联系二维码",
    responses={
        **_READ_ERRORS,
        200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
    },
)
def site_contact_image(
    sha256: Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")],
    service: SiteConfigurationServiceDependency,
    owner_id: PublicContactScopeDependency,
) -> Response:
    return Response(
        content=service.image(owner_id=owner_id, sha256=sha256),
        media_type="image/png",
        headers={"cache-control": "no-store", "x-content-type-options": "nosniff"},
    )


@router.get(
    "/site/source-icons/{source_key}.svg",
    operation_id="getPublicSourceIcon",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="当前公开来源的本地回退图标",
    description="本地生成,不代理任意URL或调用外部服务。撤回后拒绝读取。",
    responses={
        **_READ_ERRORS,
        200: {"content": {"image/svg+xml": {"schema": {"type": "string"}}}},
    },
)
def site_source_icon(
    source_key: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")],
    service: PublicSiteReadingServiceDependency,
    owner_id: PublicPublicationScopeDependency,
) -> Response:
    return Response(
        content=service.source_icon(owner_id=owner_id, source_key=source_key),
        media_type="image/svg+xml",
        headers={"cache-control": "no-store"},
    )


@router.get(
    "/site/source-icons/{source_key}/{mode}",
    operation_id="getPublicSourceAvatar",
    response_model=None,
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="当前公开来源的已准入头像缓存",
    description="仅当前公开来源且独立MEDIA授权及Evidence缓存有效时读取,GET不采集。",
    responses={
        **_READ_ERRORS,
        200: {"content": {"image/webp": {"schema": {"type": "string", "format": "binary"}}}},
    },
)
def public_source_avatar(
    source_key: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")],
    mode: Literal["avatar-48", "avatar-96"],
    service: PublicSiteReadingServiceDependency,
    icons: SourceIconReadingServiceDependency,
    owner_id: PublicPublicationScopeDependency,
) -> Response:
    service.source_icon(owner_id=owner_id, source_key=source_key)
    value = icons.read_by_source_key(owner_id=owner_id, source_key=source_key, mode=mode)
    service.source_icon(owner_id=owner_id, source_key=source_key)
    return Response(
        content=value.body,
        media_type=value.mime_type,
        headers={"cache-control": "no-store", "x-content-type-options": "nosniff"},
    )


@router.get(
    "/operations/site",
    operation_id="getOperatorSiteConfiguration",
    response_model=SiteConfigurationView,
    status_code=status.HTTP_200_OK,
    summary="读取独立运营站点设置",
    responses=_WRITE_ERRORS,
)
def get_site_configuration(
    response: Response,
    service: SiteConfigurationServiceDependency,
    owner_id: OperatorScopeDependency,
) -> SiteConfigurationView:
    _headers(response)
    return service.get(owner_id=owner_id)


@router.put(
    "/operations/site",
    operation_id="saveOperatorSiteConfiguration",
    response_model=SiteConfigurationView,
    status_code=status.HTTP_200_OK,
    summary="保存联系资料与二维码",
    description="运营凭据/CSRF、原因、版本CAS与operation_id幂等;图片限2MiB,解码验证后规范PNG。",
    responses=_WRITE_ERRORS,
)
def save_site_configuration(
    command: SiteConfigurationInput,
    response: Response,
    service: SiteConfigurationServiceDependency,
    owner_id: OperatorWriteScopeDependency,
) -> SiteConfigurationView:
    _headers(response)
    return service.save(owner_id=owner_id, command=command)
