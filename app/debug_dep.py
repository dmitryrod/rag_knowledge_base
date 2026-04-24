"""Режим отладки по заголовку X-Debug (включается в веб-админке, Настройки)."""

from __future__ import annotations

from fastapi import Depends, Header

from app.config import Settings, get_settings


def is_client_debug(
    settings: Settings = Depends(get_settings),
    x_debug: str | None = Header(
        default=None,
        alias="X-Debug",
        description="1/true: подробные логи и тело ответа при ошибках",
    ),
) -> bool:
    if not settings.allow_client_debug:
        return False
    if x_debug is None or not str(x_debug).strip():
        return False
    return str(x_debug).strip().lower() in ("1", "true", "yes", "on")
