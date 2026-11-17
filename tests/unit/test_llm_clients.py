"""Unit tests for LLM Clients (Task 4.1 & Task 4.2).

Tests Google Gemini Flash and Groq Cloud Llama 3.3 adapters, protocol compliance,
context chunk formatting, and AnswerWithCitations schema validation.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.llm.gemini_client import (
    GeminiClient,
    LLMFormatError,
    RateLimitError,
    ServiceUnavailableError,
    format_context_chunks,
)
from cuk_assistant.llm.groq_client import GroqClient
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.llm import AnswerWithCitations


class TestAnswerWithCitationsSchema:
    """Test Pydantic v2 AnswerWithCitations contract."""

    def test_valid_instantiation(self) -> None:
        answer = AnswerWithCitations(
            direct_answer="Admissions close on July 31, 2026.",
            quoted_snippets=["last date for submission is July 31, 2026"],
            citation_chunk_ids=["adm_2026::c0"],
            confidence_score=0.98,
        )
        assert answer.direct_answer == "Admissions close on July 31, 2026."
        assert len(answer.quoted_snippets) == 1
        assert answer.citation_chunk_ids == ["adm_2026::c0"]
        assert answer.confidence_score == 0.98

    def test_default_values(self) -> None:
        answer = AnswerWithCitations(direct_answer="Yes.")
        assert answer.quoted_snippets == []
        assert answer.citation_chunk_ids == []
        assert answer.confidence_score == 1.0

    def test_forbid_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            AnswerWithCitations(
                direct_answer="Yes.",
                unknown_field="injected",  # type: ignore[call-arg]
            )

    def test_frozen_immutability(self) -> None:
        answer = AnswerWithCitations(direct_answer="Original")
        with pytest.raises(ValidationError):
            answer.direct_answer = "Modified"  # type: ignore[misc]

    def test_confidence_score_range_validation(self) -> None:
        with pytest.raises(ValidationError):
            AnswerWithCitations(direct_answer="Test", confidence_score=1.5)
        with pytest.raises(ValidationError):
            AnswerWithCitations(direct_answer="Test", confidence_score=-0.1)


class TestFormatContextChunks:
    """Test formatting of context chunks into LLM prompt text."""

    def test_format_empty_chunks(self) -> None:
        text = format_context_chunks([])
        assert "No relevant context chunks retrieved." in text

    def test_format_dict_chunks(self) -> None:
        chunks = [
            {
                "chunk_id": "cuk_syllabus::c0",
                "heading_path": ["Engineering", "CSE", "DBMS"],
                "text_content": "Unit 1 covers relational algebra and calculus.",
            },
            {
                "chunk_id": "cuk_syllabus::c1",
                "section_heading": "Textbooks",
                "text": "Silberschatz Database System Concepts 7th ed.",
            },
        ]
        text = format_context_chunks(chunks)
        assert "CHUNK ID: cuk_syllabus::c0" in text
        assert "Path: Engineering > CSE > DBMS" in text
        assert "Unit 1 covers relational algebra" in text
        assert "CHUNK ID: cuk_syllabus::c1" in text
        assert "Path: Textbooks" in text
        assert "Silberschatz" in text

    def test_format_chunk_records(self) -> None:
        chunk = ChunkRecord(
            chunk_id="cuk_notice::c0",
            doc_id="cuk_notice",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Hostel admission list is published.",
            token_count=10,
            heading_path=["Administration", "Hostel"],
        )
        text = format_context_chunks([chunk])
        assert "CHUNK ID: cuk_notice::c0" in text
        assert "Path: Administration > Hostel" in text
        assert "Hostel admission list is published." in text


class TestGeminiClient:
    """Unit tests for Gemini Flash LLM adapter."""

    def test_protocol_conformance(self) -> None:
        client = GeminiClient(api_key="test-key")
        assert isinstance(client, LLMClientProtocol)
        assert client.provider_name == "google_gemini_flash"

    @pytest.mark.asyncio
    async def test_generate_answer_success(self) -> None:
        expected_json = {
            "direct_answer": "Admissions for M.Tech close on July 31.",
            "quoted_snippets": ["M.Tech admissions close on July 31"],
            "citation_chunk_ids": ["mtech::c0"],
            "confidence_score": 0.95,
        }
        gemini_response_body = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(expected_json)}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert "gemini-2.0-flash:generateContent" in str(request.url)
            assert request.headers.get("x-goog-api-key") == "fake-gemini-key"

            # Verify payload includes context chunks and system instruction
            body = json.loads(request.read())
            assert "system_instruction" in body
            assert "contents" in body
            assert "generationConfig" in body
            assert body["generationConfig"]["response_mime_type"] == "application/json"

            return httpx.Response(200, json=gemini_response_body)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GeminiClient(api_key="fake-gemini-key", client=http_client)
            answer = await client.generate_answer(
                query="When do M.Tech admissions close?",
                context_chunks=[
                    {
                        "chunk_id": "mtech::c0",
                        "heading_path": ["Admissions"],
                        "text_content": "M.Tech admissions close on July 31",
                    }
                ],
                chat_history=[],
                system_persona="Custom University Persona",
            )

            assert isinstance(answer, AnswerWithCitations)
            assert answer.direct_answer == expected_json["direct_answer"]
            assert answer.quoted_snippets == expected_json["quoted_snippets"]
            assert answer.citation_chunk_ids == expected_json["citation_chunk_ids"]
            assert answer.confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_rate_limit_429_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"error": {"message": "Resource has been exhausted"}},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GeminiClient(api_key="fake-gemini-key", client=http_client)
            with pytest.raises(RateLimitError) as exc_info:
                await client.generate_answer("query", [], [])
            assert "429" in str(exc_info.value)
            assert exc_info.value.diagnostic_code == "LLM_EXTRACTION_FAILURE"

    @pytest.mark.asyncio
    async def test_service_unavailable_503_raises_service_unavailable_error(
        self,
    ) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Temporarily Unavailable")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GeminiClient(api_key="fake-gemini-key", client=http_client)
            with pytest.raises(ServiceUnavailableError):
                await client.generate_answer("query", [], [])

    @pytest.mark.asyncio
    async def test_malformed_json_raises_llm_format_error(self) -> None:
        gemini_response_body = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Not valid JSON output"}],
                        "role": "model",
                    }
                }
            ]
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=gemini_response_body)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GeminiClient(api_key="fake-gemini-key", client=http_client)
            with pytest.raises(LLMFormatError) as exc_info:
                await client.generate_answer("query", [], [])
            assert exc_info.value.diagnostic_code == "LLM_FORMAT_VIOLATION"

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self) -> None:
        sse_lines = [
            'data: {"candidates": [{"content": {"parts": [{"text": "The "}]}}]}\n\n',
            'data: {"candidates": [{"content": {"parts": [{"text": "last date "}]}}]}\n\n',
            'data: {"candidates": [{"content": {"parts": [{"text": "is July 31."}]}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        sse_content = "".join(sse_lines).encode("utf-8")

        async def handler(request: httpx.Request) -> httpx.Response:
            assert "streamGenerateContent" in str(request.url)
            assert "alt=sse" in str(request.url)
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_content,
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GeminiClient(api_key="fake-gemini-key", client=http_client)
            tokens: list[str] = []
            async for token in client.generate_stream("query", [], []):
                tokens.append(token)

            assert tokens == ["The ", "last date ", "is July 31."]


class TestGroqClient:
    """Unit tests for Groq Cloud Llama 3.3 adapter."""

    def test_protocol_conformance(self) -> None:
        client = GroqClient(api_key="test-groq-key")
        assert isinstance(client, LLMClientProtocol)
        assert client.provider_name == "groq_llama_3.3"

    @pytest.mark.asyncio
    async def test_generate_answer_success(self) -> None:
        expected_json = {
            "direct_answer": "Graduation requires 50% minimum marks.",
            "quoted_snippets": ["at least 50 percent marks in graduation"],
            "citation_chunk_ids": ["eligibility::c2"],
            "confidence_score": 0.99,
        }
        groq_response_body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(expected_json),
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.headers.get("Authorization") == "Bearer fake-groq-key"

            body = json.loads(request.read())
            assert body["model"] == "llama-3.3-70b-versatile"
            assert body["response_format"] == {"type": "json_object"}
            assert len(body["messages"]) >= 2
            assert body["messages"][0]["role"] == "system"

            return httpx.Response(200, json=groq_response_body)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GroqClient(api_key="fake-groq-key", client=http_client)
            answer = await client.generate_answer(
                query="What are the eligibility marks?",
                context_chunks=[
                    {
                        "chunk_id": "eligibility::c2",
                        "heading_path": ["Eligibility Criteria"],
                        "text_content": "Candidates must have secured at least 50 percent marks in graduation.",
                    }
                ],
                chat_history=[{"role": "user", "content": "Hi"}],
            )

            assert isinstance(answer, AnswerWithCitations)
            assert answer.direct_answer == expected_json["direct_answer"]
            assert answer.quoted_snippets == expected_json["quoted_snippets"]
            assert answer.citation_chunk_ids == expected_json["citation_chunk_ids"]
            assert answer.confidence_score == 0.99

    @pytest.mark.asyncio
    async def test_rate_limit_429_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "Rate limit reached"}})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GroqClient(api_key="fake-groq-key", client=http_client)
            with pytest.raises(RateLimitError):
                await client.generate_answer("query", [], [])

    @pytest.mark.asyncio
    async def test_service_unavailable_503_raises_service_unavailable_error(
        self,
    ) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GroqClient(api_key="fake-groq-key", client=http_client)
            with pytest.raises(ServiceUnavailableError):
                await client.generate_answer("query", [], [])

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self) -> None:
        sse_lines = [
            'data: {"choices": [{"delta": {"content": "Minimum "}}]}\n\n',
            'data: {"choices": [{"delta": {"content": "marks: 50%."}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        sse_content = "".join(sse_lines).encode("utf-8")

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_content,
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = GroqClient(api_key="fake-groq-key", client=http_client)
            tokens: list[str] = []
            async for token in client.generate_stream("query", [], []):
                tokens.append(token)

            assert tokens == ["Minimum ", "marks: 50%."]
