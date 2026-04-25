"""RAG test bench API: profiles, run, compare, main-chat apply, benchmarks, index jobs (v2)."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth_dep import get_auth, require_admin
from app import deps
from app.config import Settings, get_settings
from app.db_sqlite import MetadataDB
from app.rag_profile import ProfileKind, RagRuntimeProfile, RagScopeIn
from app.rag_runtime import MainChatRuntimeSnapshot, validate_main_chat_apply
from app.chroma_user_errors import http_detail_for_chroma_or_embedding_network_error
from app.rag_test_service import run_rag_test

_log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_auth)])


# --- Pydantic I/O ---


class TestProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    kind: ProfileKind = "runtime"
    profile: dict[str, Any] = Field(..., description="RagRuntimeProfile as JSON")
    is_default: bool = False


class TestProfileOut(BaseModel):
    id: str
    name: str
    kind: str
    profile: dict[str, Any]
    is_default: bool
    created_at: str
    updated_at: str
    applied_to_chat_at: str | None = None
    created_by: str | None = None


class TestRunIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=32000)
    scope: dict[str, Any] = Field(
        default_factory=lambda: {"all": True},
        description='{"all": true} or {"ids": [...], "document_ids_by_collection": {...}}',
    )
    profile: dict[str, Any] | None = None
    profile_id: str | None = None
    debug: bool = False

    @staticmethod
    def scope_model(scope: dict[str, Any]) -> RagScopeIn:
        return RagScopeIn.model_validate(scope)

    @staticmethod
    def profile_model(data: dict[str, Any]) -> RagRuntimeProfile:
        return RagRuntimeProfile.model_validate(data)


class TestCompareIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=32000)
    scope: dict[str, Any] = Field(default_factory=lambda: {"all": True})
    left_profile: dict[str, Any]
    right_profile: dict[str, Any]
    debug: bool = False


class ApplyToChatIn(BaseModel):
    profile: dict[str, Any] = Field(..., description="MainChatRuntimeSnapshot / RagRuntimeProfile safe subset")


# --- helpers ---


def _profile_row_to_out(row: dict[str, Any]) -> TestProfileOut:
    return TestProfileOut(
        id=str(row["id"]),
        name=str(row["name"]),
        kind=str(row["kind"]),
        profile=json.loads(str(row["profile_json"] or "{}")),
        is_default=bool(row.get("is_default")),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        applied_to_chat_at=str(row["applied_to_chat_at"]) if row.get("applied_to_chat_at") else None,
        created_by=str(row["created_by"]) if row.get("created_by") else None,
    )


def _serialize_chunks_for_db(chunks: list[dict[str, Any]], max_text: int = 2000) -> str:
    slim: list[dict[str, Any]] = []
    for ch in chunks:
        meta = ch.get("metadata") or {}
        t = ch.get("text") or ""
        if len(t) > max_text:
            t = t[:max_text] + "…"
        slim.append(
            {
                "chunk_id": ch.get("chunk_id"),
                "text": t,
                "metadata": meta,
                "distance": ch.get("distance"),
                "source_collection_id": ch.get("source_collection_id"),
            }
        )
    return json.dumps(slim, ensure_ascii=False)


# --- routes ---


@router.get("/rag-test/profiles", response_model=list[TestProfileOut])
def list_test_profiles(
    kind: str | None = Query(default=None, description="runtime | index"),
) -> list[TestProfileOut]:
    db = deps.get_db()
    rows = db.list_rag_test_profiles(kind=kind)
    return [_profile_row_to_out(r) for r in rows]


@router.post("/rag-test/profiles", response_model=TestProfileOut, dependencies=[Depends(require_admin)])
def create_test_profile(
    body: TestProfileCreate,
    _settings: Settings = Depends(get_settings),
) -> TestProfileOut:
    RagRuntimeProfile.model_validate(body.profile) if body.kind == "runtime" else body.profile
    pid = str(uuid4())
    db = deps.get_db()
    db.insert_rag_test_profile(
        pid,
        body.name,
        body.kind,
        json.dumps(body.profile, ensure_ascii=False),
        is_default=body.is_default,
    )
    db.audit("rag.profile.create", f"id={pid} name={body.name} kind={body.kind}")
    row = db.get_rag_test_profile(pid)
    assert row
    return _profile_row_to_out(row)


@router.get("/rag-test/profiles/{profile_id}", response_model=TestProfileOut)
def get_test_profile(profile_id: str) -> TestProfileOut:
    db = deps.get_db()
    row = db.get_rag_test_profile(profile_id)
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_row_to_out(row)


@router.put("/rag-test/profiles/{profile_id}", response_model=TestProfileOut, dependencies=[Depends(require_admin)])
def update_test_profile(
    profile_id: str,
    body: TestProfileCreate,
) -> TestProfileOut:
    db = deps.get_db()
    if not db.get_rag_test_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    RagRuntimeProfile.model_validate(body.profile) if body.kind == "runtime" else None
    ok = db.update_rag_test_profile(
        profile_id,
        body.name,
        body.kind,
        json.dumps(body.profile, ensure_ascii=False),
        is_default=body.is_default,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Update failed")
    db.audit("rag.profile.update", f"id={profile_id}")
    row = db.get_rag_test_profile(profile_id)
    assert row
    return _profile_row_to_out(row)


@router.delete("/rag-test/profiles/{profile_id}", dependencies=[Depends(require_admin)])
def delete_test_profile(profile_id: str) -> dict[str, str]:
    db = deps.get_db()
    if not db.delete_rag_test_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    db.audit("rag.profile.delete", f"id={profile_id}")
    return {"status": "deleted", "id": profile_id}


@router.post("/rag-test/profiles/import", response_model=TestProfileOut, dependencies=[Depends(require_admin)])
def import_test_profile(
    body: TestProfileCreate,
    settings: Settings = Depends(get_settings),
) -> TestProfileOut:
    return create_test_profile(body, settings)


@router.get("/rag-test/profiles/{profile_id}/export")
def export_test_profile(profile_id: str) -> JSONResponse:
    db = deps.get_db()
    row = db.get_rag_test_profile(profile_id)
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    payload = {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "profile": json.loads(str(row["profile_json"] or "{}")),
        "is_default": bool(row.get("is_default")),
    }
    return JSONResponse(content=payload)


@router.post("/rag-test/run")
def test_run(
    body: TestRunIn,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    db = deps.get_db()
    prof: RagRuntimeProfile
    profile_id_ref: str | None = body.profile_id
    if body.profile_id:
        row = db.get_rag_test_profile(body.profile_id)
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")
        prof = RagRuntimeProfile.model_validate(json.loads(str(row["profile_json"] or "{}")))
    elif body.profile:
        prof = TestRunIn.profile_model(body.profile)
    else:
        prof = RagRuntimeProfile()
    scope = TestRunIn.scope_model(body.scope)
    try:
        out = run_rag_test(
            settings,
            deps.get_chroma(),
            db,
            body.question,
            scope,
            prof,
            debug=body.debug,
        )
    except Exception as e:
        _log.exception("rag test run failed")
        d = http_detail_for_chroma_or_embedding_network_error(e)
        raise HTTPException(status_code=502 if d else 500, detail=d or str(e)) from e
    run_id = str(uuid4())
    snap = prof.model_dump()
    err_json = None
    row: dict[str, Any] = {
        "id": run_id,
        "profile_id": profile_id_ref,
        "profile_snapshot_json": json.dumps(snap, ensure_ascii=False),
        "question": body.question,
        "scope_json": json.dumps(body.scope, ensure_ascii=False),
        "answer": out.get("answer"),
        "citations_json": json.dumps(out.get("citations") or [], ensure_ascii=False),
        "retrieved_chunks_json": _serialize_chunks_for_db(out.get("chunks") or []),
        "metrics_json": json.dumps(out.get("metrics") or {}, ensure_ascii=False),
        "llm_request_json": None,
        "llm_response_meta_json": (
            json.dumps(out.get("llm_response_meta") or {}, ensure_ascii=False)
            if out.get("llm_response_meta")
            else None
        ),
        "demo_mode": 1 if out.get("demo_mode") else 0,
        "error_json": err_json,
        "created_at": "",
    }
    from app.db_sqlite import utc_now_iso

    row["created_at"] = utc_now_iso()
    db.insert_rag_test_run(row)
    db.audit("rag.test.run", f"id={run_id} len={len(body.question)}")
    return {
        "run_id": run_id,
        "profile": snap,
        **out,
    }


@router.post("/rag-test/compare")
def test_compare(
    body: TestCompareIn,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    db = deps.get_db()
    scope = RagScopeIn.model_validate(body.scope)
    left = RagRuntimeProfile.model_validate(body.left_profile)
    right = RagRuntimeProfile.model_validate(body.right_profile)
    try:
        out_l = run_rag_test(
            settings, deps.get_chroma(), db, body.question, scope, left, debug=body.debug
        )
        out_r = run_rag_test(
            settings, deps.get_chroma(), db, body.question, scope, right, debug=body.debug
        )
    except Exception as e:
        _log.exception("rag test compare failed")
        d = http_detail_for_chroma_or_embedding_network_error(e)
        raise HTTPException(status_code=502 if d else 500, detail=d or str(e)) from e
    pair_id = str(uuid4())
    from app.db_sqlite import utc_now_iso

    def _store_side(out: dict[str, Any], prof: RagRuntimeProfile) -> str:
        rid = str(uuid4())
        snap = prof.model_dump()
        row = {
            "id": rid,
            "profile_id": None,
            "profile_snapshot_json": json.dumps(snap, ensure_ascii=False),
            "question": body.question,
            "scope_json": json.dumps(body.scope, ensure_ascii=False),
            "answer": out.get("answer"),
            "citations_json": json.dumps(out.get("citations") or [], ensure_ascii=False),
            "retrieved_chunks_json": _serialize_chunks_for_db(out.get("chunks") or []),
            "metrics_json": json.dumps(out.get("metrics") or {}, ensure_ascii=False),
            "llm_request_json": None,
            "llm_response_meta_json": (
                json.dumps(out.get("llm_response_meta") or {}, ensure_ascii=False)
                if out.get("llm_response_meta")
                else None
            ),
            "demo_mode": 1 if out.get("demo_mode") else 0,
            "error_json": None,
            "created_at": utc_now_iso(),
        }
        db.insert_rag_test_run(row)
        return rid

    left_id = _store_side(out_l, left)
    right_id = _store_side(out_r, right)
    ids_l = {str(c.get("chunk_id")) for c in (out_l.get("chunks") or []) if c.get("chunk_id")}
    ids_r = {str(c.get("chunk_id")) for c in (out_r.get("chunks") or []) if c.get("chunk_id")}
    comparison = {
        "chunk_id_overlap": len(ids_l & ids_r),
        "delta_total_ms": (out_l.get("metrics") or {}).get("total_ms", 0) - (out_r.get("metrics") or {}).get(
            "total_ms", 0
        ),
    }
    db.insert_rag_test_run_pair(
        {
            "id": pair_id,
            "left_run_id": left_id,
            "right_run_id": right_id,
            "question": body.question,
            "comparison_metrics_json": json.dumps(comparison, ensure_ascii=False),
            "created_at": utc_now_iso(),
        }
    )
    db.audit("rag.test.compare", f"pair={pair_id} left={left_id} right={right_id}")
    return {
        "pair_id": pair_id,
        "left_run_id": left_id,
        "right_run_id": right_id,
        "comparison": comparison,
        "left": out_l,
        "right": out_r,
    }


@router.get("/rag-test/runs")
def list_test_runs(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    db = deps.get_db()
    return db.list_rag_test_runs(limit=limit)


@router.get("/rag-test/runs/{run_id}")
def get_test_run(run_id: str) -> dict[str, Any]:
    db = deps.get_db()
    row = db.get_rag_test_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(row)


@router.get("/rag-test/main-chat-profile")
def main_chat_profile_get() -> dict[str, Any]:
    db = deps.get_db()
    row = db.get_rag_runtime_settings()
    if not row:
        return {"profile": None, "raw": None}
    return {
        "profile": json.loads(str(row.get("profile_snapshot_json") or "{}")),
        "updated_at": row.get("updated_at"),
        "updated_by": row.get("updated_by"),
    }


@router.post("/rag-test/apply-to-chat", dependencies=[Depends(require_admin)])
def main_chat_apply(
    body: ApplyToChatIn,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    try:
        prof = RagRuntimeProfile.model_validate(body.profile)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {e}") from e
    try:
        validate_main_chat_apply(settings, prof)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    snap = MainChatRuntimeSnapshot.from_profile(prof)
    db = deps.get_db()
    db.upsert_rag_runtime_settings(
        json.dumps(snap.model_dump(), ensure_ascii=False),
        updated_by="api",
    )
    # optional: keep profile name ref — skipped for MVP
    db.audit("rag.profile.apply", "main_chat runtime overrides")
    return {"status": "ok", "message": "Runtime overrides applied to main chat"}


# --- v2: benchmarks ---


class BenchmarkSetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None


@router.get("/rag-test/benchmarks")
def benchmark_list() -> list[dict[str, Any]]:
    return deps.get_db().list_benchmark_sets()


@router.post("/rag-test/benchmarks", dependencies=[Depends(require_admin)])
def benchmark_create(body: BenchmarkSetCreate) -> dict[str, str]:
    sid = str(uuid4())
    deps.get_db().insert_benchmark_set(sid, body.name, body.description)
    deps.get_db().audit("rag.benchmark.set.create", f"id={sid} name={body.name}")
    return {"id": sid, "name": body.name}


@router.get("/rag-test/benchmarks/{set_id}/questions")
def benchmark_questions_list(set_id: str) -> list[dict[str, Any]]:
    db = deps.get_db()
    if not db.get_benchmark_set(set_id):
        raise HTTPException(status_code=404, detail="Benchmark set not found")
    return db.list_benchmark_questions(set_id)


class BenchmarkQuestionIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=16000)
    expected: dict[str, Any] | None = None
    tags: list[str] | None = None


@router.post("/rag-test/benchmarks/{set_id}/questions", dependencies=[Depends(require_admin)])
def benchmark_question_add(set_id: str, body: BenchmarkQuestionIn) -> dict[str, str]:
    db = deps.get_db()
    if not db.get_benchmark_set(set_id):
        raise HTTPException(status_code=404, detail="Benchmark set not found")
    qid = str(uuid4())
    db.insert_benchmark_question(
        qid,
        set_id,
        body.question,
        json.dumps(body.expected, ensure_ascii=False) if body.expected else None,
        json.dumps(body.tags, ensure_ascii=False) if body.tags else None,
    )
    return {"id": qid}


@router.post("/rag-test/benchmarks/{set_id}/run")
def benchmark_run_batch(
    set_id: str,
    body: dict[str, Any],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Run all questions in set with a single profile; store benchmark run and item rows."""
    db = deps.get_db()
    if not db.get_benchmark_set(set_id):
        raise HTTPException(status_code=404, detail="Benchmark set not found")
    prof = RagRuntimeProfile.model_validate(body.get("profile") or {})
    scope = RagScopeIn.model_validate(body.get("scope") or {"all": True})
    questions = db.list_benchmark_questions(set_id)
    if not questions:
        raise HTTPException(status_code=400, detail="No questions in set")
    run_id = str(uuid4())
    from app.db_sqlite import utc_now_iso

    now = utc_now_iso()
    db.insert_benchmark_run(
        {
            "id": run_id,
            "set_id": set_id,
            "profile_snapshot_json": json.dumps(prof.model_dump(), ensure_ascii=False),
            "status": "running",
            "summary_metrics_json": None,
            "created_at": now,
            "finished_at": None,
        }
    )
    results: list[dict[str, Any]] = []
    for q in questions:
        qid = str(q["id"])
        text = str(q["question"])
        out = run_rag_test(
            settings,
            deps.get_chroma(),
            db,
            text,
            scope,
            prof,
            debug=False,
        )
        tr_id = str(uuid4())
        db.insert_rag_test_run(
            {
                "id": tr_id,
                "profile_id": None,
                "profile_snapshot_json": json.dumps(prof.model_dump(), ensure_ascii=False),
                "question": text,
                "scope_json": json.dumps(body.get("scope") or {"all": True}, ensure_ascii=False),
                "answer": out.get("answer"),
                "citations_json": json.dumps(out.get("citations") or [], ensure_ascii=False),
                "retrieved_chunks_json": _serialize_chunks_for_db(out.get("chunks") or []),
                "metrics_json": json.dumps(out.get("metrics") or {}, ensure_ascii=False),
                "llm_request_json": None,
                "llm_response_meta_json": None,
                "demo_mode": 1 if out.get("demo_mode") else 0,
                "error_json": None,
                "created_at": utc_now_iso(),
            }
        )
        item_id = str(uuid4())
        db.insert_benchmark_run_item(
            {
                "id": item_id,
                "benchmark_run_id": run_id,
                "question_id": qid,
                "test_run_id": tr_id,
                "metrics_json": json.dumps(out.get("metrics") or {}, ensure_ascii=False),
            }
        )
        results.append({"question_id": qid, "test_run_id": tr_id, "metrics": out.get("metrics")})
    not_found_n = sum(
        1
        for r in results
        if (r.get("metrics") or {}).get("answer_status") == "not_found"
    )
    summary = {
        "questions": len(questions),
        "not_found_rate": not_found_n / max(1, len(questions)),
    }
    fin = utc_now_iso()
    db.update_benchmark_run(
        run_id,
        status="completed",
        summary_metrics_json=json.dumps(summary, ensure_ascii=False),
        finished_at=fin,
    )
    db.audit("rag.benchmark.run", f"id={run_id} set={set_id} n={len(questions)}")
    return {"benchmark_run_id": run_id, "summary": summary, "items": results}


