"""Unit tests for chroma_user_errors."""

from __future__ import annotations

from app.chroma_user_errors import http_detail_for_chroma_or_embedding_network_error


def test_ssl_handshake_timeout_maps_to_user_detail() -> None:
    e = OSError("_ssl.c:993: The handshake operation timed out in query.")
    d = http_detail_for_chroma_or_embedding_network_error(e)
    assert d is not None
    assert "Chroma" in d
    assert "amazonaws" in d or "S3" in d


def test_unrelated_error_returns_none() -> None:
    assert http_detail_for_chroma_or_embedding_network_error(ValueError("nope")) is None
