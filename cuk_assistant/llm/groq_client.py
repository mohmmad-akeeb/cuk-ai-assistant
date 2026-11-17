"""cuk_assistant/llm/groq_client.py

Groq Cloud Llama 3.3 70B LLM client adapter using OpenAI-compatible REST API.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.llm.gemini_client import (
    LLMFormatError,
    RateLimitError,
    ServiceUnavailableError,
    format_context_chunks,
)
from cuk_assistant.schemas.llm import AnswerWithCitations


class GroqClient:
    """Direct REST client for Groq Cloud Llama 3.3 70B free tier."""

    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_SYSTEM_PERSONA = (
        "You are the official Central University of Kashmir (CUK) AI Assistant. "
        "Synthesize an accurate, factual answer based strictly on the provided context chunks. "
        "Do not invent facts. Every factual statement must cite exact verbatim substrings "
        "from the context chunks along with their chunk IDs."
    )

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model
        self.base_url = base_url
        self._custom_client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "groq_llama_3.3"

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        if self._owned_client is None or self._owned_client.is_closed:
            self._owned_client = httpx.AsyncClient(timeout=self._timeout)
        return self._owned_client

    async def aclose(self) -> None:
        """Close internally managed HTTP client."""
        if self._owned_client is not None and not self._owned_client.is_closed:
            await self._owned_client.aclose()
            self._owned_client = None

    async def __aenter__(self) -> GroqClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    def _build_messages(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
        enforce_json: bool = True,
    ) -> list[dict[str, str]]:
        persona = system_persona or self.DEFAULT_SYSTEM_PERSONA
        if enforce_json:
            system_content = (
                f"{persona}\n\n"
                "CRITICAL: You MUST respond ONLY with a single valid JSON object matching this schema:\n"
                "{\n"
                '  "direct_answer": "Direct factual synthesized response",\n'
                '  "quoted_snippets": ["Exact verbatim substring from context chunks"],\n'
                '  "citation_chunk_ids": ["chunk_id backing quoted_snippets"],\n'
                '  "confidence_score": 1.0\n'
                "}\n"
                "Do NOT wrap output in markdown codeblocks (no ```json). "
                "Ensure quoted_snippets are 100% exact character-for-character copies of text from context chunks."
            )
        else:
            system_content = persona

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant", "system"):
                messages.append({"role": role, "content": content})

        context_text = format_context_chunks(context_chunks)
        user_turn_content = (
            f"Context Chunks:\n{context_text}\n\n"
            f"User Query:\n{query}\n\n"
            "Synthesize your response strictly based on the context chunks above."
        )
        messages.append({"role": "user", "content": user_turn_content})
        return messages

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        """Generate structured AnswerWithCitations using Groq Llama 3.3 REST API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        messages = self._build_messages(
            query=query,
            context_chunks=context_chunks,
            chat_history=chat_history,
            system_persona=system_persona,
            enforce_json=True,
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        client = self._get_client()
        try:
            resp = await client.post(self.base_url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(f"Groq connection error: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitError(f"Groq 429 Rate Limit Exceeded: {resp.text}")
        if resp.status_code in (502, 503, 504):
            raise ServiceUnavailableError(
                f"Groq Service Unavailable ({resp.status_code}): {resp.text}"
            )
        resp.raise_for_status()

        try:
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMFormatError("Groq response contained no choices")
            content = choices[0].get("message", {}).get("content", "")

            # Strip possible markdown codeblocks if model wrapped JSON
            cleaned_text = content.strip()
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines).strip()

            parsed = json.loads(cleaned_text)
            return AnswerWithCitations.model_validate(parsed)
        except LLMFormatError:
            raise
        except Exception as exc:
            raise LLMFormatError(
                f"Failed to parse AnswerWithCitations from Groq response: {exc}"
            ) from exc

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated text tokens using Groq completions streaming."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        messages = self._build_messages(
            query=query,
            context_chunks=context_chunks,
            chat_history=chat_history,
            system_persona=system_persona,
            enforce_json=False,
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
        }

        client = self._get_client()
        try:
            async with client.stream("POST", self.base_url, json=payload, headers=headers) as resp:
                if resp.status_code == 429:
                    body = await resp.aread()
                    raise RateLimitError(
                        f"Groq 429 Rate Limit Exceeded: {body.decode(errors='replace')}"
                    )
                if resp.status_code in (502, 503, 504):
                    body = await resp.aread()
                    raise ServiceUnavailableError(
                        f"Groq Service Unavailable ({resp.status_code}): {body.decode(errors='replace')}"
                    )
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    raw_data = line[5:].strip()
                    if not raw_data or raw_data == "[DONE]":
                        continue
                    try:
                        chunk_obj = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk_obj.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(f"Groq connection error: {exc}") from exc


# Runtime protocol check
_: type[LLMClientProtocol] = GroqClient

__all__ = ["GroqClient"]
