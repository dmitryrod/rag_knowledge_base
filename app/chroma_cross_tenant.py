"""Семантический поиск по наборам (tenant_id, collection_id)."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app import deps


def query_multi_cross_tenant(
    settings: Settings,
    targets: list[tuple[str, str]],
    query_text: str,
    n_results: int,
) -> list[dict[str, Any]]:
    """Сливает top‑k по тем же правилам, что ``ChromaStore.query_multi``, но по разным Chroma."""
    uniq: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for t, c in targets:
        if not t or not c:
            continue
        key = (t, c)
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    if not uniq:
        return []
    if len(uniq) == 1:
        tid, cid = uniq[0]
        store = deps.get_chroma_for_tenant(settings, tid)
        return store.query(cid, query_text, n_results)
    n = max(1, int(n_results))
    per = max(1, (n + len(uniq) - 1) // len(uniq))
    per = min(max(per, 4), n)
    merged: list[dict[str, Any]] = []
    for tenant_id, cid in uniq:
        store = deps.get_chroma_for_tenant(settings, tenant_id)
        part = store.query(cid, query_text, n_results=per)
        for ch in part:
            row = {
                **ch,
                "source_collection_id": cid,
                "source_tenant_id": tenant_id,
            }
            merged.append(row)

    def _dist(x: dict[str, Any]) -> float:
        d = x.get("distance")
        if d is None:
            return float("inf")
        try:
            return float(d)
        except (TypeError, ValueError):
            return float("inf")

    merged.sort(key=_dist)
    return merged[:n]
