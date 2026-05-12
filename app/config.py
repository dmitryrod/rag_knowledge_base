"""Runtime configuration from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_env_files() -> tuple[str, ...]:
    """По умолчанию загружаются `app/.env`, затем `.env` (корень перекрывает шаблон)."""
    v = os.getenv("KNOWLEDGE_TESTS_NO_DOTENV", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return ()
    return ("app/.env", ".env")


class Settings(BaseSettings):
    """Application settings; loads from `app/.env` and then root `.env`."""

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

    # Ingest/RAG лимиты — только из окружения (см. `app/.env`); в тестах — setdefault в `app/tests/conftest.py`.
    chunk_size: int = Field(validation_alias=AliasChoices("CHUNK_SIZE"))
    chunk_overlap: int = Field(validation_alias=AliasChoices("CHUNK_OVERLAP"))
    max_upload_mb: int = Field(validation_alias=AliasChoices("MAX_UPLOAD_MB"))
    retrieval_top_k: int = Field(validation_alias=AliasChoices("RETRIEVAL_TOP_K"))
    # Если false — даже при X-Debug: 1 в ответ не отдаётся traceback (только серверные логи)
    allow_client_debug: bool = Field(
        default=False,
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
    # DEMO читает чужой каталог tenants/<id>/ (разделы/документы остаются read-only из-за site_role=demo).
    # Приоритет: tenant_id ниже, затем share-токен из registry; иначе пустой env_demo.
    demo_workspace_tenant_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEMO_WORKSPACE_TENANT_ID", "APP_DEMO_WORKSPACE_TENANT_ID"),
    )
    demo_workspace_share_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DEMO_WORKSPACE_SHARE_TOKEN",
            "APP_DEMO_WORKSPACE_SHARE_TOKEN",
        ),
    )

    # --- Reverse proxy (Traefik / nginx): клиентский IP и заголовки перехода ---
    trust_proxy_headers: bool = Field(
        default=False,
        validation_alias=AliasChoices("TRUST_PROXY_HEADERS", "APP_TRUST_PROXY_HEADERS"),
    )
    trust_proxy_hosts: str = Field(
        default="*",
        validation_alias=AliasChoices("TRUST_PROXY_HOSTS", "APP_TRUST_PROXY_HOSTS"),
    )

    # Cookie сессии: флаг Secure (только HTTPS). За TLS-терминатором задайте SESSION_COOKIE_HTTPS_ONLY=true.
    session_cookie_https_only: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "SESSION_COOKIE_HTTPS_ONLY",
            "SESSION_COOKIE_SECURE",
        ),
    )

    # OpenAPI / Swagger / ReDoc. true — отключить все три (в проде часто выключают или закрывают Basic).
    app_openapi_disabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("APP_OPENAPI_DISABLED", "APP_DOCS_DISABLED"),
    )
    app_docs_basic_auth_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_DOCS_BASIC_AUTH_USER", "DOCS_BASIC_AUTH_USER"),
    )
    app_docs_basic_auth_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_DOCS_BASIC_AUTH_PASSWORD", "DOCS_BASIC_AUTH_PASSWORD"),
    )

    # Лимиты (in-memory, один процесс). max=0 — выключено.
    rate_limit_auth_login_max: int = Field(
        default=0,
        ge=0,
        le=100_000,
        validation_alias=AliasChoices("RATE_LIMIT_AUTH_LOGIN_MAX"),
    )
    rate_limit_auth_login_window_sec: int = Field(
        default=900,
        ge=5,
        le=86_400,
        validation_alias=AliasChoices("RATE_LIMIT_AUTH_LOGIN_WINDOW_SEC"),
    )
    rate_limit_v1_post_max: int = Field(
        default=0,
        ge=0,
        le=1_000_000,
        validation_alias=AliasChoices("RATE_LIMIT_V1_POST_MAX"),
    )
    rate_limit_v1_post_window_sec: int = Field(
        default=60,
        ge=1,
        le=3600,
        validation_alias=AliasChoices("RATE_LIMIT_V1_POST_WINDOW_SEC"),
    )

    # Минимальный интервал между исходящими вызовами LLM (мс) для одного субъекта auth. 0 — без лимита.
    # Пример: 1000 ≈ не чаще 1 раза/сек; 60000 ≈ раз в минуту.
    llm_min_interval_ms: int = Field(
        default=0,
        ge=0,
        le=3_600_000,
        validation_alias=AliasChoices("LLM_MIN_INTERVAL_MS"),
    )


def get_settings() -> Settings:
    return Settings()


def polza_allowlist_ids(settings: Settings) -> set[str]:
    """Разрешённые идентификаторы модели; пустое множество — проверка allowlist не применяется."""
    raw = settings.polza_chat_model_allowlist
    if not raw or not raw.strip():
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_session_login_configured(settings: Settings) -> bool:
    """True, если browser session login реально включён: есть SESSION_SECRET и env-учётка для входа."""
    sec = (settings.session_secret or "").strip()
    return bool(sec and has_session_credentials(settings))


def has_session_credentials(settings: Settings) -> bool:
    """True, если заданы env-учётки, которые делают auth обязательной даже без SESSION_SECRET."""
    al = (settings.admin_login or "").strip()
    ap = settings.admin_password
    demo_login = (settings.demo_login or "").strip()
    demo_password = settings.demo_password
    has_admin = bool(al and ap is not None and str(ap) != "")
    has_demo = bool(
        settings.demo_enabled
        and demo_login
        and demo_password is not None
        and str(demo_password) != ""
    )
    return bool(has_admin or has_demo)


def is_auth_required(settings: Settings) -> bool:
    """Требовать auth, если заданы API-ключи или env-учётки для session login."""
    keys = bool(
        settings.app_api_key or settings.app_admin_key or settings.app_member_key
    )
    return keys or has_session_credentials(settings)


def is_polza_model_allowlisted(settings: Settings) -> bool:
    """True, если модель разрешена или allowlist не задан."""
    allowed = polza_allowlist_ids(settings)
    if not allowed:
        return True
    return settings.polza_chat_model in allowed
