"""cuk_assistant/core/protocols/llm.py

Abstract protocol interface for generative LLM providers.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cuk_assistant.schemas.llm import AnswerWithCitations


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Abstract contract for generative LLM providers."""

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        """Generate a structured AnswerWithCitations response."""
        ...

    @property
    def provider_name(self) -> str:
        """Identifier of active provider (e.g. 'google_gemini_flash', 'groq_llama_3.3')."""
        ...


__all__ = ["LLMClientProtocol"]
