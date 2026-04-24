"""API key guard и RBAC (admin / member)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)

Role = Literal["admin", "member"]


@dataclass(frozen=True)
class AuthContext:
    """role=None — ключи не настроены, доступ без проверки (dev)."""

    role: Role | None


def _any_key_configured(settings: Settings) -> bool:
    return bool(settings.app_api_key or settings.app_admin_key or settings.app_member_key)


def is_auth_configured(settings: Settings) -> bool:
    """True, если на сервере задан хотя бы один из APP_API_KEY / APP_ADMIN_KEY / APP_MEMBER_KEY."""
    return _any_key_configured(settings)


def _resolve_role(token: str | None, settings: Settings) -> Role | None:
    if not token:
        return None
    if settings.app_admin_key and token == settings.app_admin_key:
        return "admin"
    if settings.app_member_key and token == settings.app_member_key:
        return "member"
    if settings.app_api_key and token == settings.app_api_key:
        return "admin"
    return None


def get_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Depends(_header),
) -> AuthContext:
    if not _any_key_configured(settings):
        return AuthContext(role=None)
    auth = request.headers.get("Authorization")
    bearer = None
    if auth and auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    token = x_api_key or bearer
    role = _resolve_role(token, settings)
    if role is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return AuthContext(role=role)


def require_admin(auth: AuthContext = Depends(get_auth)) -> None:
    if auth.role is None:
        return
    if auth.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
