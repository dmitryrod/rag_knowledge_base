"""Сессионный вход, /auth/me и multi-tenant data layout."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "false")
    monkeypatch.setenv("POLZA_API_KEY", "")
    from importlib import reload

    import app.config
    import app.main

    reload(app.config)
    reload(app.main)
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health_session_login_configured(client_session: TestClient) -> None:
    r = client_session.get("/v1/health")
    assert r.status_code == 200
    j = r.json()
    assert j["session_login_configured"] is True
    assert j["auth_configured"] is True


def test_auth_login_me_flow(client_session: TestClient) -> None:
    r = client_session.post("/v1/auth/login", json={"username": "admin", "password": "adminpass"})
    assert r.status_code == 200, r.text
    m = client_session.get("/v1/auth/me")
    assert m.status_code == 200
    body = m.json()
    assert body["tenant_id"] == "env_admin"
    assert body["site_role"] == "admin"
    assert body["subject"] == "env_admin"
    assert body["display_login"] == "admin"
    assert body["can_manage_users"] is True


def test_registry_user_me_display_login(client_session: TestClient) -> None:
    """Созданный admin пользователь: /me даёт display_login=username, свой tenant."""
    assert client_session.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "adminpass"},
    ).status_code == 200
    u = "member_test_user"
    created = client_session.post(
        "/v1/admin/users",
        json={"username": u, "password": "secret123", "site_role": "member"},
    )
    assert created.status_code == 201, created.text
    tenant = created.json()["tenant_id"]
    assert client_session.post("/v1/auth/logout", json={}).status_code == 200
    lg = client_session.post("/v1/auth/login", json={"username": u, "password": "secret123"})
    assert lg.status_code == 200, lg.text
    me = client_session.get("/v1/auth/me").json()
    assert me["tenant_id"] == tenant
    assert me["display_login"] == u
    assert me["subject"] != u
    assert len(me["subject"]) == 36


def test_tenant_data_paths_after_init(client_session: TestClient) -> None:
    """После init_stores существуют каталоги tenants/env_admin и registry."""
    client_session.post("/v1/auth/login", json={"username": "admin", "password": "adminpass"})
    from app.config import get_settings

    data = Path(get_settings().data_dir)
    assert (data / "tenants" / "env_admin" / "metadata.db").is_file()
    assert (data / "registry.db").is_file()
