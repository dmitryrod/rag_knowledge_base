"""Multi-tenant paths and legacy data directory migration."""

from __future__ import annotations

import shutil
from pathlib import Path

# Стабильные идентификаторы тенантов для учёток из env и API-ключей (admin tenant).
TENANT_ENV_ADMIN = "env_admin"
TENANT_ENV_DEMO = "env_demo"


def tenants_root(data_dir: Path) -> Path:
    return data_dir / "tenants"


def tenant_dir(data_dir: Path, tenant_id: str) -> Path:
    return tenants_root(data_dir) / tenant_id


def migrate_legacy_layout(data_dir: Path) -> None:
    """Переносит legacy `metadata.db` + `chroma/` из корня data в `tenants/env_admin/`."""
    data_dir = data_dir.resolve()
    legacy_db = data_dir / "metadata.db"
    legacy_chroma = data_dir / "chroma"
    tr = tenants_root(data_dir)
    target = tenant_dir(data_dir, TENANT_ENV_ADMIN)
    if not legacy_db.is_file():
        return
    if tr.exists() and (target / "metadata.db").is_file():
        return
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "metadata.db").is_file():
        shutil.move(str(legacy_db), str(target / "metadata.db"))
    if legacy_chroma.is_dir() and not (target / "chroma").exists():
        shutil.move(str(legacy_chroma), str(target / "chroma"))
