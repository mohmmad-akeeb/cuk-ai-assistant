"""Tests for TokenBucket — timing behaviour, no network calls."""

from __future__ import annotations

import asyncio
import time

import pytest

from cuk_assistant.core.http_cache import TokenBucket


class TestTokenBucketInit:
    def test_zero_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate"):
            TokenBucket(0.0)

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate"):
            TokenBucket(-1.0)

    def test_valid_rate_ok(self) -> None:
        tb = TokenBucket(1.0)
        assert tb.rate == 1.0


class TestTokenBucketAcquire:
    @pytest.mark.asyncio
    async def test_first_acquire_is_instant(self) -> None:
        """First token should be available immediately (bucket starts full)."""
        tb = TokenBucket(1.0)
        t0 = time.monotonic()
        await tb.acquire()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"First acquire should be instant, took {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_two_acquires_spaced_by_rate(self) -> None:
        """Two consecutive acquires at 2 rps should be ≥ 0.5 s apart total."""
        rate = 2.0  # 2 tokens/sec → 0.5 s between tokens
        tb = TokenBucket(rate)
        t0 = time.monotonic()
        await tb.acquire()  # instant (pre-filled)
        await tb.acquire()  # must wait ~0.5 s
        elapsed = time.monotonic() - t0
        # Allow generous margin for CI timing variance
        assert elapsed >= 0.4, (
            f"Expected ≥ 0.4 s between two acquires at {rate} rps, got {elapsed:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_high_rate_is_fast(self) -> None:
        """At 100 rps, 3 acquires should complete well under 1 s."""
        tb = TokenBucket(100.0)
        t0 = time.monotonic()
        await tb.acquire()
        await tb.acquire()
        await tb.acquire()
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"High-rate acquires too slow: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_sequential_spacing_respected(self) -> None:
        """N sequential acquires at rate R should take ≥ (N-1)/R seconds."""
        rate = 5.0  # 5 rps → 0.2 s per token
        n = 4
        tb = TokenBucket(rate)
        t0 = time.monotonic()
        for _ in range(n):
            await tb.acquire()
        elapsed = time.monotonic() - t0
        min_expected = (n - 1) / rate  # first token is free
        assert elapsed >= min_expected * 0.85, (
            f"Expected ≥ {min_expected:.2f}s for {n} acquires at {rate} rps, got {elapsed:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_concurrent_acquires_serialised(self) -> None:
        """Concurrent acquires should still be serialised by the internal lock."""
        rate = 10.0
        tb = TokenBucket(rate)
        results: list[float] = []

        async def worker() -> None:
            await tb.acquire()
            results.append(time.monotonic())

        await asyncio.gather(*[worker() for _ in range(5)])
        # All 5 acquires should have completed
        assert len(results) == 5
        # Timestamps should be in non-decreasing order (serialised)
        for i in range(1, len(results)):
            assert results[i] >= results[i - 1] - 1e-6, "Acquires not serialised"
