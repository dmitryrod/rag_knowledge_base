"""Polza (OpenAI-compatible) chat completions."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings

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


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    """POST /chat/completions; returns assistant message content."""
    if not settings.polza_api_key:
        raise RuntimeError("POLZA_API_KEY is not set")

    url = settings.polza_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.polza_chat_model,
        "messages": messages,
        "temperature": settings.polza_temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.polza_api_key}",
        "Content-Type": "application/json",
    }
    parsed = urlparse(url)
    host: str | None = parsed.hostname
    host_s = host if host else "?"
    with httpx.Client(timeout=120.0) as client:
        try:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
        except httpx.ConnectError as e:
            _log.exception(
                "Polza connect/DNS failed: host=%s url=%s model=%s",
                host_s,
                url,
                settings.polza_chat_model,
            )
            raise LlmUpstreamError(
                "Не удаётся подключиться к LLM: сеть или DNS (хост "
                f"{host_s!r}). Проверьте POLZA_BASE_URL, DNS контейнера/хоста "
                "и что имя разрешается из среды запуска (см. app/docs/troubleshooting.md).",
                host=host,
                status_code=502,
            ) from e
        except httpx.TimeoutException as e:
            _log.exception(
                "Polza timeout: host=%s model=%s",
                host_s,
                settings.polza_chat_model,
            )
            raise LlmUpstreamError(
                "Превышен таймаут ожидания ответа от LLM. Повторите запрос.",
                host=host,
                status_code=504,
            ) from e
        except httpx.HTTPError as e:
            _log.exception(
                "Polza request failed: url=%s model=%s status=%s",
                url,
                settings.polza_chat_model,
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
    return content


def parse_json_response(raw: str) -> dict[str, Any]:
    """Extract JSON object from model output (handles ```json fences)."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)
