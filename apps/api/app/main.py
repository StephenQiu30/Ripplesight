from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.app.api.routes.check_runs import router as check_runs_router
from apps.api.app.api.routes.health import router as health_router
from apps.api.app.api.routes.hotspots import router as hotspots_router
from apps.api.app.api.routes.keywords import router as keywords_router
from apps.api.app.api.routes.notifications import router as notifications_router
from apps.api.app.api.routes.settings import router as settings_router
from apps.api.app.api.routes.sources import router as sources_router
from apps.api.app.db.init_schema import initialize_database
from apps.api.app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    scheduler_task = start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler(scheduler_task)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Hotspot Radar API",
        version="0.1.0",
        description="Rebuilt FastAPI backend for the self-hosted AI hotspot monitoring MVP.",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(keywords_router)
    app.include_router(sources_router)
    app.include_router(hotspots_router)
    app.include_router(check_runs_router)
    app.include_router(notifications_router)
    app.include_router(settings_router)
    return app


app = create_app()
