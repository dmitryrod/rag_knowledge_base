"""RAG chat: retrieve chunks + LLM with citation-first JSON output."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.chroma_store import ChromaStore
from app.config import Settings
from app import llm as llm_mod

_log = logging.getLogger(__name__)


def build_context_block(
    chunks: list[dict[str, Any]],
    *,
    collection_labels: dict[str, str] | None = None,
) -> str:
    labels = collection_labels or {}
    lines: list[str] = []
    for i, ch in enumerate(chunks, start=1):
        cid = ch.get("chunk_id", "")
        meta = ch.get("metadata") or {}
        fn = meta.get("filename", "")
        text = ch.get("text", "")
        src = ch.get("source_collection_id")
        sec = ""
        if src:
            label = labels.get(str(src), str(src)[:8] + "…")
            sec = f" section={label}"
        lines.append(f"[{i}] chunk_id={cid} filename={fn}{sec}\n{text}")
    return "\n\n---\n\n".join(lines)


def run_chat(
    settings: Settings,
    store: ChromaStore,
    user_message: str,
    *,
    collection_ids: list[str],
    collection_labels: dict[str, str] | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    cids = [c for c in collection_ids if c]
    if not cids:
        return {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: не выбраны разделы для поиска.",
            "citations": [],
            "chunks_considered": 0,
        }
    if debug:
        _log.info(
            "run_chat: start collection_ids=%s message_len=%s retrieval_top_k=%s polza_set=%s egress=%s",
            cids,
            len(user_message),
            settings.retrieval_top_k,
            bool(settings.polza_api_key),
            settings.allow_llm_egress,
        )
    try:
        if len(cids) == 1:
            chunks = store.query(
                cids[0],
                user_message,
                n_results=settings.retrieval_top_k,
            )
        else:
            chunks = store.query_multi(
                cids,
                user_message,
                n_results=settings.retrieval_top_k,
            )
    except Exception:
        _log.exception("run_chat: Chroma query failed collection_ids=%s", cids)
        raise
    if debug:
        _log.info("run_chat: retrieved chunks count=%s", len(chunks))
    if not chunks:
        return {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: в индексе нет фрагментов для запроса.",
            "citations": [],
            "chunks_considered": 0,
        }

    def _fallback_citations(limit: int = 5) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for ch in chunks[:limit]:
            out.append(
                {
                    "chunk_id": str(ch.get("chunk_id", "")),
                    "quote": ((ch.get("text") or "")[:240]).strip(),
                }
            )
        return out

    context = build_context_block(chunks, collection_labels=collection_labels)
    system = (
        "Ты корпоративный ассистент. Отвечай ТОЛЬКО на основе CONTEXT. "
        "Если фрагменты в CONTEXT относятся к вопросу — ответь по ним и обязательно заполни citations "
        "(chunk_id из CONTEXT, quote — короткая выдержка). "
        "Фразу «НЕ НАЙДЕНО В БАЗЕ» используй только если ни один фрагмент CONTEXT не релевантен вопросу; "
        "в спорных случаях лучше оперись на ближайшие по смыслу фрагменты и укажи citations. "
        "Верни только валидный JSON без markdown-обёртки: поля answer (markdown), citations (массив {chunk_id, quote})."
    )
    user = f"ВОПРОС:\n{user_message}\n\nCONTEXT:\n{context}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    use_remote_llm = bool(settings.polza_api_key) and settings.allow_llm_egress
    if debug:
        _log.info("run_chat: use_remote_llm=%s", use_remote_llm)

    if not use_remote_llm:
        parts = ["[Локальный контур] LLM не вызывается."]
        if settings.polza_api_key and not settings.allow_llm_egress:
            parts.append("Задайте ALLOW_LLM_EGRESS=true для вызова Polza.")
        elif not settings.polza_api_key:
            parts.append("Задайте POLZA_API_KEY и при необходимости ALLOW_LLM_EGRESS=true.")
        parts.append(f"Retrieved {len(chunks)} chunk(s).")
        return {
            "answer": " ".join(parts),
            "citations": _fallback_citations(3),
            "chunks_considered": len(chunks),
            "demo_mode": True,
        }

    if debug:
        _log.info("run_chat: calling Polza model=%s", settings.polza_chat_model)
    try:
        raw = llm_mod.chat_completion(settings, messages)
    except Exception:
        _log.exception("run_chat: llm.chat_completion failed")
        raise
    if debug:
        _log.info("run_chat: LLM response raw_len=%s", len(raw) if raw else 0)
    try:
        parsed = llm_mod.parse_json_response(raw)
    except json.JSONDecodeError:  # type: ignore[misc]
        parsed = {
            "answer": raw.strip(),
            "citations": [
                {"chunk_id": ch.get("chunk_id"), "quote": (ch.get("text") or "")[:120]}
                for ch in chunks[:5]
            ],
        }
    answer = str(parsed.get("answer", "")).strip()
    cites = parsed.get("citations")
    if not isinstance(cites, list):
        cites = []
    normalized = []
    for c in cites:
        if isinstance(c, dict):
            normalized.append(
                {
                    "chunk_id": str(c.get("chunk_id", "")),
                    "quote": str(c.get("quote", "")),
                }
            )

    # При пустых citations с удалённой LLM раньше не подставлялись retrieval-цитаты, если в answer
    # было «НЕ НАЙДЕНО…» — визуально хуже, чем демо-режим без LLM. Если чанки есть, всегда даём
    # fallback-цитаты из топа retrieval, чтобы совпадало с no-egress и было видно, что в индексе было.
    if chunks and not any(normalized):
        normalized = _fallback_citations(5)

    return {
        "answer": answer,
        "citations": normalized,
        "chunks_considered": len(chunks),
    }
