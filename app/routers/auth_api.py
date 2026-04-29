"""Публичные эндпоинты входа и /me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth_dep import (
    Principal,
    display_login_for_principal,
    get_principal,
    is_user_panel_admin,
    try_login_with_password,
)
from app.config import get_settings
from app.deps import get_registry
from app.registry_db import RegistryDB
from app.router_tenant_bind import bind_tenant_context

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., min_length=1, max_length=512)


@router.post("/auth/login")
def auth_login(request: Request, body: LoginBody) -> dict[str, bool | str]:
    settings = get_settings()
    registry = get_registry()
    p = try_login_with_password(body.username, body.password, settings, registry)
    if p is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    sr = p.site_role
    request.session["auth"] = {
        "tenant_id": p.tenant_id,
        "site_role": sr if sr is not None else "admin",
        "subject": p.subject,
        "kind": "session",
    }
    return {"ok": True, "tenant_id": p.tenant_id}


@router.post("/auth/logout")
def auth_logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me", dependencies=[Depends(bind_tenant_context)])
def auth_me(
    principal: Principal = Depends(get_principal),
    registry: RegistryDB = Depends(get_registry),
) -> dict:
    return {
        "tenant_id": principal.tenant_id,
        "site_role": principal.site_role,
        "subject": principal.subject,
        "display_login": display_login_for_principal(principal, registry),
        "is_demo": principal.site_role == "demo",
        "can_manage_users": is_user_panel_admin(principal),
    }
