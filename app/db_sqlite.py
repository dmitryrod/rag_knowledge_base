"""SQLite metadata: collections, documents, audit log."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetadataDB:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime TEXT,
                    size_bytes INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (collection_id) REFERENCES collections(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_collection(self, name: str, coll_id: str | None = None) -> str:
        cid = coll_id or str(uuid4())
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO collections (id, name, created_at) VALUES (?, ?, ?)",
                (cid, name, ts),
            )
            conn.commit()
        return cid

    def list_collections(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM collections ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_collection(self, coll_id: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, created_at FROM collections WHERE id = ?",
                (coll_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_documents_in_collection(self, collection_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE collection_id = ?", (collection_id,))
            conn.commit()

    def delete_collection(self, coll_id: str) -> bool:
        self.delete_documents_in_collection(coll_id)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM collections WHERE id = ?", (coll_id,))
            conn.commit()
        return cur.rowcount > 0

    def insert_document(
        self,
        collection_id: str,
        doc_id: str,
        filename: str,
        mime: str | None,
        size_bytes: int,
    ) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, collection_id, filename, mime, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (doc_id, collection_id, filename, mime, size_bytes, ts),
            )
            conn.commit()

    def list_documents(self, collection_id: str) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, filename, mime, size_bytes, created_at
                FROM documents WHERE collection_id = ?
                ORDER BY created_at DESC
                """,
                (collection_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_document(self, collection_id: str, doc_id: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, collection_id, filename, mime, size_bytes, created_at
                FROM documents WHERE collection_id = ? AND id = ?
                """,
                (collection_id, doc_id),
            ).fetchone()
        return dict(row) if row else None

    def delete_document_row(self, collection_id: str, doc_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE collection_id = ? AND id = ?",
                (collection_id, doc_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def audit(self, action: str, detail: str) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, action, detail) VALUES (?, ?, ?)",
                (ts, action, detail),
            )
            conn.commit()

    def list_audit(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, ts, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
