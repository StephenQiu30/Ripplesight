from __future__ import annotations

from fastapi import FastAPI

from apps.api.app.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Hotspot Radar API",
        version="0.1.0",
        description="Rebuilt FastAPI backend for the self-hosted AI hotspot monitoring MVP.",
    )
    app.include_router(health_router)
    return app


app = create_app()
