"""SQLite metadata: collections, documents, audit log, chat threads/messages."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

from app.rag_scope import RAG_ALL_PLACEHOLDER_ID, RAG_ALL_PLACEHOLDER_NAME


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_threads_collection "
                "ON chat_threads(collection_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_threads_updated "
                "ON chat_threads(updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread "
                "ON chat_messages(thread_id, created_at)"
            )
            self._ensure_chat_threads_rag_column(conn)
            conn.commit()
        self._ensure_rag_all_collection()

    def _ensure_chat_threads_rag_column(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("PRAGMA table_info(chat_threads)")
        cols = [r[1] for r in cur.fetchall()]
        if "rag_scope_json" not in cols:
            conn.execute("ALTER TABLE chat_threads ADD COLUMN rag_scope_json TEXT")

    def _ensure_rag_all_collection(self) -> None:
        """Служебный раздел для тредов «по всем коллекциям» (FK)."""
        with self._connect() as conn:
            r = conn.execute(
                "SELECT 1 FROM collections WHERE id = ?",
                (RAG_ALL_PLACEHOLDER_ID,),
            ).fetchone()
            if r:
                return
            ts = utc_now_iso()
            conn.execute(
                "INSERT INTO collections (id, name, created_at) VALUES (?, ?, ?)",
                (RAG_ALL_PLACEHOLDER_ID, RAG_ALL_PLACEHOLDER_NAME, ts),
            )
            conn.commit()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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

    # --- Chat threads / messages (ChatGPT-like persisted history) ---

    def create_chat_thread(
        self,
        collection_id: str,
        title: str | None = None,
        rag_scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tid = str(uuid4())
        ts = utc_now_iso()
        default_title = title.strip() if title and title.strip() else "Новый чат"
        rag_j = json.dumps(rag_scope, ensure_ascii=False) if rag_scope else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_threads (id, collection_id, title, created_at, updated_at, rag_scope_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tid, collection_id, default_title, ts, ts, rag_j),
            )
            conn.commit()
        row = self.get_chat_thread(tid)
        assert row is not None
        return row

    def get_chat_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, collection_id, title, created_at, updated_at, rag_scope_json
                FROM chat_threads WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        raw = d.get("rag_scope_json")
        if raw:
            try:
                d["rag"] = json.loads(str(raw))
            except json.JSONDecodeError:
                d["rag"] = None
        else:
            d["rag"] = None
        return d

    def list_chat_threads(
        self,
        collection_id: str | None = None,
        limit: int = 500,
        *,
        legacy_single_only: bool = False,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 1000))
        with self._connect() as conn:
            if collection_id and legacy_single_only:
                rows = conn.execute(
                    """
                    SELECT id, collection_id, title, created_at, updated_at, rag_scope_json
                    FROM chat_threads
                    WHERE collection_id = ?
                      AND (rag_scope_json IS NULL OR rag_scope_json = '')
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (collection_id, lim),
                ).fetchall()
            elif collection_id:
                rows = conn.execute(
                    """
                    SELECT id, collection_id, title, created_at, updated_at, rag_scope_json
                    FROM chat_threads WHERE collection_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (collection_id, lim),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, collection_id, title, created_at, updated_at, rag_scope_json
                    FROM chat_threads
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            raw = d.get("rag_scope_json")
            if raw:
                try:
                    d["rag"] = json.loads(str(raw))
                except json.JSONDecodeError:
                    d["rag"] = None
            else:
                d["rag"] = None
            out.append(d)
        return out

    def update_chat_thread_title(self, thread_id: str, title: str) -> bool:
        t = title.strip()
        if not t:
            return False
        ts = utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE chat_threads SET title = ?, updated_at = ? WHERE id = ?",
                (t, ts, thread_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_chat_thread(self, thread_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM chat_threads WHERE id = ?", (thread_id,))
            conn.commit()
        return cur.rowcount > 0

    def insert_chat_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mid = str(uuid4())
        ts = utc_now_iso()
        cites = json.dumps(citations, ensure_ascii=False) if citations else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, thread_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mid, thread_id, role, content, cites, ts),
            )
            conn.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE id = ?",
                (ts, thread_id),
            )
            conn.commit()
        row = self.get_chat_message(mid)
        assert row is not None
        return row

    def get_chat_message(self, message_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, thread_id, role, content, citations_json, created_at
                FROM chat_messages WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        raw = d.get("citations_json")
        if raw:
            try:
                d["citations"] = json.loads(str(raw))
            except json.JSONDecodeError:
                d["citations"] = []
        else:
            d["citations"] = []
        del d["citations_json"]
        return d

    def list_chat_messages(self, thread_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, thread_id, role, content, citations_json, created_at
                FROM chat_messages WHERE thread_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (thread_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            raw = d.get("citations_json")
            if raw:
                try:
                    d["citations"] = json.loads(str(raw))
                except json.JSONDecodeError:
                    d["citations"] = []
            else:
                d["citations"] = []
            del d["citations_json"]
            out.append(d)
        return out
