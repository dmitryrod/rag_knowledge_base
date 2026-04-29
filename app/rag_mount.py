"""Раскрытие монтирований каталогов до пар (issuer_tenant_id, collection_id) для Chroma."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import Settings
from app import deps

if TYPE_CHECKING:
    from app.db_sqlite import MetadataDB


def expand_local_collection_ids_to_chroma_targets(
    settings: Settings,
    local_tenant_id: str,
    local_db: MetadataDB,
    logical_collection_ids: list[str],
) -> list[tuple[str, str]]:
    """Логические id разделов в локальном metadata → пары для чтения Chroma у источника или локально."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []

    def add_pair(tenant_id: str, cid: str) -> None:
        key = (tenant_id, cid)
        if key not in seen:
            seen.add(key)
            out.append(key)

    for cid_in in logical_collection_ids:
        cid = str(cid_in).strip()
        if not cid:
            continue
        row = local_db.get_collection(cid)
        if not row:
            continue
        mnt_tid = row.get("mount_issuer_tenant_id")
        mnt_root = row.get("mount_issuer_root_collection_id")
        if mnt_tid and mnt_root:
            issuer_tid = str(mnt_tid)
            idb = deps.get_db_for_tenant(settings, issuer_tid)
            for uc in idb.collection_subtree_postorder(str(mnt_root)):
                add_pair(issuer_tid, uc)
        else:
            for lc in local_db.collection_subtree_postorder(cid):
                add_pair(local_tenant_id, lc)

    return out


def collection_labels_for_chroma_targets(
    settings: Settings,
    targets: list[tuple[str, str]],
) -> dict[str, str]:
    """Подписи разделов по id (глобально уникальному collection id из БД источника)."""
    labels: dict[str, str] = {}
    by_tenant: dict[str, set[str]] = {}
    for tid, cid in targets:
        by_tenant.setdefault(tid, set()).add(cid)
    for tenant_id, cids in by_tenant.items():
        db_layer = deps.get_db_for_tenant(settings, tenant_id)
        for cid in sorted(cids):
            row = db_layer.get_collection(cid)
            labels[cid] = str(row["name"]) if row else cid[:8] + "…"
    return labels


def list_documents_maybe_mount(
    settings: Settings,
    local_db: MetadataDB,
    collection_id: str,
) -> list[dict[str, Any]]:
    """Документы раздела; для монтирования собирает все файлы под деревом источника."""
    row = local_db.get_collection(collection_id)
    if row is None:
        return []
    mnt_tid = row.get("mount_issuer_tenant_id")
    mroot = row.get("mount_issuer_root_collection_id")
    if mnt_tid and mroot:
        idb = deps.get_db_for_tenant(settings, str(mnt_tid))
        combined: list[dict[str, Any]] = []
        root_s = str(mroot)
        for subcid in idb.collection_subtree_postorder(root_s):
            for d in idb.list_documents(subcid):
                combined.append(dict(d))
        return combined
    return list(local_db.list_documents(collection_id))
