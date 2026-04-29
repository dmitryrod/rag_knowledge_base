"""Админ: пользователи (только env admin)."""

from __future__ import annotations

from uuid import uuid4

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth_dep import require_users_panel
from app.config import Settings, get_settings
from app.deps import get_registry, provision_tenant
from app.passwords import hash_password

router = APIRouter(
    prefix="/admin/users",
    dependencies=[Depends(require_users_panel)],
    tags=["admin-users"],
)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., min_length=1, max_length=512)
    site_role: str = Field(default="member", description="member или admin")


class UserOut(BaseModel):
    id: str
    username: str
    tenant_id: str
    site_role: str
    created_at: str


@router.get("", response_model=list[UserOut])
def list_users() -> list[UserOut]:
    reg = get_registry()
    rows = reg.list_users()
    return [
        UserOut(
            id=u.id,
            username=u.username,
            tenant_id=u.tenant_id,
            site_role=u.site_role,
            created_at=u.created_at,
        )
        for u in rows
    ]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, settings: Settings = Depends(get_settings)) -> UserOut:
    if body.site_role not in ("member", "admin"):
        raise HTTPException(status_code=400, detail="site_role must be member or admin")
    tenant_id = str(uuid4())
    provision_tenant(settings, tenant_id)
    try:
        u = get_registry().create_user(
            body.username.strip(),
            hash_password(body.password),
            tenant_id,
            site_role=body.site_role,
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="Username already exists") from e
    return UserOut(
        id=u.id,
        username=u.username,
        tenant_id=u.tenant_id,
        site_role=u.site_role,
        created_at=u.created_at,
    )


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str) -> None:
    ok = get_registry().delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
