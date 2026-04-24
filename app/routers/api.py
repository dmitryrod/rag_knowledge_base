"""REST API v1: collections, documents, chat, audit."""

from __future__ import annotations

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

from app.auth_dep import get_auth, require_admin
from app.chat_service import run_chat
from app.config import Settings, get_settings, is_polza_model_allowlisted
from app import deps
from app.ingest import chunk_text, extract_text

router = APIRouter(dependencies=[Depends(get_auth)])
public = APIRouter()


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


@public.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0", "data_dir": str(settings.data_dir)}


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


@router.post("/collections/{collection_id}/chat", response_model=ChatOut)
def chat(
    collection_id: str,
    body: ChatIn,
    settings: Settings = Depends(get_settings),
) -> ChatOut:
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
        "chat.query",
        f"collection={collection_id} len={len(body.message)} chunks={out.get('chunks_considered')}",
    )
    return ChatOut(
        answer=out["answer"],
        citations=out.get("citations") or [],
        chunks_considered=int(out.get("chunks_considered") or 0),
        demo_mode=out.get("demo_mode"),
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
    fmt: Annotated[
        Literal["markdown", "plain"],
        Query(alias="format", description="markdown или plain"),
    ] = "markdown",
) -> PlainTextResponse:
    """Экспорт ответа RAG в текст или markdown с блоком цитат."""
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
    media = "text/markdown; charset=utf-8" if fmt == "markdown" else "text/plain; charset=utf-8"
    return PlainTextResponse(content=text, media_type=media)


@router.get("/audit", dependencies=[Depends(require_admin)])
def audit_list(limit: int = 50) -> list[dict]:
    return deps.get_db().list_audit(limit=min(limit, 500))
