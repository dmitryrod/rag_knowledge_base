"""Общее для pytest — до первого импорта `app.config` (иначе локальный app/.env залипает в Tests)."""

from __future__ import annotations

import os

# KNOWLEDGE_TESTS_NO_DOTENV отключает чтение `.env`; подставляем те же ключи, что в `app/.env.example`.
for _k, _v in (
    ("CHUNK_SIZE", "800"),
    ("CHUNK_OVERLAP", "120"),
    ("MAX_UPLOAD_MB", "10"),
    ("RETRIEVAL_TOP_K", "8"),
):
    os.environ.setdefault(_k, _v)


def pytest_configure() -> None:
    """Всегда включать изоляцию — иначе локальный app/.env затаптывает ожидания тестов."""
    os.environ["KNOWLEDGE_TESTS_NO_DOTENV"] = "1"
