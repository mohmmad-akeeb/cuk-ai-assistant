"""Unit tests for Central Factory Assembly and RAG Pipeline Orchestrator.

Validates:
1. Component factory Dependency Injection (DI) contracts.
2. Complete 8-step turn execution lifecycle in RAGOrchestrator.
3. Observability and diagnostic failure code attribution.
4. Token callbacks and streaming generator protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cuk_assistant.agent.router import AdaptiveRouter
from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.core.factory import (
    create_guardrails,
    create_input_guard,
    create_llm_pool,
    create_rag_orchestrator,
    create_reranker,
    create_router,
    create_session_store,
    create_vector_store,
)
from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.core.protocols.session import SessionStoreProtocol
from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.guardrails.subsystems.citation_verifier import VerbatimCitationVerifier
from cuk_assistant.guardrails.output_guard import OutputGuard
from cuk_assistant.llm.pool import LLMProviderPool
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator, TurnResult
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.llm import AnswerWithCitations
from cuk_assistant.schemas.retrieval import ScoredChunk

# ---------------------------------------------------------------------------
# Test Doubles / Mocks for Abstract Protocols
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock LLM provider satisfying LLMClientProtocol."""

    def __init__(
        self,
        answer: AnswerWithCitations | None = None,
        should_fail: bool = False,
    ) -> None:
        self.provider_name = "mock_llm"
        self.should_fail = should_fail
        self.default_answer = answer or AnswerWithCitations(
            direct_answer="Database Management Systems covers Relational Models and Normalization.",
            quoted_snippets=["Relational Models and Normalization."],
            citation_chunk_ids=["chunk_db_1"],
            confidence_score=0.95,
        )
        self.last_query: str | None = None
        self.last_context: list[dict[str, Any]] | None = None
        self.last_history: list[dict[str, str]] | None = None

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ) -> AnswerWithCitations:
        self.last_query = query
        self.last_context = context_chunks
        self.last_history = chat_history
        if self.should_fail:
            raise RuntimeError("LLM inference unavailable")
        return self.default_answer

    async def generate_stream(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
        chat_history: list[dict[str, str]],
        system_persona: str | None = None,
    ):
        for token in ["Database ", "Management ", "Systems ", "covers ", "Relational ", "Models."]:
            yield token


class MockCoordinator:
    """Mock retrieval coordinator returning synthetic candidate chunks."""

    def __init__(self, candidates: list[ScoredChunk] | None = None) -> None:
        if candidates is not None:
            self.candidates = candidates
        else:
            meta = {
                "doc_id": "doc_cse_syllabus",
                "doc_type": "syllabus",
                "title": "B.Tech CSE Syllabus Regulation 2022",
                "source_url": "https://cukashmir.ac.in/syllabus.pdf",
                "page_number": 14,
                "section_heading": "Unit 2: DBMS",
            }
            chunk = ChunkRecord(
                chunk_id="chunk_db_1",
                doc_id="doc_cse_syllabus",
                chunk_index=0,
                chunk_type=ChunkType.PARAGRAPH,
                text_content="Database Management Systems covers Relational Models and Normalization.",
                token_count=10,
                page_number=14,
                section_heading="Unit 2: DBMS",
                metadata=meta,
            )
            self.candidates = [ScoredChunk(chunk=chunk, score=0.88)]
        self.last_query: str | None = None
        self.last_filters: Any = None

    def retrieve(
        self,
        query: str,
        filters: Any = None,
        top_k: int = 5,
        trace_id: str | None = None,
    ) -> list[ScoredChunk]:
        self.last_query = query
        self.last_filters = filters
        return self.candidates


# ---------------------------------------------------------------------------
# Task 5.3A: Factory Assembly Tests
# ---------------------------------------------------------------------------


