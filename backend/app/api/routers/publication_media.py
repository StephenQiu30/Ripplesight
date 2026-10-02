from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Response

from api.dependencies import (
    OperatorScopeDependency,
    OperatorWriteScopeDependency,
    PublicationMediaReadingServiceDependency,
    PublicationMediaServiceDependency,
    UserScopeDependency,
)
from core.errors import ApplicationError
from core.schemas import ErrorView
from publication.media_mirror_schemas import MediaMirrorInput, MediaMirrorRunView

router = APIRouter(prefix="/publication", tags=["发布媒体"])
Mode = Literal[
    "original",
    "avatar",
    "card",
    "thumb",
    "full",
    "og",
    "avatar-48",
    "avatar-96",
    "image-336",
    "image-720",
    "image-1200",
    "image-1600",
]
_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "固定媒体或许可已不可读取"},
    422: {"model": ErrorView, "description": "媒体标识或尺寸输入无效"},
    503: {"model": ErrorView, "description": "媒体对象存储不可用"},
    500: {"model": ErrorView, "description": "媒体读取内部异常"},
}


def _media_response(body: bytes, mime: str, digest: str) -> Response:
    return Response(
        body,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "ETag": f'"{digest}"',
        },
    )


@router.post(
    "/items/{content_id}/media",
    operation_id="requestPublicationMediaMirror",
    response_model=MediaMirrorRunView,
    status_code=202,
    summary="显式受理固定正文媒体镜像",
    description="只接受当前已获准精选全文的固定候选;不允许任意URL,同版本/许可修订复用已有Job。",
    responses={
        400: {"model": ErrorView, "description": "媒体功能关闭或候选超限"},
        401: {"model": ErrorView, "description": "运营令牌无效"},
        403: {"model": ErrorView, "description": "运营写入未授权"},
        409: {"model": ErrorView, "description": "固定正文或许可已经变化"},
        422: {"model": ErrorView, "description": "镜像输入无效"},
        503: {"model": ErrorView, "description": "数据库不可用"},
        500: {"model": ErrorView, "description": "镜像受理内部异常"},
    },
)
def request_mirror(
    content_id: Annotated[UUID, Path()],
    command: MediaMirrorInput,
    owner_id: UserScopeDependency,
    service: PublicationMediaServiceDependency,
    _: OperatorWriteScopeDependency,
) -> MediaMirrorRunView:
    return service.request(owner_id=owner_id, content_id=content_id, command=command)


@router.get(
    "/media/runs/{run_id}",
    operation_id="getPublicationMediaMirrorRun",
    response_model=MediaMirrorRunView,
    status_code=200,
    summary="读取媒体镜像任务状态",
    responses={
        **_READ_ERRORS,
        401: {"model": ErrorView, "description": "运营令牌无效"},
        403: {"model": ErrorView, "description": "运营访问未授权"},
        409: {"model": ErrorView, "description": "正文许可已变化"},
    },
)
def read_run(
    run_id: Annotated[UUID, Path()],
    owner_id: UserScopeDependency,
    service: PublicationMediaServiceDependency,
    _: OperatorScopeDependency,
    response: Response,
) -> MediaMirrorRunView:
    response.headers["Cache-Control"] = "no-store"
    value = service.get(owner_id=owner_id, run_id=run_id)
    if value is None:
        raise ApplicationError("resource_not_found")
    return value


@router.get(
    "/media/{file_id}/{mode}/site",
    operation_id="getSitePublicationMedia",
    response_model=None,
    status_code=200,
    summary="读取站内许可的固定媒体字节",
    responses={
        **_READ_ERRORS,
        200: {
            "content": {
                "image/webp": {},
                "image/jpeg": {},
                "image/png": {},
                "image/gif": {},
                "image/svg+xml": {},
                "video/mp4": {},
                "video/webm": {},
                "video/ogg": {},
            }
        },
    },
)
def site_media(
    file_id: Annotated[UUID, Path()],
    mode: Mode,
    owner_id: UserScopeDependency,
    service: PublicationMediaReadingServiceDependency,
) -> Response:
    value = service.read(owner_id=owner_id, file_id=file_id, mode=mode, redistribute=False)
    return _media_response(value.body, value.mime_type, value.sha256)


@router.get(
    "/media/{file_id}/{mode}",
    operation_id="getPublicationMedia",
    response_model=None,
    status_code=200,
    summary="读取明确获准再分发的固定媒体字节",
    responses={
        **_READ_ERRORS,
        200: {
            "content": {
                "image/webp": {},
                "image/jpeg": {},
                "image/png": {},
                "image/gif": {},
                "image/svg+xml": {},
                "video/mp4": {},
                "video/webm": {},
                "video/ogg": {},
            }
        },
    },
)
def public_media(
    file_id: Annotated[UUID, Path()],
    mode: Mode,
    owner_id: UserScopeDependency,
    service: PublicationMediaReadingServiceDependency,
) -> Response:
    value = service.read(owner_id=owner_id, file_id=file_id, mode=mode, redistribute=True)
    return _media_response(value.body, value.mime_type, value.sha256)
