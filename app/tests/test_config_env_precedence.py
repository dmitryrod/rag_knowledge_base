from __future__ import annotations

from importlib import reload
from pathlib import Path


def test_root_dotenv_overrides_empty_auth_values_from_app_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / ".env").write_text(
        "\n".join(
            [
                "SESSION_SECRET=",
                "ADMIN_LOGIN=",
                "ADMIN_PASSWORD=",
                "CHUNK_SIZE=800",
                "CHUNK_OVERLAP=120",
                "MAX_UPLOAD_MB=10",
                "RETRIEVAL_TOP_K=8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "SESSION_SECRET=root-secret",
                "ADMIN_LOGIN=root-admin",
                "ADMIN_PASSWORD=root-pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KNOWLEDGE_TESTS_NO_DOTENV", "0")
    for key in (
        "SESSION_SECRET",
        "APP_SESSION_SECRET",
        "ADMIN_LOGIN",
        "APP_ADMIN_LOGIN",
        "ADMIN_PASSWORD",
        "APP_ADMIN_PASSWORD",
        "CHUNK_SIZE",
        "CHUNK_OVERLAP",
        "MAX_UPLOAD_MB",
        "RETRIEVAL_TOP_K",
    ):
        monkeypatch.delenv(key, raising=False)

    import app.config

    reload(app.config)
    from app.auth_dep import is_auth_configured, is_session_login_configured
    from app.config import Settings

    settings = Settings()

    assert settings.session_secret == "root-secret"
    assert settings.admin_login == "root-admin"
    assert settings.admin_password == "root-pass"
    assert is_auth_configured(settings) is True
    assert is_session_login_configured(settings) is True
