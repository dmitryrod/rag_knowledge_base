"""Перед каждым защищённым роутом выставляет current tenant для deps.get_db()."""

from __future__ import annotations

from fastapi import Depends

from app.auth_dep import Principal, get_principal
from app.request_tenant import set_current_tenant_id


def bind_tenant_context(principal: Principal = Depends(get_principal)) -> None:
    set_current_tenant_id(principal.tenant_id)
