from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.cache import valkey_client
from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        default_limit: int = 100,
        default_window: int = 60,
    ):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/health/live", "/health/ready", "/metrics"):
            return await call_next(request)

        client_id = self._get_client_id(request)
        limit, window = self._get_rate_limit(request)

        allowed, current, remaining = await valkey_client.rate_limit_check(
            key=client_id,
            limit=limit,
            window=window,
        )

        if not allowed:
            return Response(
                content='{"error": "Rate limit exceeded", "retry_after": window}',
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(window),
                    "Retry-After": str(window),
                },
                media_type="application/json",
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window)

        return response

    def _get_client_id(self, request: Request) -> str:
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _get_rate_limit(self, request: Request) -> tuple[int, int]:
        path = request.url.path
        method = request.method

        if path.startswith("/v1/auth"):
            return settings.RATE_LIMIT_AUTH_FAILURES, 300
        if path.startswith("/v1/devices/pair"):
            return settings.RATE_LIMIT_PAIRING, 300
        if path.startswith("/v1/commands") and method == "POST":
            return settings.RATE_LIMIT_COMMANDS, 60
        if path.startswith("/v1/approvals") and method in ("POST", "PUT", "PATCH"):
            return settings.RATE_LIMIT_APPROVALS, 60
        if "/ws" in path:
            return settings.RATE_LIMIT_WS_CONNECTIONS, 60
        if path == "/health/detail":
            return settings.RATE_LIMIT_HEALTH_DETAIL, 60

        return self.default_limit, self.default_window


async def check_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> tuple[bool, int, int]:
    return await valkey_client.rate_limit_check(key, limit, window)
