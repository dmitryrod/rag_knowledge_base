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

    def count_chunks_for_document(self, collection_id: str, document_id: str) -> int:
        col = self._get(collection_id)
        got = col.get(where={"document_id": document_id})
        return len(got.get("ids") or [])

    def count_embeddings(self, collection_id: str) -> int:
        """Число записей (чанков) в Chroma-коллекции раздела."""
        try:
            col = self._get(collection_id)
            return int(col.count())
        except Exception:
            return 0

    def total_embeddings_for_collection_ids(self, collection_ids: list[str]) -> int:
        total = 0
        for cid in collection_ids:
            total += self.count_embeddings(cid)
        return total

    def copy_document_vectors_to_collection(
        self, source_collection_id: str, target_collection_id: str, document_id: str
    ) -> int:
        """Копирует чанки документа из source Chroma в target (source не трогает).

        При `source == target` — 0, без I/O. Вызывать до обновления SQLite; после успешного
        UPDATE удалить векторы из source через `delete_by_document`.
        """
        if source_collection_id == target_collection_id:
            return 0
        col_src = self._get(source_collection_id)
        got = col_src.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        ids = list(got.get("ids") or [])
        if not ids:
            return 0
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        dlist: list[str] = []
        mlist: list[dict[str, Any]] = []
        for i, _cid in enumerate(ids):
            d = docs[i] if i < len(docs) and docs[i] is not None else ""
            dlist.append(d if isinstance(d, str) else str(d))
            md: dict[str, Any] = metas[i] if i < len(metas) and metas[i] is not None else {}
            if not isinstance(md, dict):
                md = {}
            mlist.append(md)
        col_tgt = self._get(target_collection_id)
        # Идемпотентность: повторный перенос / частичный retry не должен падать на duplicate id.
        try:
            self.delete_by_document(target_collection_id, document_id)
        except Exception:
            pass
        col_tgt.add(ids=ids, documents=dlist, metadatas=mlist)
        return len(ids)

    def update_document_filename_metadata(
        self, collection_id: str, doc_id: str, filename: str
    ) -> int:
        """Обновить `filename` в метаданных всех чанков документа. Возвращает число чанков."""
        col = self._get(collection_id)
        got = col.get(where={"document_id": doc_id})
        ids = list(got.get("ids") or [])
        metas = got.get("metadatas") or []
        if not ids:
            return 0
        new_metas: list[dict[str, Any]] = []
        for m in metas:
            md = dict(m) if m else {}
            md["filename"] = filename
            md["document_id"] = doc_id
            new_metas.append(md)
        col.update(ids=ids, metadatas=new_metas)
        return len(ids)

    def query(
        self,
        collection_id: str,
        query_text: str,
        n_results: int,
        *,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        col = self._get(collection_id)
        q_kw: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            q_kw["where"] = where
        if where_document is not None:
            q_kw["where_document"] = where_document
        res = col.query(**q_kw)
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

    def query_multi(
        self,
        collection_ids: list[str],
        query_text: str,
        n_results: int,
        *,
        where_by_collection: dict[str, dict[str, Any]] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Семантический поиск сразу по нескольким Chroma-коллекциям; слияние по distance (меньше — релевантнее)."""
        ids = [c for c in collection_ids if c]
        if not ids:
            return []
        if len(ids) == 1:
            w0 = (where_by_collection or {}).get(ids[0])
            return self.query(
                ids[0],
                query_text,
                n_results,
                where=w0,
                where_document=where_document,
            )
        n = max(1, int(n_results))
        per = max(1, (n + len(ids) - 1) // len(ids))
        per = min(max(per, 4), n)
        merged: list[dict[str, Any]] = []
        for cid in ids:
            w0 = (where_by_collection or {}).get(cid)
            part = self.query(
                cid,
                query_text,
                n_results=per,
                where=w0,
                where_document=where_document,
            )
            for ch in part:
                row = {**ch, "source_collection_id": cid}
                merged.append(row)

        def _dist(x: dict[str, Any]) -> float:
            d = x.get("distance")
            if d is None:
                return float("inf")
            try:
                return float(d)
            except (TypeError, ValueError):
                return float("inf")

        merged.sort(key=_dist)
        return merged[:n]
