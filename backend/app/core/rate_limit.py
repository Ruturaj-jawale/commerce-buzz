"""In-process rate limiter for customer-facing API and MCP routes."""

from collections import defaultdict, deque
from time import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

_SKIP_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json", "/redoc")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path == prefix or path.startswith(prefix + "/") for prefix in _SKIP_PREFIXES):
            return await call_next(request)
        limit = get_settings().rate_limit_per_minute
        if limit <= 0:
            return await call_next(request)
        key = request.headers.get("x-api-key") or request.client.host if request.client else "unknown"
        now = time()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        window.append(now)
        return await call_next(request)
