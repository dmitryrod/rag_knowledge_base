"""In-memory rate limits (single process)."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimitExceeded(Exception):
    """Too many attempts in sliding window."""

    def __init__(self, retry_after_sec: float) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_sec = max(0.0, float(retry_after_sec))


class LlmRateLimitExceeded(Exception):
    """Minimum interval between LLM calls not met."""

    def __init__(self, retry_after_sec: float) -> None:
        super().__init__("llm rate limit exceeded")
        self.retry_after_sec = max(0.0, float(retry_after_sec))


_lock = threading.Lock()
_login_events: dict[str, deque[float]] = {}
_post_events: dict[str, deque[float]] = {}
_llm_last_mono: dict[str, float] = {}


def _prune(queue: deque[float], now_mono: float, window_sec: float) -> None:
    cutoff = now_mono - window_sec
    while queue and queue[0] < cutoff:
        queue.popleft()


def record_sliding_or_raise(
    bucket: dict[str, deque[float]],
    key: str,
    *,
    window_sec: float,
    max_events: int,
) -> None:
    """Register one event or raise RateLimitExceeded (retry_after = time to next slot)."""
    if max_events <= 0:
        return
    now = time.monotonic()
    with _lock:
        q = bucket.setdefault(key, deque())
        _prune(q, now, window_sec)
        if len(q) >= max_events:
            oldest = q[0]
            retry_after = window_sec - (now - oldest)
            raise RateLimitExceeded(retry_after if retry_after > 0 else 0.01)
        q.append(now)


def consume_llm_min_interval_or_raise(subject_key: str, min_interval_ms: int) -> None:
    """Block next LLM call until min_interval_ms elapsed since last call for this key."""
    if min_interval_ms <= 0 or not subject_key:
        return
    gap = min_interval_ms / 1000.0
    now = time.monotonic()
    with _lock:
        last = _llm_last_mono.get(subject_key)
        if last is not None:
            elapsed = now - last
            if elapsed < gap:
                raise LlmRateLimitExceeded(gap - elapsed)
        _llm_last_mono[subject_key] = now


def register_auth_login_attempt_or_raise(client_ip: str, window_sec: float, max_attempts: int) -> None:
    """Limit POST /v1/auth/login per client IP (sliding window). max_attempts<=0 disables."""
    if max_attempts <= 0:
        return
    record_sliding_or_raise(
        _login_events,
        f"login:{client_ip}",
        window_sec=window_sec,
        max_events=max_attempts,
    )