class TestCentralFactoryAssembly:
    """Validate DI component creation and wiring in cuk_assistant.core.factory."""

    def test_create_llm_pool_assembly(self) -> None:
        """Verify create_llm_pool instantiates LLMProviderPool with Gemini & Groq."""
        pool = create_llm_pool(gemini_api_key="test_gemini", groq_api_key="test_groq")
        assert isinstance(pool, LLMClientProtocol)
        assert isinstance(pool, LLMProviderPool)
        assert len(pool.providers) == 2
        provider_names = [p.provider_name for p in pool.providers]
        assert "google_gemini_flash" in provider_names
        assert "groq_llama_3.3" in provider_names

    def test_create_guardrails_assembly(self) -> None:
        """Verify create_guardrails returns composite, output guard, and verifier."""
        composite, out_guard, verifier = create_guardrails()
        assert hasattr(composite, "validate_input")
        assert hasattr(composite, "validate_and_scrub_output")
        assert isinstance(out_guard, OutputGuard)
        assert isinstance(verifier, VerbatimCitationVerifier)

    def test_create_session_store_assembly(self) -> None:
        """Verify create_session_store returns SQLiteSessionStore in memory or disk."""
        store = create_session_store(db_path=":memory:")
        assert isinstance(store, SessionStoreProtocol)
        assert isinstance(store, SQLiteSessionStore)
        store.close()

    def test_create_vector_store_lancedb_dir_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_dir = str(tmp_path / "custom_lancedb")
        monkeypatch.setenv("LANCEDB_DIR", custom_dir)
        store = create_vector_store()
        assert str(store._db_path) == custom_dir

    def test_create_vector_store_explicit_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("LANCEDB_DIR", str(tmp_path / "env_lancedb"))
        explicit_dir = str(tmp_path / "explicit_lancedb")
        store = create_vector_store(db_path=explicit_dir)
        assert str(store._db_path) == explicit_dir

    def test_create_session_store_sqlite_db_path_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_db = str(tmp_path / "custom_sessions.db")
        monkeypatch.setenv("SQLITE_DB_PATH", custom_db)
        store = create_session_store()
        assert str(store._db_path) == custom_db
        store.close()

    def test_create_session_store_explicit_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "custom_sessions.db"))
        store = create_session_store(db_path=":memory:")
        assert store._is_memory is True
        store.close()

    def test_create_reranker_cache_dir_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLASHRANK_CACHE_PATH", "/env/factory_cache")
        with patch("cuk_assistant.retrieval.subsystems.flashrank_reranker.Ranker") as mock_ranker:
            reranker = create_reranker()
            assert reranker._cache_dir == "/env/factory_cache"
            assert mock_ranker.call_args.kwargs["cache_dir"] == "/env/factory_cache"

    def test_create_router_assembly(self) -> None:
        """Verify create_router instantiates AdaptiveRouter."""
        router = create_router()
        assert isinstance(router, AdaptiveRouter)

    def test_create_rag_orchestrator_assembly(self) -> None:
        """Verify create_rag_orchestrator constructs fully wired RAGOrchestrator."""
        orchestrator = create_rag_orchestrator(
            session_store_kwargs={"db_path": ":memory:"},
            llm_kwargs={"gemini_api_key": "test_k"},
        )
        assert isinstance(orchestrator, RAGOrchestrator)
        assert orchestrator.retrieval_coordinator is not None
        assert orchestrator.llm_client is not None
        assert orchestrator.input_guard is not None
        assert orchestrator.output_guard is not None
        assert orchestrator.citation_verifier is not None
        assert orchestrator.session_store is not None
        assert orchestrator.router is not None
        if hasattr(orchestrator.session_store, "close"):
            orchestrator.session_store.close()


# ---------------------------------------------------------------------------
# Task 5.3B: RAG Orchestrator Pipeline Turn Tests
# ---------------------------------------------------------------------------


