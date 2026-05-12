"""Какой tenant_id использовать для SQLite/Chroma при входе учётной записи DEMO из env."""

from __future__ import annotations

import logging

from app.auth_dep import Principal
from app.config import Settings
from app.registry_db import RegistryDB
from app.tenancy import TENANT_ENV_DEMO

_log = logging.getLogger(__name__)


def resolve_demo_storage_tenant_id(settings: Settings, registry: RegistryDB) -> str:
    """Приоритет: DEMO_WORKSPACE_TENANT_ID → DEMO_WORKSPACE_SHARE_TOKEN → собственный env_demo.

    Если ``DEMO_WORKSPACE_SHARE_TOKEN`` задан, но не найден в registry (устарел, другая БД),
    токен игнорируется и используется ``env_demo``, чтобы приложение поднималось при деплое.
    """
    raw_tid = (settings.demo_workspace_tenant_id or "").strip()
    if raw_tid:
        return raw_tid
    token = (settings.demo_workspace_share_token or "").strip()
    if token:
        link = registry.resolve_share_token(token)
        if link is None:
            _log.warning(
                "DEMO_WORKSPACE_SHARE_TOKEN не найден в registry (истёк или другой registry.db); "
                "используется tenant %s. Уберите токен из .env или выставьте DEMO_WORKSPACE_TENANT_ID.",
                TENANT_ENV_DEMO,
            )
            return TENANT_ENV_DEMO
        return link.issuer_tenant_id
    return TENANT_ENV_DEMO


def effective_storage_tenant_id(principal: Principal, settings: Settings, registry: RegistryDB) -> str:
    """tenant для get_db/get_chroma: у env_demo может указывать на shadow-каталог."""
    # Только встроенная demo из .env; registry-пользователи с role=demo не затрагиваем.
    if principal.subject != "env_demo":
        return principal.tenant_id
    return resolve_demo_storage_tenant_id(settings, registry)


__all__ = ["effective_storage_tenant_id", "resolve_demo_storage_tenant_id"]
