"""Unit tests for in-memory rate limit helpers."""

from __future__ import annotations

import time

import pytest

from app.rate_limits import (
    LlmRateLimitExceeded,
    RateLimitExceeded,
    consume_llm_min_interval_or_raise,
    record_sliding_or_raise,
)


def test_sliding_window_blocks_after_bucket_full() -> None:
    bucket: dict = {}
    key = "k1"
    record_sliding_or_raise(bucket, key, window_sec=10.0, max_events=2)
    record_sliding_or_raise(bucket, key, window_sec=10.0, max_events=2)
    with pytest.raises(RateLimitExceeded):
        record_sliding_or_raise(bucket, key, window_sec=10.0, max_events=2)


def test_llm_min_interval_blocks_immediate_repeat() -> None:
    consume_llm_min_interval_or_raise("subj-a", 500)
    with pytest.raises(LlmRateLimitExceeded):
        consume_llm_min_interval_or_raise("subj-a", 500)
    # other subject independent
    consume_llm_min_interval_or_raise("subj-b", 500)


def test_llm_min_interval_allows_after_sleep() -> None:
    consume_llm_min_interval_or_raise("subj-c", 50)
    time.sleep(0.07)
    consume_llm_min_interval_or_raise("subj-c", 50)


def test_disabled_sliding_when_max_zero() -> None:
    bucket: dict = {}
    record_sliding_or_raise(bucket, "x", window_sec=1.0, max_events=0)
    assert bucket == {}
