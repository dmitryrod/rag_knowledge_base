"""Текст из файлов: кодировки для RAG/чанков."""

from __future__ import annotations

from app.ingest import _decode_plain_text_bytes, extract_text


def test_decode_plain_utf8() -> None:
    raw = "Тест UTF-8: слово".encode("utf-8")
    s = _decode_plain_text_bytes(raw)
    assert "Тест" in s
    assert "\ufffd" not in s


def test_decode_plain_cp1251_not_replacement_chars() -> None:
    # Байты в CP1251, невалидны как UTF-8 — раньше decode(utf-8, replace) давал U+FFFD
    raw = "Документ на русском".encode("cp1251")
    s = _decode_plain_text_bytes(raw)
    assert "русском" in s
    assert "\ufffd" not in s


def test_extract_text_txt_respects_cp1251() -> None:
    raw = "Строка из Windows-1251".encode("cp1251")
    t = extract_text("notes.txt", raw)
    assert "Строка" in t
    assert "\ufffd" not in t
