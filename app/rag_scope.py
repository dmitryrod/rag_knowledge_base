"""RAG scope: all sections, one or many collections (Chroma + SQLite)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

# Служебная «коллекция» в SQLite для потоков «по всем разделам» (FK + список тредов).
RAG_ALL_PLACEHOLDER_ID = "__knowledge_rag_all__"
RAG_ALL_PLACEHOLDER_NAME = "Все разделы"


def parse_rag_scope_json(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        d = json.loads(str(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    return d


def normalize_id_list(ids: list[str]) -> list[str]:
    out: list[str] = []
    for x in ids:
        s = str(x).strip()
        if s and s not in out and s != RAG_ALL_PLACEHOLDER_ID:
            out.append(s)
    return sorted(out)


def scopes_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if bool(a.get("all")) and bool(b.get("all")):
        return True
    la = normalize_id_list(list(a.get("ids") or [])) if a.get("ids") else []
    lb = normalize_id_list(list(b.get("ids") or [])) if b.get("ids") else []
    if la or lb:
        return la == lb
    return False


def thread_matches_rag(
    collection_id: str,
    rag_scope: dict[str, Any] | None,
    user_rag: dict[str, Any],
) -> bool:
    """Совпадение треда с выбранной в UI областью RAG (все / список id)."""
    if user_rag.get("all") is True:
        return bool(rag_scope and rag_scope.get("all") is True) and collection_id == RAG_ALL_PLACEHOLDER_ID
    uids = normalize_id_list(list(user_rag.get("ids") or []))
    if not uids:
        return False
    if rag_scope and rag_scope.get("all") is True:
        return False
    if not rag_scope or not any(rag_scope.values()):
        return len(uids) == 1 and collection_id == uids[0]
    if rag_scope.get("all"):
        return False
    tids = normalize_id_list(list(rag_scope.get("ids") or []))
    if not tids:
        return len(uids) == 1 and collection_id == uids[0]
    return tids == uids


def collection_ids_for_retrieval(
    list_collection_ids: list[str],
    *,
    collection_id: str,
    rag_scope: dict[str, Any] | None,
) -> list[str]:
    """Список Chroma collection id для запроса (без плейсхоллера), только существующие в метаданных."""
    real = [c for c in list_collection_ids if c != RAG_ALL_PLACEHOLDER_ID]
    sreal = set(real)
    if rag_scope and rag_scope.get("all") is True:
        return list(real)
    if rag_scope and rag_scope.get("ids"):
        got = normalize_id_list(
            [str(x) for x in (rag_scope.get("ids") or []) if x != RAG_ALL_PLACEHOLDER_ID]
        )
        return [x for x in got if x in sreal]
    if collection_id and collection_id != RAG_ALL_PLACEHOLDER_ID and collection_id in sreal:
        return [collection_id]
    return []


def expand_collection_ids_with_subtrees(
    root_ids: list[str],
    *,
    subtree_postorder: Callable[[str], list[str]],
    valid: set[str],
) -> list[str]:
    """Раскрыть каждый выбранный раздел до всех подразделов (дерево SQLite).

    Документы лежат в Chroma коллекции своего раздела; выбор только родителя без детей
    не находил бы файлы во вложенных папках.
    """
    seen: set[str] = set()
    out: list[str] = []
    for rid in root_ids:
        if rid not in valid:
            continue
        for cid in subtree_postorder(rid):
            if cid in valid and cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out
