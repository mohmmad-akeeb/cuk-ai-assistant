"""cuk_assistant/llm/pool.py

LLM Provider Pool, Round-Robin Load Balancer & Circuit-Breaker Failover Subsystem.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from enum import StrEnum
from typing import Any

import httpx

from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.llm.gemini_client import (
    LLMError,
    LLMFormatError,
    RateLimitError,
    ServiceUnavailableError,
)
from cuk_assistant.schemas.llm import AnswerWithCitations

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    """Circuit breaker operational states."""

    CLOSED = "CLOSED"  # Healthy, passing traffic
    OPEN = "OPEN"  # Tripped, traffic blocked
    HALF_OPEN = "HALF_OPEN"  # Testing single probe request


class CircuitBreaker:
    """Per-provider circuit breaker state machine."""

    def __init__(
        self,
        provider_name: str,
        cooloff_seconds: float = 60.0,
        failure_threshold: int = 1,
        time_provider: Callable[[], float] = time.time,
    ) -> None:
        self.provider_name = provider_name
        self.cooloff_seconds = cooloff_seconds
        self.failure_threshold = failure_threshold
        self._time_provider = time_provider

        self._state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self.last_success_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Current dynamic state accounting for elapsed cooloff time."""
        if self._state == CircuitState.OPEN:
            now = self._time_provider()
            if now - self.last_failure_time >= self.cooloff_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def is_available(self) -> bool:
        """Check if provider can accept a request."""
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful request execution."""
        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_success_time = self._time_provider()

    def record_failure(self, force_open: bool = True) -> None:
        """Record a failed request execution (e.g. HTTP 429 or 503)."""
        now = self._time_provider()
        self.failure_count += 1
        self.last_failure_time = now

        if force_open or self.failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker tripped OPEN for provider '%s' (failure_count=%d, cooloff=%.1fs)",
                self.provider_name,
                self.failure_count,
                self.cooloff_seconds,
            )

    def trip(self) -> None:
        """Explicitly trip the circuit breaker OPEN."""
        self.record_failure(force_open=True)

    def reset(self) -> None:
        """Reset breaker to healthy CLOSED state."""
        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0


class LLMProviderPool:
    """Pool manager providing round-robin load-balancing and 429 failover."""

    def __init__(
        self,
        providers: Sequence[LLMClientProtocol],
        cooloff_seconds: float = 60.0,
        failure_threshold: int = 1,
        time_provider: Callable[[], float] = time.time,
    ) -> None:
        if not providers:
            raise ValueError("LLMProviderPool requires at least one provider.")

        self.providers: list[LLMClientProtocol] = list(providers)
        self.cooloff_seconds = cooloff_seconds
        self.failure_threshold = failure_threshold
        self._time_provider = time_provider

        self._breakers: dict[str, CircuitBreaker] = {
            p.provider_name: CircuitBreaker(
                provider_name=p.provider_name,
                cooloff_seconds=cooloff_seconds,
                failure_threshold=failure_threshold,
                time_provider=time_provider,
            )
            for p in self.providers
        }
        self._current_index: int = 0

    @property
    def provider_name(self) -> str:
        """Pool identifier."""
        return "provider_pool"

    def get_breaker(self, provider_name: str) -> CircuitBreaker:
        """Retrieve circuit breaker for a named provider."""
        if provider_name not in self._breakers:
            raise KeyError(f"Provider '{provider_name}' not found in pool.")
        return self._breakers[provider_name]

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Inspection snapshot of all providers and their circuit breaker states."""
        return {
            name: {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "last_failure_time": breaker.last_failure_time,
                "last_success_time": breaker.last_success_time,
                "is_available": breaker.is_available(),
            }
            for name, breaker in self._breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers to healthy CLOSED state."""
        for breaker in self._breakers.values():
            breaker.reset()

    def _select_next_healthy_provider(
        self,
        skip_names: set[str] | None = None,
    ) -> tuple[LLMClientProtocol, CircuitBreaker]:
        """Select next healthy provider using round-robin rotation."""
        num_providers = len(self.providers)
        skipped = skip_names or set()

        for i in range(num_providers):
            candidate_index = (self._current_index + i) % num_providers
            candidate = self.providers[candidate_index]
            breaker = self._breakers[candidate.provider_name]

            if candidate.provider_name in skipped:
                continue

            if breaker.is_available():
                self._current_index = (candidate_index + 1) % num_providers
                return candidate, breaker

        raise ServiceUnavailableError(
            message="All LLM providers in pool are currently unavailable (circuits OPEN).",
            diagnostic_code="LLM_EXTRACTION_FAILURE",
        )

    def _should_trip_breaker(self, exc: Exception) -> bool:
        """Determine if an exception should trip the breaker for the provider."""
        if isinstance(exc, (RateLimitError, ServiceUnavailableError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (401, 403, 404, 429, 500, 502, 503, 504)
        return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        """Generate structured answer with automatic round-robin and 429 failover."""
        tried_providers: set[str] = set()
        last_exception: Exception | None = None

        for _ in range(len(self.providers)):
            try:
                provider, breaker = self._select_next_healthy_provider(skip_names=tried_providers)
            except ServiceUnavailableError as pool_exc:
                if last_exception is not None:
                    raise last_exception from pool_exc
                raise pool_exc from None

            tried_providers.add(provider.provider_name)
            try:
                answer = await provider.generate_answer(
                    query=query,
                    context_chunks=context_chunks,
                    chat_history=chat_history,
                    system_persona=system_persona,
                )
                breaker.record_success()
                return answer
            except Exception as exc:
                last_exception = exc
                if self._should_trip_breaker(exc):
                    breaker.record_failure(force_open=True)
                    logger.warning(
                        "Provider '%s' failed with %s; failing over to next provider.",
                        provider.provider_name,
                        type(exc).__name__,
                    )
                    continue
                # If it's a non-failover error (e.g. bad user payload), propagate immediately
                raise

        raise ServiceUnavailableError(
            message=f"All LLM providers exhausted: {last_exception}",
            diagnostic_code="LLM_EXTRACTION_FAILURE",
        )

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated tokens with transparent failover before first token yield."""
        tried_providers: set[str] = set()
        last_exception: Exception | None = None

        for _ in range(len(self.providers)):
            try:
                provider, breaker = self._select_next_healthy_provider(skip_names=tried_providers)
            except ServiceUnavailableError as pool_exc:
                if last_exception is not None:
                    raise last_exception from pool_exc
                raise pool_exc from None

            tried_providers.add(provider.provider_name)
            stream_iter = provider.generate_stream(
                query=query,
                context_chunks=context_chunks,
                chat_history=chat_history,
                system_persona=system_persona,
            )

            try:
                # Probe first chunk to verify stream initialized without HTTP 429/503
                first_chunk = await anext(stream_iter)
            except (StopAsyncIteration, StopIteration):
                breaker.record_success()
                return
            except Exception as exc:
                last_exception = exc
                if self._should_trip_breaker(exc):
                    breaker.record_failure(force_open=True)
                    logger.warning(
                        "Streaming for provider '%s' failed at start: %s; failing over.",
                        provider.provider_name,
                        type(exc).__name__,
                    )
                    continue
                raise

            # Successful start
            breaker.record_success()
            yield first_chunk

            async for chunk in stream_iter:
                yield chunk
            return

        raise ServiceUnavailableError(
            message=f"All LLM providers exhausted during stream initialization: {last_exception}",
            diagnostic_code="LLM_EXTRACTION_FAILURE",
        )


# Runtime protocol check
_: type[LLMClientProtocol] = LLMProviderPool

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "LLMError",
    "LLMFormatError",
    "LLMProviderPool",
    "RateLimitError",
    "ServiceUnavailableError",
]
