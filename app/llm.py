"""Polza (OpenAI-compatible) chat completions."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.llm_types import LlmCompletionResult

_log = logging.getLogger(__name__)


class LlmUpstreamError(Exception):
    """Сеть, DNS, таймаут или иной сбой до валидного HTTP-ответа от Polza/LLM.

    Атрибуты:
        host: хост из URL запроса (для логов).
        status_code: 502 (шлюз) или 504 (таймаут) — для HTTP-ответа API.
    """

    def __init__(
        self,
        message: str,
        *,
        host: str | None = None,
        status_code: int = 502,
    ) -> None:
        super().__init__(message)
        self.host = host
        self.status_code = int(status_code)


def _build_chat_payload(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    model_override: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    seed: int | None = None,
    response_format: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_override or settings.polza_chat_model,
        "messages": messages,
        "temperature": (
            float(settings.polza_temperature) if temperature is None else float(temperature)
        ),
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if max_completion_tokens is not None:
        payload["max_completion_tokens"] = max_completion_tokens
    if seed is not None:
        payload["seed"] = seed
    if response_format is not None:
        payload["response_format"] = response_format
    if provider is not None:
        payload["provider"] = provider
    return payload


def chat_completion_with_result(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    model_override: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    seed: int | None = None,
    response_format: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> LlmCompletionResult:
    """POST /chat/completions; returns content + model/provider/usage for diagnostics."""
    if not settings.polza_api_key:
        raise RuntimeError("POLZA_API_KEY is not set")

    url = settings.polza_base_url.rstrip("/") + "/chat/completions"
    payload = _build_chat_payload(
        settings,
        messages,
        model_override=model_override,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        max_completion_tokens=max_completion_tokens,
        seed=seed,
        response_format=response_format,
        provider=provider,
    )
    headers = {
        "Authorization": f"Bearer {settings.polza_api_key}",
        "Content-Type": "application/json",
    }
    parsed = urlparse(url)
    host: str | None = parsed.hostname
    host_s = host if host else "?"
    with httpx.Client(timeout=timeout) as client:
        try:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
        except httpx.ConnectError as e:
            mdl = str(payload.get("model", settings.polza_chat_model))
            _log.exception(
                "Polza connect/DNS failed: host=%s url=%s model=%s",
                host_s,
                url,
                mdl,
            )
            raise LlmUpstreamError(
                "Не удаётся подключиться к LLM: сеть или DNS (хост "
                f"{host_s!r}). Проверьте POLZA_BASE_URL, DNS контейнера/хоста "
                "и что имя разрешается из среды запуска (см. app/docs/troubleshooting.md).",
                host=host,
                status_code=502,
            ) from e
        except httpx.TimeoutException as e:
            mdl = str(payload.get("model", settings.polza_chat_model))
            _log.exception(
                "Polza timeout: host=%s model=%s",
                host_s,
                mdl,
            )
            raise LlmUpstreamError(
                "Превышен таймаут ожидания ответа от LLM. Повторите запрос.",
                host=host,
                status_code=504,
            ) from e
        except httpx.HTTPError as e:
            mdl = str(payload.get("model", settings.polza_chat_model))
            _log.exception(
                "Polza request failed: url=%s model=%s status=%s",
                url,
                mdl,
                getattr(e, "response", None) and getattr(e.response, "status_code", None),
            )
            raise
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("No choices in LLM response")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Invalid message content in LLM response")
    usage: dict[str, Any] = {}
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage = raw_usage
    return LlmCompletionResult(
        content=content,
        model=data.get("model") if isinstance(data.get("model"), str) else None,
        provider=data.get("provider") if isinstance(data.get("provider"), str) else None,
        usage=usage,
        raw=data if isinstance(data, dict) else {},
    )


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    """POST /chat/completions; returns assistant message content (legacy)."""
    return chat_completion_with_result(settings, messages).content


def parse_json_response(raw: str) -> dict[str, Any]:
    """Extract JSON object from model output (handles ```json fences)."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)
