from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from traceback import extract_tb
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.errors import ERROR_CATEGORIES, ApplicationError, ErrorCategory
from core.schemas import ErrorView, ValidationErrorItem


@dataclass(frozen=True, slots=True)
class PublicError:
    status_code: int
    code: str
    message: str


INTERNAL_ERROR = PublicError(500, "internal_error", "服务暂时不可用")
HTTP_ERRORS: Mapping[int, PublicError] = {
    400: PublicError(400, "bad_request", "请求无效"),
    401: PublicError(401, "unauthorized", "需要登录"),
    403: PublicError(403, "forbidden", "没有权限"),
    404: PublicError(404, "not_found", "请求资源不存在"),
    405: PublicError(405, "method_not_allowed", "请求方法不支持"),
    409: PublicError(409, "conflict", "请求与当前资源状态冲突"),
    413: PublicError(413, "payload_too_large", "请求内容过大"),
    415: PublicError(415, "unsupported_media_type", "请求格式不受支持"),
    422: PublicError(422, "validation_error", "请求参数校验失败"),
    429: PublicError(429, "rate_limited", "请求过于频繁"),
    500: INTERNAL_ERROR,
    502: PublicError(502, "upstream_error", "上游服务响应异常"),
    503: PublicError(503, "dependency_unavailable", "必要依赖暂不可用"),
    504: PublicError(504, "upstream_timeout", "上游服务响应超时"),
}
APPLICATION_ERRORS: Mapping[str, PublicError] = {
    "invalid_alert_input": PublicError(422, "invalid_alert_input", "告警参数不符合要求"),
    "alert_configuration_conflict": PublicError(
        409, "alert_configuration_conflict", "主题或告警目标版本已变化,请重新读取"
    ),
    "alert_prerequisite_unavailable": PublicError(
        409, "alert_prerequisite_unavailable", "有效输入或已成功投递的当前目标尚未就绪"
    ),
    "publication_not_configured": PublicError(
        503, "publication_not_configured", "公开资讯尚未发布"
    ),
    "publication_rate_limited": PublicError(
        429, "publication_rate_limited", "公开分发请求过于频繁,请稍后重试"
    ),
    "publication_distribution_unavailable": PublicError(
        503, "publication_distribution_unavailable", "公开分发暂不可用"
    ),
    "invalid_credentials": PublicError(401, "invalid_credentials", "账号或密码错误"),
    "invalid_session": PublicError(401, "invalid_session", "请登录后继续"),
    "invalid_email_code": PublicError(401, "invalid_email_code", "验证码无效或已过期"),
    "invalid_oauth_state": PublicError(401, "invalid_oauth_state", "授权已失效,请重新登录"),
    "github_authentication_failed": PublicError(
        401, "github_authentication_failed", "GitHub授权未完成"
    ),
    "credentials_verification_required": PublicError(
        403, "credentials_verification_required", "请验证当前密码或邮箱后修改凭据"
    ),
    "identity_link_conflict": PublicError(
        409, "identity_link_conflict", "登录身份无法关联到当前账户"
    ),
    "account_setup_required": PublicError(
        403, "account_setup_required", "请先设置用户名和密码完成注册"
    ),
    "username_unavailable": PublicError(409, "username_unavailable", "用户名无法使用"),
    "invalid_avatar": PublicError(
        422, "invalid_avatar", "请选择有效的 JPG、PNG 或 WebP 静态图片,最大 2 MB"
    ),
    "auth_rate_limited": PublicError(429, "auth_rate_limited", "登录请求过于频繁,请稍后重试"),
    "auth_dependency_unavailable": PublicError(
        503, "auth_dependency_unavailable", "登录服务暂时不可用"
    ),
    "github_login_unavailable": PublicError(503, "github_login_unavailable", "GitHub登录尚未配置"),
    "notification_email_not_bound": PublicError(
        422, "notification_email_not_bound", "请先绑定并验证账户邮箱"
    ),
    "email_login_unavailable": PublicError(503, "email_login_unavailable", "邮箱登录尚未配置"),
    "email_delivery_unavailable": PublicError(
        503, "email_delivery_unavailable", "验证码邮件暂时无法发送"
    ),
    "invalid_ai_input": PublicError(422, "invalid_ai_input", "模型能力配置不符合当前要求"),
    "ai_configuration_conflict": PublicError(
        409, "ai_configuration_conflict", "模型能力配置已变化,请重新读取当前版本"
    ),
    "ai_model_unavailable": PublicError(503, "ai_model_unavailable", "当前任务的固定模型暂不可用"),
    "publication_search_busy": PublicError(
        503, "publication_search_busy", "搜索结果较多,请收窄条件后重试"
    ),
    "selectbench_disabled": PublicError(503, "selectbench_disabled", "模型评测尚未启用"),
    "media_storage_unavailable": PublicError(503, "media_storage_unavailable", "媒体存储暂不可用"),
    "connection_disabled": PublicError(409, "connection_disabled", "连接已停用"),
    "connection_authentication_required": PublicError(
        409, "connection_authentication_required", "连接授权已失效且需要更新凭据后重新验证"
    ),
    "connection_credentials_missing": PublicError(
        409, "connection_credentials_missing", "请先由维护者配置服务端连接凭据"
    ),
    "connection_owner_confirmation_required": PublicError(
        409, "connection_owner_confirmation_required", "请本人核查账号和访问状态后确认恢复"
    ),
    "connection_safety_resume_conflict": PublicError(
        409, "connection_safety_resume_conflict", "当前连接没有待恢复的安全停用"
    ),
    "invalid_connection_configuration": PublicError(
        422, "invalid_connection_configuration", "来源连接配置不符合当前来源要求"
    ),
    "invalid_comment_scope": PublicError(
        422, "invalid_comment_scope", "评论查询范围不能同时指定线程根和直接父节点"
    ),
    "invalid_comment_cursor": PublicError(
        422, "invalid_comment_cursor", "评论分页游标不属于当前查询范围"
    ),
    "invalid_content_filter": PublicError(422, "invalid_content_filter", "作品筛选条件无效"),
    "codex_monitor_disabled": PublicError(409, "codex_monitor_disabled", "公告监控尚未启用"),
    "codex_version_conflict": PublicError(
        409, "codex_version_conflict", "公告状态已更新, 请重新读取"
    ),
    "invalid_codex_input": PublicError(422, "invalid_codex_input", "公告监控输入无效"),
    "codex_source_unavailable": PublicError(
        503, "codex_source_unavailable", "公告来源尚未就绪或暂不可用"
    ),
    "invalid_event_filter": PublicError(422, "invalid_event_filter", "事件筛选条件无效"),
    "invalid_event_correction": PublicError(422, "invalid_event_correction", "事件修订输入无效"),
    "invalid_editorial_input": PublicError(422, "invalid_editorial_input", "编辑分析输入无效"),
    "translation_disabled": PublicError(409, "translation_disabled", "全文翻译尚未启用"),
    "translation_material_unavailable": PublicError(
        404, "translation_material_unavailable", "固定正文或全文许可不可用"
    ),
    "translation_revision_conflict": PublicError(
        409, "translation_revision_conflict", "译文版本已更新, 请重新读取"
    ),
    "operator_disabled": PublicError(403, "operator_disabled", "维护入口尚未启用"),
    "invalid_feedback_input": PublicError(422, "invalid_feedback_input", "反馈输入无效"),
    "feedback_disabled": PublicError(503, "feedback_disabled", "反馈入口尚未就绪"),
    "feedback_rate_limited": PublicError(
        429, "feedback_rate_limited", "反馈提交过于频繁, 请稍后重试"
    ),
    "feedback_banned": PublicError(403, "feedback_banned", "当前反馈请求不可接受"),
    "operations_revision_conflict": PublicError(
        409, "operations_revision_conflict", "维护对象版本已更新"
    ),
    "invalid_operations_input": PublicError(422, "invalid_operations_input", "维护输入无效"),
    "indexnow_configuration_changed": PublicError(
        409, "indexnow_configuration_changed", "索引提交配置已变化"
    ),
    "indexnow_budget_unavailable": PublicError(
        503, "indexnow_budget_unavailable", "索引提交预算尚未准入"
    ),
    "indexnow_submission_unknown": PublicError(
        503, "indexnow_submission_unknown", "索引提交结果待人工核对"
    ),
    "indexnow_submission_rejected": PublicError(
        503, "indexnow_submission_rejected", "索引服务未接受提交"
    ),
    "invalid_evaluation_input": PublicError(422, "invalid_evaluation_input", "评测输入无效"),
    "evaluation_input_conflict": PublicError(409, "evaluation_input_conflict", "评测输入已变更"),
    "external_source_disabled": PublicError(
        403, "external_source_disabled", "外部摄入入口尚未启用"
    ),
    "external_source_authentication_required": PublicError(
        401, "external_source_authentication_required", "需要来源摄入授权"
    ),
    "external_source_rate_limited": PublicError(
        429, "external_source_rate_limited", "来源摄入请求过于频繁,请稍后重试"
    ),
    "operator_authentication_required": PublicError(
        401, "operator_authentication_required", "需要维护授权"
    ),
    "invalid_export_input": PublicError(422, "invalid_export_input", "导出输入或规模不符合约束"),
    "export_input_unavailable": PublicError(
        404, "export_input_unavailable", "固定导出输入不可访问"
    ),
    "export_version_conflict": PublicError(
        409, "export_version_conflict", "导出版本冲突或相同版本已有导出任务"
    ),
    "export_not_ready": PublicError(409, "export_not_ready", "导出文件尚未生成成功"),
    "export_storage_unavailable": PublicError(
        503, "export_storage_unavailable", "私有导出对象存储不可用"
    ),
    "invalid_edition_input": PublicError(422, "invalid_edition_input", "刊期或修订输入无效"),
    "edition_revision_conflict": PublicError(
        409, "edition_revision_conflict", "刊期修订已更新, 请重新读取"
    ),
    "edition_input_unavailable": PublicError(
        409, "edition_input_unavailable", "刊期没有有效材料或材料许可已变更"
    ),
    "event_revision_conflict": PublicError(
        409, "event_revision_conflict", "事件版本已更新, 请重新读取"
    ),
    "editorial_version_conflict": PublicError(
        409, "editorial_version_conflict", "分析或人工修订版本已更新, 请重新读取"
    ),
    "editorial_target_conflict": PublicError(
        409, "editorial_target_conflict", "相同平台入口与目标已有来源,请修改现有来源配置"
    ),
    "editorial_source_disabled": PublicError(
        409, "editorial_source_disabled", "编辑分析来源尚未启用"
    ),
    "editorial_source_unavailable": PublicError(
        409, "editorial_source_unavailable", "来源连接或许可已变化,请重新核对当前版本"
    ),
    "editorial_material_unavailable": PublicError(
        404, "editorial_material_unavailable", "当前版本的分析材料不可读"
    ),
    "editorial_export_not_authorized": PublicError(
        403, "editorial_export_not_authorized", "原始材料尚未获准用于个人文件导出"
    ),
    "invalid_publication_input": PublicError(
        422, "invalid_publication_input", "公开阅读配置或材料输入无效"
    ),
    "invalid_publication_cursor": PublicError(
        422, "invalid_publication_cursor", "公开阅读游标不属于当前查询范围"
    ),
    "publication_revision_conflict": PublicError(
        409, "publication_revision_conflict", "公开阅读修订已更新, 请重新读取"
    ),
    "publication_epoch_conflict": PublicError(
        409, "publication_epoch_conflict", "精选内容版本已更新, 请刷新列表"
    ),
    "invalid_event_cursor": PublicError(
        422, "invalid_event_cursor", "事件分页游标不属于当前查询范围"
    ),
    "invalid_content_cursor": PublicError(
        422, "invalid_content_cursor", "作品分页游标不属于当前筛选条件"
    ),
    "connection_version_conflict": PublicError(
        409, "connection_version_conflict", "连接版本已变更且需要重新验证"
    ),
    "comments_not_ready": PublicError(409, "comments_not_ready", "当前作品或来源尚不支持评论复采"),
    "comments_rate_limited": PublicError(
        409, "comments_rate_limited", "此帖的评论复采间隔尚未结束"
    ),
    "comments_budget_exhausted": PublicError(
        409, "comments_budget_exhausted", "当前来源或全局请求额度不足"
    ),
    "csrf_invalid": PublicError(403, "csrf_invalid", "请求安全校验失败"),
    "database_unavailable": PublicError(503, "database_unavailable", "数据库暂不可用"),
    "idempotency_conflict": PublicError(409, "idempotency_conflict", "操作标识已用于其他请求"),
    "job_not_cancellable": PublicError(409, "job_not_cancellable", "任务当前状态不可取消"),
    "job_not_retryable": PublicError(409, "job_not_retryable", "任务当前状态不可重试"),
    "retry_budget_exhausted": PublicError(
        409, "retry_budget_exhausted", "当前来源或全局每日请求额度不足"
    ),
    "invalid_monitor_rules": PublicError(422, "invalid_monitor_rules", "至少需要一个包含关键词"),
    "keyword_group_conflict": PublicError(
        422,
        "keyword_group_conflict",
        "同一关键词不能同时出现在冲突分组",
    ),
    "leaderboard_not_published": PublicError(404, "leaderboard_not_published", "尚无已发布模型榜"),
    "resource_not_found": PublicError(404, "resource_not_found", "请求资源不存在"),
    "source_target_not_allowed": PublicError(
        422, "source_target_not_allowed", "目标地址不在当前连接允许范围"
    ),
    "source_preset_not_applied": PublicError(
        409, "source_preset_not_applied", "所选来源尚未应用预设或不支持关键词搜索"
    ),
    "topic_archived": PublicError(409, "topic_archived", "已归档主题不能再修改"),
    "topic_not_ready": PublicError(409, "topic_not_ready", "主题来源尚未就绪"),
    "invalid_topic_source_selection": PublicError(
        422, "invalid_topic_source_selection", "所选来源不属于当前主题"
    ),
    "topic_version_conflict": PublicError(409, "topic_version_conflict", "主题已被其他修改更新"),
}

