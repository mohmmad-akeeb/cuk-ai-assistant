"""tests/unit/test_retrieval_coordinator.py

Unit tests for HybridRetrievalCoordinator and Scope Fallback Engine.
Tests FR-4.1, FR-4.2, FR-4.3, FR-4.4, and FR-4.5.
"""

from typing import Any

import pytest

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
)
from cuk_assistant.retrieval.subsystems.coordinator import (
    HybridRetrievalCoordinator,
    extract_circular_reference,
    format_where_filter,
)
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType, ParentChunkContainer
from cuk_assistant.schemas.retrieval import ScoredChunk


class MockEmbeddingModel:
    """Mock dense embedding model conforming to EmbeddingModelProtocol."""

    def __init__(self, dimension: int = 384) -> None:
        self._dim = dimension
        self.embed_query_calls: list[str] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.05] * self._dim for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        self.embed_query_calls.append(query)
        return [0.05] * self._dim

    @property
    def dimension(self) -> int:
        return self._dim


class MockVectorStore:
    """Mock vector store conforming to VectorStoreProtocol."""

    def __init__(self) -> None:
        self.hybrid_search_calls: list[dict[str, Any]] = []
        self.get_parent_calls: list[str] = []
        self.regex_search_calls: list[str] = []
        self.delete_calls: list[str] = []

        # Return payloads configured per test
        self.hybrid_search_results: dict[str | None, list[ScoredChunk]] = {}
        self.default_hybrid_results: list[ScoredChunk] = []
        self.parent_chunks: dict[str, Any] = {}
        self.regex_search_results: dict[str, list[Any]] = {}

    def add_chunks(self, chunks: list[Any], embeddings: list[list[float]]) -> None:
        pass

    def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int = 30,
        where_filter: str | None = None,
    ) -> list[ScoredChunk]:
        self.hybrid_search_calls.append(
            {
                "query_text": query_text,
                "query_vector": query_vector,
                "top_k": top_k,
                "where_filter": where_filter,
            }
        )
        if where_filter in self.hybrid_search_results:
            return self.hybrid_search_results[where_filter]
        return self.default_hybrid_results

    def get_parent_chunk(self, parent_chunk_id: str) -> Any | None:
        self.get_parent_calls.append(parent_chunk_id)
        return self.parent_chunks.get(parent_chunk_id)

    def deterministic_regex_search(self, pattern: str) -> list[Any]:
        self.regex_search_calls.append(pattern)
        return self.regex_search_results.get(pattern, [])

    def delete_document(self, doc_id: str) -> None:
        self.delete_calls.append(doc_id)


class MockReranker:
    """Mock cross-encoder reranker conforming to RerankerProtocol."""

    def __init__(self, boost: float = 0.1) -> None:
        self.rerank_calls: list[dict[str, Any]] = []
        self.boost = boost

    def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        self.rerank_calls.append({"query": query, "candidates": candidates, "top_k": top_k})
        # Simulate cross-encoder scoring by applying boost to candidate scores
        reranked = []
        for i, c in enumerate(candidates[:top_k]):
            new_score = min(1.0, c.score + self.boost - (i * 0.01))
            reranked.append(c.model_copy(update={"score": new_score}))
        return reranked


class MockTelemetrySink:
    """Mock telemetry sink conforming to TelemetrySinkProtocol."""

    def __init__(self) -> None:
        self.tagged_failures: list[dict[str, Any]] = []
        self.logged_spans: list[dict[str, Any]] = []

    def log_span(self, name: str, attributes: dict[str, Any], duration_ms: float) -> None:
        self.logged_spans.append(
            {"name": name, "attributes": attributes, "duration_ms": duration_ms}
        )

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        self.tagged_failures.append(
            {"trace_id": trace_id, "diagnostic_code": diagnostic_code, "details": details}
        )

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        pass


def make_chunk_record(chunk_id: str, text: str, parent_id: str | None = None) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id=chunk_id.split("::")[0],
        chunk_index=0,
        chunk_type=ChunkType.PARAGRAPH,
        text_content=text,
        token_count=15,
        parent_chunk_id=parent_id,
        metadata={"title": f"Doc {chunk_id}"},
    )


