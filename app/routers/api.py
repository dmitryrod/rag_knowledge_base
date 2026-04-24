"""REST API v1: collections, documents, chat, audit."""

from __future__ import annotations

import logging
import traceback
from typing import Annotated, Literal
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
from pydantic import BaseModel, Field

from app.auth_dep import get_auth, is_auth_configured, require_admin
from app.chat_service import run_chat
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


class CollectionOut(BaseModel):
    id: str
    name: str
    created_at: str


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)


class ChatOut(BaseModel):
    answer: str
    citations: list[dict]
    chunks_considered: int
    demo_mode: bool | None = None


class ChatThreadCreate(BaseModel):
    collection_id: str = Field(..., min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=256)


class ChatThreadOut(BaseModel):
    id: str
    collection_id: str
    title: str
    created_at: str
    updated_at: str


class ChatThreadPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class ChatMessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    citations: list[dict]
    created_at: str


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
    cid = db.create_collection(body.name)
    db.audit("collection.create", f"id={cid} name={body.name}")
    row = db.get_collection(cid)
    assert row
    return CollectionOut(id=row["id"], name=row["name"], created_at=row["created_at"])


@router.get("/collections", response_model=list[CollectionOut])
def list_collections() -> list[CollectionOut]:
    db = deps.get_db()
    rows = db.list_collections()
    return [CollectionOut(id=r["id"], name=r["name"], created_at=r["created_at"]) for r in rows]


@router.delete("/collections/{collection_id}", dependencies=[Depends(require_admin)])
def delete_collection(collection_id: str, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    db = deps.get_db()
    if not db.get_collection(collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    deps.get_chroma().drop_collection(collection_id)
    db.delete_collection(collection_id)
    db.audit("collection.delete", f"id={collection_id}")
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
        _check_polza_allowlist(settings)
        db = deps.get_db()
        if not db.get_collection(collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        out = run_chat(
            settings,
            deps.get_chroma(),
            collection_id,
            body.message,
            debug=client_debug,
        )
        if client_debug:
            _log.info(
                "POST /chat: run_chat ok chunks_considered=%s demo_mode=%s",
                out.get("chunks_considered"),
                out.get("demo_mode"),
            )
        try:
            db.audit(
                "chat.query",
                f"collection={collection_id} len={len(body.message)} chunks={out.get('chunks_considered')}",
            )
        except Exception:
            # Ответ RAG уже готов; audit — не best-effort для UX, но логируем (иначе 500 зря)
            _log.exception("POST /chat: audit_log write failed; ответ чата отдаётся")
        return ChatOut(
            answer=str(out.get("answer", "")),
            citations=list(out.get("citations") or []),
            chunks_considered=int(out.get("chunks_considered") or 0),
            demo_mode=out.get("demo_mode"),
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
        _check_polza_allowlist(settings)
        db = deps.get_db()
        if not db.get_collection(collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        out = run_chat(
            settings,
            deps.get_chroma(),
            collection_id,
            body.message,
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
        description="Фильтр по разделу (RAG collection id)",
    ),
) -> list[ChatThreadOut]:
    db = deps.get_db()
    rows = db.list_chat_threads(collection_id=collection_id)
    return [
        ChatThreadOut(
            id=r["id"],
            collection_id=r["collection_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.post("/chat/threads", response_model=ChatThreadOut)
def create_chat_thread(body: ChatThreadCreate) -> ChatThreadOut:
    db = deps.get_db()
    if not db.get_collection(body.collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    row = db.create_chat_thread(body.collection_id, body.title)
    db.audit("chat.thread.create", f"id={row['id']} collection={body.collection_id}")
    return ChatThreadOut(
        id=row["id"],
        collection_id=row["collection_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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
    return ChatThreadOut(
        id=row["id"],
        collection_id=row["collection_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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
    collection_id = thread["collection_id"]
    if client_debug:
        _log.info(
            "POST /chat/threads/.../messages: thread=%s collection=%s len=%s",
            thread_id,
            collection_id,
            len(body.message),
        )
    try:
        _check_polza_allowlist(settings)
        db = deps.get_db()
        if not db.get_collection(collection_id):
            raise HTTPException(status_code=404, detail="Collection not found")
        db.insert_chat_message(thread_id, "user", body.message, citations=None)
        out = run_chat(
            settings,
            deps.get_chroma(),
            collection_id,
            body.message,
            debug=client_debug,
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
                f"thread={thread_id} collection={collection_id} len={len(body.message)} chunks={out.get('chunks_considered')}",
            )
        except Exception:
            _log.exception("POST thread message: audit failed; ответ отдаётся")
        return ChatOut(
            answer=str(out.get("answer", "")),
            citations=cites,
            chunks_considered=int(out.get("chunks_considered") or 0),
            demo_mode=out.get("demo_mode"),
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
