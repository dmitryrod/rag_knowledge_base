"""Chroma persistent vector store per logical collection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.api import Collection


def _coll_name(collection_id: str) -> str:
    safe = collection_id.replace("-", "_")
    return f"knowledge_{safe}"


class ChromaStore:
    def __init__(self, persist_dir: Path) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))

    def _get(self, collection_id: str) -> Collection:
        name = _coll_name(collection_id)
        return self._client.get_or_create_collection(
            name=name,
            metadata={"collection_id": collection_id},
        )

    def drop_collection(self, collection_id: str) -> None:
        name = _coll_name(collection_id)
        try:
            self._client.delete_collection(name)
        except Exception:
            pass

    def upsert_chunks(
        self,
        collection_id: str,
        doc_id: str,
        filename: str,
        chunks: list[str],
    ) -> None:
        col = self._get(collection_id)
        ids = [f"{doc_id}__{i}" for i in range(len(chunks))]
        metadatas: list[dict[str, Any]] = [
            {
                "document_id": doc_id,
                "filename": filename,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        col.add(ids=ids, documents=chunks, metadatas=metadatas)

    def delete_by_document(self, collection_id: str, doc_id: str) -> int:
        col = self._get(collection_id)
        got = col.get(where={"document_id": doc_id})
        ids = got.get("ids") or []
        if ids:
            col.delete(ids=ids)
        return len(ids)

    def query(
        self,
        collection_id: str,
        query_text: str,
        n_results: int,
    ) -> list[dict[str, Any]]:
        col = self._get(collection_id)
        res = col.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict[str, Any]] = []
        ids_list = res.get("ids") or [[]]
        docs_list = res.get("documents") or [[]]
        meta_list = res.get("metadatas") or [[]]
        dist_list = res.get("distances") or [[]]
        for i, chunk_id in enumerate(ids_list[0]):
            out.append(
                {
                    "chunk_id": chunk_id,
                    "text": docs_list[0][i] if docs_list[0] else "",
                    "metadata": meta_list[0][i] if meta_list[0] else {},
                    "distance": dist_list[0][i] if dist_list[0] else None,
                }
            )
        return out
