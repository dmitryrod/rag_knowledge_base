"""RAG chat: retrieve chunks + LLM with citation-first JSON output."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.chroma_cross_tenant import query_multi_cross_tenant
from app.config import Settings
from app import llm as llm_mod
from app.rag_filters import filter_chunks_by_distance
from app.rag_runtime import DEFAULT_SYSTEM_PROMPT

_log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{3,}")
_RU_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ими",
    "ыми",
    "иях",
    "ую",
    "юю",
    "ая",
    "ое",
    "ые",
    "ие",
    "ый",
    "ий",
    "ой",
    "ом",
    "ем",
    "ах",
    "ях",
    "ов",
    "ев",
    "ей",
    "ам",
    "ям",
    "ия",
    "ья",
    "ы",
    "и",
    "а",
    "я",
    "е",
    "у",
    "ю",
    "о",
)
_STOP_WORDS = {
    "без",
    "база",
    "базе",
    "базы",
    "был",
    "была",
    "были",
    "быть",
    "все",
    "для",
    "его",
    "если",
    "есть",
    "или",
    "как",
    "какая",
    "какие",
    "какой",
    "когда",
    "мне",
    "надо",
    "они",
    "при",
    "про",
    "что",
    "чем",
    "это",
    "этот",
    "существует",
    "существуют",
}


def _stem_word(word: str) -> str:
    w = word.lower().replace("ё", "е")
    for suffix in _RU_SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def _lexical_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in _WORD_RE.findall(text.lower().replace("ё", "е")):
        if raw in _STOP_WORDS:
            continue
        stem = _stem_word(raw)
        if stem and stem not in _STOP_WORDS:
            terms.add(stem)
    return terms


def _lexically_relevant_chunks(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    q_terms = _lexical_terms(question)
    if not q_terms:
        return []
    min_overlap = 1 if len(q_terms) <= 2 else 2
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, ch in enumerate(chunks):
        text = str(ch.get("text") or "")
        overlap = q_terms & _lexical_terms(text)
        if len(overlap) >= min_overlap:
            scored.append((len(overlap), idx, ch))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [ch for _, _, ch in scored[:limit]]


def _best_excerpt(question: str, text: str, *, max_len: int = 420) -> str:
    q_terms = _lexical_terms(question)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return text[:max_len].strip()
    best = max(
        sentences,
        key=lambda sent: len(q_terms & _lexical_terms(sent)),
    )
    if len(best) <= max_len:
        return best
    return best[:max_len].rstrip() + "..."


def _fallback_answer_from_relevant_chunks(
    question: str,
    chunks: list[dict[str, Any]],
) -> str:
    excerpts: list[str] = []
    seen: set[str] = set()
    for ch in chunks[:3]:
        excerpt = _best_excerpt(question, str(ch.get("text") or ""))
        if excerpt and excerpt not in seen:
            seen.add(excerpt)
            excerpts.append(excerpt)
    if not excerpts:
        return "По найденным фрагментам: релевантный фрагмент найден, см. цитаты ниже."
    return "По найденным фрагментам: " + " ".join(excerpts)


def _citations_from_chunks(
    chunks: list[dict[str, Any]],
    *,
    limit: int = 5,
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


def _answer_signals_not_found(answer: str) -> bool:
    return "не найдено" in (answer or "").lower()


def replacement_char_report(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Сводка по чанкам, в тексте которых уже есть U+FFFD (типично — старый ingest с replace).

    Исходные байты в таком чанке уже потеряны; исправление — перезагрузка/переиндексация документа.

    Args:
        chunks: элементы retrieval с ключами ``text``, ``chunk_id``, ``metadata``.

    Returns:
        ``count``, список ``items`` с ``chunk_id`` и ``filename``, и краткая ``note``.
    """
    items: list[dict[str, str]] = []
    for ch in chunks:
        t = str(ch.get("text") or "")
        if "\ufffd" not in t:
            continue
        meta = ch.get("metadata") or {}
        fn = ""
        if isinstance(meta, dict):
            fn = str(meta.get("filename") or "")
        items.append(
            {
                "chunk_id": str(ch.get("chunk_id", "")),
                "filename": fn,
            }
        )
    return {
        "count": len(items),
        "items": items,
        "note": "Текст в индексе содержит U+FFFD; переиндексируйте исходный файл.",
    }


