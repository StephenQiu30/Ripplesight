from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from connections.services import SourceConnectionService
from content.collection import WebPageCollectionService
from content.comments import CommentManualRunService
from content.hotlist import HotlistService
from content.services import ContentService
from core.errors import ApplicationError, DependencyUnavailableError
from db.demo import resolve_demo_scope
from jobs.coverage import CollectionCoverageQueryService
from jobs.services import JobService
from monitors.runs import MonitorTopicRunService
from monitors.services import MonitorTopicService
from reports.services import ReportService


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
        session, credentials=request.app.state.settings.source_credentials
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


def get_report_service(session: SessionDependency) -> ReportService:
    return ReportService(session)


ReportServiceDependency = Annotated[ReportService, Depends(get_report_service)]


def get_demo_scope(session: SessionDependency) -> UUID:
    return resolve_demo_scope(session)


DemoScopeDependency = Annotated[UUID, Depends(get_demo_scope)]


def get_demo_write_scope(
    scope_id: DemoScopeDependency,
    csrf_header: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> UUID:
    if csrf_header != "1":
        raise ApplicationError("csrf_invalid")
    return scope_id


DemoWriteScopeDependency = Annotated[UUID, Depends(get_demo_write_scope)]
