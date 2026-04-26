"""Unit tests for RAG chat (egress on/off, citation fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.chat_service import replacement_char_report, run_chat
from app.config import Settings


def _mk_settings(monkeypatch: pytest.MonkeyPatch, *, egress: bool, key: str | None = "test-key") -> Settings:
    """Переменные окружения хоста и app/.env не должны ломать тесты."""
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "true" if egress else "false")
    if key:
        monkeypatch.setenv("POLZA_API_KEY", key)
    else:
        monkeypatch.delenv("POLZA_API_KEY", raising=False)
    monkeypatch.setenv("POLZA_BASE_URL", "https://polza.ai/api/v1")
    monkeypatch.setenv("POLZA_CHAT_MODEL", "openai/gpt-4o-mini")
    monkeypatch.delenv("POLZA_CHAT_MODEL_ALLOWLIST", raising=False)
    return Settings()


def test_egress_not_found_empty_citations_no_fallback_to_avoid_masking_bad_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Явное «не найдено» от модели: не подставляем top-k цитаты (иначе маскируют плохой scope)."""
    from app import chat_service as cs

    store = MagicMock()
    store.query.return_value = [
        {"chunk_id": "a__0", "text": "Правило один: тест", "metadata": {"filename": "f.txt"}},
    ]

    def fake_llm(_settings: Settings, _messages: list) -> str:
        return '{"answer": "НЕ НАЙДЕНО В БАЗЕ.", "citations": []}'

    monkeypatch.setattr(cs.llm_mod, "chat_completion", fake_llm)
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "вопрос",
        collection_ids=["col1"],
    )
    assert out["chunks_considered"] == 1
    assert out["citations"] == []


def test_egress_not_found_with_relevant_plywood_chunk_gets_extractive_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если retrieval явно релевантен, «не найдено» от LLM не должно скрывать фрагменты."""
    from app import chat_service as cs

    store = MagicMock()
    store.query.return_value = [
        {
            "chunk_id": "plywood__0",
            "text": (
                "Фанера бывает березовой, хвойной и комбинированной. "
                "По сорту выделяют E, I, II, III и IV; сорт зависит от дефектов шпона."
            ),
            "metadata": {"filename": "fanera.txt"},
        },
    ]

    def fake_llm(_settings: Settings, _messages: list) -> str:
        return '{"answer": "НЕ НАЙДЕНО В БАЗЕ", "citations": []}'

    monkeypatch.setattr(cs.llm_mod, "chat_completion", fake_llm)
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "Какие существуют виды, типы, сорта фанеры?",
        collection_ids=["col1"],
    )
    assert out["answer"].startswith("По найденным фрагментам:")
    assert "НЕ НАЙДЕНО" not in out["answer"]
    assert out["citations"] == [
        {
            "chunk_id": "plywood__0",
            "quote": (
                "Фанера бывает березовой, хвойной и комбинированной. "
                "По сорту выделяют E, I, II, III и IV; сорт зависит от дефектов шпона."
            ),
        }
    ]


def test_plain_text_not_found_with_relevant_chunk_gets_extractive_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-JSON «не найдено» идёт через тот же relevance gate, а не через слепые citations."""
    from app import chat_service as cs

    store = MagicMock()
    store.query.return_value = [
        {
            "chunk_id": "plywood__1",
            "text": "Фанера делится по породе древесины и по сортам поверхности шпона.",
            "metadata": {"filename": "fanera.txt"},
        },
    ]

    def fake_llm(_settings: Settings, _messages: list) -> str:
        return "НЕ НАЙДЕНО В БАЗЕ"

    monkeypatch.setattr(cs.llm_mod, "chat_completion", fake_llm)
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "Какие бывают сорта фанеры?",
        collection_ids=["col1"],
    )
    assert out["answer"].startswith("По найденным фрагментам:")
    assert out["citations"][0]["chunk_id"] == "plywood__1"


def test_plain_text_not_found_with_one_broad_overlap_does_not_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Для многословного вопроса одного широкого совпадения мало, чтобы спасать «не найдено»."""
    from app import chat_service as cs

    store = MagicMock()
    store.query.return_value = [
        {
            "chunk_id": "noise__0",
            "text": "В документе описаны виды монтажных работ и сроки выполнения проекта.",
            "metadata": {"filename": "noise.txt"},
        },
    ]

    def fake_llm(_settings: Settings, _messages: list) -> str:
        return "НЕ НАЙДЕНО В БАЗЕ"

    monkeypatch.setattr(cs.llm_mod, "chat_completion", fake_llm)
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "Какие существуют виды, типы, сорта фанеры?",
        collection_ids=["col1"],
    )
    assert out["answer"] == "НЕ НАЙДЕНО В БАЗЕ"
    assert out["citations"] == []


def test_egress_answer_ok_empty_citations_gets_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой citations без «не найдено» — по-прежнему fallback из retrieval."""
    from app import chat_service as cs

    store = MagicMock()
    store.query.return_value = [
        {"chunk_id": "a__0", "text": "Правило один: тест", "metadata": {"filename": "f.txt"}},
    ]

    def fake_llm(_settings: Settings, _messages: list) -> str:
        return '{"answer": "Краткий ответ по базе.", "citations": []}'

    monkeypatch.setattr(cs.llm_mod, "chat_completion", fake_llm)
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "вопрос",
        collection_ids=["col1"],
    )
    assert len(out["citations"]) >= 1
    assert "a__0" in (out["citations"][0].get("chunk_id") or "")


def test_no_egress_uses_demo_with_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MagicMock()
    store.query.return_value = [
        {"chunk_id": "b__0", "text": "текст", "metadata": {}},
    ]
    out = run_chat(
        _mk_settings(monkeypatch, egress=False, key="k"),
        store,
        "q",
        collection_ids=["c"],
    )
    assert out.get("demo_mode") is True
    assert len(out["citations"]) >= 1


def test_replacement_char_report_empty() -> None:
    assert replacement_char_report([])["count"] == 0
    assert replacement_char_report([{"text": "чистый русский", "chunk_id": "a"}])["count"] == 0


def test_replacement_char_report_detects_u_fffd() -> None:
    r = replacement_char_report(
        [
            {
                "chunk_id": "x__0",
                "text": "битый\uFFFDсимвол",
                "metadata": {"filename": "old.txt"},
            }
        ]
    )
    assert r["count"] == 1
    assert r["items"][0]["chunk_id"] == "x__0"
    assert r["items"][0]["filename"] == "old.txt"


def test_zero_chunks_early_return(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MagicMock()
    store.query.return_value = []
    out = run_chat(
        _mk_settings(monkeypatch, egress=True),
        store,
        "q",
        collection_ids=["c"],
    )
    assert out["chunks_considered"] == 0
    assert "индексе" in (out.get("answer") or "")
