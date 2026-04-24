"""Polza (OpenAI-compatible) chat completions."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import Settings


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
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
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
