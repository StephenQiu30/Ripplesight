from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from apps.api.app.core.settings import settings

logger = logging.getLogger("ai_hotspot_radar")


def mask_sensitive_headers(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    sensitive = {"authorization", "cookie", "x-api-key", "api-key"}
    result: dict[str, str] = {}
    for key, value in raw_headers:
        name = key.decode("latin1").lower()
        if name in sensitive:
            result[name] = "***"
        else:
            result[name] = value.decode("latin1")
    return result


def _clean_path(path: str) -> str:
    return path.replace("<", "").replace(">", "")


class RequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next: Callable):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        audit_enabled = getattr(settings, "app_env", "").lower() != "test"
        if audit_enabled:
            safe_headers = mask_sensitive_headers(list(request.headers.raw))
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": _clean_path(request.url.path),
                    "query": request.url.query,
                    "status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "headers": safe_headers,
                    "client": request.client.host if request.client else "unknown",
                },
            )
        return response


class _RateBucket:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.timestamps: deque[float] = deque()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self.requests_per_minute = max(requests_per_minute, 1)
        self.window_seconds = 60
        self._buckets: dict[str, _RateBucket] = {}
        self._lock = threading.Lock()

    async def dispatch(self, request, call_next: Callable):
        if self.requests_per_minute <= 0:
            return await call_next(request)
        client = request.client.host if request.client else "anonymous"
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(client, _RateBucket(self.requests_per_minute))
            while bucket.timestamps and now - bucket.timestamps[0] > self.window_seconds:
                bucket.timestamps.popleft()
            if len(bucket.timestamps) >= bucket.limit:
                logger.warning("rate_limit_exceeded", extra={"client": client, "path": request.url.path})
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limit", "message": "请求过于频繁，请稍后重试。"}},
                )
            bucket.timestamps.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(self.requests_per_minute - len(bucket.timestamps), 0))
        return response
