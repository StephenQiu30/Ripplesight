from __future__ import annotations

from collections.abc import Generator
from hmac import compare_digest
from ipaddress import ip_address
from typing import Annotated, cast
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request, Response, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ai.capability_services import AiCapabilityService
from analysis.editorial_services import EditorialService
from analysis.evaluation_services import SelectBenchService
from analysis.translation_services import ContentTranslationService
from connections.editorial_icon_services import SourceIconService
from connections.editorial_services import EditorialSourceService
from connections.services import SourceConnectionService
from content.collection import WebPageCollectionService
from content.comments import CommentManualRunService
from content.hotlist import HotlistService
from content.services import ContentService
from core.errors import ApplicationError, DependencyUnavailableError
from events.corrections import EventCorrectionService
from events.facts import EventFactReadService
from events.heat import EventHeatService
from events.reads import EventReadService
from identity.profile_services import IdentityProfileService
from identity.services import AuthenticatedIdentity, IdentityService
from identity.services import CreatedIdentitySession as CreatedIdentitySession
from jobs.coverage import CollectionCoverageQueryService
from jobs.services import JobService
from knowledge.document_services import WorkspaceDocumentService
from leaderboard.reads import LeaderboardReadService
from monitors.codex_services import CodexResetService
from monitors.runs import MonitorTopicRunService
from monitors.services import MonitorTopicService
from notifications.alert_services import AlertService
from notifications.email_subscription import ReportEmailSubscriptionService
from notifications.operator import NotificationOperatorService
from notifications.services import NotificationTargetService
from operations.services import OperationsService
from operations.site_services import SiteConfigurationService
from publication.application import PublicationApplicationService
from publication.distribution_limits import PublicDistributionLimiter
from publication.mcp import PublicationMcpService
from publication.media_mirror_execution import MediaObjectStorage
from publication.media_mirror_reading import PublicationMediaReadingService
from publication.media_mirror_services import PublicationMediaService
from publication.site_reading import PublicSiteReadingService
from reports.edition_services import EditionService
from reports.export_services import PrivateExportService
from reports.services import ReportService
from sources.editorial_preview_services import EditorialSourcePreviewService
from sources.icons_reading import SourceIconReadingService


def get_session(request: Request) -> Generator[Session, None, None]:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    session = factory()
    try:
        yield session
    finally:
        if session.in_transaction():
            session.rollback()
        session.close()


SessionDependency = Annotated[Session, Depends(get_session)]


def get_alert_service(request: Request, session: SessionDependency) -> AlertService:
    return AlertService(session, request.app.state.settings)


AlertServiceDependency = Annotated[AlertService, Depends(get_alert_service)]


def get_ai_capability_service(request: Request, session: SessionDependency) -> AiCapabilityService:
    return AiCapabilityService(session, request.app.state.settings)


AiCapabilityServiceDependency = Annotated[AiCapabilityService, Depends(get_ai_capability_service)]


def get_source_icon_service(session: SessionDependency) -> SourceIconService:
    return SourceIconService(session)


SourceIconServiceDependency = Annotated[SourceIconService, Depends(get_source_icon_service)]


def get_source_icon_reading_service(
    request: Request, session: SessionDependency
) -> SourceIconReadingService:
    return SourceIconReadingService(session, getattr(request.app.state, "media_storage", None))


SourceIconReadingServiceDependency = Annotated[
    SourceIconReadingService, Depends(get_source_icon_reading_service)
]


def get_site_configuration_service(
    request: Request, session: SessionDependency
) -> SiteConfigurationService:
    return SiteConfigurationService(session, request.app.state.settings)


SiteConfigurationServiceDependency = Annotated[
    SiteConfigurationService, Depends(get_site_configuration_service)
]


def get_public_site_reading_service(session: SessionDependency) -> PublicSiteReadingService:
    return PublicSiteReadingService(session)


PublicSiteReadingServiceDependency = Annotated[
    PublicSiteReadingService, Depends(get_public_site_reading_service)
]


def get_selectbench_service(request: Request, session: SessionDependency) -> SelectBenchService:
    return SelectBenchService(
        session,
        enabled=request.app.state.settings.selectbench_enabled,
        settings=request.app.state.settings,
    )


SelectBenchServiceDependency = Annotated[SelectBenchService, Depends(get_selectbench_service)]


