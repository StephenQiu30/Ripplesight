from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def error_payload(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "request_id": request_id or uuid4().hex,
    }


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid4().hex)
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    message = detail.get("message") if isinstance(detail, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=code or f"http_{exc.status_code}",
            message=message or "Request failed",
            request_id=request_id,
            details=detail if isinstance(detail, dict) else {},
        ),
    )


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid4().hex)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code="internal_error",
            message="Unexpected server error",
            request_id=request_id,
            details={"exception_type": exc.__class__.__name__},
        ),
    )
