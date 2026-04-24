"""FastAPI entrypoint."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config import get_settings
from app.deps import init_stores
from app.routers.api import public, router

_STATIC = Path(__file__).resolve().parent / "static"


def _listen_port() -> int:
    """Порт HTTP-сервера (как у uvicorn: PORT / APP_PORT, иначе 8000)."""
    raw = os.environ.get("PORT") or os.environ.get("APP_PORT") or "8000"
    return int(raw)


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
    settings = get_settings()
    init_stores(settings)
    _print_open_urls()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Knowledge workspace",
        version="0.3.0",
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    def admin_index() -> FileResponse:
        """Корень: статическая веб-админка (см. app/static/index.html)."""
        return FileResponse(
            _STATIC / "index.html",
            media_type="text/html; charset=utf-8",
        )

    app.include_router(public, prefix="/v1", tags=["health"])
    app.include_router(router, prefix="/v1", tags=["api"])
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