class TestRAGOrchestratorTurn:
    """Validate 8-step turn orchestration in RAGOrchestrator."""

    @pytest.fixture
    def test_env(self) -> dict[str, Any]:
        """Set up isolated orchestrator test fixture."""
        store = SQLiteSessionStore(":memory:")
        sink = InMemoryTelemetrySink()
        coordinator = MockCoordinator()
        llm = MockLLMClient()
        _, out_guard, verifier = create_guardrails()
        inp_guard = create_input_guard()
        router = create_router(input_guard=inp_guard)

        orchestrator = RAGOrchestrator(
            retrieval_coordinator=coordinator,
            llm_client=llm,
            input_guard=inp_guard,
            output_guard=out_guard,
            citation_verifier=verifier,
            session_store=store,
            router=router,
            telemetry_sink=sink,
        )

        return {
            "orchestrator": orchestrator,
            "store": store,
            "sink": sink,
            "coordinator": coordinator,
            "llm": llm,
        }

    @pytest.mark.asyncio
    async def test_input_guard_blocked_deflection(self, test_env: dict[str, Any]) -> None:
        """Step 1: Test out-of-domain or unsafe query triggers deflection and tags GUARDRAIL_BLOCKED."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        sink: InMemoryTelemetrySink = test_env["sink"]

        # Out-of-domain query (e.g. recipe)
        events: list[dict[str, Any]] = []
        async for event in orchestrator.stream_turn(
            query="How do I bake chocolate chip cookies?",
            session_id="sess-guard-1",
        ):
            events.append(event)

        # Must tag failure in sink
        failures = sink.get_failures()
        assert len(failures) >= 1
        assert any(
            f["diagnostic_code"] == FailureDiagnosticCode.GUARDRAIL_BLOCKED for f in failures
        )

        # Verify emitted events
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["diagnostic_code"] == FailureDiagnosticCode.GUARDRAIL_BLOCKED.value

        tokens = "".join(e.get("token", "") for e in events if e.get("type") == "token")
        assert "Central University of Kashmir" in tokens

    @pytest.mark.asyncio
    async def test_conversational_greeting_direct_handling(self, test_env: dict[str, Any]) -> None:
        """Step 3C: Conversational greeting returns direct response without retrieval."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        store: SQLiteSessionStore = test_env["store"]

        result: TurnResult = await orchestrator.handle_turn(
            query="Hello there!",
            session_id="sess-greet-1",
        )
        assert "Central University of Kashmir" in result.content
        assert result.citations == []
        assert result.quick_replies is None

        # Verify session persistence
        messages = store.get_session_history("sess-greet-1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_faceted_slot_prompt_emission(self, test_env: dict[str, Any]) -> None:
        """Step 3B: Missing mandatory slots emit slot_prompt event with options."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]

        events: list[dict[str, Any]] = []
        async for event in orchestrator.stream_turn(
            query="What is the syllabus for B.Tech CSE?",
            session_id="sess-slots-1",
        ):
            events.append(event)

        slot_events = [e for e in events if e.get("type") == "slot_prompt"]
        assert len(slot_events) == 1
        assert slot_events[0]["target_slot"] == "batch_year"
        assert len(slot_events[0]["options"]) >= 2

    @pytest.mark.asyncio
    async def test_full_rag_cycle_retrieval_generation_verification(
        self, test_env: dict[str, Any]
    ) -> None:
        """Steps 4-8: Full retrieval, answer synthesis, citation card assembly, and persistence."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        store: SQLiteSessionStore = test_env["store"]

        tokens_received: list[str] = []

        def token_listener(tok: str) -> None:
            tokens_received.append(tok)

        result: TurnResult = await orchestrator.handle_turn(
            query="What is the syllabus for B.Tech CSE DBMS?",
            slots={"program": "B.Tech CSE", "batch_year": 2022, "semester": "Semester 4"},
            session_id="sess-rag-success",
            token_callback=token_listener,
        )

        assert "Database Management Systems" in result.content
        assert len(result.citations) >= 1
        assert result.citations[0]["citation_id"] == "cite_1"
        assert result.citations[0]["doc_type"] == "syllabus"
        assert result.citations[0]["page_number"] == 14
        assert len(tokens_received) > 0

        # Verify history saved
        history = store.get_session_history("sess-rag-success")
        assert len(history) == 2
        assert history[1].role == "assistant"
        assert history[1].quoted_citations is not None

    @pytest.mark.asyncio
    async def test_citation_hallucination_redaction(self, test_env: dict[str, Any]) -> None:
        """Step 6: Ungrounded quoted snippets are flagged as LLM_HALLUCINATION and redacted."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        llm: MockLLMClient = test_env["llm"]
        sink: InMemoryTelemetrySink = test_env["sink"]

        # Return snippet that does NOT exist in retrieved mock context
        fake_snippet = "This is a fabricated university policy on exams."
        llm.default_answer = AnswerWithCitations(
            direct_answer=f"The regulation states: {fake_snippet}",
            quoted_snippets=[fake_snippet],
            citation_chunk_ids=["chunk_db_1"],
            confidence_score=0.9,
        )

        result: TurnResult = await orchestrator.handle_turn(
            query="What is the exam policy?",
            slots={"program": "B.Tech CSE"},
            session_id="sess-hallucinate",
        )

        assert "[UNVERIFIED CLAIM REDACTED]" in result.content
        assert result.diagnostic_code == FailureDiagnosticCode.LLM_HALLUCINATION.value

        failures = sink.get_failures()
        hallucinations = [
            f for f in failures if f["diagnostic_code"] == FailureDiagnosticCode.LLM_HALLUCINATION
        ]
        assert len(hallucinations) >= 1

    @pytest.mark.asyncio
    async def test_output_pii_scrubbing(self, test_env: dict[str, Any]) -> None:
        """Step 7: Sensitive student PII (phone number, Aadhaar) is automatically redacted."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        llm: MockLLMClient = test_env["llm"]

        pii_answer = (
            "Contact professor at +91 9876543210 or student Aadhaar 1234 5678 9012. "
            "Database Management Systems covers Relational Models."
        )
        llm.default_answer = AnswerWithCitations(
            direct_answer=pii_answer,
            quoted_snippets=[],
            citation_chunk_ids=[],
            confidence_score=0.9,
        )

        result: TurnResult = await orchestrator.handle_turn(
            query="Give me student details and syllabus",
            slots={"program": "B.Tech CSE", "batch_year": 2022, "semester": "Semester 4"},
            session_id="sess-pii",
        )

        assert "+91 9876543210" not in result.content
        assert "[REDACTED_PHONE]" in result.content
        assert "1234 5678 9012" not in result.content
        assert "[REDACTED_ID]" in result.content

    @pytest.mark.asyncio
    async def test_retrieval_empty_tagging(self, test_env: dict[str, Any]) -> None:
        """Step 4: Zero candidate chunks tags RETRIEVAL_EMPTY."""
        orchestrator: RAGOrchestrator = test_env["orchestrator"]
        coordinator: MockCoordinator = test_env["coordinator"]
        sink: InMemoryTelemetrySink = test_env["sink"]

        coordinator.candidates = []  # Empty corpus

        result: TurnResult = await orchestrator.handle_turn(
            query="What is the syllabus for Astro-Physics?",
            slots={"program": "Astro-Physics", "batch_year": 2022, "semester": "Semester 1"},
            session_id="sess-empty-retrieval",
        )
        assert result is not None

        failures = sink.get_failures()
        empty_failures = [
            f for f in failures if f["diagnostic_code"] == FailureDiagnosticCode.RETRIEVAL_EMPTY
        ]
        assert len(empty_failures) >= 1
