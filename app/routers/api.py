"""REST API v1: collections, documents, chat, audit."""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth_dep import get_auth, is_auth_configured, require_admin
from app.chat_service import run_chat
from app.rag_runtime import main_chat_effective_settings
from app.rag_scope import (
    RAG_ALL_PLACEHOLDER_ID,
    collection_ids_for_retrieval,
    expand_collection_ids_with_subtrees,
    normalize_id_list,
    parse_rag_scope_json,
    thread_matches_rag,
)
from app.config import Settings, get_settings, is_polza_model_allowlisted
from app.debug_dep import is_client_debug
from app import deps
from app.ingest import chunk_text, extract_text
from app.llm import LlmUpstreamError

router = APIRouter(dependencies=[Depends(get_auth)])
public = APIRouter()
_log = logging.getLogger(__name__)


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    parent_id: str | None = Field(
        default=None,
        description="Родительский раздел; null или отсутствие — корень",
    )


class CollectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    parent_id: str | None = None


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, max_length=512)


class DocumentMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_collection_id: str = Field(..., min_length=1, max_length=256)


class CollectionOut(BaseModel):
    id: str
    name: str
    created_at: str
    parent_id: str | None = None


class DocumentNode(BaseModel):
    type: Literal["document"] = "document"
    id: str
    name: str
    collection_id: str
    size_bytes: int | None = None
    mime: str | None = None
    created_at: str


class CollectionTreeNode(BaseModel):
    type: Literal["section"] = "section"
    id: str
    name: str
    parent_id: str | None = None
    created_at: str
    children: list["CollectionTreeNode"] = Field(default_factory=list)
    documents: list[DocumentNode] = Field(default_factory=list)


CollectionTreeNode.model_rebuild()


class KnowledgeStatsOut(BaseModel):
    sections_count: int
    documents_count: int
    chunks_count: int
    embedding_vectors_count: int
    document_files_size_bytes: int
    metadata_db_size_bytes: int
    chroma_storage_size_bytes: int
    data_dir_size_bytes: int
    chat_threads_count: int
    chat_messages_count: int
    audit_log_rows: int


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)


class ChatOut(BaseModel):
    answer: str
    citations: list[dict]
    chunks_considered: int
    demo_mode: bool | None = None
    debug: dict[str, Any] | None = None


class ChatThreadCreate(BaseModel):
    """Создать тред: либо `collection_id` (один раздел), либо `rag` (все или несколько)."""

    collection_id: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=256)
    rag: dict[str, Any] | None = None

    @model_validator(mode="after")
    def one_scope_source(self) -> "ChatThreadCreate":
        if self.rag is not None and self.collection_id is not None:
            raise ValueError("Укажите либо collection_id, либо rag, не оба")
        if self.rag is None and self.collection_id is None:
            raise ValueError("Нужен collection_id или rag")
        return self


class ChatThreadOut(BaseModel):
    id: str
    collection_id: str
    title: str
    created_at: str
    updated_at: str
    rag: dict | None = None


class ChatThreadPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class ChatMessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    citations: list[dict]
    created_at: str


