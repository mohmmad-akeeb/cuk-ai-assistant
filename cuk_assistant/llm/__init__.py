"""cuk_assistant/llm

Generative LLM Subsystem: Free-Tier Adapters, Protocol Schemas & Circuit Breaker Pool.
"""

from cuk_assistant.llm.gemini_client import (
    GeminiClient,
    LLMError,
    LLMFormatError,
    RateLimitError,
    ServiceUnavailableError,
    format_context_chunks,
)
from cuk_assistant.llm.groq_client import GroqClient
from cuk_assistant.llm.pool import CircuitBreaker, CircuitState, LLMProviderPool

# Architectural alias
LLMPool = LLMProviderPool

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "GeminiClient",
    "GroqClient",
    "LLMError",
    "LLMFormatError",
    "LLMPool",
    "LLMProviderPool",
    "RateLimitError",
    "ServiceUnavailableError",
    "format_context_chunks",
]
