"""RAG chat: retrieve chunks + LLM with citation-first JSON output."""

from __future__ import annotations

import json
from typing import Any

from app.chroma_store import ChromaStore
from app.config import Settings
from app import llm as llm_mod


def build_context_block(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, ch in enumerate(chunks, start=1):
        cid = ch.get("chunk_id", "")
        meta = ch.get("metadata") or {}
        fn = meta.get("filename", "")
        text = ch.get("text", "")
        lines.append(f"[{i}] chunk_id={cid} filename={fn}\n{text}")
    return "\n\n---\n\n".join(lines)


def run_chat(
    settings: Settings,
    store: ChromaStore,
    collection_id: str,
    user_message: str,
) -> dict[str, Any]:
    chunks = store.query(
        collection_id,
        user_message,
        n_results=settings.retrieval_top_k,
    )
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

    context = build_context_block(chunks)
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

    raw = llm_mod.chat_completion(settings, messages)
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
