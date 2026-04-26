"""RAG test bench: retrieve + optional LLM with profile overrides and diagnostics."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from statistics import median
from typing import Any

from app.chroma_store import ChromaStore
from app.chat_service import build_context_block, replacement_char_report
from app.config import Settings, is_polza_model_allowlisted
from app import llm as llm_mod
from app.rag_profile import JsonMode, RagRuntimeProfile, RagScopeIn
from app.rag_filters import filter_chunks_by_distance
from app.rag_runtime import DEFAULT_SYSTEM_PROMPT, merge_settings_with_profile
from app.rag_scope import (
    RAG_ALL_PLACEHOLDER_ID,
    expand_collection_ids_with_subtrees,
    normalize_id_list,
)
from app.db_sqlite import MetadataDB

_log = logging.getLogger(__name__)


def _scope_to_collection_ids(db: MetadataDB, scope: RagScopeIn) -> tuple[list[str], dict[str, str]]:
    all_meta = [r for r in db.list_collections() if r["id"] != RAG_ALL_PLACEHOLDER_ID]
    all_cids = [str(r["id"]) for r in all_meta]
    sreal = set(all_cids)
    names = {str(r["id"]): str(r["name"]) for r in all_meta}
    if scope.all:
        tids = list(all_cids)
    else:
        raw = scope.ids or []
        base = normalize_id_list([str(x) for x in raw])
        base = [x for x in base if x in sreal]
        tids = expand_collection_ids_with_subtrees(
            base,
            subtree_postorder=db.collection_subtree_postorder,
            valid=sreal,
        )
    labels = {k: names.get(k, k[:8] + "…") for k in tids}
    return tids, labels


def _where_map_from_scope(scope: RagScopeIn, collection_ids: list[str]) -> dict[str, dict[str, Any]] | None:
    m = scope.document_ids_by_collection
    if not m:
        return None
    out: dict[str, dict[str, Any]] = {}
    for cid in collection_ids:
        dids = m.get(cid)
        if dids and len(dids) > 0:
            out[cid] = {"document_id": {"$in": [str(x) for x in dids]}}
    return out or None


def _json_mode_to_response_format(mode: JsonMode) -> dict[str, Any] | None:
    if mode == "none":
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    if mode == "json_schema_strict":
        # Strict schema would require a schema body; use json_object for API compatibility in MVP
        return {"type": "json_object"}
    return None


def _dist_stats(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    fs: list[float] = []
    for ch in chunks:
        d = ch.get("distance")
        if d is None:
            continue
        try:
            fs.append(float(d))
        except (TypeError, ValueError):
            continue
    if not fs:
        return {
            "distance_min": None,
            "distance_max": None,
            "distance_avg": None,
            "distance_p50": None,
        }
    return {
        "distance_min": min(fs),
        "distance_max": max(fs),
        "distance_avg": sum(fs) / len(fs),
        "distance_p50": float(median(fs)),
    }


def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _normalize_citation_list(cites: Any) -> list[dict[str, str]]:
    if not isinstance(cites, list):
        return []
    out: list[dict[str, str]] = []
    for c in cites:
        if isinstance(c, dict):
            out.append(
                {
                    "chunk_id": str(c.get("chunk_id", "")),
                    "quote": str(c.get("quote", "")),
                }
            )
    return out


def _fallback_citations(
    chunks: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ch in chunks[:limit]:
        out.append(
            {
                "chunk_id": str(ch.get("chunk_id", "")),
                "quote": ((ch.get("text") or "")[:240]).strip(),
            }
        )
    return out


def _citation_coverage(retrieved: list[dict[str, Any]], citations: list[dict[str, str]]) -> float:
    ids = {str(ch.get("chunk_id", "")) for ch in retrieved if ch.get("chunk_id")}
    if not ids:
        return 0.0
    cited = {c.get("chunk_id", "") for c in citations if c.get("chunk_id")}
    if not cited:
        return 0.0
    hit = len(cited & ids)
    return hit / max(1, len(cited))


def run_rag_test(
    base_settings: Settings,
    store: ChromaStore,
    db: MetadataDB,
    user_message: str,
    scope: RagScopeIn,
    profile: RagRuntimeProfile,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Run one test retrieval + optional LLM; returns answer, citations, chunks, metrics."""
    t0 = time.perf_counter()
    cids, col_labels = _scope_to_collection_ids(db, scope)
    if not cids:
        return {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: не выбраны разделы для поиска.",
            "citations": [],
            "chunks": [],
            "chunks_considered": 0,
            "retrieved_count": 0,
            "filtered_by_distance_count": 0,
            "demo_mode": True,
            "llm_skipped": True,
            "llm_skip_reason": "no_collections",
            "metrics": {
                "total_ms": (time.perf_counter() - t0) * 1000,
                "retrieval_ms": 0.0,
                "llm_ms": 0.0,
            },
        }

    merged = merge_settings_with_profile(base_settings, profile)
    n_results = int(profile.retrieval_top_k)
    where_by = _where_map_from_scope(scope, cids)
    wf = profile.where_document

    tr0 = time.perf_counter()
    try:
        if len(cids) == 1:
            chunks = store.query(
                cids[0],
                user_message,
                n_results,
                where=(where_by or {}).get(cids[0]) if where_by else None,
                where_document=wf,
            )
            for ch in chunks:
                ch["source_collection_id"] = cids[0]
        else:
            chunks = store.query_multi(
                cids,
                user_message,
                n_results,
                where_by_collection=where_by,
                where_document=wf,
            )
    except Exception:
        _log.exception("run_rag_test: chroma query failed")
        raise
    retrieval_ms = (time.perf_counter() - tr0) * 1000
    retrieved_count = len(chunks)

    chunks, filtered_n = filter_chunks_by_distance(chunks, profile.distance_threshold)
    if not chunks:
        total_ms = (time.perf_counter() - t0) * 1000
        return {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: в индексе нет фрагментов для запроса (после фильтра distance).",
            "citations": [],
            "chunks": [],
            "chunks_considered": 0,
            "retrieved_count": retrieved_count,
            "filtered_by_distance_count": filtered_n,
            "demo_mode": True,
            "llm_skipped": True,
            "llm_skip_reason": "no_chunks_after_filter",
            "metrics": {
                "total_ms": total_ms,
                "retrieval_ms": retrieval_ms,
                "llm_ms": 0.0,
                **_dist_stats([]),
            },
        }

    context = build_context_block(chunks, collection_labels=col_labels)
    system = profile.effective_system_prompt(DEFAULT_SYSTEM_PROMPT)
    user_block = f"ВОПРОС:\n{user_message}\n\nCONTEXT:\n{context}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_block},
    ]

    can_llm = (
        bool(base_settings.polza_api_key)
        and base_settings.allow_llm_egress
        and profile.llm_enabled
    )
    if profile.llm_model and can_llm and not is_polza_model_allowlisted(merged):
        can_llm = False

    llm_ms = 0.0
    demo_mode: bool = False
    llm_skipped = True
    llm_skip_reason: str | None = "no_egress_or_disabled"
    raw_llm: dict[str, Any] = {}
    answer = ""
    citations: list[dict[str, str]] = []
    fallback_citations_used = False

    if not can_llm:
        demo_mode = True
        parts = ["[Локальный контур] LLM не вызывается."]
        if profile.llm_enabled and not base_settings.allow_llm_egress:
            parts.append("Профиль запрашивает LLM, но ALLOW_LLM_EGRESS=false.")
        if profile.llm_enabled and not base_settings.polza_api_key:
            parts.append("Задайте POLZA_API_KEY.")
        if profile.llm_enabled and profile.llm_model and not is_polza_model_allowlisted(merged):
            parts.append("Модель не в POLZA_CHAT_MODEL_ALLOWLIST.")
        parts.append(f"Retrieved {len(chunks)} chunk(s), filtered {filtered_n} by distance.")
        answer = " ".join(parts)
        if profile.fallback_mode == "top_chunks":
            citations = _fallback_citations(chunks, 3)
            fallback_citations_used = len(citations) > 0
        elif profile.fallback_mode == "not_found":
            answer = "НЕ НАЙДЕНО В БАЗЕ: (no-egress, citations отключены профилем)."
            citations = []
    else:
        assert base_settings.polza_api_key
        response_fmt = _json_mode_to_response_format(profile.json_mode)
        tl0 = time.perf_counter()
        try:
            res = llm_mod.chat_completion_with_result(
                merged,
                messages,
                model_override=profile.llm_model,
                temperature=profile.temperature,
                top_p=profile.top_p,
                max_tokens=profile.max_tokens,
                max_completion_tokens=profile.max_completion_tokens,
                seed=profile.seed,
                response_format=response_fmt,
                provider=profile.provider,
                timeout=profile.timeout_seconds,
            )
        except Exception:
            _log.exception("run_rag_test: LLM call failed")
            raise
        llm_ms = (time.perf_counter() - tl0) * 1000
        llm_skipped = False
        llm_skip_reason = None
        demo_mode = False
        raw_text = res.content
        raw_llm = res.to_response_meta()
        raw_llm["raw"] = res.raw
        if debug:
            _log.info("run_rag_test: raw_len=%s", len(raw_text) if raw_text else 0)
        try:
            parsed = llm_mod.parse_json_response(raw_text)
        except json.JSONDecodeError:
            parsed = {
                "answer": raw_text.strip(),
                "citations": [
                    {"chunk_id": ch.get("chunk_id"), "quote": (ch.get("text") or "")[:120]}
                    for ch in chunks[:5]
                ],
            }
        answer = str(parsed.get("answer", "")).strip()
        citations = _normalize_citation_list(parsed.get("citations"))
        if chunks and not any(citations):
            if profile.fallback_mode == "top_chunks":
                citations = _fallback_citations(chunks, 5)
                fallback_citations_used = True
            elif profile.fallback_mode == "not_found":
                answer = "НЕ НАЙДЕНО В БАЗЕ" if not answer else answer
                fallback_citations_used = False
            else:
                # none: leave empty
                pass

    total_ms = (time.perf_counter() - t0) * 1000
    dist = _dist_stats(chunks)
    ccov = _citation_coverage(chunks, citations)
    answer_status = "not_found" if "НЕ НАЙДЕНО" in (answer or "") else "answered"
    if demo_mode:
        answer_status = "no_egress_demo"

    out: dict[str, Any] = {
        "answer": answer,
        "citations": citations,
        "chunks": chunks,
        "chunks_considered": len(chunks),
        "retrieved_count": retrieved_count,
        "filtered_by_distance_count": filtered_n,
        "demo_mode": demo_mode,
        "llm_skipped": llm_skipped,
        "llm_skip_reason": llm_skip_reason,
        "fallback_citations_used": fallback_citations_used,
        "llm_response_meta": raw_llm,
        "metrics": {
            "total_ms": total_ms,
            "retrieval_ms": retrieval_ms,
            "llm_ms": llm_ms,
            "citation_coverage": ccov,
            "citation_count": len(citations),
            "answer_status": answer_status,
            "answer_hash": _hash_text(answer or ""),
            "citation_set_hash": _hash_text(json.dumps(citations, sort_keys=True, ensure_ascii=False)),
            "fallback_citations_used": fallback_citations_used,
            **dist,
        },
    }
    if debug:
        out["debug"] = {"retrieval_encoding": replacement_char_report(chunks)}
    return out