class TestHelpers:
    """Unit tests for query parsing and filter formatting helpers."""

    def test_extract_circular_reference(self) -> None:
        assert (
            extract_circular_reference("Details on circular CUK/Acad/2023/102")
            == "CUK/Acad/2023/102"
        )
        assert (
            extract_circular_reference("Check notice no. CUKmr/Acad/2023/45 immediately")
            == "CUKmr/Acad/2023/45"
        )
        assert extract_circular_reference("Syllabus for CS-204 course") == "CS-204"
        assert extract_circular_reference("What is the fee for BT101?") == "BT101"
        assert extract_circular_reference("Show circular 2023/102") == "2023/102"
        assert extract_circular_reference("General university admission query") is None
        assert extract_circular_reference("Event on 2024-11-15 in main hall") is None

    def test_format_where_filter(self) -> None:
        assert format_where_filter(None) is None
        assert format_where_filter("") is None
        assert format_where_filter("department = 'Biotechnology'") == "department = 'Biotechnology'"
        assert (
            format_where_filter({"department": "Biotechnology"}) == "department = 'Biotechnology'"
        )
        assert (
            format_where_filter({"department": "Biotechnology", "batch_year": 2023})
            == "department = 'Biotechnology' AND batch_year = 2023"
        )
        assert format_where_filter({"is_active": True}) == "is_active = true"
        assert format_where_filter({"dept": ["CS", "IT"]}) == "dept IN ('CS', 'IT')"


