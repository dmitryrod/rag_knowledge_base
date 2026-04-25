"""Typed structures for Polza / OpenAI-compatible chat completion responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LlmCompletionResult:
    """Assistant text plus provider metadata for diagnostics and billing."""

    content: str
    model: str | None = None
    provider: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_response_meta(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
        }
