"""Текущий tenant_id в рамках HTTP-запроса (после resolve Principal)."""

from __future__ import annotations

from contextvars import ContextVar

current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def set_current_tenant_id(tenant_id: str) -> None:
    current_tenant_id.set(tenant_id)


def require_bound_tenant_id() -> str:
    """Извлечь текущий tenant после bind_tenant_context; иначе ошибка (не подставлять env_admin)."""

    tid = current_tenant_id.get()
    if tid is None:
        msg = "tenant context missing (bind_tenant_context required)"
        raise RuntimeError(msg)
    return tid


__all__ = [
    "current_tenant_id",
    "set_current_tenant_id",
    "require_bound_tenant_id",
]
