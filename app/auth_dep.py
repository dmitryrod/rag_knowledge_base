"""Аутентификация: API-ключи, сессия, principal для multi-tenant."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from typing_extensions import Annotated

from app.config import Settings, get_settings
from app.config import is_auth_required as config_is_auth_required
from app.passwords import verify_password
from app.registry_db import RegistryDB
from app.tenancy import TENANT_ENV_ADMIN, TENANT_ENV_DEMO

_header = APIKeyHeader(name="X-API-Key", auto_error=False)

Role = Literal["admin", "member"]
SiteRole = Literal["admin", "member", "demo"]


def _any_key_configured(settings: Settings) -> bool:
    return bool(settings.app_api_key or settings.app_admin_key or settings.app_member_key)


def is_auth_configured(settings: Settings) -> bool:
    """True, если нужна аутентификация (ключи и/или сессионный вход)."""
    return config_is_auth_required(settings)


@dataclass(frozen=True)
class AuthContext:
    """role=None — dev-режим без проверки (как при отсутствии ключей и сессии)."""

    role: Role | None


@dataclass(frozen=True)
class Principal:
    """Текущий субъект: тенант и роль на уровне приложения."""

    tenant_id: str
    site_role: SiteRole | None  # None только в dev без auth
    subject: str
    kind: Literal["dev", "session", "api_key"]


def principal_to_auth_context(p: Principal) -> AuthContext:
    if p.site_role is None:
        return AuthContext(role=None)
    if p.site_role == "admin":
        return AuthContext(role="admin")
    return AuthContext(role="member")


def _session_auth_blob(request: Request) -> dict | None:
    sess = getattr(request, "session", None)
    if sess is None:
        return None
    raw = sess.get("auth")
    if not isinstance(raw, dict):
        return None
    return raw


def _resolve_from_api_key(token: str | None, settings: Settings) -> Principal | None:
    if not token or not _any_key_configured(settings):
        return None
    if settings.app_admin_key and token == settings.app_admin_key:
        return Principal(
            tenant_id=TENANT_ENV_ADMIN,
            site_role="admin",
            subject="api_admin",
            kind="api_key",
        )
    if settings.app_member_key and token == settings.app_member_key:
        return Principal(
            tenant_id=TENANT_ENV_ADMIN,
            site_role="member",
            subject="api_member",
            kind="api_key",
        )
    if settings.app_api_key and token == settings.app_api_key:
        return Principal(
            tenant_id=TENANT_ENV_ADMIN,
            site_role="admin",
            subject="api_legacy",
            kind="api_key",
        )
    return None


def try_login_with_password(
    username: str,
    password: str,
    settings: Settings,
    registry: RegistryDB,
) -> Principal | None:
    """Проверка логина/пароля: env admin/demo, затем registry users."""
    al = (settings.admin_login or "").strip()
    ap = settings.admin_password
    if al and ap is not None and username.strip() == al:
        if secrets.compare_digest(password, str(ap)):
            return Principal(
                tenant_id=TENANT_ENV_ADMIN,
                site_role="admin",
                subject="env_admin",
                kind="session",
            )
    if (
        getattr(settings, "demo_enabled", False)
        and (settings.demo_login or "").strip()
        and settings.demo_password is not None
        and username.strip() == (settings.demo_login or "").strip()
        and secrets.compare_digest(password, str(settings.demo_password))
    ):
        return Principal(
            tenant_id=TENANT_ENV_DEMO,
            site_role="demo",
            subject="env_demo",
            kind="session",
        )
    ru = registry.get_by_username(username.strip())
    if ru is None:
        return None
    h = registry.get_password_hash(ru.id)
    if not h or not verify_password(password, h):
        return None
    sr: SiteRole = "member"
    if ru.site_role in ("admin", "member", "demo"):
        sr = ru.site_role  # type: ignore[assignment]
    return Principal(
        tenant_id=ru.tenant_id,
        site_role=sr,
        subject=ru.id,
        kind="session",
    )


def resolve_principal(
    request: Request,
    settings: Settings,
    x_api_key: str | None,
    registry: RegistryDB,
) -> Principal:
    auth = request.headers.get("Authorization")
    bearer = None
    if auth and auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    token = x_api_key or bearer

    blob = _session_auth_blob(request)
    if blob:
        try:
            tenant_id = str(blob["tenant_id"])
            site_role_raw = blob.get("site_role")
            subject = str(blob.get("subject", ""))
            kind_raw = str(blob.get("kind", "session"))
            if site_role_raw in (None, ""):
                sr: SiteRole | None = None
            elif site_role_raw in ("admin", "member", "demo"):
                sr = site_role_raw  # type: ignore[assignment]
            else:
                sr = "member"
            if kind_raw in ("session", "registry", "env"):
                return Principal(
                    tenant_id=tenant_id,
                    site_role=sr,
                    subject=subject or "session",
                    kind="session",
                )
        except (KeyError, TypeError, ValueError):
            pass

    pk = _resolve_from_api_key(token, settings)
    if pk is not None:
        return pk

    if not is_auth_configured(settings):
        return Principal(tenant_id=TENANT_ENV_ADMIN, site_role=None, subject="dev", kind="dev")

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: str | None = Depends(_header),
) -> Principal:
    from app.deps import get_registry

    return resolve_principal(request, settings, x_api_key, get_registry())


def get_auth(principal: Annotated[Principal, Depends(get_principal)]) -> AuthContext:
    """Совместимость: admin/member как раньше; demo считается member."""
    return principal_to_auth_context(principal)


def require_admin(auth: Annotated[AuthContext, Depends(get_auth)]) -> None:
    if auth.role is None:
        return
    if auth.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def require_app_admin(principal: Annotated[Principal, Depends(get_principal)]) -> None:
    """Строго site_role=admin (не demo/member)."""
    if principal.site_role is None:
        return
    if principal.site_role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def forbid_demo_writes(principal: Annotated[Principal, Depends(get_principal)]) -> None:
    if principal.site_role == "demo":
        raise HTTPException(status_code=403, detail="Not allowed for demo role")


def is_user_panel_admin(p: Principal) -> bool:
    """Панель пользователей: только env-admin и dev; API-ключи admin; не demo/registry-admin."""
    if p.kind == "dev":
        return True
    if p.tenant_id != TENANT_ENV_ADMIN or p.site_role != "admin":
        return False
    if p.kind == "api_key":
        return p.subject in ("api_admin", "api_legacy")
    if p.kind == "session":
        return p.subject == "env_admin"
    return False


def require_users_panel(principal: Annotated[Principal, Depends(get_principal)]) -> None:
    if not is_user_panel_admin(principal):
        raise HTTPException(status_code=403, detail="Env admin only")
