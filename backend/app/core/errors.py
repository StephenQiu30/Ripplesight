from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

type ErrorContextValue = str | int | float | bool | None


class ErrorCategory(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFLICT = "conflict"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"


ERROR_CATEGORIES: Mapping[str, ErrorCategory] = MappingProxyType(
    {
        "invalid_credentials": ErrorCategory.AUTHENTICATION,
        "invalid_session": ErrorCategory.AUTHENTICATION,
        "invalid_email_code": ErrorCategory.AUTHENTICATION,
        "invalid_oauth_state": ErrorCategory.AUTHENTICATION,
        "github_authentication_failed": ErrorCategory.AUTHENTICATION,
        "credentials_verification_required": ErrorCategory.AUTHORIZATION,
        "identity_link_conflict": ErrorCategory.CONFLICT,
        "username_unavailable": ErrorCategory.CONFLICT,
        "notification_email_not_bound": ErrorCategory.INVALID_INPUT,
        "invalid_avatar": ErrorCategory.INVALID_INPUT,
        "auth_rate_limited": ErrorCategory.RATE_LIMITED,
        "auth_dependency_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "github_login_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "email_login_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "email_delivery_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "connection_disabled": ErrorCategory.CONFLICT,
        "invalid_ai_input": ErrorCategory.INVALID_INPUT,
        "ai_configuration_conflict": ErrorCategory.CONFLICT,
        "ai_model_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "operator_disabled": ErrorCategory.AUTHORIZATION,
        "invalid_feedback_input": ErrorCategory.INVALID_INPUT,
        "selectbench_disabled": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "feedback_disabled": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "feedback_rate_limited": ErrorCategory.RATE_LIMITED,
        "feedback_banned": ErrorCategory.AUTHORIZATION,
        "operations_revision_conflict": ErrorCategory.CONFLICT,
        "invalid_operations_input": ErrorCategory.INVALID_INPUT,
        "indexnow_configuration_changed": ErrorCategory.CONFLICT,
        "indexnow_budget_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "indexnow_submission_unknown": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "indexnow_submission_rejected": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "publication_not_configured": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "publication_rate_limited": ErrorCategory.RATE_LIMITED,
        "publication_distribution_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "publication_search_busy": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "invalid_evaluation_input": ErrorCategory.INVALID_INPUT,
        "evaluation_input_conflict": ErrorCategory.CONFLICT,
        "operator_authentication_required": ErrorCategory.AUTHENTICATION,
        "external_source_disabled": ErrorCategory.AUTHORIZATION,
        "external_source_authentication_required": ErrorCategory.AUTHENTICATION,
        "external_source_rate_limited": ErrorCategory.RATE_LIMITED,
        "connection_authentication_required": ErrorCategory.CONFLICT,
        "connection_credentials_missing": ErrorCategory.CONFLICT,
        "connection_owner_confirmation_required": ErrorCategory.CONFLICT,
        "connection_safety_resume_conflict": ErrorCategory.CONFLICT,
        "invalid_connection_configuration": ErrorCategory.INVALID_INPUT,
        "invalid_comment_scope": ErrorCategory.INVALID_INPUT,
        "invalid_comment_cursor": ErrorCategory.INVALID_INPUT,
        "invalid_content_filter": ErrorCategory.INVALID_INPUT,
        "invalid_content_cursor": ErrorCategory.INVALID_INPUT,
        "invalid_event_filter": ErrorCategory.INVALID_INPUT,
        "invalid_event_cursor": ErrorCategory.INVALID_INPUT,
        "invalid_event_correction": ErrorCategory.INVALID_INPUT,
        "event_revision_conflict": ErrorCategory.CONFLICT,
        "invalid_editorial_input": ErrorCategory.INVALID_INPUT,
        "translation_disabled": ErrorCategory.CONFLICT,
        "translation_material_unavailable": ErrorCategory.NOT_FOUND,
        "translation_revision_conflict": ErrorCategory.CONFLICT,
        "invalid_export_input": ErrorCategory.INVALID_INPUT,
        "export_input_unavailable": ErrorCategory.NOT_FOUND,
        "export_version_conflict": ErrorCategory.CONFLICT,
        "export_not_ready": ErrorCategory.CONFLICT,
        "export_storage_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "invalid_edition_input": ErrorCategory.INVALID_INPUT,
        "invalid_alert_input": ErrorCategory.INVALID_INPUT,
        "alert_configuration_conflict": ErrorCategory.CONFLICT,
        "alert_prerequisite_unavailable": ErrorCategory.CONFLICT,
        "edition_revision_conflict": ErrorCategory.CONFLICT,
        "edition_input_unavailable": ErrorCategory.CONFLICT,
        "editorial_version_conflict": ErrorCategory.CONFLICT,
        "editorial_source_disabled": ErrorCategory.CONFLICT,
        "editorial_source_unavailable": ErrorCategory.CONFLICT,
        "editorial_material_unavailable": ErrorCategory.NOT_FOUND,
        "editorial_export_not_authorized": ErrorCategory.AUTHORIZATION,
        "invalid_publication_input": ErrorCategory.INVALID_INPUT,
        "media_storage_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "invalid_publication_cursor": ErrorCategory.INVALID_INPUT,
        "publication_revision_conflict": ErrorCategory.CONFLICT,
        "publication_epoch_conflict": ErrorCategory.CONFLICT,
        "codex_monitor_disabled": ErrorCategory.CONFLICT,
        "codex_version_conflict": ErrorCategory.CONFLICT,
        "invalid_codex_input": ErrorCategory.INVALID_INPUT,
        "codex_source_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "connection_version_conflict": ErrorCategory.CONFLICT,
        "comments_not_ready": ErrorCategory.CONFLICT,
        "comments_rate_limited": ErrorCategory.CONFLICT,
        "comments_budget_exhausted": ErrorCategory.CONFLICT,
        "csrf_invalid": ErrorCategory.AUTHORIZATION,
        "database_unavailable": ErrorCategory.DEPENDENCY_UNAVAILABLE,
        "idempotency_conflict": ErrorCategory.CONFLICT,
        "job_not_cancellable": ErrorCategory.CONFLICT,
        "job_not_retryable": ErrorCategory.CONFLICT,
        "retry_budget_exhausted": ErrorCategory.CONFLICT,
        "invalid_monitor_rules": ErrorCategory.INVALID_INPUT,
        "invalid_topic_source_selection": ErrorCategory.INVALID_INPUT,
        "keyword_group_conflict": ErrorCategory.INVALID_INPUT,
        "resource_not_found": ErrorCategory.NOT_FOUND,
        "source_target_not_allowed": ErrorCategory.INVALID_INPUT,
        "source_preset_not_applied": ErrorCategory.CONFLICT,
        "topic_archived": ErrorCategory.CONFLICT,
        "topic_not_ready": ErrorCategory.CONFLICT,
        "topic_version_conflict": ErrorCategory.CONFLICT,
    }
)


def get_error_category(code: str) -> ErrorCategory:
    try:
        return ERROR_CATEGORIES[code]
    except KeyError as error:
        raise ValueError(f"unregistered application error code: {code}") from error


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        *,
        context: Mapping[str, ErrorContextValue] | None = None,
    ) -> None:
        get_error_category(code)
        super().__init__(code)
        self.code = code
        self.context = dict(context or {})


class DependencyUnavailableError(ApplicationError):
    """A required runtime dependency cannot currently serve requests."""

    def __init__(
        self,
        code: str = "database_unavailable",
        *,
        context: Mapping[str, ErrorContextValue] | None = None,
    ) -> None:
        if get_error_category(code) is not ErrorCategory.DEPENDENCY_UNAVAILABLE:
            raise ValueError(f"error code is not a dependency failure: {code}")
        super().__init__(code, context=context)
