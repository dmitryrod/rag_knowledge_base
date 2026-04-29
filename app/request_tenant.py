"""Текущий tenant_id в рамках HTTP-запроса (после resolve Principal)."""

from __future__ import annotations

from contextvars import ContextVar

from app.tenancy import TENANT_ENV_ADMIN

current_tenant_id: ContextVar[str] = ContextVar(
    "current_tenant_id", default=TENANT_ENV_ADMIN
)


def set_current_tenant_id(tenant_id: str) -> None:
    current_tenant_id.set(tenant_id)