def get_operations_service(request: Request, session: SessionDependency) -> OperationsService:
    settings = request.app.state.settings
    return OperationsService(
        session,
        feedback_secret=(
            settings.feedback_hmac_secret.get_secret_value()
            if settings.feedback_hmac_secret is not None
            else None
        ),
        maintenance_enabled=settings.operations_maintenance_enabled,
        feedback_forward_enabled=settings.feedback_forward_enabled,
        backup_configured=(
            settings.operations_backup_directory is not None
            and settings.operations_restore_database_url is not None
        ),
    )


OperationsServiceDependency = Annotated[OperationsService, Depends(get_operations_service)]


def get_report_email_subscription_service(
    request: Request, session: SessionDependency
) -> ReportEmailSubscriptionService:
    return ReportEmailSubscriptionService(session, request.app.state.settings)


ReportEmailSubscriptionServiceDependency = Annotated[
    ReportEmailSubscriptionService, Depends(get_report_email_subscription_service)
]


def get_notification_target_service(session: SessionDependency) -> NotificationTargetService:
    return NotificationTargetService(session)


NotificationTargetServiceDependency = Annotated[
    NotificationTargetService, Depends(get_notification_target_service)
]


def get_notification_operator_service(session: SessionDependency) -> NotificationOperatorService:
    return NotificationOperatorService(session)


NotificationOperatorServiceDependency = Annotated[
    NotificationOperatorService, Depends(get_notification_operator_service)
]


def get_editorial_service(request: Request, session: SessionDependency) -> EditorialService:
    return EditorialService(
        session,
        settings=request.app.state.settings,
        indexing_enabled=request.app.state.settings.publication_indexing_enabled,
    )


EditorialServiceDependency = Annotated[EditorialService, Depends(get_editorial_service)]


def get_translation_service(
    request: Request, session: SessionDependency
) -> ContentTranslationService:
    return ContentTranslationService(
        session,
        settings=request.app.state.settings,
        enabled=request.app.state.settings.ai_enabled,
    )


TranslationServiceDependency = Annotated[
    ContentTranslationService, Depends(get_translation_service)
]


def get_editorial_source_service(
    request: Request, session: SessionDependency
) -> EditorialSourceService:
    return EditorialSourceService(
        session,
        external_tokens=request.app.state.settings.editorial_external_tokens,
        ingress_hmac_secret=request.app.state.settings.editorial_ingress_hmac_secret,
    )


EditorialSourceServiceDependency = Annotated[
    EditorialSourceService, Depends(get_editorial_source_service)
]


def get_editorial_source_preview_service(
    request: Request, session: SessionDependency
) -> EditorialSourcePreviewService:
    return EditorialSourcePreviewService(session, request.app.state.settings)


EditorialSourcePreviewServiceDependency = Annotated[
    EditorialSourcePreviewService, Depends(get_editorial_source_preview_service)
]


def get_edition_service(request: Request, session: SessionDependency) -> EditionService:
    return EditionService(session, settings=request.app.state.settings)


EditionServiceDependency = Annotated[EditionService, Depends(get_edition_service)]


def get_publication_service(
    request: Request, session: SessionDependency
) -> PublicationApplicationService:
    settings = request.app.state.settings
    return PublicationApplicationService(
        session,
        origin=settings.web_base_url,
        indexing_enabled=settings.publication_indexing_enabled,
        public_categories=settings.public_publication_categories,
    )


PublicationServiceDependency = Annotated[
    PublicationApplicationService, Depends(get_publication_service)
]


def get_publication_mcp_service(
    service: PublicationServiceDependency,
) -> PublicationMcpService:
    return PublicationMcpService(service)


PublicationMcpServiceDependency = Annotated[
    PublicationMcpService, Depends(get_publication_mcp_service)
]


def get_publication_media_service(
    request: Request,
    session: SessionDependency,
) -> PublicationMediaService:
    return PublicationMediaService(session, enabled=request.app.state.settings.media_mirror_enabled)


PublicationMediaServiceDependency = Annotated[
    PublicationMediaService, Depends(get_publication_media_service)
]


def get_publication_media_reading_service(
    request: Request,
    session: SessionDependency,
) -> PublicationMediaReadingService:
    storage = cast(MediaObjectStorage | None, getattr(request.app.state, "media_storage", None))
    return PublicationMediaReadingService(
        session, storage, public_categories=request.app.state.settings.public_publication_categories
    )


PublicationMediaReadingServiceDependency = Annotated[
    PublicationMediaReadingService, Depends(get_publication_media_reading_service)
]


def require_database(session: SessionDependency) -> None:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise DependencyUnavailableError() from error


DatabaseReadyDependency = Annotated[None, Depends(require_database)]


def get_job_service(session: SessionDependency) -> JobService:
    return JobService(session)