@router.get("/rag-test/benchmark-runs/{run_id}")
def benchmark_run_get(run_id: str) -> dict[str, Any]:
    db = deps.get_db()
    row = db.get_benchmark_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    items = db.list_benchmark_run_items(run_id)
    return {"run": dict(row), "items": items}


# --- v2: index profiles (draft / placeholder jobs) ---


class IndexProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    profile_json: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


@router.get("/rag-test/index-profiles")
def index_profiles_list() -> list[dict[str, Any]]:
    return deps.get_db().list_rag_index_profiles()


@router.post("/rag-test/index-profiles", dependencies=[Depends(require_admin)])
def index_profile_create(body: IndexProfileCreate) -> dict[str, str]:
    pid = str(uuid4())
    deps.get_db().insert_rag_index_profile(
        pid,
        body.name,
        json.dumps(body.profile_json, ensure_ascii=False),
        status=body.status,
    )
    deps.get_db().audit("rag.index.profile.create", f"id={pid} name={body.name}")
    return {"id": pid}


@router.post("/rag-test/index-profiles/{profile_id}/sandbox-reindex", dependencies=[Depends(require_admin)])
def index_sandbox_reindex_placeholder(profile_id: str) -> dict[str, str]:
    db = deps.get_db()
    if not db.get_rag_index_profile(profile_id):
        raise HTTPException(status_code=404, detail="Index profile not found")
    jid = str(uuid4())
    from app.db_sqlite import utc_now_iso

    db.insert_rag_index_job(
        {
            "id": jid,
            "index_profile_id": profile_id,
            "status": "queued",
            "source_scope_json": None,
            "counts_json": None,
            "error_json": None,
            "created_at": utc_now_iso(),
            "finished_at": None,
        }
    )
    db.audit("rag.index.sandbox.create", f"job={jid} profile={profile_id}")
    return {
        "job_id": jid,
        "message": "Sandbox reindex is a placeholder: implement ingest into alternate Chroma path in a follow-up.",
    }


@router.get("/rag-test/index-jobs/{job_id}")
def index_job_get(job_id: str) -> dict[str, Any]:
    row = deps.get_db().get_rag_index_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)
