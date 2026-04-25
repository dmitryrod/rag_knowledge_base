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
            self._init_rag_test_schema(conn)
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

    # --- RAG test: profiles, runs, main-chat runtime overrides, benchmarks, index (v2) ---

    def _init_rag_test_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_test_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'runtime',
                profile_json TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                applied_to_chat_at TEXT,
                created_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_test_runs (
                id TEXT PRIMARY KEY,
                profile_id TEXT,
                profile_snapshot_json TEXT NOT NULL,
                question TEXT NOT NULL,
                scope_json TEXT,
                answer TEXT,
                citations_json TEXT,
                retrieved_chunks_json TEXT,
                metrics_json TEXT,
                llm_request_json TEXT,
                llm_response_meta_json TEXT,
                demo_mode INTEGER,
                error_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES rag_test_profiles(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_test_run_pairs (
                id TEXT PRIMARY KEY,
                left_run_id TEXT NOT NULL,
                right_run_id TEXT NOT NULL,
                question TEXT NOT NULL,
                comparison_metrics_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (left_run_id) REFERENCES rag_test_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (right_run_id) REFERENCES rag_test_runs(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_runtime_settings (
                id TEXT PRIMARY KEY,
                profile_snapshot_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_benchmark_sets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_benchmark_questions (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL,
                question TEXT NOT NULL,
                expected_json TEXT,
                tags_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (set_id) REFERENCES rag_benchmark_sets(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_benchmark_runs (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL,
                profile_snapshot_json TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_metrics_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY (set_id) REFERENCES rag_benchmark_sets(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_benchmark_run_items (
                id TEXT PRIMARY KEY,
                benchmark_run_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                test_run_id TEXT,
                metrics_json TEXT,
                human_label TEXT,
                notes TEXT,
                FOREIGN KEY (benchmark_run_id) REFERENCES rag_benchmark_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES rag_benchmark_questions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_index_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                sandbox_collection_map_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_index_jobs (
                id TEXT PRIMARY KEY,
                index_profile_id TEXT NOT NULL,
                status TEXT NOT NULL,
                source_scope_json TEXT,
                counts_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY (index_profile_id) REFERENCES rag_index_profiles(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_test_runs_created ON rag_test_runs(created_at DESC)")

    def get_rag_runtime_settings(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, profile_snapshot_json, updated_at, updated_by FROM rag_runtime_settings WHERE id = ?",
                ("main_chat",),
            ).fetchone()
        return dict(row) if row else None

    def upsert_rag_runtime_settings(
        self,
        profile_snapshot_json: str,
        updated_by: str | None = None,
    ) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_runtime_settings (id, profile_snapshot_json, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_snapshot_json = excluded.profile_snapshot_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                ("main_chat", profile_snapshot_json, ts, updated_by),
            )
            conn.commit()

    def list_rag_test_profiles(self, kind: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM rag_test_profiles WHERE kind = ? ORDER BY updated_at DESC",
                    (kind,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM rag_test_profiles ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_rag_test_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_test_profiles WHERE id = ?", (profile_id,)).fetchone()
        return dict(row) if row else None

    def insert_rag_test_profile(
        self,
        profile_id: str,
        name: str,
        kind: str,
        profile_json: str,
        *,
        is_default: bool = False,
        created_by: str | None = None,
    ) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_test_profiles (
                    id, name, kind, profile_json, is_default, created_at, updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, name, kind, profile_json, 1 if is_default else 0, ts, ts, created_by),
            )
            conn.commit()

    def update_rag_test_profile(
        self,
        profile_id: str,
        name: str,
        kind: str,
        profile_json: str,
        *,
        is_default: bool = False,
    ) -> bool:
        ts = utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE rag_test_profiles SET
                    name = ?, kind = ?, profile_json = ?, is_default = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, kind, profile_json, 1 if is_default else 0, ts, profile_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_rag_test_profile(self, profile_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_test_profiles WHERE id = ?", (profile_id,))
            conn.commit()
        return cur.rowcount > 0

    def mark_profile_applied_to_chat(self, profile_id: str) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE rag_test_profiles SET applied_to_chat_at = ? WHERE id = ?",
                (ts, profile_id),
            )
            conn.commit()

    def insert_rag_test_run(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_test_runs (
                    id, profile_id, profile_snapshot_json, question, scope_json, answer, citations_json,
                    retrieved_chunks_json, metrics_json, llm_request_json, llm_response_meta_json,
                    demo_mode, error_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row.get("profile_id"),
                    row["profile_snapshot_json"],
                    row["question"],
                    row.get("scope_json"),
                    row.get("answer"),
                    row.get("citations_json"),
                    row.get("retrieved_chunks_json"),
                    row.get("metrics_json"),
                    row.get("llm_request_json"),
                    row.get("llm_response_meta_json"),
                    row.get("demo_mode"),
                    row.get("error_json"),
                    row["created_at"],
                ),
            )
            conn.commit()

    def get_rag_test_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_test_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_rag_test_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rag_test_runs ORDER BY created_at DESC LIMIT ?",
                (lim,),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_rag_test_run_pair(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_test_run_pairs (
                    id, left_run_id, right_run_id, question, comparison_metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["left_run_id"],
                    row["right_run_id"],
                    row["question"],
                    row.get("comparison_metrics_json"),
                    row["created_at"],
                ),
            )
            conn.commit()

    # --- Benchmark (v2) ---

    def insert_benchmark_set(self, set_id: str, name: str, description: str | None) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_benchmark_sets (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (set_id, name, description, ts, ts),
            )
            conn.commit()

    def list_benchmark_sets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM rag_benchmark_sets ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_benchmark_set(self, set_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_benchmark_sets WHERE id = ?", (set_id,)).fetchone()
        return dict(row) if row else None

    def update_benchmark_set(self, set_id: str, name: str, description: str | None) -> bool:
        ts = utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE rag_benchmark_sets SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description, ts, set_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_benchmark_set(self, set_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_benchmark_sets WHERE id = ?", (set_id,))
            conn.commit()
        return cur.rowcount > 0

    def insert_benchmark_question(
        self,
        qid: str,
        set_id: str,
        question: str,
        expected_json: str | None,
        tags_json: str | None,
    ) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_benchmark_questions (id, set_id, question, expected_json, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (qid, set_id, question, expected_json, tags_json, ts),
            )
            conn.commit()

    def list_benchmark_questions(self, set_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rag_benchmark_questions WHERE set_id = ? ORDER BY created_at",
                (set_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_benchmark_question(self, qid: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_benchmark_questions WHERE id = ?", (qid,)).fetchone()
        return dict(row) if row else None

    def delete_benchmark_question(self, qid: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_benchmark_questions WHERE id = ?", (qid,))
            conn.commit()
        return cur.rowcount > 0

    def insert_benchmark_run(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_benchmark_runs (
                    id, set_id, profile_snapshot_json, status, summary_metrics_json, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["set_id"],
                    row["profile_snapshot_json"],
                    row["status"],
                    row.get("summary_metrics_json"),
                    row["created_at"],
                    row.get("finished_at"),
                ),
            )
            conn.commit()

    def update_benchmark_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        summary_metrics_json: str | None = None,
        finished_at: str | None = None,
    ) -> bool:
        parts: list[str] = []
        vals: list[Any] = []
        if status is not None:
            parts.append("status = ?")
            vals.append(status)
        if summary_metrics_json is not None:
            parts.append("summary_metrics_json = ?")
            vals.append(summary_metrics_json)
        if finished_at is not None:
            parts.append("finished_at = ?")
            vals.append(finished_at)
        if not parts:
            return False
        vals.append(run_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE rag_benchmark_runs SET {', '.join(parts)} WHERE id = ?",
                vals,
            )
            conn.commit()
        return cur.rowcount > 0

    def get_benchmark_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_benchmark_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_benchmark_runs(self, set_id: str, limit: int = 20) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 100))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rag_benchmark_runs WHERE set_id = ? ORDER BY created_at DESC LIMIT ?",
                (set_id, lim),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_benchmark_run_item(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_benchmark_run_items (
                    id, benchmark_run_id, question_id, test_run_id, metrics_json, human_label, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["benchmark_run_id"],
                    row["question_id"],
                    row.get("test_run_id"),
                    row.get("metrics_json"),
                    row.get("human_label"),
                    row.get("notes"),
                ),
            )
            conn.commit()

    def list_benchmark_run_items(self, benchmark_run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rag_benchmark_run_items WHERE benchmark_run_id = ?",
                (benchmark_run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Index profiles / jobs (v2) ---

    def insert_rag_index_profile(
        self,
        profile_id: str,
        name: str,
        profile_json: str,
        status: str = "draft",
        sandbox_collection_map_json: str | None = None,
    ) -> None:
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_index_profiles (
                    id, name, profile_json, status, sandbox_collection_map_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, name, profile_json, status, sandbox_collection_map_json, ts, ts),
            )
            conn.commit()

    def list_rag_index_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM rag_index_profiles ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_rag_index_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_index_profiles WHERE id = ?", (profile_id,)).fetchone()
        return dict(row) if row else None

    def update_rag_index_profile(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        profile_json: str | None = None,
        status: str | None = None,
        sandbox_collection_map_json: str | None = None,
    ) -> bool:
        ts = utc_now_iso()
        parts: list[str] = ["updated_at = ?"]
        vals: list[Any] = [ts]
        if name is not None:
            parts.append("name = ?")
            vals.append(name)
        if profile_json is not None:
            parts.append("profile_json = ?")
            vals.append(profile_json)
        if status is not None:
            parts.append("status = ?")
            vals.append(status)
        if sandbox_collection_map_json is not None:
            parts.append("sandbox_collection_map_json = ?")
            vals.append(sandbox_collection_map_json)
        vals.append(profile_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE rag_index_profiles SET {', '.join(parts)} WHERE id = ?",
                vals,
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_rag_index_profile(self, profile_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_index_profiles WHERE id = ?", (profile_id,))
            conn.commit()
        return cur.rowcount > 0

    def insert_rag_index_job(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_index_jobs (
                    id, index_profile_id, status, source_scope_json, counts_json, error_json, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["index_profile_id"],
                    row["status"],
                    row.get("source_scope_json"),
                    row.get("counts_json"),
                    row.get("error_json"),
                    row["created_at"],
                    row.get("finished_at"),
                ),
            )
            conn.commit()

    def get_rag_index_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rag_index_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_rag_index_jobs(self, index_profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rag_index_jobs WHERE index_profile_id = ? ORDER BY created_at DESC",
                (index_profile_id,),
            ).fetchall()
        return [dict(r) for r in rows]