JobServiceDependency = Annotated[JobService, Depends(get_job_service)]


def get_collection_coverage_service(
    request: Request, session: SessionDependency
) -> CollectionCoverageQueryService:
    return CollectionCoverageQueryService(
        session,
        hotlist_interval_seconds=request.app.state.settings.hotlist_interval_seconds,
    )


CollectionCoverageServiceDependency = Annotated[
    CollectionCoverageQueryService,
    Depends(get_collection_coverage_service),
]


def get_webpage_collection_service(session: SessionDependency) -> WebPageCollectionService:
    return WebPageCollectionService(session)


WebPageCollectionServiceDependency = Annotated[
    WebPageCollectionService,
    Depends(get_webpage_collection_service),
]


def get_monitor_topic_service(session: SessionDependency) -> MonitorTopicService:
    return MonitorTopicService(session)


MonitorTopicServiceDependency = Annotated[
    MonitorTopicService,
    Depends(get_monitor_topic_service),
]


def get_monitor_topic_run_service(
    request: Request, session: SessionDependency
) -> MonitorTopicRunService:
    return MonitorTopicRunService(session, request.app.state.settings)


MonitorTopicRunServiceDependency = Annotated[
    MonitorTopicRunService,
    Depends(get_monitor_topic_run_service),
]


def get_source_connection_service(
    request: Request, session: SessionDependency
) -> SourceConnectionService:
    return SourceConnectionService(
        session,
        credentials=request.app.state.settings.source_credentials,
        chrome_owner_id=request.app.state.settings.bilibili_chrome_owner_id,
    )


SourceConnectionServiceDependency = Annotated[
    SourceConnectionService,
    Depends(get_source_connection_service),
]


def get_content_service(session: SessionDependency) -> ContentService:
    return ContentService(session)


ContentServiceDependency = Annotated[ContentService, Depends(get_content_service)]


def get_comment_manual_run_service(session: SessionDependency) -> CommentManualRunService:
    return CommentManualRunService(session)


CommentManualRunServiceDependency = Annotated[
    CommentManualRunService, Depends(get_comment_manual_run_service)
]


def get_hotlist_service(session: SessionDependency) -> HotlistService:
    return HotlistService(session)


HotlistServiceDependency = Annotated[HotlistService, Depends(get_hotlist_service)]


def get_report_service(request: Request, session: SessionDependency) -> ReportService:
    return ReportService(session, settings=request.app.state.settings)


ReportServiceDependency = Annotated[ReportService, Depends(get_report_service)]


def get_private_export_service(
    request: Request, session: SessionDependency
) -> PrivateExportService:
    return PrivateExportService(session, getattr(request.app.state, "media_storage", None))


PrivateExportServiceDependency = Annotated[
    PrivateExportService, Depends(get_private_export_service)
]


def get_event_read_service(session: SessionDependency) -> EventReadService:
    return EventReadService(session)


EventReadServiceDependency = Annotated[EventReadService, Depends(get_event_read_service)]


def get_event_correction_service(session: SessionDependency) -> EventCorrectionService:
    return EventCorrectionService(session)


EventCorrectionServiceDependency = Annotated[
    EventCorrectionService, Depends(get_event_correction_service)
]


def get_event_fact_read_service(session: SessionDependency) -> EventFactReadService:
    return EventFactReadService(session)


EventFactReadServiceDependency = Annotated[
    EventFactReadService, Depends(get_event_fact_read_service)
]


def get_heat_service(session: SessionDependency) -> EventHeatService:
    return EventHeatService(session)


EventHeatServiceDependency = Annotated[EventHeatService, Depends(get_heat_service)]


def get_leaderboard_read_service(session: SessionDependency) -> LeaderboardReadService:
    return LeaderboardReadService(session)


LeaderboardReadServiceDependency = Annotated[
    LeaderboardReadService, Depends(get_leaderboard_read_service)
]


def get_codex_reset_service(request: Request, session: SessionDependency) -> CodexResetService:
    return CodexResetService(session, settings=request.app.state.settings)


CodexResetServiceDependency = Annotated[CodexResetService, Depends(get_codex_reset_service)]


def get_identity_service(request: Request, session: SessionDependency) -> IdentityService:
    return IdentityService(
        session,
        request.app.state.settings,
        verification=request.app.state.identity_verification,
        github=request.app.state.identity_github,
        email=request.app.state.identity_email,
    )


IdentityServiceDependency = Annotated[IdentityService, Depends(get_identity_service)]


