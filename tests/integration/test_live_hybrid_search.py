"""tests/integration/test_live_hybrid_search.py

Integration smoke tests for live hybrid retrieval over the populated LanceDB vector store.
Tests reciprocal rank fusion (RRF), dense embedding with FastEmbed, sparse BM25 with Tantivy,
and FlashRank reranking against real CUK domain queries.
"""

from __future__ import annotations

import pytest

from cuk_assistant.core.factory import create_retrieval_coordinator
from cuk_assistant.retrieval.subsystems.coordinator import HybridRetrievalCoordinator
from cuk_assistant.schemas.chunks import ChunkRecord
from cuk_assistant.schemas.retrieval import ScoredChunk


@pytest.fixture(scope="module")
def retrieval_coordinator() -> HybridRetrievalCoordinator:
    """Initialize live Retrieval Coordinator connected to populated data/lancedb."""
    coordinator = create_retrieval_coordinator()
    return coordinator


class TestLiveHybridRetrieval:
    """Live integration verification suite for hybrid vector + lexical search."""

    def test_coordinator_initialization(
        self, retrieval_coordinator: HybridRetrievalCoordinator
    ) -> None:
        """Verify coordinator components are correctly assembled via Factory DI."""
        assert isinstance(retrieval_coordinator, HybridRetrievalCoordinator)
        assert retrieval_coordinator.vector_store is not None
        assert retrieval_coordinator.embedding_model is not None
        assert retrieval_coordinator.reranker is not None

    @pytest.mark.parametrize(
        "query,expected_keywords",
        [
            ("admission fee structure", ["admission", "fee", "program", "course", "eligibility"]),
            (
                "controller of examinations circulars",
                ["examination", "controller", "circular", "notice", "semester", "date sheet"],
            ),
            (
                "biotechnology syllabus and courses",
                ["biotechnology", "syllabus", "course", "credits", "department"],
            ),
        ],
    )
    def test_domain_queries_return_valid_results(
        self,
        retrieval_coordinator: HybridRetrievalCoordinator,
        query: str,
        expected_keywords: list[str],
    ) -> None:
        """Execute queries across core CUK domains and verify RRF results."""
        results: list[ScoredChunk] = retrieval_coordinator.retrieve(query=query, top_k=5)

        assert len(results) > 0, f"Query '{query}' returned 0 results"
        assert len(results) <= 5

        # Verify result structure and valid scores
        for scored in results:
            assert isinstance(scored, ScoredChunk)
            assert isinstance(scored.chunk, ChunkRecord)
            assert scored.score > 0.0, f"Non-positive score for chunk {scored.chunk_id}"
            assert len(scored.chunk.text_content.strip()) > 0
            assert scored.chunk.doc_id
            assert scored.chunk.chunk_id
            assert isinstance(scored.chunk.metadata, dict)

        # Verify semantic relevance: at least one of the top results matches expected domain keywords
        combined_text = " ".join(r.chunk.text_content.lower() for r in results)
        matched_keywords = [kw for kw in expected_keywords if kw in combined_text]
        assert len(matched_keywords) > 0, (
            f"None of keywords {expected_keywords} found in results for '{query}'"
        )

    def test_raw_hybrid_search_rrf_scoring(
        self, retrieval_coordinator: HybridRetrievalCoordinator
    ) -> None:
        """Directly verify vector store hybrid search and RRF score monotonicity."""
        query = "university campus administration"
        query_vector = retrieval_coordinator.embedding_model.embed_query(query)

        raw_results = retrieval_coordinator.vector_store.hybrid_search(
            query_text=query,
            query_vector=query_vector,
            top_k=5,
        )

        assert len(raw_results) > 0
        for i in range(len(raw_results) - 1):
            assert raw_results[i].score >= raw_results[i + 1].score, (
                "Hybrid search results should be sorted descending by RRF score"
            )

    def test_parent_chunk_context_expansion(
        self, retrieval_coordinator: HybridRetrievalCoordinator
    ) -> None:
        """Verify parent container section lookup for retrieved chunks."""
        results = retrieval_coordinator.retrieve(query="admissions", top_k=10)
        assert len(results) > 0

        # Find a chunk with a parent_chunk_id
        chunks_with_parent = [r for r in results if r.chunk.parent_chunk_id]
        if chunks_with_parent:
            target = chunks_with_parent[0]
            assert target.chunk.parent_chunk_id is not None
            parent = retrieval_coordinator.vector_store.get_parent_chunk(
                target.chunk.parent_chunk_id
            )
            if parent is not None:
                assert parent.doc_id == target.chunk.doc_id
                assert len(parent.full_section_text) > 0
                assert parent.heading_title

    def test_scoped_filtering_and_scope_relaxation(
        self, retrieval_coordinator: HybridRetrievalCoordinator
    ) -> None:
        """Test metadata filtering and automatic scope relaxation fallback."""
        # 1. Valid filter that matches documents
        results_valid = retrieval_coordinator.retrieve(
            query="academic circular",
            filters={"is_university_wide": True},
            top_k=5,
        )
        assert len(results_valid) > 0
        for r in results_valid:
            assert r.chunk.metadata.get("is_university_wide") is True

        # 2. Restrictive filter triggering scope relaxation (FR-4.4)
        results_relaxed = retrieval_coordinator.retrieve(
            query="academic circular",
            filters={"department": "NonExistentDepartment_XYZ_999"},
            top_k=5,
        )
        # Should auto-relax and return general university results
        assert retrieval_coordinator.last_scope_relaxed is True
        assert len(results_relaxed) > 0
