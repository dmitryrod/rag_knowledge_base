"""Merge RAG runtime profile into Settings; validate safe main-chat application."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, is_polza_model_allowlisted
from app.rag_profile import RagRuntimeProfile

DEFAULT_SYSTEM_PROMPT = (
    "Ты корпоративный ассистент. Отвечай ТОЛЬКО на основе CONTEXT. "
    "Если фрагменты в CONTEXT относятся к вопросу — ответь по ним и обязательно заполни citations "
    "(chunk_id из CONTEXT, quote — короткая выдержка). "
    "Фразу «НЕ НАЙДЕНО В БАЗЕ» используй только если ни один фрагмент CONTEXT не релевантен вопросу; "
    "в спорных случаях лучше оперись на ближайшие по смыслу фрагменты и укажи citations. "
    "Верни только валидный JSON без markdown-обёртки: поля answer (markdown), citations (массив {chunk_id, quote})."
)


class MainChatRuntimeSnapshot(BaseModel):
    """Only safe, index-independent fields for persisting in rag_runtime_settings."""

    retrieval_top_k: int = Field(default=8, ge=1, le=30)
    distance_threshold: float | None = None
    llm_enabled: bool = True
    llm_model: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    seed: int | None = None
    system_prompt: str | None = None
    citations_required: bool = True
    fallback_mode: str = "top_chunks"
    timeout_seconds: float = Field(default=120.0, ge=5.0, le=600.0)
    provider: dict[str, Any] | None = None

    @classmethod
    def from_profile(cls, p: RagRuntimeProfile) -> MainChatRuntimeSnapshot:
        return cls(
            retrieval_top_k=p.retrieval_top_k,
            distance_threshold=p.distance_threshold,
            llm_enabled=p.llm_enabled,
            llm_model=p.llm_model,
            temperature=p.temperature,
            top_p=p.top_p,
            max_tokens=p.max_tokens,
            seed=p.seed,
            system_prompt=p.system_prompt,
            citations_required=p.citations_required,
            fallback_mode=p.fallback_mode,
            timeout_seconds=p.timeout_seconds,
            provider=p.provider,
        )


def profile_to_settings_patch(profile: RagRuntimeProfile) -> dict[str, Any]:
    """Fields on Settings to override via model_copy."""
    patch: dict[str, Any] = {"retrieval_top_k": profile.retrieval_top_k}
    if profile.llm_model:
        patch["polza_chat_model"] = profile.llm_model
    patch["polza_temperature"] = profile.temperature
    return patch


def merge_settings_with_profile(base: Settings, profile: RagRuntimeProfile) -> Settings:
    """Return new Settings with retrieval/model/temperature from profile."""
    patch = profile_to_settings_patch(profile)
    return base.model_copy(update=patch)


def validate_main_chat_apply(base: Settings, profile: RagRuntimeProfile) -> None:
    """Raise ValueError if profile cannot be applied to main chat."""
    if profile.retrieval_top_k < 1 or profile.retrieval_top_k > 30:
        msg = "retrieval_top_k must be 1..30"
        raise ValueError(msg)
    if profile.json_mode not in ("none",):
        msg = "main chat: json_mode must be none"
        raise ValueError(msg)
    if profile.where_document:
        msg = "main chat: where_document not allowed in saved overrides"
        raise ValueError(msg)
    if not profile.citations_required:
        msg = "main chat: citations_required must be true for production chat"
        raise ValueError(msg)
    if profile.fallback_mode not in ("top_chunks",):
        msg = "main chat: only fallback_mode=top_chunks supported"
        raise ValueError(msg)
    if profile.llm_model:
        # Simulate merged settings for allowlist check
        merged = base.model_copy(
            update={"polza_chat_model": profile.llm_model, "polza_temperature": profile.temperature}
        )
        if base.polza_api_key and base.allow_llm_egress and not is_polza_model_allowlisted(merged):
            msg = "llm_model not in POLZA_CHAT_MODEL_ALLOWLIST"
            raise ValueError(msg)


def snapshot_to_profile(snap: MainChatRuntimeSnapshot) -> RagRuntimeProfile:
    return RagRuntimeProfile(
        retrieval_top_k=snap.retrieval_top_k,
        distance_threshold=snap.distance_threshold,
        llm_enabled=snap.llm_enabled,
        llm_model=snap.llm_model,
        temperature=snap.temperature,
        top_p=snap.top_p,
        max_tokens=snap.max_tokens,
        max_completion_tokens=None,
        seed=snap.seed,
        system_prompt=snap.system_prompt,
        citations_required=snap.citations_required,
        fallback_mode=snap.fallback_mode,  # type: ignore[arg-type]
        json_mode="none",
        where_document=None,
        timeout_seconds=snap.timeout_seconds,
        provider=snap.provider,
    )


def load_main_chat_profile_json(raw: str | None) -> RagRuntimeProfile | None:
    if not raw or not str(raw).strip():
        return None
    data = json.loads(raw)
    snap = MainChatRuntimeSnapshot.model_validate(data)
    return snapshot_to_profile(snap)


def main_chat_effective_settings(
    base: Settings,
    db: Any,
) -> tuple[Settings, str | None, float | None]:
    """Merge SQLite `rag_runtime_settings` into Settings; gate LLM on profile.llm_enabled."""
    row = db.get_rag_runtime_settings() if db else None
    if not row:
        return base, None, None
    prof = load_main_chat_profile_json(str(row.get("profile_snapshot_json") or ""))
    if not prof:
        return base, None, None
    merged = merge_settings_with_profile(base, prof)
    if not prof.llm_enabled:
        merged = merged.model_copy(update={"allow_llm_egress": False})
    return merged, prof.system_prompt, prof.distance_threshold
