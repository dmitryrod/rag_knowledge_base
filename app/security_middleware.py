"""HTTP middleware: optional Basic auth on OpenAPI/UIs, coarse POST limits on /v1."""

from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from app.config import Settings
from app.rate_limits import RateLimitExceeded, _post_events, record_sliding_or_raise


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _docs_paths(path: str) -> bool:
    return (
        path == "/openapi.json"
        or path.startswith("/docs")
        or path.startswith("/redoc")
    )


class DocsBasicAuthMiddleware(BaseHTTPMiddleware):
    """Optional HTTP Basic for /docs, /redoc, /openapi.json."""

    def __init__(self, app: Callable[..., Awaitable], settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        s = self._settings
        user = (s.app_docs_basic_auth_user or "").strip()
        pwd = s.app_docs_basic_auth_password
        if not user or pwd is None or str(pwd) == "":
            return await call_next(request)
        if not _docs_paths(request.url.path):
            return await call_next(request)
        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("basic "):
            return _basic_challenge()
        try:
            raw = base64.b64decode(auth[6:].strip(), validate=True)
        except (binascii.Error, ValueError):
            return _basic_challenge()
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _basic_challenge()
        if ":" not in decoded:
            return _basic_challenge()
        u, _, p = decoded.partition(":")
        if not secrets.compare_digest(u, user) or not secrets.compare_digest(p, str(pwd)):
            return _basic_challenge()
        return await call_next(request)


def _basic_challenge() -> PlainTextResponse:
    return PlainTextResponse(
        "Authorization required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="API docs"'},
    )


class V1PostRateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limit for POST under /v1 (except health and auth login)."""

    def __init__(self, app: Callable[..., Awaitable], settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        s = self._settings
        max_n = s.rate_limit_v1_post_max
        if max_n <= 0 or request.method != "POST":
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/v1/"):
            return await call_next(request)
        if path == "/v1/health" or path.startswith("/v1/auth/login"):
            return await call_next(request)
        ip = _client_ip(request)
        try:
            record_sliding_or_raise(
                _post_events,
                f"post:{ip}",
                window_sec=float(s.rate_limit_v1_post_window_sec),
                max_events=max_n,
            )
        except RateLimitExceeded as e:
            return PlainTextResponse(
                "Too Many Requests",
                status_code=429,
                headers={"Retry-After": str(max(1, int(e.retry_after_sec) + 1))},
            )
        return await call_next(request)
