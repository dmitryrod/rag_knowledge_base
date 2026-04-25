"""Pydantic models for RAG test runtime profiles and scopes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

JsonMode = Literal["none", "json_object", "json_schema_strict"]
FallbackMode = Literal["top_chunks", "none", "not_found"]
ProfileKind = Literal["runtime", "index"]


class RagScopeIn(BaseModel):
    """RAG collection scope: all collections, explicit ids, optional per-collection document filter."""

    all: bool | None = Field(default=None, description="Search all sections")
    ids: list[str] | None = Field(default=None, description="Explicit collection UUIDs")
    document_ids_by_collection: dict[str, list[str]] | None = Field(
        default=None,
        description="Optional map collection_id -> document_id list to filter chunks",
    )

    @model_validator(mode="after")
    def normalize(self) -> RagScopeIn:
        if self.all is True:
            return self
        if self.ids:
            return self
        if self.all is None and not self.ids:
            return RagScopeIn(all=True, ids=None, document_ids_by_collection=self.document_ids_by_collection)
        return self


class RagRuntimeProfile(BaseModel):
    """Per-request or saved profile for RAG test / main-chat safe overrides."""

    retrieval_top_k: int = Field(default=8, ge=1, le=30)
    distance_threshold: float | None = Field(
        default=None,
        description="If set, drop chunks with distance > threshold after retrieval",
    )
    llm_enabled: bool = True
    llm_model: str | None = Field(default=None, max_length=256)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=128000)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    system_prompt: str | None = Field(
        default=None,
        max_length=32000,
        description="Override; default is citation-first JSON prompt",
    )
    citations_required: bool = True
    fallback_mode: FallbackMode = "top_chunks"
    json_mode: JsonMode = "none"
    where_document: dict[str, Any] | None = Field(
        default=None,
        description="Chroma where_document filter (MVP: optional)",
    )
    timeout_seconds: float = Field(default=120.0, ge=5.0, le=600.0)
    provider: dict[str, Any] | None = Field(
        default=None,
        description="Optional Polza provider routing object",
    )

    @field_validator("llm_model")
    @classmethod
    def strip_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("system_prompt")
    @classmethod
    def validate_prompt(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        return str(v).strip()

    def effective_system_prompt(self, default: str) -> str:
        return self.system_prompt if self.system_prompt else default
