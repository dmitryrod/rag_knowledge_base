"""SQLite registry: пользователи, созданные admin (логин вне env)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RegistryUser:
    id: str
    username: str
    tenant_id: str
    site_role: str
    created_at: str


class RegistryDB:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    site_role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_user(
        self,
        username: str,
        password_hash: str,
        tenant_id: str,
        site_role: str = "member",
    ) -> RegistryUser:
        uid = str(uuid4())
        ts = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, tenant_id, site_role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uid, username, password_hash, tenant_id, site_role, ts),
            )
        return RegistryUser(
            id=uid, username=username, tenant_id=tenant_id, site_role=site_role, created_at=ts
        )

    def get_by_username(self, username: str) -> RegistryUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, tenant_id, site_role, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return RegistryUser(
            id=row["id"],
            username=row["username"],
            tenant_id=row["tenant_id"],
            site_role=row["site_role"],
            created_at=row["created_at"],
        )

    def get_password_hash(self, user_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["password_hash"])

    def list_users(self) -> list[RegistryUser]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, tenant_id, site_role, created_at FROM users ORDER BY created_at"
            ).fetchall()
        return [
            RegistryUser(
                id=r["id"],
                username=r["username"],
                tenant_id=r["tenant_id"],
                site_role=r["site_role"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_user(self, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0
