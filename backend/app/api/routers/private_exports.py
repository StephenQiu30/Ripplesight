"""Authenticated private export commands, receipts and bounded attachment bytes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from api.dependencies import (
    PrivateExportServiceDependency,
    UserScopeDependency,
    UserWriteScopeDependency,
)
from core.schemas import ErrorView
from reports.export_schemas import ContentExportInput, ExportView, ReportExportInput

router = APIRouter(tags=["私有导出"])

_READ: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorView, "description": "导出资源不存在或不属于当前账户"},
    422: {"model": ErrorView, "description": "输入校验失败"},
    503: {"model": ErrorView, "description": "数据库或私有对象存储不可用"},
    500: {"model": ErrorView, "description": "内部异常"},
}
_WRITE = {
    **_READ,
    403: {"model": ErrorView, "description": "CSRF或材料导出用途未获准"},
    409: {"model": ErrorView, "description": "固定输入版本或幂等操作冲突"},
}


@router.post(
    "/reports/{report_id}/exports",
    operation_id="createReportExport",
    response_model=ExportView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="受理固定报告版本的私有导出",
    responses=_WRITE,
)
def create_report_export(
    report_id: UUID,
    command: ReportExportInput,
    response: Response,
    service: PrivateExportServiceDependency,
    owner_id: UserWriteScopeDependency,
) -> ExportView:
    result = service.accept_report(owner_id=owner_id, report_id=report_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.post(
    "/content-exports",
    operation_id="createContentExport",
    response_model=ExportView,
    status_code=status.HTTP_202_ACCEPTED,
    summary="受理固定原始内容版本的私有导出",
    responses=_WRITE,
)
def create_content_export(
    command: ContentExportInput,
    response: Response,
    service: PrivateExportServiceDependency,
    owner_id: UserWriteScopeDependency,
) -> ExportView:
    result = service.accept_content(owner_id=owner_id, command=command)
    response.headers["cache-control"] = "no-store"
    return result


@router.get(
    "/report-exports/{export_id}",
    operation_id="getReportExport",
    response_model=ExportView,
    status_code=status.HTTP_200_OK,
    summary="读取本人报告导出任务状态",
    responses=_READ,
)
def get_report_export(
    export_id: UUID,
    response: Response,
    service: PrivateExportServiceDependency,
    owner_id: UserScopeDependency,
) -> ExportView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner_id, export_id=export_id, kind="report")


@router.get(
    "/content-exports/{export_id}",
    operation_id="getContentExport",
    response_model=ExportView,
    status_code=status.HTTP_200_OK,
    summary="读取本人内容导出任务状态",
    responses=_READ,
)
def get_content_export(
    export_id: UUID,
    response: Response,
    service: PrivateExportServiceDependency,
    owner_id: UserScopeDependency,
) -> ExportView:
    response.headers["cache-control"] = "no-store"
    return service.get(owner_id=owner_id, export_id=export_id, kind="content")


_DOWNLOAD = {
    **_READ,
    403: {"model": ErrorView, "description": "当前导出用途不允许下载"},
    409: {"model": ErrorView, "description": "文件尚未成功或固定版本已变化"},
    200: {
        "content": {
            mime: {"schema": {"type": "string", "format": "binary"}}
            for mime in ("text/markdown", "application/pdf", "text/csv", "application/json")
        },
        "headers": {
            "Content-Disposition": {
                "schema": {"type": "string"},
                "description": "本人私有附件名称",
            },
            "Cache-Control": {"schema": {"type": "string"}, "description": "private, no-store"},
            "X-Content-SHA256": {"schema": {"type": "string"}, "description": "实际文件SHA256"},
        },
    },
}


def _download_response(body: bytes, mime_type: str, filename: str, sha256: str) -> Response:
    return Response(
        content=body,
        media_type=mime_type,
        headers={
            "cache-control": "private, no-store",
            "content-disposition": f'attachment; filename="{filename}"',
            "x-content-sha256": sha256,
            "x-content-type-options": "nosniff",
        },
    )


@router.get(
    "/report-exports/{export_id}/download",
    operation_id="downloadReportExport",
    response_class=Response,
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="复验全部当前权限后下载本人报告文件",
    responses=_DOWNLOAD,
)
def download_report_export(
    export_id: UUID, service: PrivateExportServiceDependency, owner_id: UserScopeDependency
) -> Response:
    item = service.download(owner_id=owner_id, export_id=export_id, kind="report")
    return _download_response(item.body, item.mime_type, item.filename, item.sha256)


@router.get(
    "/content-exports/{export_id}/download",
    operation_id="downloadContentExport",
    response_class=Response,
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="复验全部当前权限后下载本人原始内容文件",
    responses=_DOWNLOAD,
)
def download_content_export(
    export_id: UUID, service: PrivateExportServiceDependency, owner_id: UserScopeDependency
) -> Response:
    item = service.download(owner_id=owner_id, export_id=export_id, kind="content")
    return _download_response(item.body, item.mime_type, item.filename, item.sha256)
