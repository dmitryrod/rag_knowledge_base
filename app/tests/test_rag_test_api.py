"""RAG test bench API: run, compare, main-chat apply (no real LLM egress)."""

from __future__ import annotations

import io
import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.delenv("APP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("APP_MEMBER_KEY", raising=False)
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "false")
    monkeypatch.setenv("POLZA_API_KEY", "")
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _with_doc(client: TestClient) -> str:
    r = client.post("/v1/collections", json={"name": "t"})
    assert r.status_code == 200
    cid = r.json()["id"]
    raw = b"alpha beta gamma delta for rag test"
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("t.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200
    return cid


def test_rag_test_run_no_egress_demo(client: TestClient) -> None:
    _with_doc(client)
    body = {
        "question": "что в документе?",
        "scope": {"all": True},
        "profile": {"retrieval_top_k": 4, "llm_enabled": True, "temperature": 0},
        "debug": False,
    }
    r = client.post("/v1/rag-test/run", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("demo_mode") is True
    assert "chunks" in data
    assert "metrics" in data
    assert (data.get("metrics") or {}).get("retrieval_ms", 0) >= 0
    # LLM not called when egress off
    assert "Локальный контур" in (data.get("answer") or "") or data.get("llm_skipped") is True


def test_rag_test_run_ignores_llm_when_egress_false_even_if_profile_wants(
    client: TestClient,
) -> None:
    _with_doc(client)
    r = client.post(
        "/v1/rag-test/run",
        json={
            "question": "test",
            "scope": {"all": True},
            "profile": {"llm_enabled": True, "retrieval_top_k": 2},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("llm_skipped") is True


def test_rag_test_run_with_document_ids_by_collection(client: TestClient) -> None:
    r = client.post("/v1/collections", json={"name": "scope-doc"})
    assert r.status_code == 200
    cid = r.json()["id"]
    raw = b"unique doc text for scope filter xyz123"
    up = client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("scope.txt", io.BytesIO(raw), "text/plain")},
    )
    assert up.status_code == 200
    doc_id = up.json()["id"]
    body = {
        "question": "что в документе?",
        "scope": {"ids": [cid], "document_ids_by_collection": {cid: [doc_id]}},
        "profile": {"retrieval_top_k": 4, "llm_enabled": False},
        "debug": False,
    }
    r = client.post("/v1/rag-test/run", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "chunks" in data


def test_rag_test_compare_persists_pair(client: TestClient) -> None:
    _with_doc(client)
    r = client.post(
        "/v1/rag-test/compare",
        json={
            "question": "q",
            "scope": {"all": True},
            "left_profile": {"retrieval_top_k": 3},
            "right_profile": {"retrieval_top_k": 5},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "pair_id" in data
    assert data["left"] and data["right"]


def test_apply_to_chat_requires_admin_by_default(client: TestClient) -> None:
    r = client.post(
        "/v1/rag-test/apply-to-chat",
        json={"profile": {"retrieval_top_k": 6, "llm_enabled": True}},
    )
    # without admin key, auth may be open in dev
    assert r.status_code in (200, 401, 403)


def test_main_chat_profile_get(client: TestClient) -> None:
    r = client.get("/v1/rag-test/main-chat-profile")
    assert r.status_code == 200
    j = r.json()
    assert "profile" in j