_ALLOWED_HEADERS: Mapping[int, frozenset[str]] = {
    401: frozenset({"www-authenticate"}),
    405: frozenset({"allow"}),
    429: frozenset({"retry-after"}),
    503: frozenset({"retry-after"}),
}
_SAFE_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_VALIDATION_MESSAGES: Mapping[str, str] = {
    "bool_parsing": "请输入有效布尔值",
    "date_parsing": "请输入有效日期",
    "datetime_parsing": "请输入有效日期时间",
    "extra_forbidden": "包含不允许的字段",
    "float_parsing": "请输入有效数字",
    "greater_than": "输入值必须更大",
    "greater_than_equal": "输入值过小",
    "int_parsing": "请输入有效整数",
    "less_than": "输入值必须更小",
    "less_than_equal": "输入值过大",
    "list_type": "请输入有效列表",
    "literal_error": "请选择有效值",
    "missing": "此字段为必填项",
    "string_too_long": "输入内容过长",
    "string_too_short": "输入内容过短",
    "string_type": "请输入有效文本",
    "uuid_parsing": "请输入有效标识",
    "value_error": "输入值不合法",
}


def _request_id(request: Request) -> UUID:
    candidate = getattr(request.state, "request_id", None)
    try:
        return UUID(str(candidate))
    except (TypeError, ValueError, AttributeError):
        request_id = uuid4()
        request.state.request_id = str(request_id)
        return request_id


