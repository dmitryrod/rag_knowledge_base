"""Shared dependencies: settings, DB, Chroma, registry (multi-tenant)."""

from __future__ import annotations

from pathlib import Path

from app.chroma_store import ChromaStore
from app.config import Settings, get_settings
from app.db_sqlite import MetadataDB
from app.registry_db import RegistryDB
from app.request_tenant import current_tenant_id
from app.tenancy import TENANT_ENV_ADMIN, TENANT_ENV_DEMO, migrate_legacy_layout, tenant_dir

_registry_db: RegistryDB | None = None
_tenant_stores: dict[str, tuple[MetadataDB, ChromaStore]] = {}


def init_stores(settings: Settings) -> None:
    """Инициализация registry, миграция legacy layout, прогрев тенантов env_admin / env_demo."""
    global _registry_db, _tenant_stores
    data = Path(settings.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    migrate_legacy_layout(data)
    _registry_db = RegistryDB(data / "registry.db")
    _tenant_stores.clear()
    _ensure_tenant_store(settings, TENANT_ENV_ADMIN)
    if (
        settings.demo_enabled
        and (settings.demo_login or "").strip()
        and settings.demo_password is not None
        and str(settings.demo_password) != ""
    ):
        _ensure_tenant_store(settings, TENANT_ENV_DEMO)


def _ensure_tenant_store(settings: Settings, tenant_id: str) -> tuple[MetadataDB, ChromaStore]:
    if tenant_id in _tenant_stores:
        return _tenant_stores[tenant_id]
    td = tenant_dir(settings.data_dir, tenant_id)
    td.mkdir(parents=True, exist_ok=True)
    db = MetadataDB(td / "metadata.db")
    chroma = ChromaStore(td / "chroma")
    _tenant_stores[tenant_id] = (db, chroma)
    return db, chroma


def provision_tenant(settings: Settings, tenant_id: str) -> None:
    """Создаёт каталог и инициализирует SQLite + Chroma для нового пользователя."""
    _ensure_tenant_store(settings, tenant_id)


def get_registry() -> RegistryDB:
    if _registry_db is None:
        raise RuntimeError("Stores not initialized")
    return _registry_db


def get_db_for_tenant(settings: Settings, tenant_id: str) -> MetadataDB:
    return _ensure_tenant_store(settings, tenant_id)[0]


def get_chroma_for_tenant(settings: Settings, tenant_id: str) -> ChromaStore:
    return _ensure_tenant_store(settings, tenant_id)[1]


def get_db() -> MetadataDB:
    tid = current_tenant_id.get()
    return get_db_for_tenant(get_settings(), tid)


def get_chroma() -> ChromaStore:
    tid = current_tenant_id.get()
    return get_chroma_for_tenant(get_settings(), tid)


__all__ = [
    "init_stores",
    "get_settings",
    "get_registry",
    "get_db_for_tenant",
    "get_chroma_for_tenant",
    "provision_tenant",
    "get_db",
    "get_chroma",
]
