"""Unit tests for LLM Provider Pool, Round-Robin Load Balancing & Circuit Breaker (Task 4.3).

Tests:
1. Protocol conformance.
2. Circuit breaker state machine (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
3. Round-robin rotation between healthy providers.
4. Transparent instant failover on HTTP 429 / 503 without raising exceptions to caller.
5. Cooloff expiration and half-open probing.
6. Exhaustion handling when all providers are unavailable.
7. Streaming transparent failover.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.llm.gemini_client import (
    RateLimitError,
    ServiceUnavailableError,
)
from cuk_assistant.llm.pool import (
    CircuitBreaker,
    CircuitState,
    LLMProviderPool,
)
from cuk_assistant.schemas.llm import AnswerWithCitations


class MockLLMClient:
    """Mock LLM provider for pool testing."""

    def __init__(
        self,
        name: str,
        answer_text: str = "Mock answer",
        fail_with: Exception | None = None,
        fail_stream_with: Exception | None = None,
    ) -> None:
        self.name = name
        self.answer_text = answer_text
        self.fail_with = fail_with
        self.fail_stream_with = fail_stream_with
        self.call_count: int = 0
        self.stream_call_count: int = 0

    @property
    def provider_name(self) -> str:
        return self.name

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with
        return AnswerWithCitations(
            direct_answer=f"[{self.name}] {self.answer_text}",
            quoted_snippets=["sample quote"],
            citation_chunk_ids=["chunk_1"],
            confidence_score=0.99,
        )

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AsyncIterator[str]:
        self.stream_call_count += 1
        if self.fail_stream_with is not None:
            raise self.fail_stream_with
        for token in [f"[{self.name}] ", "token1 ", "token2"]:
            yield token


class FakeClock:
    """Controllable clock for circuit breaker time testing."""

    def __init__(self, initial_time: float = 1000.0) -> None:
        self.current_time = initial_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


class TestCircuitBreakerStateMachine:
    """Test state transitions of individual CircuitBreaker."""

    def test_initial_state_closed(self) -> None:
        clock = FakeClock()
        cb = CircuitBreaker("provider_a", cooloff_seconds=60.0, time_provider=clock.time)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available() is True
        assert cb.failure_count == 0

    def test_record_failure_trips_to_open(self) -> None:
        clock = FakeClock()
        cb = CircuitBreaker("provider_a", cooloff_seconds=60.0, time_provider=clock.time)
        cb.record_failure(force_open=True)

        assert cb.state == CircuitState.OPEN
        assert cb.is_available() is False
        assert cb.failure_count == 1
        assert cb.last_failure_time == clock.time()

    def test_cooloff_advancement_transitions_to_half_open(self) -> None:
        clock = FakeClock(100.0)
        cb = CircuitBreaker("provider_a", cooloff_seconds=60.0, time_provider=clock.time)
        cb.record_failure(force_open=True)

        # Still within cooloff
        clock.advance(30.0)
        assert cb.state == CircuitState.OPEN
        assert cb.is_available() is False

        # Past cooloff
        clock.advance(31.0)  # total 61s
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_available() is True

    def test_half_open_probe_success_resets_to_closed(self) -> None:
        clock = FakeClock(100.0)
        cb = CircuitBreaker("provider_a", cooloff_seconds=60.0, time_provider=clock.time)
        cb.record_failure(force_open=True)
        clock.advance(65.0)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb.is_available() is True
        assert cb.failure_count == 0

    def test_half_open_probe_failure_trips_back_to_open(self) -> None:
        clock = FakeClock(100.0)
        cb = CircuitBreaker("provider_a", cooloff_seconds=60.0, time_provider=clock.time)
        cb.record_failure(force_open=True)
        clock.advance(65.0)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure(force_open=True)

        assert cb.state == CircuitState.OPEN
        assert cb.is_available() is False
        assert cb.last_failure_time == clock.time()


class TestLLMProviderPool:
    """Test LLMProviderPool load balancing and 429 failover."""

    def test_protocol_conformance(self) -> None:
        p1 = MockLLMClient("p1")
        pool = LLMProviderPool([p1])
        assert isinstance(pool, LLMClientProtocol)
        assert pool.provider_name == "provider_pool"

    def test_requires_at_least_one_provider(self) -> None:
        with pytest.raises(ValueError):
            LLMProviderPool([])

    @pytest.mark.asyncio
    async def test_round_robin_alternation_healthy_providers(self) -> None:
        p1 = MockLLMClient("gemini")
        p2 = MockLLMClient("groq")
        clock = FakeClock()
        pool = LLMProviderPool([p1, p2], time_provider=clock.time)

        # Call 1 -> p1 (gemini)
        res1 = await pool.generate_answer("q1", [], [])
        assert "[gemini]" in res1.direct_answer
        assert p1.call_count == 1
        assert p2.call_count == 0

        # Call 2 -> p2 (groq)
        res2 = await pool.generate_answer("q2", [], [])
        assert "[groq]" in res2.direct_answer
        assert p1.call_count == 1
        assert p2.call_count == 1

        # Call 3 -> p1 (gemini)
        res3 = await pool.generate_answer("q3", [], [])
        assert "[gemini]" in res3.direct_answer
        assert p1.call_count == 2
        assert p2.call_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_429_instant_transparent_failover(self) -> None:
        # p1 (gemini) fails with HTTP 429 RateLimitError
        p1 = MockLLMClient("gemini", fail_with=RateLimitError("Quota 429 exceeded"))
        # p2 (groq) healthy
        p2 = MockLLMClient("groq", answer_text="Groq fallback answer")

        clock = FakeClock()
        pool = LLMProviderPool([p1, p2], cooloff_seconds=60.0, time_provider=clock.time)

        # Execution should succeed seamlessly via p2 without raising error to user
        answer = await pool.generate_answer("Admissions deadline?", [], [])
        assert "[groq]" in answer.direct_answer
        assert p1.call_count == 1
        assert p2.call_count == 1

        # Breaker for p1 must be tripped OPEN
        breaker_p1 = pool.get_breaker("gemini")
        assert breaker_p1.state == CircuitState.OPEN
        assert breaker_p1.is_available() is False

        # Subsequent call must immediately route to healthy p2 (skipping tripped p1)
        answer2 = await pool.generate_answer("Next query", [], [])
        assert "[groq]" in answer2.direct_answer
        assert p1.call_count == 1  # p1 was not called because its circuit is OPEN!
        assert p2.call_count == 2

    @pytest.mark.asyncio
    async def test_cooloff_probing_restores_tripped_provider(self) -> None:
        p1 = MockLLMClient("gemini", fail_with=RateLimitError("Quota 429"))
        p2 = MockLLMClient("groq", answer_text="Groq response")
        clock = FakeClock(1000.0)
        pool = LLMProviderPool([p1, p2], cooloff_seconds=60.0, time_provider=clock.time)

        # Trip p1
        await pool.generate_answer("q1", [], [])
        assert pool.get_breaker("gemini").state == CircuitState.OPEN

        # Advance time by 65s (past 60s cooloff)
        clock.advance(65.0)
        assert pool.get_breaker("gemini").state == CircuitState.HALF_OPEN

        # Fix p1
        p1.fail_with = None
        p1.answer_text = "Gemini restored"

        # Next call probes p1 and succeeds
        answer = await pool.generate_answer("q2", [], [])
        assert "[gemini]" in answer.direct_answer
        assert pool.get_breaker("gemini").state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_all_providers_failing_raises_service_unavailable(self) -> None:
        p1 = MockLLMClient("gemini", fail_with=RateLimitError("Gemini 429"))
        p2 = MockLLMClient("groq", fail_with=ServiceUnavailableError("Groq 503"))
        clock = FakeClock()
        pool = LLMProviderPool([p1, p2], time_provider=clock.time)

        with pytest.raises(ServiceUnavailableError) as exc_info:
            await pool.generate_answer("Query", [], [])

        assert exc_info.value.diagnostic_code == "LLM_EXTRACTION_FAILURE"
        assert pool.get_breaker("gemini").state == CircuitState.OPEN
        assert pool.get_breaker("groq").state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_generate_stream_failover_on_429(self) -> None:
        p1 = MockLLMClient("gemini", fail_stream_with=RateLimitError("Gemini stream 429"))
        p2 = MockLLMClient("groq")
        clock = FakeClock()
        pool = LLMProviderPool([p1, p2], time_provider=clock.time)

        tokens: list[str] = []
        async for token in pool.generate_stream("Stream query", [], []):
            tokens.append(token)

        assert tokens == ["[groq] ", "token1 ", "token2"]
        assert pool.get_breaker("gemini").state == CircuitState.OPEN
        assert pool.get_breaker("groq").state == CircuitState.CLOSED

    def test_pool_status_inspection_and_reset(self) -> None:
        p1 = MockLLMClient("gemini")
        p2 = MockLLMClient("groq")
        clock = FakeClock()
        pool = LLMProviderPool([p1, p2], time_provider=clock.time)

        status = pool.get_status()
        assert "gemini" in status
        assert "groq" in status
        assert status["gemini"]["state"] == "CLOSED"
        assert status["gemini"]["is_available"] is True

        # Trip gemini
        pool.get_breaker("gemini").trip()
        assert pool.get_breaker("gemini").state == CircuitState.OPEN

        # Reset all
        pool.reset_all()
        assert pool.get_breaker("gemini").state == CircuitState.CLOSED
