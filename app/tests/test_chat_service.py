"""Unit tests for RAG chat (egress on/off, citation fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.chat_service import run_chat
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


def test_egress_not_found_json_still_gets_fallback_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Модель вернула «НЕ НАЙДЕНО» и пустой citations — retrieval не пустой, цитаты из чанков."""
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