def get_identity_profile_service(session: SessionDependency) -> IdentityProfileService:
    return IdentityProfileService(session)


IdentityProfileServiceDependency = Annotated[
    IdentityProfileService, Depends(get_identity_profile_service)
]
_SESSION_COOKIE = APIKeyCookie(name="hotkey_session", scheme_name="SessionCookie", auto_error=False)


def require_identity_session(
    service: IdentityServiceDependency,
    response: Response,
    token: Annotated[str | None, Security(_SESSION_COOKIE)],
) -> AuthenticatedIdentity:
    response.headers["cache-control"] = "no-store"
    return service.authenticate(token)


AuthenticatedIdentityDependency = Annotated[
    AuthenticatedIdentity, Depends(require_identity_session)
]


def require_same_origin(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.settings.web_origin:
        raise ApplicationError("csrf_invalid")


def require_identity_csrf(
    request: Request,
    service: IdentityServiceDependency,
    identity: AuthenticatedIdentityDependency,
    cookie: Annotated[str | None, Cookie(alias="hotkey_csrf", include_in_schema=False)] = None,
    header: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> AuthenticatedIdentity:
    require_same_origin(request)
    service.validate_csrf(identity, cookie=cookie, header=header)
    return identity


CsrfProtectedIdentityDependency = Annotated[AuthenticatedIdentity, Depends(require_identity_csrf)]


def get_user_scope(identity: AuthenticatedIdentityDependency) -> UUID:
    return identity.view.user.id


UserScopeDependency = Annotated[UUID, Depends(get_user_scope)]


def get_user_write_scope(identity: CsrfProtectedIdentityDependency) -> UUID:
    return identity.view.user.id


UserWriteScopeDependency = Annotated[UUID, Depends(get_user_write_scope)]


def get_public_contact_scope(request: Request) -> UUID | None:
    return cast(UUID | None, request.app.state.settings.public_contact_owner_id)


PublicContactScopeDependency = Annotated[UUID | None, Depends(get_public_contact_scope)]


def get_public_publication_scope(request: Request) -> UUID:
    """Public reading never selects an account from a cookie or an arbitrary partition."""
    owner_id = cast(UUID | None, request.app.state.settings.public_publication_owner_id)
    if owner_id is None:
        raise ApplicationError("publication_not_configured")
    return owner_id


PublicPublicationScopeDependency = Annotated[UUID, Depends(get_public_publication_scope)]


def get_public_distribution_scope(request: Request) -> UUID:
    try:
        return get_public_publication_scope(request)
    except ApplicationError as error:
        if error.code == "publication_not_configured":
            raise ApplicationError("resource_not_found") from None
        raise


PublicDistributionScopeDependency = Annotated[UUID, Depends(get_public_distribution_scope)]


def get_public_distribution_limiter(request: Request) -> PublicDistributionLimiter:
    return PublicDistributionLimiter(request.app.state.identity_redis)


PublicDistributionLimiterDependency = Annotated[
    PublicDistributionLimiter, Depends(get_public_distribution_limiter)
]


def require_public_distribution_limit(
    request: Request,
    owner_id: PublicDistributionScopeDependency,
    limiter: PublicDistributionLimiterDependency,
) -> None:
    # Use the trusted TCP peer, matching identity's treatment of forwarding headers.
    try:
        peer = str(ip_address(request.client.host)) if request.client else "unknown"
    except ValueError:
        peer = "unknown"
    limiter.require_allowed(owner_id=owner_id, peer=peer)


def get_operator_scope(
    request: Request,
    scope_id: UserScopeDependency,
    token: Annotated[str | None, Header(alias="X-HotKey-Operator-Token")] = None,
) -> UUID:
    secret = request.app.state.settings.operator_token
    if secret is None or not secret.get_secret_value():
        raise ApplicationError("operator_disabled")
    if token is None or not compare_digest(token.encode(), secret.get_secret_value().encode()):
        raise ApplicationError("operator_authentication_required")
    return scope_id


OperatorScopeDependency = Annotated[UUID, Depends(get_operator_scope)]


def get_operator_write_scope(
    scope_id: OperatorScopeDependency,
    identity: CsrfProtectedIdentityDependency,
) -> UUID:
    return scope_id


OperatorWriteScopeDependency = Annotated[UUID, Depends(get_operator_write_scope)]


def get_workspace_document_service(request: Request) -> WorkspaceDocumentService:
    return WorkspaceDocumentService(request.app.state.settings)


WorkspaceDocumentServiceDependency = Annotated[
    WorkspaceDocumentService, Depends(get_workspace_document_service)
]