def _build_chat_debug_payload(
    collection_ids: list[str],
    raw_chunks: list[dict[str, Any]],
    distance_filtered_out: int,
    *,
    preview_from: list[dict[str, Any]],
) -> dict[str, Any]:
    prev = preview_from[:12]
    top_chunks: list[dict[str, Any]] = []
    for ch in prev:
        meta = ch.get("metadata") or {}
        top_chunks.append(
            {
                "chunk_id": ch.get("chunk_id"),
                "distance": ch.get("distance"),
                "filename": meta.get("filename"),
                "source_collection_id": ch.get("source_collection_id"),
                "text_preview": ((ch.get("text") or "")[:160]).strip(),
            }
        )
    dists: list[float] = []
    for ch in raw_chunks:
        d = ch.get("distance")
        if d is None:
            continue
        try:
            dists.append(float(d))
        except (TypeError, ValueError):
            continue
    dist_summary: dict[str, Any] = {
        "min": min(dists) if dists else None,
        "max": max(dists) if dists else None,
    }
    return {
        "collection_ids": list(collection_ids),
        "retrieval_raw_count": len(raw_chunks),
        "distance_filtered_out": distance_filtered_out,
        "distance_summary": dist_summary,
        "top_chunks": top_chunks,
        "retrieval_encoding": replacement_char_report(preview_from),
    }


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
    store: ChromaStore | None,
    user_message: str,
    *,
    collection_ids: list[str] | None = None,
    chroma_targets: list[tuple[str, str]] | None = None,
    collection_labels: dict[str, str] | None = None,
    debug: bool = False,
    system_prompt_override: str | None = None,
    distance_threshold: float | None = None,
) -> dict[str, Any]:
    use_cross = bool(chroma_targets)
    if use_cross:
        cids_dbg = [c for _, c in (chroma_targets or []) if c]
    else:
        cids_dbg = [c for c in (collection_ids or []) if c]

    if not use_cross:
        assert store is not None
        if not collection_ids:
            return {
                "answer": "НЕ НАЙДЕНО В БАЗЕ: не выбраны разделы для поиска.",
                "citations": [],
                "chunks_considered": 0,
            }
        cids = [c for c in collection_ids if c]
    else:
        cids = cids_dbg
        if not cids:
            return {
                "answer": "НЕ НАЙДЕНО В БАЗЕ: не выбраны разделы для поиска.",
                "citations": [],
                "chunks_considered": 0,
            }
    if debug:
        _log.info(
            "run_chat: start collection_ids=%s cross_tenant=%s message_len=%s retrieval_top_k=%s polza_set=%s egress=%s",
            cids_dbg,
            use_cross,
            len(user_message),
            settings.retrieval_top_k,
            bool(settings.polza_api_key),
            settings.allow_llm_egress,
        )
    try:
        if use_cross:
            assert chroma_targets is not None
            chunks = query_multi_cross_tenant(
                settings,
                chroma_targets,
                user_message,
                settings.retrieval_top_k,
            )
        elif len(cids) == 1:
            assert store is not None
            chunks = store.query(
                cids[0],
                user_message,
                n_results=settings.retrieval_top_k,
            )
        else:
            assert store is not None
            chunks = store.query_multi(
                cids,
                user_message,
                n_results=settings.retrieval_top_k,
            )
    except Exception:
        _log.exception("run_chat: Chroma query failed collection_ids=%s", cids_dbg)
        raise
    if debug:
        _log.info("run_chat: retrieved chunks count=%s", len(chunks))
    if not chunks:
        out_empty: dict[str, Any] = {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: в индексе нет фрагментов для запроса.",
            "citations": [],
            "chunks_considered": 0,
        }
        if debug:
            out_empty["debug"] = {
                "collection_ids": cids_dbg,
                "retrieval_raw_count": 0,
                "distance_filtered_out": 0,
                "top_chunks": [],
                "retrieval_encoding": replacement_char_report([]),
            }
        return out_empty

    chunks_before_filter = list(chunks)
    chunks, dropped_n = filter_chunks_by_distance(chunks, distance_threshold)
    if not chunks:
        out_f: dict[str, Any] = {
            "answer": "НЕ НАЙДЕНО В БАЗЕ: в индексе нет фрагментов для запроса (после фильтра distance).",
            "citations": [],
            "chunks_considered": 0,
        }
        if debug:
            out_f["debug"] = _build_chat_debug_payload(
                cids_dbg,
                chunks_before_filter,
                dropped_n,
                preview_from=chunks_before_filter,
            )
        return out_f

    def _fallback_citations(limit: int = 5) -> list[dict[str, str]]:
        return _citations_from_chunks(chunks, limit=limit)

    context = build_context_block(chunks, collection_labels=collection_labels)
    system = system_prompt_override.strip() if system_prompt_override and system_prompt_override.strip() else (
        DEFAULT_SYSTEM_PROMPT
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
        demo_out: dict[str, Any] = {
            "answer": " ".join(parts),
            "citations": _fallback_citations(3),
            "chunks_considered": len(chunks),
            "demo_mode": True,
        }
        if debug:
            demo_out["debug"] = _build_chat_debug_payload(
                cids_dbg,
                chunks_before_filter,
                dropped_n,
                preview_from=chunks,
            )
        return demo_out

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
        raw_answer = raw.strip()
        parsed = {
            "answer": raw_answer,
            "citations": [] if _answer_signals_not_found(raw_answer) else _citations_from_chunks(chunks),
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

    # Если LLM перестраховалась и сказала «не найдено», локально спасаем только явно
    # релевантный retrieval. Иначе не маскируем плохой scope случайными top-k цитатами.
    if chunks and not any(normalized):
        if _answer_signals_not_found(answer):
            relevant_chunks = _lexically_relevant_chunks(user_message, chunks)
            if relevant_chunks:
                answer = _fallback_answer_from_relevant_chunks(user_message, relevant_chunks)
                normalized = _citations_from_chunks(relevant_chunks, limit=5)
        else:
            normalized = _fallback_citations(5)

    out: dict[str, Any] = {
        "answer": answer,
        "citations": normalized,
        "chunks_considered": len(chunks),
    }
    if debug:
        out["debug"] = _build_chat_debug_payload(
            cids_dbg,
            chunks_before_filter,
            dropped_n,
            preview_from=chunks,
        )
    return out
