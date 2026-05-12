"""Перед каждым защищённым роутом выставляет current tenant для deps.get_db()."""

from __future__ import annotations

from fastapi import Depends

from app.auth_dep import Principal, get_principal
from app.config import Settings, get_settings
from app.demo_workspace import effective_storage_tenant_id
from app.deps import get_registry
from app.registry_db import RegistryDB
from app.request_tenant import set_current_tenant_id


async def bind_tenant_context(
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
    registry: RegistryDB = Depends(get_registry),
) -> None:
    """Async: sync Depends run in a thread pool and do not propagate ContextVar to the request task."""
    set_current_tenant_id(effective_storage_tenant_id(principal, settings, registry))
