"""Хеширование паролей для пользователей registry."""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Возвращает ASCII-safe строку хеша bcrypt."""
    raw = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return raw.decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
