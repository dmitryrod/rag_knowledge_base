"""Runtime configuration from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_env_files() -> tuple[str, ...]:
    """По умолчанию загружаются `.env`, `app/.env`; в pytest задаётся KNOWLEDGE_TESTS_NO_DOTENV=1 без reload."""
    v = os.getenv("KNOWLEDGE_TESTS_NO_DOTENV", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return ()
    return (".env", "app/.env")


class Settings(BaseSettings):
    """Application settings; loads from `.env` in cwd or `app/.env`."""

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Auth (optional): если не задан ни один ключ — dev-режим без проверки.
    # APP_API_KEY — legacy: полный доступ (admin).
    # APP_ADMIN_KEY / APP_MEMBER_KEY — RBAC: admin — разделы, ingest, audit; member — чтение + чат.
    app_api_key: str | None = Field(default=None, validation_alias=AliasChoices("APP_API_KEY"))
    app_admin_key: str | None = Field(default=None, validation_alias=AliasChoices("APP_ADMIN_KEY"))
    app_member_key: str | None = Field(default=None, validation_alias=AliasChoices("APP_MEMBER_KEY"))

    data_dir: Path = Field(
        default=Path(__file__).resolve().parent / "data",
        validation_alias=AliasChoices("APP_DATA_DIR", "DATA_DIR"),
    )

    polza_api_key: str | None = None
    polza_base_url: str = "https://polza.ai/api/v1"

    @field_validator("polza_base_url")
    @classmethod
    def _polza_base_url_has_scheme(cls, v: str) -> str:
        s = (v or "").strip()
        if not s.startswith(("http://", "https://")):
            msg = "POLZA_BASE_URL must be an absolute URL (http:// or https://)"
            raise ValueError(msg)
        return s
    polza_chat_model: str = "openai/gpt-4o-mini"
    polza_temperature: float = Field(
        0.0,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices("POLZA_TEMPERATURE"),
    )
    # Список разрешённых имён моделей (через запятую). Пусто — без доп. ограничения (при включённом egress).
    polza_chat_model_allowlist: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLZA_CHAT_MODEL_ALLOWLIST", "POLZA_MODEL_ALLOWLIST"),
    )
    # По умолчанию внешние вызовы LLM выключены; для Polza задайте true.
    allow_llm_egress: bool = Field(default=False, validation_alias=AliasChoices("ALLOW_LLM_EGRESS"))

    chunk_size: int = 800
    chunk_overlap: int = 120
    max_upload_mb: int = 10
    retrieval_top_k: int = 8
    # Если false — даже при X-Debug: 1 в ответ не отдаётся traceback (только серверные логи)
    allow_client_debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("APP_ALLOW_CLIENT_DEBUG", "APP_CLIENT_DEBUG"),
    )
    # Браузер: префикс для fetch() к API (когда UI открыт с другого origin/порта). Без слеша на конце.
    app_public_base_url: str = Field(default="", validation_alias=AliasChoices("APP_PUBLIC_BASE_URL"))
    # CORS: через запятую (http://a:3000) или * — иначе «Failed to fetch» при веб-UI не с того origin.
    app_cors_origins: str = Field(default="*", validation_alias=AliasChoices("APP_CORS_ORIGINS"))

    # Сессионный вход (браузер). Подпись cookie для Starlette SessionMiddleware.
    session_secret: str | None = Field(default=None, validation_alias=AliasChoices("SESSION_SECRET", "APP_SESSION_SECRET"))
    # Учётка admin из env (полный доступ). Пароль сравнивается через secrets.compare_digest.
    admin_login: str | None = Field(default=None, validation_alias=AliasChoices("ADMIN_LOGIN", "APP_ADMIN_LOGIN"))
    admin_password: str | None = Field(default=None, validation_alias=AliasChoices("ADMIN_PASSWORD", "APP_ADMIN_PASSWORD"))
    # DEMO: только при demo_enabled=true и заданных логине/пароле.
    demo_enabled: bool = Field(default=False, validation_alias=AliasChoices("DEMO_ENABLED", "APP_DEMO_ENABLED"))
    demo_login: str | None = Field(default=None, validation_alias=AliasChoices("DEMO_LOGIN", "APP_DEMO_LOGIN"))
    demo_password: str | None = Field(default=None, validation_alias=AliasChoices("DEMO_PASSWORD", "APP_DEMO_PASSWORD"))


def get_settings() -> Settings:
    return Settings()


def polza_allowlist_ids(settings: Settings) -> set[str]:
    """Разрешённые идентификаторы модели; пустое множество — проверка allowlist не применяется."""
    raw = settings.polza_chat_model_allowlist
    if not raw or not raw.strip():
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_session_login_configured(settings: Settings) -> bool:
    """True, если заданы секрет сессии и пара admin login/password для POST /v1/auth/login."""
    sec = (settings.session_secret or "").strip()
    al = (settings.admin_login or "").strip()
    ap = settings.admin_password
    return bool(sec and al and ap is not None and str(ap) != "")


def is_auth_required(settings: Settings) -> bool:
    """Ключи API и/или сессионный вход — иначе dev-режим без проверки."""
    keys = bool(
        settings.app_api_key or settings.app_admin_key or settings.app_member_key
    )
    return keys or is_session_login_configured(settings)


def is_polza_model_allowlisted(settings: Settings) -> bool:
    """True, если модель разрешена или allowlist не задан."""
    allowed = polza_allowlist_ids(settings)
    if not allowed:
        return True
    return settings.polza_chat_model in allowed