class TestHybridRetrievalCoordinator:
    """Validate end-to-end coordinator workflows."""

    @pytest.fixture
    def setup_coordinator(
        self,
    ) -> tuple[
        HybridRetrievalCoordinator,
        MockVectorStore,
        MockEmbeddingModel,
        MockReranker,
        MockTelemetrySink,
    ]:
        vstore = MockVectorStore()
        embedder = MockEmbeddingModel()
        reranker = MockReranker()
        sink = MockTelemetrySink()
        coordinator = HybridRetrievalCoordinator(
            vector_store=vstore,
            embedding_model=embedder,
            reranker=reranker,
            relevance_threshold=0.35,
            telemetry_sink=sink,
        )
        return coordinator, vstore, embedder, reranker, sink

    def test_standard_retrieval_flow(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        coordinator, vstore, embedder, reranker, sink = setup_coordinator

        # Configure 3 hybrid results
        chunk1 = make_chunk_record("doc1::c0", "Admissions for B.Tech")
        chunk2 = make_chunk_record("doc2::c0", "Fee structure for B.Tech")
        vstore.default_hybrid_results = [
            ScoredChunk(chunk=chunk1, score=0.75, dense_score=0.7, lexical_score=0.8),
            ScoredChunk(chunk=chunk2, score=0.65, dense_score=0.6, lexical_score=0.7),
        ]

        results = coordinator.retrieve(
            query="B.Tech admissions and fee",
            filters={"category": "admission"},
            top_k=2,
            expand_parent_context=False,
        )

        # Verify embedding query called
        assert len(embedder.embed_query_calls) == 1
        assert embedder.embed_query_calls[0] == "B.Tech admissions and fee"

        # Verify vector store called with formatted filter
        assert len(vstore.hybrid_search_calls) == 1
        assert vstore.hybrid_search_calls[0]["where_filter"] == "category = 'admission'"

        # Verify reranker invoked
        assert len(reranker.rerank_calls) == 1

        # Verify results returned
        assert len(results) == 2
        assert results[0].score == pytest.approx(0.85, abs=0.01)  # Reranked score
        assert results[0].scope_relaxed is False
        assert results[0].regex_fallback is False
        assert coordinator.last_scope_relaxed is False
        assert coordinator.last_regex_fallback is False

    def test_scope_fallback_auto_relaxation_fr_4_4(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """FR-4.4: If scoped search returns 0 results, relax to global search."""
        coordinator, vstore, _embedder, _reranker, _sink = setup_coordinator

        scoped_filter = "department = 'Biotechnology'"
        # Scoped search returns 0 results
        vstore.hybrid_search_results[scoped_filter] = []

        # Global search (where_filter=None) returns 1 candidate
        global_chunk = make_chunk_record("gen_doc::c1", "General university admission details")
        vstore.hybrid_search_results[None] = [
            ScoredChunk(chunk=global_chunk, score=0.70, dense_score=0.70, lexical_score=0.65)
        ]

        results = coordinator.retrieve(
            query="When do admissions start?",
            filters={"department": "Biotechnology"},
            top_k=5,
            expand_parent_context=False,
        )

        # Vector store called twice: first scoped, second global
        assert len(vstore.hybrid_search_calls) == 2
        assert vstore.hybrid_search_calls[0]["where_filter"] == scoped_filter
        assert vstore.hybrid_search_calls[1]["where_filter"] is None

        # Coordinator flagged scope relaxation
        assert coordinator.last_scope_relaxed is True
        assert len(results) == 1
        assert results[0].scope_relaxed is True
        assert results[0].chunk.metadata["scope_relaxed"] is True

    def test_deterministic_regex_fallback_on_recall_miss_fr_4_5(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """FR-4.5: Low score or empty candidates with circular code triggers deterministic regex scan."""
        coordinator, vstore, _embedder, _reranker, sink = setup_coordinator

        # Hybrid search returns low scoring irrelevant candidate
        weak_chunk = make_chunk_record("junk::c0", "Unrelated notice on parking")
        vstore.default_hybrid_results = [
            ScoredChunk(chunk=weak_chunk, score=0.20)  # Below 0.35 threshold
        ]

        # Regex search finds exact circular match
        circular_code = "CUK/Acad/2023/102"
        exact_chunk = make_chunk_record(
            "cuk_notices::c4", "Circular CUK/Acad/2023/102: Semester Registration dates"
        )
        vstore.regex_search_results[circular_code] = [exact_chunk]

        results = coordinator.retrieve(
            query="Details on circular CUK/Acad/2023/102",
            top_k=5,
            expand_parent_context=False,
            trace_id="trc_test_regex",
        )

        # Regex search was called with detected code
        assert circular_code in vstore.regex_search_calls
        assert coordinator.last_regex_fallback is True

        # Results wrapped with score 1.0 and regex_fallback=True
        assert len(results) == 1
        assert results[0].score == 1.0
        assert results[0].regex_fallback is True
        assert results[0].chunk.metadata["regex_fallback"] is True
        assert results[0].chunk.chunk_id == "cuk_notices::c4"

        # Telemetry sink tagged RETRIEVAL_RECALL_MISS
        assert len(sink.tagged_failures) == 1
        assert (
            sink.tagged_failures[0]["diagnostic_code"]
            == FailureDiagnosticCode.RETRIEVAL_RECALL_MISS
        )
        assert sink.tagged_failures[0]["trace_id"] == "trc_test_regex"
        assert sink.tagged_failures[0]["details"]["pattern"] == circular_code

    def test_parent_context_expansion(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """Step 6: Parent section hydration into retrieved chunk metadata."""
        coordinator, vstore, _embedder, _reranker, _sink = setup_coordinator

        parent_id = "doc_syllabus::p1"
        child_chunk = make_chunk_record(
            "doc_syllabus::c5", "Unit 1: Data Structures", parent_id=parent_id
        )
        vstore.default_hybrid_results = [ScoredChunk(chunk=child_chunk, score=0.88)]

        parent_container = ParentChunkContainer(
            parent_chunk_id=parent_id,
            doc_id="doc_syllabus",
            heading_title="Computer Science Syllabus 2024",
            heading_level=2,
            section_token_count=150,
            full_section_text="## Computer Science Syllabus 2024\nUnit 1: Data Structures\nUnit 2: Algorithms",
            child_chunk_ids=["doc_syllabus::c5"],
        )
        vstore.parent_chunks[parent_id] = parent_container

        results = coordinator.retrieve(
            query="Data Structures syllabus",
            top_k=1,
            expand_parent_context=True,
        )

        assert len(results) == 1
        assert parent_id in vstore.get_parent_calls
        meta = results[0].metadata
        assert "parent_context" in meta
        assert "Computer Science Syllabus 2024" in meta["parent_context"]
        assert meta["parent_section_text"] == parent_container.full_section_text

    def test_retrieval_empty_telemetry_attribution(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """When query returns 0 candidates and has no circular code, tag RETRIEVAL_EMPTY."""
        coordinator, vstore, _embedder, _reranker, sink = setup_coordinator

        vstore.default_hybrid_results = []

        results = coordinator.retrieve(
            query="Completely nonexistent university topic",
            top_k=5,
            expand_parent_context=False,
            trace_id="trc_empty",
        )

        assert len(results) == 0
        assert len(sink.tagged_failures) == 1
        assert sink.tagged_failures[0]["diagnostic_code"] == FailureDiagnosticCode.RETRIEVAL_EMPTY
        assert sink.tagged_failures[0]["trace_id"] == "trc_empty"

    def test_corpus_missing_content_telemetry_attribution(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """When query has circular code but regex search returns 0 matches, tag CORPUS_MISSING_CONTENT."""
        coordinator, vstore, _embedder, _reranker, sink = setup_coordinator

        vstore.default_hybrid_results = []
        vstore.regex_search_results["CUK/Acad/9999/000"] = []

        results = coordinator.retrieve(
            query="Details on circular CUK/Acad/9999/000",
            top_k=5,
            expand_parent_context=False,
            trace_id="trc_missing_doc",
        )

        assert len(results) == 0
        assert len(sink.tagged_failures) == 1
        assert (
            sink.tagged_failures[0]["diagnostic_code"]
            == FailureDiagnosticCode.CORPUS_MISSING_CONTENT
        )
        assert sink.tagged_failures[0]["trace_id"] == "trc_missing_doc"

    def test_scope_relaxed_and_regex_fallback_combined(
        self,
        setup_coordinator: tuple[
            HybridRetrievalCoordinator,
            MockVectorStore,
            MockEmbeddingModel,
            MockReranker,
            MockTelemetrySink,
        ],
    ) -> None:
        """Both scope relaxation and regex fallback triggered when filtered and global are empty."""
        coordinator, vstore, _embedder, _reranker, _sink = setup_coordinator

        # Both scoped and global searches return empty
        vstore.hybrid_search_results["department = 'Biotechnology'"] = []
        vstore.hybrid_search_results[None] = []

        # But regex search finds the document
        circular_code = "CUKmr/Acad/2023/45"
        matched_chunk = make_chunk_record(
            "notice_45::c0", "Notice CUKmr/Acad/2023/45: Lab safety guidelines"
        )
        vstore.regex_search_results[circular_code] = [matched_chunk]

        results = coordinator.retrieve(
            query="Check notice no. CUKmr/Acad/2023/45",
            filters={"department": "Biotechnology"},
            top_k=3,
            expand_parent_context=False,
        )

        assert len(results) == 1
        assert results[0].scope_relaxed is True
        assert results[0].regex_fallback is True
        assert results[0].chunk.metadata["scope_relaxed"] is True
        assert results[0].chunk.metadata["regex_fallback"] is True
        assert coordinator.last_scope_relaxed is True
        assert coordinator.last_regex_fallback is True

    def test_retrieval_without_reranker(self) -> None:
        """Coordinator functions correctly when reranker is None."""
        vstore = MockVectorStore()
        embedder = MockEmbeddingModel()
        coordinator = HybridRetrievalCoordinator(
            vector_store=vstore,
            embedding_model=embedder,
            reranker=None,
        )

        c1 = make_chunk_record("d1::c0", "First chunk")
        c2 = make_chunk_record("d2::c0", "Second chunk")
        vstore.default_hybrid_results = [
            ScoredChunk(chunk=c1, score=0.60),
            ScoredChunk(chunk=c2, score=0.90),
        ]

        results = coordinator.retrieve("test query", top_k=2, expand_parent_context=False)
        assert len(results) == 2
        # Sorted descending by score
        assert results[0].score == 0.90
        assert results[1].score == 0.60

    def test_parent_context_expansion_with_dict_parent(self) -> None:
        """Step 6: Parent section hydration when parent is a dict."""
        vstore = MockVectorStore()
        embedder = MockEmbeddingModel()
        coordinator = HybridRetrievalCoordinator(
            vector_store=vstore,
            embedding_model=embedder,
            reranker=None,
        )

        parent_id = "parent_dict_1"
        child = make_chunk_record("child::c0", "Child content", parent_id=parent_id)
        vstore.default_hybrid_results = [ScoredChunk(chunk=child, score=0.85)]
        vstore.parent_chunks[parent_id] = {
            "full_section_text": "Dict Parent Section Full Text",
            "heading_title": "Dict Heading",
        }

        results = coordinator.retrieve("query", top_k=1, expand_parent_context=True)
        assert len(results) == 1
        assert results[0].metadata["parent_context"] == "Dict Parent Section Full Text"
