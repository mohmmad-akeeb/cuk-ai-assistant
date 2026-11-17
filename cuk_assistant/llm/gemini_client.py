"""cuk_assistant/llm/gemini_client.py

Google Gemini Flash LLM client adapter using direct REST API.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.schemas.llm import AnswerWithCitations


class LLMError(Exception):
    """Base exception for LLM subsystem errors."""

    def __init__(self, message: str, diagnostic_code: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


class RateLimitError(LLMError):
    """HTTP 429 Rate limit or quota exhaustion."""

    def __init__(self, message: str = "Rate limit exceeded (HTTP 429)") -> None:
        super().__init__(message, diagnostic_code="LLM_EXTRACTION_FAILURE")


class ServiceUnavailableError(LLMError):
    """HTTP 503 or service unreachable."""

    def __init__(
        self,
        message: str = "Service unavailable",
        diagnostic_code: str = "LLM_EXTRACTION_FAILURE",
    ) -> None:
        super().__init__(message, diagnostic_code=diagnostic_code)


class LLMFormatError(LLMError):
    """LLM response format violation or invalid JSON schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message, diagnostic_code="LLM_FORMAT_VIOLATION")


def format_context_chunks(chunks: list[dict[str, Any]] | list[Any]) -> str:
    """Format context chunks with chunk IDs and breadcrumbs into prompt text."""
    if not chunks:
        return "No relevant context chunks retrieved."

    formatted: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            chunk_id = chunk.get("chunk_id", "unknown_chunk")
            heading_path = chunk.get("heading_path") or []
            section_heading = chunk.get("section_heading")
            text = chunk.get("text_content") or chunk.get("text") or ""
            doc_id = chunk.get("doc_id", "")
        else:
            chunk_id = getattr(chunk, "chunk_id", "unknown_chunk")
            heading_path = getattr(chunk, "heading_path", []) or []
            section_heading = getattr(chunk, "section_heading", None)
            text = getattr(chunk, "text_content", None) or getattr(chunk, "text", "") or ""
            doc_id = getattr(chunk, "doc_id", "")

        if heading_path:
            breadcrumb = " > ".join(str(h) for h in heading_path)
        elif section_heading:
            breadcrumb = str(section_heading)
        elif doc_id:
            breadcrumb = str(doc_id)
        else:
            breadcrumb = "General"

        formatted.append(f"--- CHUNK ID: {chunk_id} [Path: {breadcrumb}] ---\n{text}\n")

    return "\n".join(formatted)


class GeminiClient:
    """Direct REST client for Google Gemini Flash free tier."""

    DEFAULT_MODEL = "gemini-2.0-flash"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
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
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self._base_url = base_url
        self._custom_client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "google_gemini_flash"

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

    async def __aenter__(self) -> GeminiClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    def _build_contents(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []

        # Add conversation history
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                {
                    "role": gemini_role,
                    "parts": [{"text": content}],
                }
            )

        # Append current user turn with context chunks
        context_text = format_context_chunks(context_chunks)
        user_turn_text = (
            f"Context Chunks:\n{context_text}\n\n"
            f"User Query:\n{query}\n\n"
            "Requirements:\n"
            "1. Answer direct and factually using ONLY the context chunks above.\n"
            "2. Extract exact verbatim substring quotes from the context chunks into 'quoted_snippets'.\n"
            "3. Put the corresponding chunk IDs in 'citation_chunk_ids'.\n"
            "4. Return valid JSON matching the schema."
        )
        contents.append(
            {
                "role": "user",
                "parts": [{"text": user_turn_text}],
            }
        )
        return contents

    def _build_request_payload(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
        enforce_json_schema: bool = True,
    ) -> dict[str, Any]:
        persona = system_persona or self.DEFAULT_SYSTEM_PERSONA
        contents = self._build_contents(query, context_chunks, chat_history)

        payload: dict[str, Any] = {
            "contents": contents,
            "system_instruction": {
                "parts": [{"text": persona}],
            },
        }

        if enforce_json_schema:
            payload["generationConfig"] = {
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "OBJECT",
                    "properties": {
                        "direct_answer": {
                            "type": "STRING",
                            "description": "Direct factual synthesized response",
                        },
                        "quoted_snippets": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "Exact verbatim substrings extracted from context chunks",
                        },
                        "citation_chunk_ids": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "List of chunk_ids backing the quoted snippets",
                        },
                        "confidence_score": {
                            "type": "NUMBER",
                            "description": "Model self-reported confidence score between 0.0 and 1.0",
                        },
                    },
                    "required": [
                        "direct_answer",
                        "quoted_snippets",
                        "citation_chunk_ids",
                    ],
                },
            }

        return payload

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        """Generate structured AnswerWithCitations using Gemini Flash REST API."""
        url = self._base_url.format(model=self.model, method="generateContent")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key

        payload = self._build_request_payload(
            query=query,
            context_chunks=context_chunks,
            chat_history=chat_history,
            system_persona=system_persona,
            enforce_json_schema=True,
        )

        client = self._get_client()
        params = {"key": self.api_key} if self.api_key else None
        try:
            resp = await client.post(url, json=payload, headers=headers, params=params)
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(f"Gemini connection error: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitError(f"Gemini 429 Rate Limit Exceeded: {resp.text}")
        if resp.status_code in (502, 503, 504):
            raise ServiceUnavailableError(
                f"Gemini Service Unavailable ({resp.status_code}): {resp.text}"
            )
        resp.raise_for_status()

        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMFormatError("Gemini response contained no candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise LLMFormatError("Gemini response candidate had no content parts")
            text = parts[0].get("text", "")
            # Strip markdown formatting wrappers if model enclosed JSON in ```json
            cleaned_text = text.strip()
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
                f"Failed to parse AnswerWithCitations from Gemini response: {exc}"
            ) from exc

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated text tokens using Gemini streamGenerateContent?alt=sse."""
        url = self._base_url.format(model=self.model, method="streamGenerateContent")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key

        payload = self._build_request_payload(
            query=query,
            context_chunks=context_chunks,
            chat_history=chat_history,
            system_persona=system_persona,
            enforce_json_schema=False,
        )

        client = self._get_client()
        params: dict[str, str] = {"alt": "sse"}
        if self.api_key:
            params["key"] = self.api_key

        try:
            async with client.stream(
                "POST", url, json=payload, headers=headers, params=params
            ) as resp:
                if resp.status_code == 429:
                    body = await resp.aread()
                    raise RateLimitError(
                        f"Gemini 429 Rate Limit Exceeded: {body.decode(errors='replace')}"
                    )
                if resp.status_code in (502, 503, 504):
                    body = await resp.aread()
                    raise ServiceUnavailableError(
                        f"Gemini Service Unavailable ({resp.status_code}): {body.decode(errors='replace')}"
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

                    candidates = chunk_obj.get("candidates", [])
                    for cand in candidates:
                        for part in cand.get("content", {}).get("parts", []):
                            token = part.get("text", "")
                            if token:
                                yield token
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(f"Gemini connection error: {exc}") from exc


# Runtime protocol check
_: type[LLMClientProtocol] = GeminiClient

__all__ = [
    "GeminiClient",
    "LLMError",
    "LLMFormatError",
    "RateLimitError",
    "ServiceUnavailableError",
    "format_context_chunks",
]