def _thread_to_out(row: dict[str, Any]) -> ChatThreadOut:
    return ChatThreadOut(
        id=str(row["id"]),
        collection_id=str(row["collection_id"]),
        title=str(row["title"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        rag=row.get("rag"),
    )


def _safe_file_size(p: Path) -> int:
    try:
        return int(p.stat().st_size) if p.is_file() else 0
    except OSError:
        return 0


def _dir_size_bytes(p: Path) -> int:
    total = 0
    if not p.exists():
        return 0
    try:
        for sub in p.rglob("*"):
            if sub.is_file():
                try:
                    total += sub.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _row_parent_id(r: dict[str, Any]) -> str | None:
    p = r.get("parent_id")
    if p is None or p == "":
        return None
    return str(p)


def _build_knowledge_tree() -> list[CollectionTreeNode]:
    db = deps.get_db()
    rows = [
        r
        for r in db.list_collections()
        if str(r["id"]) != RAG_ALL_PLACEHOLDER_ID
    ]
    by_id = {str(r["id"]): r for r in rows}

    def make_node(cid: str) -> CollectionTreeNode:
        row = by_id[cid]
        child_ids = db.list_child_collection_ids(cid)
        children = [make_node(c) for c in child_ids]
        raw_docs = db.list_documents(cid)
        doc_nodes: list[DocumentNode] = []
        for d in raw_docs:
            doc_nodes.append(
                DocumentNode(
                    id=str(d["id"]),
                    name=str(d.get("filename") or d["id"]),
                    collection_id=cid,
                    size_bytes=int(d["size_bytes"])
                    if d.get("size_bytes") is not None
                    else None,
                    mime=str(d["mime"]) if d.get("mime") is not None else None,
                    created_at=str(d["created_at"]),
                )
            )
        return CollectionTreeNode(
            id=cid,
            name=str(row["name"]),
            parent_id=_row_parent_id(row),
            created_at=str(row["created_at"]),
            children=children,
            documents=doc_nodes,
        )

    roots = [str(r["id"]) for r in rows if _row_parent_id(r) is None]
    roots.sort(key=lambda i: by_id[i]["name"])
    return [make_node(r) for r in roots]


def _retrieval_ids_and_labels(
    thread_row: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """Какие Chroma-коллекции искать и подписи разделов для контекста."""
    db = deps.get_db()
    rscope = thread_row.get("rag")
    if rscope is None and thread_row.get("rag_scope_json") is not None:
        rscope = parse_rag_scope_json(str(thread_row.get("rag_scope_json") or ""))
    all_meta = [r for r in db.list_collections() if r["id"] != RAG_ALL_PLACEHOLDER_ID]
    all_cids = [str(r["id"]) for r in all_meta]
    sreal = set(all_cids)
    names = {str(r["id"]): str(r["name"]) for r in all_meta}
    base_tids = collection_ids_for_retrieval(
        all_cids,
        collection_id=str(thread_row["collection_id"]),
        rag_scope=rscope,
    )
    if rscope and rscope.get("all") is True:
        tids = base_tids
    else:
        tids = expand_collection_ids_with_subtrees(
            base_tids,
            subtree_postorder=db.collection_subtree_postorder,
            valid=sreal,
        )
    labels = {k: names.get(k, k[:8] + "…") for k in tids}
    return tids, labels


def _legacy_chat_collection_ids_and_labels(
    collection_id: str,
) -> tuple[list[str], dict[str, str]]:
    """POST /collections/{id}/chat: искать в разделе и во всех вложенных (как в UI-дереве)."""
    db = deps.get_db()
    all_meta = [r for r in db.list_collections() if r["id"] != RAG_ALL_PLACEHOLDER_ID]
    all_cids = [str(r["id"]) for r in all_meta]
    sreal = set(all_cids)
    names = {str(r["id"]): str(r["name"]) for r in all_meta}
    base = [collection_id] if collection_id in sreal else []
    tids = expand_collection_ids_with_subtrees(
        base,
        subtree_postorder=db.collection_subtree_postorder,
        valid=sreal,
    )
    labels = {k: names.get(k, k[:8] + "…") for k in tids}
    return tids, labels


@public.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "version": "0.4.0",
        "data_dir": str(settings.data_dir),
        "auth_configured": is_auth_configured(settings),
    }


@router.post("/collections", response_model=CollectionOut, dependencies=[Depends(require_admin)])
def create_collection(
    body: CollectionCreate,
    settings: Settings = Depends(get_settings),
) -> CollectionOut:
    db = deps.get_db()
    if body.parent_id:
        if body.parent_id == RAG_ALL_PLACEHOLDER_ID:
            raise HTTPException(
                status_code=400,
                detail="Cannot create section under reserved system collection",
            )
        parent = db.get_collection(body.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent collection not found")
    cid = db.create_collection(body.name, parent_id=body.parent_id)
    db.audit(
        "collection.create",
        f"id={cid} name={body.name} parent_id={body.parent_id!r}",
    )
    row = db.get_collection(cid)
    assert row
    return CollectionOut(
        id=str(row["id"]),
        name=str(row["name"]),
        created_at=str(row["created_at"]),
        parent_id=_row_parent_id(row),
    )


@router.get("/collections", response_model=list[CollectionOut])
def list_collections() -> list[CollectionOut]:
    db = deps.get_db()
    rows = [r for r in db.list_collections() if r["id"] != RAG_ALL_PLACEHOLDER_ID]
    return [
        CollectionOut(
            id=str(r["id"]),
            name=str(r["name"]),
            created_at=str(r["created_at"]),
            parent_id=_row_parent_id(r),
        )
        for r in rows
    ]


@router.get("/collections/tree", response_model=list[CollectionTreeNode])
def get_collections_tree() -> list[CollectionTreeNode]:
    return _build_knowledge_tree()


@router.get("/knowledge/stats", response_model=KnowledgeStatsOut)
def knowledge_stats(settings: Settings = Depends(get_settings)) -> KnowledgeStatsOut:
    db = deps.get_db()
    store = deps.get_chroma()
    user_ids = [
        str(r["id"])
        for r in db.list_collections()
        if str(r["id"]) != RAG_ALL_PLACEHOLDER_ID
    ]
    doc_agg = db.documents_aggregate()
    chunks = store.total_embeddings_for_collection_ids(user_ids)
    data_dir = Path(settings.data_dir)
    meta_path = data_dir / "metadata.db"
    chroma_dir = data_dir / "chroma"
    return KnowledgeStatsOut(
        sections_count=db.count_user_sections(),
        documents_count=doc_agg["count"],
        chunks_count=chunks,
        embedding_vectors_count=chunks,
        document_files_size_bytes=doc_agg["size_bytes_sum"],
        metadata_db_size_bytes=_safe_file_size(meta_path),
        chroma_storage_size_bytes=_dir_size_bytes(chroma_dir),
        data_dir_size_bytes=_dir_size_bytes(data_dir),
        chat_threads_count=db.chat_threads_count(),
        chat_messages_count=db.chat_messages_count(),
        audit_log_rows=db.audit_log_rows_count(),
    )


@router.patch(
    "/collections/{collection_id}",
    response_model=CollectionOut,
    dependencies=[Depends(require_admin)],
)
def patch_collection(collection_id: str, body: CollectionPatch) -> CollectionOut:
    if collection_id == RAG_ALL_PLACEHOLDER_ID:
        raise HTTPException(status_code=400, detail="Reserved system collection")
    db = deps.get_db()
    row = db.get_collection(collection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Collection not found")
    data = body.model_dump(exclude_unset=True)
    new_name: str | None = None
    if "name" in data and data["name"] is not None:
        new_name = str(data["name"])
    if "parent_id" in data:
        np = data["parent_id"]
        if np == RAG_ALL_PLACEHOLDER_ID:
            raise HTTPException(
                status_code=400,
                detail="Cannot move section under reserved system collection",
            )
        if np is not None:
            pr = db.get_collection(str(np))
            if not pr:
                raise HTTPException(status_code=404, detail="Parent collection not found")
            if db.would_parent_create_cycle(collection_id, str(np)):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid parent: would create a cycle",
                )
        db.update_collection(
            collection_id,
            name=new_name,
            parent_id=np,
        )
    elif "name" in data:
        db.update_collection(collection_id, name=new_name)
    out = db.get_collection(collection_id)
    assert out
    return CollectionOut(
        id=str(out["id"]),
        name=str(out["name"]),
        created_at=str(out["created_at"]),
        parent_id=_row_parent_id(out),
    )


@router.delete("/collections/{collection_id}", dependencies=[Depends(require_admin)])
def delete_collection(collection_id: str, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    if collection_id == RAG_ALL_PLACEHOLDER_ID:
        raise HTTPException(status_code=400, detail="Reserved system collection")
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    order = db.collection_subtree_postorder(collection_id)
    store = deps.get_chroma()
    for cid in order:
        store.drop_collection(cid)
        db.delete_collection(cid)
    db.audit("collection.delete", f"subtree_root={collection_id} ids={order!r}")
    return {"status": "deleted", "id": collection_id}


@router.post("/collections/{collection_id}/documents", dependencies=[Depends(require_admin)])
async def upload_document(
    collection_id: str,
    file: Annotated[UploadFile, File(...)],
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    raw = await file.read()
    max_b = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_b:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.max_upload_mb} MB)")
    name = file.filename or "unnamed"
    try:
        text = extract_text(name, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="No text extracted from file")
    doc_id = str(uuid4())
    store = deps.get_chroma()
    store.delete_by_document(collection_id, doc_id)  # no-op
    store.upsert_chunks(collection_id, doc_id, name, chunks)
    db.insert_document(
        collection_id,
        doc_id,
        name,
        file.content_type,
        len(raw),
    )
    db.audit(
        "document.upload",
        f"collection={collection_id} doc={doc_id} file={name} chunks={len(chunks)}",
    )
    return {
        "id": doc_id,
        "collection_id": collection_id,
        "filename": name,
        "chunks": str(len(chunks)),
    }


@router.get("/collections/{collection_id}/documents")
def list_documents(collection_id: str) -> list[dict]:
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return db.list_documents(collection_id)


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    dependencies=[Depends(require_admin)],
)
def delete_document(collection_id: str, document_id: str) -> dict[str, str]:
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    if not db.get_document(collection_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    deps.get_chroma().delete_by_document(collection_id, document_id)
    db.delete_document_row(collection_id, document_id)
    db.audit("document.delete", f"collection={collection_id} doc={document_id}")
    return {"status": "deleted", "id": document_id}


@router.patch(
    "/collections/{collection_id}/documents/{document_id}",
    dependencies=[Depends(require_admin)],
)
def patch_document(
    collection_id: str, document_id: str, body: DocumentPatch
) -> dict[str, Any]:
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    if not db.get_document(collection_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    fn = body.filename.strip()
    if not fn:
        raise HTTPException(status_code=400, detail="filename is empty")
    store = deps.get_chroma()
    store.update_document_filename_metadata(collection_id, document_id, fn)
    db.update_document_filename(collection_id, document_id, fn)
    db.audit(
        "document.patch",
        f"collection={collection_id} doc={document_id} filename={fn!r}",
    )
    row = db.get_document(collection_id, document_id)
    assert row
    return dict(row)


@router.post(
    "/collections/{target_collection_id}/documents/{document_id}/move",
    dependencies=[Depends(require_admin)],
)
def move_document(
    target_collection_id: str, document_id: str, body: DocumentMoveIn
) -> dict[str, Any]:
    """Перемещает документ в другой раздел: Chroma-чанки + `documents.collection_id`."""
    from app.chroma_user_errors import http_detail_for_chroma_or_embedding_network_error

    source = (body.source_collection_id or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="source_collection_id is required")
    if source == RAG_ALL_PLACEHOLDER_ID or target_collection_id == RAG_ALL_PLACEHOLDER_ID:
        raise HTTPException(status_code=400, detail="Reserved system collection")
    db = deps.get_db()
    if not db.get_collection(source):
        raise HTTPException(status_code=404, detail="Source collection not found")
    if not db.get_collection(target_collection_id):
        raise HTTPException(status_code=404, detail="Target collection not found")
    if not db.get_document(source, document_id):
        raise HTTPException(status_code=404, detail="Document not found in source")
    if source == target_collection_id:
        row = db.get_document(target_collection_id, document_id)
        assert row
        return dict(row)
    store = deps.get_chroma()
    n = 0
    try:
        n = store.copy_document_vectors_to_collection(
            source, target_collection_id, document_id
        )
    except Exception as e:  # noqa: BLE001 — mapping to 502/500
        d = http_detail_for_chroma_or_embedding_network_error(e)
        if d:
            _log.warning("document.move: chroma copy: %s", e)
            raise HTTPException(status_code=502, detail=d) from e
        _log.exception("document.move: chroma copy failed")
        raise HTTPException(status_code=500, detail="Chroma error") from e
    if not db.update_document_collection_id(source, document_id, target_collection_id):
        if n:
            try:
                store.delete_by_document(target_collection_id, document_id)
            except Exception:  # noqa: BLE001
                _log.exception("document.move: rollback target after failed SQL")
        raise HTTPException(status_code=500, detail="Failed to update document")
    if n:
        try:
            store.delete_by_document(source, document_id)
        except Exception as e:  # noqa: BLE001
            d = http_detail_for_chroma_or_embedding_network_error(e)
            if d:
                _log.error("document.move: delete source chunks after success SQL: %s", e)
                raise HTTPException(status_code=502, detail=d) from e
            _log.exception("document.move: delete source failed")
            raise HTTPException(
                status_code=500, detail="Document moved in DB; vector cleanup failed"
            ) from e
    db.audit(
        "document.move",
        f"source={source} target={target_collection_id} doc={document_id} chunks={n}",
    )
    row = db.get_document(target_collection_id, document_id)
    assert row
    return dict(row)


def _check_polza_allowlist(settings: Settings) -> None:
    if (
        settings.polza_api_key
        and settings.allow_llm_egress
        and not is_polza_model_allowlisted(settings)
    ):
        raise HTTPException(
            status_code=400,
            detail="POLZA_CHAT_MODEL is not included in POLZA_CHAT_MODEL_ALLOWLIST",
        )


def _rethrow_chat_error(
    e: Exception,
    *,
    settings: Settings,
    client_debug: bool,
    log_label: str,
) -> None:
    """Преобразует сбой чата/LLM в HTTP; всегда бросает HTTPException."""
    if isinstance(e, LlmUpstreamError):
        _log.warning("%s: LLM upstream: %s", log_label, e)
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    from app.chroma_user_errors import http_detail_for_chroma_or_embedding_network_error

    d = http_detail_for_chroma_or_embedding_network_error(e)
    if d:
        _log.warning("%s: chroma/embedding: %s", log_label, e)
        raise HTTPException(status_code=502, detail=d) from e
    _log.exception("%s", log_label)
    if client_debug and settings.allow_client_debug:
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "type": type(e).__name__,
                "trace": traceback.format_exc(),
            },
        ) from e
    raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/collections/{collection_id}/chat", response_model=ChatOut)
def chat(
    collection_id: str,
    body: ChatIn,
    settings: Settings = Depends(get_settings),
    client_debug: bool = Depends(is_client_debug),
) -> ChatOut:
    if client_debug:
        _log.info("POST /chat: collection_id=%s message_len=%s", collection_id, len(body.message))
    try:
        db = deps.get_db()
        eff, sys_prompt, dist_thr = main_chat_effective_settings(settings, db)
        _check_polza_allowlist(eff)
        if not db.get_collection(collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        cids, col_labels = _legacy_chat_collection_ids_and_labels(collection_id)
        out = run_chat(
            eff,
            deps.get_chroma(),
            body.message,
            collection_ids=cids,
            collection_labels=col_labels,
            debug=client_debug,
            system_prompt_override=sys_prompt,
            distance_threshold=dist_thr,
        )
        if client_debug:
            _log.info(
                "POST /chat: run_chat ok chunks_considered=%s demo_mode=%s retrieval_collections=%s",
                out.get("chunks_considered"),
                out.get("demo_mode"),
                cids,
            )
        try:
            db.audit(
                "chat.query",
                f"collection={collection_id} len={len(body.message)} chunks={out.get('chunks_considered')}"
                + (f" retrieval_cids={cids!r}" if client_debug else ""),
            )
        except Exception:
            # Ответ RAG уже готов; audit — не best-effort для UX, но логируем (иначе 500 зря)
            _log.exception("POST /chat: audit_log write failed; ответ чата отдаётся")
        return ChatOut(
            answer=str(out.get("answer", "")),
            citations=list(out.get("citations") or []),
            chunks_considered=int(out.get("chunks_considered") or 0),
            demo_mode=out.get("demo_mode"),
            debug=out.get("debug") if client_debug else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        _rethrow_chat_error(
            e,
            settings=settings,
            client_debug=client_debug,
            log_label=f"POST /chat: failed collection_id={collection_id}",
        )


def _format_export(answer: str, citations: list[dict], fmt: str) -> str:
    if fmt == "plain":
        lines = [answer.strip(), ""]
        lines.append("Citations:")
        for i, c in enumerate(citations, start=1):
            cid = c.get("chunk_id", "")
            q = c.get("quote", "")
            lines.append(f"{i}. [{cid}] {q}")
        return "\n".join(lines).strip() + "\n"
    # markdown
    md_lines = ["## Ответ", "", answer.strip(), "", "## Цитаты", ""]
    for i, c in enumerate(citations, start=1):
        cid = c.get("chunk_id", "")
        q = c.get("quote", "")
        md_lines.append(f"{i}. `chunk_id={cid}` — {q}")
    return "\n".join(md_lines).strip() + "\n"


@router.post("/collections/{collection_id}/chat/export", response_class=PlainTextResponse)
def chat_export(
    collection_id: str,
    body: ChatIn,
    settings: Settings = Depends(get_settings),
    client_debug: bool = Depends(is_client_debug),
    fmt: Annotated[
        Literal["markdown", "plain"],
        Query(alias="format", description="markdown или plain"),
    ] = "markdown",
) -> PlainTextResponse:
    """Экспорт ответа RAG в текст или markdown с блоком цитат."""
    try:
        db = deps.get_db()
        eff, sys_prompt, dist_thr = main_chat_effective_settings(settings, db)
        _check_polza_allowlist(eff)
        if not db.get_collection(collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        cids, col_labels = _legacy_chat_collection_ids_and_labels(collection_id)
        out = run_chat(
            eff,
            deps.get_chroma(),
            body.message,
            collection_ids=cids,
            collection_labels=col_labels,
            system_prompt_override=sys_prompt,
            distance_threshold=dist_thr,
        )
        db.audit(
            "chat.export",
            f"collection={collection_id} len={len(body.message)} format={fmt}",
        )
        text = _format_export(
            str(out.get("answer", "")),
            out.get("citations") or [],
            fmt,
        )
    except HTTPException:
        raise
    except Exception as e:
        _rethrow_chat_error(
            e,
            settings=settings,
            client_debug=client_debug,
            log_label=f"POST /chat/export: collection_id={collection_id}",
        )
    media = "text/markdown; charset=utf-8" if fmt == "markdown" else "text/plain; charset=utf-8"
    return PlainTextResponse(content=text, media_type=media)


def _get_thread_or_404(thread_id: str) -> dict[str, str]:
    db = deps.get_db()
    row = db.get_chat_thread(thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chat thread not found")
    return row


@router.get("/chat/threads", response_model=list[ChatThreadOut])
def list_chat_threads(
    collection_id: str | None = Query(
        default=None,
        description="Legacy: только треды с одним разделом (без rag multi/all)",
    ),
    rag: str | None = Query(
        default=None,
        description='JSON области RAG, например {"all":true} или {"ids":["uuid1","uuid2"]}',
    ),
) -> list[ChatThreadOut]:
    db = deps.get_db()
    if rag is not None and rag.strip():
        try:
            user_scope = json.loads(rag)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid rag JSON") from e
        if not isinstance(user_scope, dict):
            raise HTTPException(status_code=400, detail="rag must be a JSON object")
        rows = db.list_chat_threads(collection_id=None, limit=1000, legacy_single_only=False)
        matched = [
            r
            for r in rows
            if thread_matches_rag(
                str(r["collection_id"]),
                r.get("rag"),
                user_scope,
            )
        ]
        return [_thread_to_out(r) for r in matched[:500]]
    if collection_id is not None:
        rows = db.list_chat_threads(
            collection_id=collection_id,
            limit=500,
            legacy_single_only=True,
        )
        return [_thread_to_out(r) for r in rows]
    rows = db.list_chat_threads(limit=500)
    return [_thread_to_out(r) for r in rows]


@router.post("/chat/threads", response_model=ChatThreadOut)
def create_chat_thread(body: ChatThreadCreate) -> ChatThreadOut:
    db = deps.get_db()
    scope: dict[str, Any] | None = None
    anchor: str
    if body.rag is not None:
        if body.rag.get("all") is True:
            if not db.get_collection(RAG_ALL_PLACEHOLDER_ID):
                raise HTTPException(status_code=500, detail="RAG all placeholder missing")
            anchor = RAG_ALL_PLACEHOLDER_ID
            scope = {"all": True}
        elif body.rag.get("ids"):
            raw_ids = body.rag.get("ids")
            if not isinstance(raw_ids, list):
                raise HTTPException(status_code=400, detail="rag.ids must be a list")
            ids = normalize_id_list([str(x) for x in raw_ids])
            if not ids:
                raise HTTPException(status_code=400, detail="rag.ids is empty")
            for cid in ids:
                if not db.get_collection(cid):
                    raise HTTPException(status_code=404, detail=f"Collection not found: {cid}")
            anchor = ids[0]
            scope = {"ids": ids}
        else:
            raise HTTPException(status_code=400, detail="rag must have all: true or ids: [...]")
    else:
        assert body.collection_id is not None
        if not db.get_collection(body.collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        anchor = body.collection_id
        scope = None
    row = db.create_chat_thread(anchor, body.title, rag_scope=scope)
    db.audit("chat.thread.create", f"id={row['id']} collection={row['collection_id']} rag={scope}")
    return _thread_to_out(row)


@router.get("/chat/threads/{thread_id}/messages", response_model=list[ChatMessageOut])
def list_chat_messages(thread_id: str) -> list[ChatMessageOut]:
    _get_thread_or_404(thread_id)
    db = deps.get_db()
    rows = db.list_chat_messages(thread_id)
    return [
        ChatMessageOut(
            id=r["id"],
            thread_id=r["thread_id"],
            role=r["role"],
            content=r["content"],
            citations=list(r.get("citations") or []),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.patch("/chat/threads/{thread_id}", response_model=ChatThreadOut)
def patch_chat_thread(thread_id: str, body: ChatThreadPatch) -> ChatThreadOut:
    _get_thread_or_404(thread_id)
    db = deps.get_db()
    if not db.update_chat_thread_title(thread_id, body.title):
        raise HTTPException(status_code=400, detail="Invalid title")
    row = db.get_chat_thread(thread_id)
    assert row
    db.audit("chat.thread.rename", f"id={thread_id}")
    return _thread_to_out(row)


@router.delete("/chat/threads/{thread_id}")
def delete_chat_thread(thread_id: str) -> dict[str, str]:
    _get_thread_or_404(thread_id)
    db = deps.get_db()
    db.delete_chat_thread(thread_id)
    db.audit("chat.thread.delete", f"id={thread_id}")
    return {"status": "deleted", "id": thread_id}


@router.post("/chat/threads/{thread_id}/messages", response_model=ChatOut)
def chat_in_thread(
    thread_id: str,
    body: ChatIn,
    settings: Settings = Depends(get_settings),
    client_debug: bool = Depends(is_client_debug),
) -> ChatOut:
    thread = _get_thread_or_404(thread_id)
    if client_debug:
        _log.info(
            "POST /chat/threads/.../messages: thread=%s collection=%s len=%s",
            thread_id,
            thread["collection_id"],
            len(body.message),
        )
    try:
        db = deps.get_db()
        eff, sys_prompt, dist_thr = main_chat_effective_settings(settings, db)
        _check_polza_allowlist(eff)
        cids, col_labels = _retrieval_ids_and_labels(thread)
        if not cids:
            raise HTTPException(
                status_code=400,
                detail="No collections to search. Add sections/documents or create a new chat.",
            )
        db.insert_chat_message(thread_id, "user", body.message, citations=None)
        out = run_chat(
            eff,
            deps.get_chroma(),
            body.message,
            collection_ids=cids,
            collection_labels=col_labels,
            debug=client_debug,
            system_prompt_override=sys_prompt,
            distance_threshold=dist_thr,
        )
        cites = list(out.get("citations") or [])
        db.insert_chat_message(
            thread_id,
            "assistant",
            str(out.get("answer", "")),
            citations=cites,
        )
        if client_debug:
            _log.info(
                "POST thread message: ok chunks=%s demo=%s",
                out.get("chunks_considered"),
                out.get("demo_mode"),
            )
        try:
            db.audit(
                "chat.thread.message",
                f"thread={thread_id} collections={cids!r} len={len(body.message)} chunks={out.get('chunks_considered')}"
                + (f" retrieval_collection_count={len(cids)}" if client_debug else ""),
            )
        except Exception:
            _log.exception("POST thread message: audit failed; ответ отдаётся")
        return ChatOut(
            answer=str(out.get("answer", "")),
            citations=cites,
            chunks_considered=int(out.get("chunks_considered") or 0),
            demo_mode=out.get("demo_mode"),
            debug=out.get("debug") if client_debug else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        _rethrow_chat_error(
            e,
            settings=settings,
            client_debug=client_debug,
            log_label=f"POST thread message failed thread_id={thread_id}",
        )


@router.get("/audit", dependencies=[Depends(require_admin)])
def audit_list(limit: int = 50) -> list[dict]:
    return deps.get_db().list_audit(limit=min(limit, 500))
