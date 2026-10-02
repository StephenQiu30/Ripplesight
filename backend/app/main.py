from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.docs import register_documentation
from api.exception_handlers import register_exception_handlers
from api.middleware import register_middleware
from api.router import api_router
from api.routers.publication_exports import router as publication_exports_router
from core.config import Settings, get_settings
from core.logging import configure_logging
from db.session import create_db_engine, create_session_factory
from evidence.adapters.media_storage import create_media_storage
from operations.heartbeat import ProcessHeartbeatReporter


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(resolved_settings)
        app.state.session_factory = create_session_factory(engine)
        media_storage = create_media_storage(resolved_settings)
        app.state.media_storage = media_storage
        heartbeat = ProcessHeartbeatReporter(
            app.state.session_factory, role="api", enabled=resolved_settings.environment != "test"
        )
        heartbeat.start()
        try:
            yield
        finally:
            heartbeat.stop()
            if media_storage is not None:
                media_storage.close()
            engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    register_middleware(app)
    register_exception_handlers(app)
    register_documentation(app)
    app.include_router(api_router)
    app.include_router(publication_exports_router)
    return app
