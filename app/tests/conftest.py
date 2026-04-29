"""Общее для pytest — до первого импорта `app.config` (иначе локальный app/.env залипает в Tests)."""

from __future__ import annotations

import os


def pytest_configure() -> None:
    """Всегда включать изоляцию — иначе локальный app/.env затаптывает ожидания тестов."""
    os.environ["KNOWLEDGE_TESTS_NO_DOTENV"] = "1"
