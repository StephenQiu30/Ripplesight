from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from .errors import http_exception_handler, unexpected_exception_handler
from .routes.events import router as events_router
from .routes.governance import router as governance_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Hotspot Radar API", version="0.1.0")

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
    app.include_router(governance_router)
    app.include_router(events_router)
    return app


app = create_app()
