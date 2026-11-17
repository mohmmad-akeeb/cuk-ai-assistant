"""Unit tests for FastAPI chat endpoints wired to RAGOrchestrator.

Governed by docs/api_contracts.md Section 2.2, 2.3, 2.4 and Task 5.4.
Verifies SSE event stream protocol, synchronous chat responses, and feedback logging.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.api.main import app
from cuk_assistant.api.routes.chat import get_orchestrator, get_telemetry_sink
from cuk_assistant.api.routes.sessions import get_session_store
from cuk_assistant.core.factory import (
    create_input_guard,
    create_output_guard,
    create_router,
)
from cuk_assistant.guardrails.subsystems.citation_verifier import VerbatimCitationVerifier
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.llm import AnswerWithCitations
from cuk_assistant.schemas.retrieval import ScoredChunk


class MockLLMForApi:
    """Mock LLM for API route testing."""

    def __init__(self) -> None:
        self.provider_name = "mock_api_llm"

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        return AnswerWithCitations(
            direct_answer="Computer Networks covers TCP/IP, OSI model, and routing protocols.",
            quoted_snippets=["TCP/IP, OSI model, and routing protocols."],
            citation_chunk_ids=["chk_net_1"],
            confidence_score=0.98,
        )

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ):
        for token in ["Computer ", "Networks ", "covers ", "TCP/IP."]:
            yield token


class MockCoordinatorForApi:
    """Mock retrieval coordinator returning structured chunks."""

    def retrieve(
        self,
        query: str,
        filters: Any = None,
        top_k: int = 5,
        trace_id: str | None = None,
    ) -> list[ScoredChunk]:
        meta = {
            "doc_id": "doc_net_syllabus",
            "doc_type": "syllabus",
            "title": "B.Tech Computer Networks Syllabus",
            "source_url": "https://cukashmir.ac.in/networks.pdf",
            "page_number": 8,
            "section_heading": "Unit 1: Fundamentals",
        }
        chunk = ChunkRecord(
            chunk_id="chk_net_1",
            doc_id="doc_net_syllabus",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Computer Networks covers TCP/IP, OSI model, and routing protocols.",
            token_count=10,
            page_number=8,
            section_heading="Unit 1: Fundamentals",
            metadata=meta,
        )
        return [ScoredChunk(chunk=chunk, score=0.92)]


@pytest.fixture
def mock_orchestrator(
    memory_session_store: SQLiteSessionStore,
    memory_telemetry_sink: InMemoryTelemetrySink,
) -> RAGOrchestrator:
    """Provide fully wired mock RAGOrchestrator for API tests."""
    inp_guard = create_input_guard()
    out_guard = create_output_guard()
    verifier = VerbatimCitationVerifier()
    router = create_router(input_guard=inp_guard)
    llm = MockLLMForApi()
    coordinator = MockCoordinatorForApi()

    return RAGOrchestrator(
        retrieval_coordinator=coordinator,
        llm_client=llm,
        input_guard=inp_guard,
        output_guard=out_guard,
        citation_verifier=verifier,
        session_store=memory_session_store,
        router=router,
        telemetry_sink=memory_telemetry_sink,
    )


@pytest.fixture
def memory_session_store() -> Generator[SQLiteSessionStore, None, None]:
    """Provide an isolated in-memory SQLiteSessionStore."""
    store = SQLiteSessionStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def memory_telemetry_sink() -> InMemoryTelemetrySink:
    """Provide an isolated in-memory telemetry sink."""
    return InMemoryTelemetrySink()


@pytest.fixture
def test_client(
    memory_session_store: SQLiteSessionStore,
    memory_telemetry_sink: InMemoryTelemetrySink,
    mock_orchestrator: RAGOrchestrator,
) -> Generator[TestClient, None, None]:
    """Provide TestClient with wired dependency overrides."""
    app.dependency_overrides[get_session_store] = lambda: memory_session_store
    app.dependency_overrides[get_telemetry_sink] = lambda: memory_telemetry_sink
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    client = TestClient(app)
    client.app.state.session_store = memory_session_store

    yield client

    app.dependency_overrides.clear()


# ===========================================================================
# Orchestrated SSE Stream Endpoint Tests
# ===========================================================================


class TestOrchestratedChatStream:
    """Validate Server-Sent Events (SSE) stream behavior when wired to orchestrator."""

    def test_stream_schema_conformance_events(self, test_client: TestClient) -> None:
        """Verify streamed events conform to types: token, citation_card, done."""
        payload = {
            "message": "What is the syllabus for Computer Networks?",
            "slots": {"program": "B.Tech CSE", "batch_year": 2022, "semester": "Semester 4"},
            "session_id": "sess-stream-schema",
        }
        resp = test_client.post(
            "/api/v1/chat/stream",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.11"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["Content-Type"]

        lines = resp.text.strip().split("\n\n")
        events: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        event_types = {e.get("type") for e in events}
        # Must contain tokens, citation_cards, and conclude with done
        assert "token" in event_types
        assert "citation_card" in event_types
        assert "done" in event_types

        # Verify citation_card schema
        card_events = [e for e in events if e.get("type") == "citation_card"]
        assert len(card_events) >= 1
        card = card_events[0]
        assert "citation_id" in card
        assert "title" in card
        assert "source_url" in card
        assert "page_number" in card
        assert card["citation_id"] == "cite_1"
        assert card["doc_type"] == "syllabus"

        # Verify done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["session_id"] == "sess-stream-schema"
        assert len(done_events[0]["citations"]) >= 1

    def test_stream_slot_prompt_emission(self, test_client: TestClient) -> None:
        """Verify missing slots emit slot_prompt event with interactive choices."""
        payload = {
            "message": "What is the syllabus for B.Tech CSE?",
            "session_id": "sess-stream-slots",
        }
        resp = test_client.post(
            "/api/v1/chat/stream",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.12"},
        )
        assert resp.status_code == 200

        events: list[dict[str, Any]] = [
            json.loads(line[6:])
            for line in resp.text.strip().split("\n\n")
            if line.strip().startswith("data: ")
        ]

        slot_events = [e for e in events if e.get("type") == "slot_prompt"]
        assert len(slot_events) == 1
        assert slot_events[0]["target_slot"] == "batch_year"
        assert len(slot_events[0]["options"]) >= 2

    def test_stream_empty_query_validation(self, test_client: TestClient) -> None:
        """Verify empty queries are rejected with HTTP 400."""
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": ""},
            headers={"X-Forwarded-For": "192.0.2.13"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "EMPTY_QUERY"


# ===========================================================================
# Orchestrated Synchronous Chat Tests
# ===========================================================================


class TestOrchestratedSyncChat:
    """Validate synchronous POST /api/v1/chat endpoint with orchestrator."""

    def test_sync_chat_academic_query_with_citations(self, test_client: TestClient) -> None:
        """Verify synchronous turn returns complete ChatResponse with citations."""
        payload = {
            "query": "What is the syllabus for Computer Networks?",
            "slots": {"program": "B.Tech CSE", "batch_year": 2022, "semester": "Semester 4"},
            "session_id": "sess-sync-acad",
        }
        resp = test_client.post(
            "/api/v1/chat",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.14"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["role"] == "assistant"
        assert data["session_id"] == "sess-sync-acad"
        assert "Computer Networks covers" in data["content"]
        assert len(data["citations"]) >= 1
        assert data["citations"][0]["citation_id"] == "cite_1"
        assert "trace_id" in data["metadata"]

    def test_sync_chat_conversational_greeting(self, test_client: TestClient) -> None:
        """Verify synchronous conversational greeting returns assistant welcome message."""
        payload = {
            "query": "Hello",
            "session_id": "sess-sync-greet",
        }
        resp = test_client.post(
            "/api/v1/chat",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.15"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Central University of Kashmir" in data["content"]
        assert data["citations"] == []
