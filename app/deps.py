"""Shared dependencies: settings, DB, Chroma."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.chroma_store import ChromaStore
from app.config import Settings, get_settings
from app.db_sqlite import MetadataDB


_db: MetadataDB | None = None
_chroma: ChromaStore | None = None


def init_stores(settings: Settings) -> None:
    global _db, _chroma
    data = Path(settings.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    _db = MetadataDB(data / "metadata.db")
    _chroma = ChromaStore(data / "chroma")


def get_db() -> MetadataDB:
    if _db is None:
        raise RuntimeError("Stores not initialized")
    return _db


def get_chroma() -> ChromaStore:
    if _chroma is None:
        raise RuntimeError("Stores not initialized")
    return _chroma


__all__ = ["get_settings", "init_stores", "get_db", "get_chroma"]
