"""FastAPI entrypoint."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.deps import init_stores
from app.routers.api import public, router
from app.routers.auth_api import router as auth_api_router
from app.routers.rag_test import router as rag_test_router
from app.routers.users_admin import router as users_admin_router

_STATIC = Path(__file__).resolve().parent / "static"


def _listen_port() -> int:
    """Порт HTTP-сервера (как у uvicorn: PORT / APP_PORT, иначе 8000)."""
    raw = os.environ.get("PORT") or os.environ.get("APP_PORT") or "8000"
    return int(raw)


def _cors_allow_origins() -> list[str]:
    s = (get_settings().app_cors_origins or "*").strip()
    if s == "*":
        return ["*"]
    return [x.strip() for x in s.split(",") if x.strip()]


def _inject_index_html() -> str:
    """Подставляет window.__API_BASE__ для fetch() при APP_PUBLIC_BASE_URL."""
    path = _STATIC / "index.html"
    raw = path.read_text(encoding="utf-8")
    base = (get_settings().app_public_base_url or "").strip().rstrip("/")
    inject = f"window.__API_BASE__ = {json.dumps(base)};\n    "
    marker = "  <script>\n"
    if marker not in raw:
        return raw
    return raw.replace(marker, f"  <script>\n    {inject}", 1)


def _print_open_urls() -> None:
    """Печать в терминал адресов для браузера (Docker: задай APP_EXPOSED_PORT = порт на хосте)."""
    internal = _listen_port()
    exposed = (os.environ.get("APP_EXPOSED_PORT") or "").strip()
    if exposed:
        hport = exposed
        hint = " (маппинг Docker/хост → контейнер)"
    else:
        hport = str(internal)
        hint = ""
    base = f"http://127.0.0.1:{hport}"
    lines = [
        "",
        f"  Knowledge API{hint}",
        f"  → Веб-админка: {base}/",
        f"  → Swagger: {base}/docs",
        f"  → ReDoc:   {base}/redoc",
        f"  → Health:  {base}/v1/health",
        "",
    ]
    print("\n".join(lines), flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    logging.getLogger("app").setLevel(logging.INFO)
    settings = get_settings()
    init_stores(settings)
    _print_open_urls()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Knowledge workspace",
        version="0.5.0",
        lifespan=lifespan,
    )
    settings = get_settings()

    sess = (settings.session_secret or "").strip()
    secret_key = sess if sess else "dev-insecure-session-change-in-production"

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="knowledge_session",
        same_site="lax",
        https_only=False,
        max_age=1209600,
    )

    @app.get("/", include_in_schema=False)
    def admin_index() -> HTMLResponse:
        """Корень: веб-админка; HTML подставляет __API_BASE__ при APP_PUBLIC_BASE_URL."""
        return HTMLResponse(content=_inject_index_html(), status_code=200)

    app.include_router(public, prefix="/v1", tags=["health"])
    app.include_router(auth_api_router, prefix="/v1", tags=["auth"])
    app.include_router(users_admin_router, prefix="/v1", tags=["admin-users"])
    app.include_router(router, prefix="/v1", tags=["api"])
    app.include_router(rag_test_router, prefix="/v1", tags=["rag-test"])

    ao = _cors_allow_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ao,
        allow_credentials=(ao != ["*"]),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    return app


app = create_app()


def run() -> None:
    port = _listen_port()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
