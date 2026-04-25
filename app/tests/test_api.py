"""API tests with isolated data dir."""

from __future__ import annotations

import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    """Lifespan (init_stores) runs only when TestClient is used as context manager."""
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    # Изоляция от локального app/.env: иначе POLZA + ALLOW_LLM_EGRESS дают реальный HTTP к LLM и таймауты в CI.
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "false")
    monkeypatch.setenv("POLZA_API_KEY", "")
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def client_rbac(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_ADMIN_KEY", "adm-secret")
    monkeypatch.setenv("APP_MEMBER_KEY", "mem-secret")
    monkeypatch.delenv("APP_API_KEY", raising=False)
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


def test_root_serves_admin_ui(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "")
    assert "Knowledge" in r.text
    assert "Документы" in r.text
    assert "Тесты" in r.text
    assert "view-chat" in r.text
    assert "view-tests" in r.text
    assert 'id="testScopeMount"' in r.text
    assert 'id="profileFormA"' in r.text
    assert "Источники для теста" in r.text
    assert "Тесты RAG" in r.text
    assert 'id="testRunLoader"' in r.text
    assert 'id="testActionStatus"' in r.text
    assert "setTestActionStatus" in r.text
    assert "setTestRunLoading" in r.text
    assert 'id="btnApplyProfileA"' in r.text
    assert 'id="btnApplyProfileB"' in r.text
    assert "applyTestProfileToChat" in r.text
    assert "retrieval_top_k" in r.text
    assert 'title="Сколько top chunks' in r.text
    assert 'id="chat-thread-list"' in r.text
    assert 'id="message-composer"' in r.text
    assert "window.__API_BASE__" in r.text
    assert "function apiPath" in r.text


def test_cors_allows_preflight_for_health(client: TestClient) -> None:
    r = client.options(
        "/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    aco = r.headers.get("access-control-allow-origin") or r.headers.get(
        "Access-Control-Allow-Origin"
    )
    assert aco in ("*", "http://localhost:3000")


def test_health(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.4.0"
    assert "auth_configured" in body
    assert body["auth_configured"] is False


def test_health_auth_configured_when_keys_set(client_rbac: TestClient) -> None:
    r = client_rbac.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["auth_configured"] is True


def test_collection_document_chat_flow(client: TestClient) -> None:
    r = client.post("/v1/collections", json={"name": "demo"})
    assert r.status_code == 200
    cid = r.json()["id"]

    raw = "Правило один: все секреты только в env.\nПравило два: цитаты обязательны.".encode(
        "utf-8"
    )
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("rules.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200

    chat = client.post(
        f"/v1/collections/{cid}/chat",
        json={"message": "Какие правила в документе?"},
    )
    assert chat.status_code == 200
    data = chat.json()
    assert "answer" in data
    assert "citations" in data
    assert isinstance(data["citations"], list)
    assert len(data["citations"]) >= 1


def test_chat_returns_502_when_llm_upstream_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сеть/DNS до Polza: LlmUpstreamError -> 502, не голый 500."""
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    monkeypatch.setenv("POLZA_API_KEY", "k")
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "true")
    monkeypatch.setenv("POLZA_BASE_URL", "https://polza.ai/api/v1")
    from importlib import reload

    import app.config
    import app.llm
    import app.routers.api
    import app.main

    reload(app.config)
    reload(app.llm)
    reload(app.routers.api)
    reload(app.main)

    def _boom(
        _settings: object,
        _messages: list[dict[str, str]],
    ) -> str:
        raise app.llm.LlmUpstreamError("upstream test", host="polza.ai", status_code=502)

    monkeypatch.setattr("app.llm.chat_completion", _boom)
    from app.main import create_app

    with TestClient(create_app()) as client:
        r = client.post("/v1/collections", json={"name": "u"})
        cid = r.json()["id"]
        up = client.post(
            f"/v1/collections/{cid}/documents",
            files={"file": ("u.txt", io.BytesIO(b"hello dns."), "text/plain")},
        )
        assert up.status_code == 200
        chat = client.post(
            f"/v1/collections/{cid}/chat",
            json={"message": "q?"},
        )
    assert chat.status_code == 502
    assert chat.json()["detail"] == "upstream test"


def test_chat_threads_flow(client: TestClient) -> None:
    r = client.post("/v1/collections", json={"name": "chat-threads"})
    assert r.status_code == 200
    cid = r.json()["id"]

    raw = b"Thread rule: alpha beta."
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("t.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200

    tr = client.post("/v1/chat/threads", json={"collection_id": cid, "title": "T1"})
    assert tr.status_code == 200
    tid = tr.json()["id"]
    assert tr.json()["collection_id"] == cid

    lst = client.get("/v1/chat/threads", params={"collection_id": cid})
    assert lst.status_code == 200
    assert len(lst.json()) >= 1
    assert any(t["id"] == tid for t in lst.json())

    msg = client.post(
        f"/v1/chat/threads/{tid}/messages",
        json={"message": "What is the thread rule?"},
    )
    assert msg.status_code == 200
    assert "answer" in msg.json()
    assert len(msg.json().get("citations", [])) >= 1

    hist = client.get(f"/v1/chat/threads/{tid}/messages")
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[1]["role"] == "assistant"

    ren = client.patch(
        f"/v1/chat/threads/{tid}",
        json={"title": "Renamed"},
    )
    assert ren.status_code == 200
    assert ren.json()["title"] == "Renamed"

    dl = client.delete(f"/v1/chat/threads/{tid}")
    assert dl.status_code == 200
    gone = client.get(f"/v1/chat/threads/{tid}/messages")
    assert gone.status_code == 404


def test_member_can_chat_threads(client_rbac: TestClient) -> None:
    r = client_rbac.post(
        "/v1/collections",
        json={"name": "mem-col"},
        headers={"X-API-Key": "adm-secret"},
    )
    cid = r.json()["id"]
    client_rbac.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("x.txt", io.BytesIO(b"member thread doc."), "text/plain")},
        headers={"X-API-Key": "adm-secret"},
    )
    tr = client_rbac.post(
        "/v1/chat/threads",
        json={"collection_id": cid},
        headers={"X-API-Key": "mem-secret"},
    )
    assert tr.status_code == 200
    tid = tr.json()["id"]
    chat = client_rbac.post(
        f"/v1/chat/threads/{tid}/messages",
        json={"message": "What is in the doc?"},
        headers={"X-API-Key": "mem-secret"},
    )
    assert chat.status_code == 200
    assert len(chat.json().get("citations", [])) >= 1


def test_chat_export_markdown(client: TestClient) -> None:
    r = client.post("/v1/collections", json={"name": "ex"})
    cid = r.json()["id"]
    raw = b"Fact alpha in export test."
    client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("a.txt", io.BytesIO(raw), "text/plain")},
    )
    ex = client.post(
        f"/v1/collections/{cid}/chat/export?format=markdown",
        json={"message": "What is Fact alpha?"},
    )
    assert ex.status_code == 200
    text = ex.text
    assert "## Ответ" in text
    assert "## Цитаты" in text


def test_member_forbidden_create_collection(client_rbac: TestClient) -> None:
    r = client_rbac.post(
        "/v1/collections",
        json={"name": "x"},
        headers={"X-API-Key": "mem-secret"},
    )
    assert r.status_code == 403


def test_admin_creates_collection(client_rbac: TestClient) -> None:
    r = client_rbac.post(
        "/v1/collections",
        json={"name": "admin-col"},
        headers={"X-API-Key": "adm-secret"},
    )
    assert r.status_code == 200
    cid = r.json()["id"]

    raw = b"member may read and chat."
    up = client_rbac.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("m.txt", io.BytesIO(raw), "text/plain")},
        headers={"X-API-Key": "adm-secret"},
    )
    assert up.status_code == 200

    chat = client_rbac.post(
        f"/v1/collections/{cid}/chat",
        json={"message": "Что в документе?"},
        headers={"X-API-Key": "mem-secret"},
    )
    assert chat.status_code == 200
    assert len(chat.json().get("citations", [])) >= 1

    aud = client_rbac.get("/v1/audit", headers={"X-API-Key": "mem-secret"})
    assert aud.status_code == 403


def test_polza_allowlist_blocks_chat(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("POLZA_API_KEY", "fake-for-config")
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "true")
    monkeypatch.setenv("POLZA_CHAT_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("POLZA_CHAT_MODEL_ALLOWLIST", "other/model")

    from importlib import reload

    import app.config
    import app.main

    reload(app.config)
    reload(app.main)
    from app.main import create_app

    with TestClient(create_app()) as client:
        r = client.post("/v1/collections", json={"name": "z"})
        cid = r.json()["id"]
        chat = client.post(
            f"/v1/collections/{cid}/chat",
            json={"message": "hi"},
        )
        assert chat.status_code == 400
        assert "ALLOWLIST" in chat.json().get("detail", "").upper() or "allowlist" in (
            chat.json().get("detail") or ""
        ).lower()


def test_knowledge_tree_nested_and_empty_section(client: TestClient) -> None:
    r0 = client.post("/v1/collections", json={"name": "tree-root"})
    assert r0.status_code == 200
    root_id = r0.json()["id"]
    assert r0.json().get("parent_id") in (None, "")

    r1 = client.post(
        "/v1/collections",
        json={"name": "tree-sub", "parent_id": root_id},
    )
    assert r1.status_code == 200
    sub_id = r1.json()["id"]
    assert r1.json()["parent_id"] == root_id

    client.post("/v1/collections", json={"name": "empty-leaf", "parent_id": sub_id})

    raw = b"doc in subfolder."
    up = client.post(
        f"/v1/collections/{sub_id}/documents",
        files={"file": ("nest.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200

    tr = client.get("/v1/collections/tree")
    assert tr.status_code == 200
    tree = tr.json()
    assert isinstance(tree, list)
    root = next(t for t in tree if t["id"] == root_id)
    assert root["type"] == "section"
    sub = next(c for c in root["children"] if c["id"] == sub_id)
    assert sub["type"] == "section"
    assert any(d["name"] == "nest.txt" for d in sub["documents"])
    assert any(c["name"] == "empty-leaf" for c in sub["children"])
    empty = next(c for c in sub["children"] if c["name"] == "empty-leaf")
    assert empty["documents"] == []


def test_knowledge_stats(client: TestClient) -> None:
    r = client.get("/v1/knowledge/stats")
    assert r.status_code == 200
    s = r.json()
    for k in (
        "sections_count",
        "documents_count",
        "chunks_count",
        "embedding_vectors_count",
        "document_files_size_bytes",
        "metadata_db_size_bytes",
        "chroma_storage_size_bytes",
        "data_dir_size_bytes",
        "chat_threads_count",
        "chat_messages_count",
        "audit_log_rows",
    ):
        assert k in s
    assert isinstance(s["chunks_count"], int)


def test_patch_collection_and_document(client: TestClient) -> None:
    r = client.post("/v1/collections", json={"name": "pre-name"})
    cid = r.json()["id"]
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("orig.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert up.status_code == 200
    did = up.json()["id"]

    pr = client.patch(
        f"/v1/collections/{cid}",
        json={"name": "post-name"},
    )
    assert pr.status_code == 200
    assert pr.json()["name"] == "post-name"

    dr = client.patch(
        f"/v1/collections/{cid}/documents/{did}",
        json={"filename": "renamed.txt"},
    )
    assert dr.status_code == 200
    assert dr.json()["filename"] == "renamed.txt"


def test_patch_collection_cycle_returns_400(client: TestClient) -> None:
    a = client.post("/v1/collections", json={"name": "a"}).json()["id"]
    b = client.post(
        "/v1/collections",
        json={"name": "b", "parent_id": a},
    ).json()["id"]
    r = client.patch(f"/v1/collections/{a}", json={"parent_id": b})
    assert r.status_code == 400
    assert "cycle" in (r.json().get("detail") or "").lower()


def test_delete_collection_recursive_subtree(client: TestClient) -> None:
    root = client.post("/v1/collections", json={"name": "del-root"}).json()["id"]
    ch = client.post(
        "/v1/collections",
        json={"name": "del-ch", "parent_id": root},
    ).json()["id"]
    d = client.delete(f"/v1/collections/{root}")
    assert d.status_code == 200
    lst = client.get("/v1/collections").json()
    ids = {x["id"] for x in lst}
    assert root not in ids
    assert ch not in ids


def test_member_can_read_tree_and_stats(client_rbac: TestClient) -> None:
    t = client_rbac.get(
        "/v1/collections/tree",
        headers={"X-API-Key": "mem-secret"},
    )
    assert t.status_code == 200
    s = client_rbac.get(
        "/v1/knowledge/stats",
        headers={"X-API-Key": "mem-secret"},
    )
    assert s.status_code == 200


def test_member_forbidden_patch_section(client_rbac: TestClient) -> None:
    r = client_rbac.post(
        "/v1/collections",
        json={"name": "mp"},
        headers={"X-API-Key": "adm-secret"},
    )
    cid = r.json()["id"]
    p = client_rbac.patch(
        f"/v1/collections/{cid}",
        json={"name": "nope"},
        headers={"X-API-Key": "mem-secret"},
    )
    assert p.status_code == 403


def test_move_document_between_sections_tree_and_chroma(client: TestClient) -> None:
    from app import deps

    a = client.post("/v1/collections", json={"name": "move-a"}).json()["id"]
    b = client.post("/v1/collections", json={"name": "move-b"}).json()["id"]
    raw = b"chunkable text " * 40
    up = client.post(
        f"/v1/collections/{a}/documents",
        files={"file": ("m.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200
    did = up.json()["id"]
    store = deps.get_chroma()
    n_before = store.count_chunks_for_document(a, did)
    assert n_before >= 1
    assert store.count_chunks_for_document(b, did) == 0

    mv = client.post(
        f"/v1/collections/{b}/documents/{did}/move",
        json={"source_collection_id": a},
    )
    assert mv.status_code == 200
    assert mv.json()["collection_id"] == b

    assert store.count_chunks_for_document(a, did) == 0
    assert store.count_chunks_for_document(b, did) == n_before

    tr = client.get("/v1/collections/tree")
    assert tr.status_code == 200

    def find_doc_ids(node: dict) -> set[str]:
        out = {d["id"] for d in node.get("documents", [])}
        for ch in node.get("children", []) or []:
            out |= find_doc_ids(ch)
        return out

    under_a = under_b = False
    for root in tr.json():
        if root["id"] == a:
            under_a = did in find_doc_ids(root)
        if root["id"] == b:
            under_b = did in find_doc_ids(root)
    assert not under_a
    assert under_b


def test_move_document_noop_same_collection(client: TestClient) -> None:
    cid = client.post("/v1/collections", json={"name": "same"}).json()["id"]
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("s.txt", io.BytesIO(b"same"), "text/plain")},
    )
    assert up.status_code == 200
    did = up.json()["id"]
    mv = client.post(
        f"/v1/collections/{cid}/documents/{did}/move",
        json={"source_collection_id": cid},
    )
    assert mv.status_code == 200
    assert mv.json()["collection_id"] == cid


def test_move_document_404(client: TestClient) -> None:
    a = client.post("/v1/collections", json={"name": "x"}).json()["id"]
    b = client.post("/v1/collections", json={"name": "y"}).json()["id"]
    bad = "00000000-0000-0000-0000-000000000099"
    r = client.post(
        f"/v1/collections/{b}/documents/{bad}/move",
        json={"source_collection_id": a},
    )
    assert r.status_code == 404
    up = client.post(
        f"/v1/collections/{a}/documents",
        files={"file": ("z.txt", io.BytesIO(b"z"), "text/plain")},
    )
    did = up.json()["id"]
    r2 = client.post(
        f"/v1/collections/{b}/documents/{did}/move",
        json={"source_collection_id": bad},
    )
    assert r2.status_code == 404
    r3 = client.post(
        f"/v1/collections/{bad}/documents/{did}/move",
        json={"source_collection_id": a},
    )
    assert r3.status_code == 404


def test_member_forbidden_move_document(client_rbac: TestClient) -> None:
    a = client_rbac.post(
        "/v1/collections",
        json={"name": "ma"},
        headers={"X-API-Key": "adm-secret"},
    ).json()["id"]
    b = client_rbac.post(
        "/v1/collections",
        json={"name": "mb"},
        headers={"X-API-Key": "adm-secret"},
    ).json()["id"]
    up = client_rbac.post(
        f"/v1/collections/{a}/documents",
        files={"file": ("t.txt", io.BytesIO(b"move me"), "text/plain")},
        headers={"X-API-Key": "adm-secret"},
    )
    assert up.status_code == 200
    did = up.json()["id"]
    mv = client_rbac.post(
        f"/v1/collections/{b}/documents/{did}/move",
        json={"source_collection_id": a},
        headers={"X-API-Key": "mem-secret"},
    )
    assert mv.status_code == 403