def _safe_headers(status_code: int, headers: Mapping[str, str] | None) -> dict[str, str]:
    allowed = _ALLOWED_HEADERS.get(status_code, frozenset())
    safe: dict[str, str] = {}
    for name, value in (headers or {}).items():
        normalized = name.lower()
        if normalized not in allowed or "\r" in value or "\n" in value:
            continue
        safe[name] = value
    return safe


def _error_response(
    request: Request,
    error: PublicError,
    *,
    headers: Mapping[str, str] | None = None,
    details: list[ValidationErrorItem] | None = None,
) -> JSONResponse:
    view = ErrorView(
        code=error.code,
        message=error.message,
        request_id=_request_id(request),
        details=details,
    )
    response_headers = _safe_headers(error.status_code, headers)
    response_headers["cache-control"] = "no-store"
    response_headers["x-request-id"] = str(view.request_id)
    return JSONResponse(
        status_code=error.status_code,
        content=view.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
    )


def _http_error(status_code: int) -> PublicError:
    if status_code >= 500:
        return INTERNAL_ERROR
    return HTTP_ERRORS.get(
        status_code,
        PublicError(status_code, "http_error", "请求无法处理"),
    )


def _safe_location(location: tuple[Any, ...], error_type: str) -> list[str | int]:
    safe: list[str | int] = []
    for index, part in enumerate(location):
        if isinstance(part, int) or (
            index == 0 and part in {"body", "cookie", "header", "path", "query"}
        ):
            safe.append(part)
        elif isinstance(part, str) and _SAFE_FIELD_NAME.fullmatch(part):
            safe.append("<field>" if error_type == "extra_forbidden" else part)
        else:
            safe.append("<field>")
    return safe


