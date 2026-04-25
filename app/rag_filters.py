"""Shared chunk filters for RAG retrieval."""

from __future__ import annotations

from typing import Any


def filter_chunks_by_distance(
    chunks: list[dict[str, Any]],
    threshold: float | None,
) -> tuple[list[dict[str, Any]], int]:
    """Drop chunks with distance > threshold. Returns (kept, dropped_count)."""
    if threshold is None:
        return chunks, 0
    kept: list[dict[str, Any]] = []
    dropped = 0
    t = float(threshold)
    for ch in chunks:
        d = ch.get("distance")
        try:
            df = float(d) if d is not None else None
        except (TypeError, ValueError):
            df = None
        if df is None or df <= t:
            kept.append(ch)
        else:
            dropped += 1
    return kept, dropped
