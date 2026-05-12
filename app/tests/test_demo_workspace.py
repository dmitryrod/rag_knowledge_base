"""DEMO shadow workspace: разрешение tenant каталога и интеграция с API."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_LOGIN", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "demopass")
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "false")
    monkeypatch.setenv("POLZA_API_KEY", "")
    monkeypatch.delenv("DEMO_WORKSPACE_TENANT_ID", raising=False)
    monkeypatch.delenv("DEMO_WORKSPACE_SHARE_TOKEN", raising=False)
    from importlib import reload

    import app.config
    import app.main

    reload(app.config)
    reload(app.main)
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_resolve_demo_prefers_tenant_id_over_share_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_TESTS_NO_DOTENV", "1")
    from importlib import reload

    import app.config

    reload(app.config)
    from app.config import Settings
    from app.demo_workspace import resolve_demo_storage_tenant_id
    from app.registry_db import RegistryDB

    monkeypatch.setenv("DEMO_WORKSPACE_TENANT_ID", "env_admin")
    monkeypatch.setenv("DEMO_WORKSPACE_SHARE_TOKEN", "ignored")
    reload(app.config)
    settings = Settings()
    reg = RegistryDB(tmp_path / "reg.db")
    reg.create_share_link("other-tenant", "root-id", "ignored")
    assert resolve_demo_storage_tenant_id(settings, reg) == "env_admin"


def test_resolve_demo_share_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_TESTS_NO_DOTENV", "1")
    from importlib import reload

    import app.config

    reload(app.config)
    from app.config import Settings
    from app.demo_workspace import resolve_demo_storage_tenant_id
    from app.registry_db import RegistryDB

    reg = RegistryDB(tmp_path / "reg.db")
    tok = "demo-share-secret"
    reg.create_share_link("issuer-tid-xyz", "coll-root", tok)
    monkeypatch.setenv("DEMO_WORKSPACE_SHARE_TOKEN", tok)
    reload(app.config)
    settings = Settings()
    assert resolve_demo_storage_tenant_id(settings, reg) == "issuer-tid-xyz"


def test_resolve_demo_invalid_share_token_falls_back_to_env_demo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("KNOWLEDGE_TESTS_NO_DOTENV", "1")
    from importlib import reload

    import app.config

    reload(app.config)
    from app.config import Settings
    from app.demo_workspace import resolve_demo_storage_tenant_id
    from app.registry_db import RegistryDB
    from app.tenancy import TENANT_ENV_DEMO

    monkeypatch.setenv("DEMO_WORKSPACE_SHARE_TOKEN", "wrong")
    reload(app.config)
    settings = Settings()
    reg = RegistryDB(tmp_path / "reg.db")
    with caplog.at_level("WARNING"):
        assert resolve_demo_storage_tenant_id(settings, reg) == TENANT_ENV_DEMO
    assert "DEMO_WORKSPACE_SHARE_TOKEN" in caplog.text


def test_demo_without_shadow_sees_empty_collections(client_demo: TestClient) -> None:
    assert client_demo.post("/v1/auth/login", json={"username": "demo", "password": "demopass"}).status_code == 200
    me = client_demo.get("/v1/auth/me").json()
    assert me["tenant_id"] == "env_demo"
    assert me.get("demo_workspace_storage_tenant_id") is None
    assert client_demo.get("/v1/collections").json() == []


def test_demo_shadow_env_admin_sees_admin_collections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Пересоздаём приложение с DEMO_WORKSPACE_TENANT_ID=env_admin."""
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_LOGIN", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "demopass")
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "false")
    monkeypatch.setenv("POLZA_API_KEY", "")
    monkeypatch.setenv("DEMO_WORKSPACE_TENANT_ID", "env_admin")
    from importlib import reload

    import app.config
    import app.main

    reload(app.config)
    reload(app.main)
    from app.main import create_app

    with TestClient(create_app()) as c:
        assert c.post("/v1/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        assert c.post("/v1/collections", json={"name": "kb-for-demo"}).status_code == 200
        assert c.post("/v1/auth/logout", json={}).status_code == 200
        assert c.post("/v1/auth/login", json={"username": "demo", "password": "demopass"}).status_code == 200
        me = c.get("/v1/auth/me").json()
        assert me["tenant_id"] == "env_demo"
        assert me.get("demo_workspace_storage_tenant_id") == "env_admin"
        rows = c.get("/v1/collections").json()
        assert len(rows) == 1
        assert rows[0]["name"] == "kb-for-demo"
        blocked = c.post("/v1/collections", json={"name": "no-write"})
        assert blocked.status_code == 403