def _validation_details(error: RequestValidationError) -> list[ValidationErrorItem]:
    details: list[ValidationErrorItem] = []
    for item in error.errors():
        error_type = str(item["type"])
        details.append(
            ValidationErrorItem(
                location=_safe_location(tuple(item["loc"]), error_type),
                message=_VALIDATION_MESSAGES.get(error_type, "输入值不合法"),
                type=error_type,
            )
        )
    return details


def _exception_location(error: Exception) -> str:
    frames = extract_tb(error.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


def _log_unexpected(request: Request, error: Exception, event: str) -> None:
    structlog.get_logger("api").error(
        event,
        request_id=str(_request_id(request)),
        exception_type=type(error).__name__,
        exception_location=_exception_location(error),
    )


def _validate_application_error_map() -> None:
    missing = set(ERROR_CATEGORIES) - set(APPLICATION_ERRORS)
    extra = set(APPLICATION_ERRORS) - set(ERROR_CATEGORIES)
    if missing or extra:
        raise RuntimeError(f"application error map mismatch: missing={missing}, extra={extra}")
    for code, category in ERROR_CATEGORIES.items():
        response = APPLICATION_ERRORS[code]
        expected_status = {
            ErrorCategory.AUTHENTICATION: 401,
            ErrorCategory.AUTHORIZATION: 403,
            ErrorCategory.CONFLICT: 409,
            ErrorCategory.DEPENDENCY_UNAVAILABLE: 503,
            ErrorCategory.INVALID_INPUT: 422,
            ErrorCategory.NOT_FOUND: 404,
            ErrorCategory.RATE_LIMITED: 429,
        }[category]
        if response.status_code != expected_status:
            raise RuntimeError(
                f"application error has invalid status: code={code}, expected={expected_status}"
            )


def register_exception_handlers(app: FastAPI) -> None:
    _validate_application_error_map()

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        headers = None
        if error.code == "publication_search_busy":
            headers = {"retry-after": "5"}
        if error.code == "feedback_rate_limited":
            seconds = error.context.get("retry_after")
            if isinstance(seconds, int) and not isinstance(seconds, bool) and 0 <= seconds <= 3600:
                headers = {"retry-after": str(seconds)}
        if error.code == "external_source_rate_limited":
            seconds = error.context.get("retry_after_seconds")
            if isinstance(seconds, int) and not isinstance(seconds, bool) and 0 <= seconds <= 60:
                headers = {"retry-after": str(seconds)}
        if error.code in {"auth_rate_limited", "publication_rate_limited"}:
            seconds = error.context.get("retry_after_seconds")
            if isinstance(seconds, int) and not isinstance(seconds, bool) and 1 <= seconds <= 3600:
                headers = {"retry-after": str(seconds)}
        return _error_response(request, APPLICATION_ERRORS[error.code], headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        public_error = _http_error(error.status_code)
        return _error_response(request, public_error, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            HTTP_ERRORS[422],
            details=_validation_details(error),
        )

    @app.exception_handler(ResponseValidationError)
    async def response_validation_error_handler(
        request: Request,
        error: ResponseValidationError,
    ) -> JSONResponse:
        _log_unexpected(request, error, "response_validation_failed")
        return _error_response(request, INTERNAL_ERROR)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        _log_unexpected(request, error, "unhandled_exception")
        return _error_response(request, INTERNAL_ERROR)
