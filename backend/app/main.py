from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis import Redis

from api.docs import register_documentation
from api.exception_handlers import register_exception_handlers
from api.middleware import register_middleware
from api.router import api_router
from api.routers.publication_exports import public_router as public_publication_exports_router
from api.routers.publication_exports import router as publication_exports_router
from core.config import Settings, get_settings
from core.logging import configure_logging
from db.session import create_db_engine, create_session_factory
from evidence.adapters.media_storage import create_media_storage
from identity.adapters.email import SmtpEmailAdapter
from identity.adapters.github import GitHubAdapter
from identity.adapters.verification_store import VerificationStore
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
            app.state.identity_redis.close()
            app.state.identity_http.close()
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
    app.state.identity_redis = Redis.from_url(
        resolved_settings.redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    app.state.identity_http = httpx.Client(timeout=10, follow_redirects=False)
    app.state.identity_verification = VerificationStore(
        app.state.identity_redis,
        resolved_settings.email_code_hmac_key.get_secret_value()
        if resolved_settings.email_code_hmac_key
        else None,
    )
    app.state.identity_github = GitHubAdapter(
        app.state.identity_http,
        resolved_settings.github_client_id,
        resolved_settings.github_client_secret.get_secret_value()
        if resolved_settings.github_client_secret
        else None,
        f"{resolved_settings.web_origin}/api/identity/github/callback",
    )
    app.state.identity_email = SmtpEmailAdapter(
        resolved_settings.auth_smtp_host,
        resolved_settings.auth_smtp_port,
        resolved_settings.auth_smtp_tls,
        resolved_settings.auth_smtp_username.get_secret_value()
        if resolved_settings.auth_smtp_username
        else None,
        resolved_settings.auth_smtp_password.get_secret_value()
        if resolved_settings.auth_smtp_password
        else None,
        resolved_settings.auth_smtp_from_email,
    )
    register_middleware(app)
    register_exception_handlers(app)
    register_documentation(app)
    app.include_router(api_router)
    app.include_router(publication_exports_router)
    app.include_router(public_publication_exports_router)
    return app
