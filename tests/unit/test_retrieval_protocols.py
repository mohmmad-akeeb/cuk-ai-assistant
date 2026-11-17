"""tests/unit/test_retrieval_protocols.py

Unit tests for ScoredChunk value object and Storage/Reranker protocols.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from cuk_assistant.core.protocols.reranker import RerankerProtocol
from cuk_assistant.core.protocols.storage import (
    EmbeddingModelProtocol,
    VectorStoreProtocol,
)
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.retrieval import ScoredChunk


class TestScoredChunkModel:
    """Validate ScoredChunk value object schema and invariants."""

    @pytest.fixture
    def sample_chunk_record(self) -> ChunkRecord:
        return ChunkRecord(
            chunk_id="cuk_doc_101::c0",
            doc_id="cuk_doc_101",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Central University of Kashmir admission criteria for 2024.",
            token_count=10,
            metadata={"department": "Biotechnology", "batch_year": 2024},
        )

    def test_scored_chunk_with_chunk_record(self, sample_chunk_record: ChunkRecord) -> None:
        scored = ScoredChunk(
            chunk=sample_chunk_record,
            score=0.88,
            dense_score=0.85,
            lexical_score=0.72,
            rrf_rank=2,
            scope_relaxed=False,
            regex_fallback=False,
        )
        assert scored.chunk == sample_chunk_record
        assert scored.score == 0.88
        assert scored.dense_score == 0.85
        assert scored.lexical_score == 0.72
        assert scored.rrf_rank == 2
        assert scored.scope_relaxed is False
        assert scored.regex_fallback is False
        assert scored.chunk_id == "cuk_doc_101::c0"
        assert scored.text_content == "Central University of Kashmir admission criteria for 2024."
        assert scored.metadata["department"] == "Biotechnology"

    def test_scored_chunk_with_dict(self) -> None:
        chunk_dict = {
            "chunk_id": "raw_chunk_99",
            "text_content": "Syllabus for Information Technology BT-101",
            "metadata": {"course_code": "BT-101"},
        }
        scored = ScoredChunk(
            chunk=chunk_dict,
            score=0.92,
        )
        assert scored.chunk == chunk_dict
        assert scored.score == 0.92
        assert scored.dense_score == 0.0
        assert scored.lexical_score == 0.0
        assert scored.rrf_rank is None
        assert scored.scope_relaxed is False
        assert scored.regex_fallback is False
        assert scored.chunk_id == "raw_chunk_99"
        assert scored.text_content == "Syllabus for Information Technology BT-101"
        assert scored.metadata["course_code"] == "BT-101"

    def test_scored_chunk_immutability(self, sample_chunk_record: ChunkRecord) -> None:
        scored = ScoredChunk(chunk=sample_chunk_record, score=0.75)
        with pytest.raises(ValidationError):
            scored.score = 0.90  # type: ignore[misc]

    def test_scored_chunk_forbids_extra_fields(self, sample_chunk_record: ChunkRecord) -> None:
        with pytest.raises(ValidationError):
            ScoredChunk(
                chunk=sample_chunk_record,
                score=0.75,
                unrecognized_field="invalid",  # type: ignore[call-arg]
            )

    def test_scored_chunk_serialization(self, sample_chunk_record: ChunkRecord) -> None:
        scored = ScoredChunk(
            chunk=sample_chunk_record,
            score=0.82,
            dense_score=0.80,
            lexical_score=0.65,
            rrf_rank=1,
            scope_relaxed=True,
            regex_fallback=False,
        )
        dumped = scored.model_dump()
        assert dumped["score"] == 0.82
        assert dumped["scope_relaxed"] is True
        assert dumped["chunk"]["chunk_id"] == "cuk_doc_101::c0"

        json_str = scored.model_dump_json()
        assert "cuk_doc_101::c0" in json_str
        assert "0.82" in json_str


class TestProtocolsRuntimeCheckable:
    """Validate runtime_checkable behavior of Storage and Reranker protocols."""

    def test_embedding_model_protocol_conformance(self) -> None:
        class ValidEmbeddingModel:
            def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[0.1] * 384 for _ in texts]

            def embed_query(self, query: str) -> list[float]:
                return [0.1] * 384

            @property
            def dimension(self) -> int:
                return 384

        class IncompleteEmbeddingModel:
            def embed_query(self, query: str) -> list[float]:
                return [0.1] * 384

        assert isinstance(ValidEmbeddingModel(), EmbeddingModelProtocol)
        assert not isinstance(IncompleteEmbeddingModel(), EmbeddingModelProtocol)

    def test_vector_store_protocol_conformance(self) -> None:
        class ValidVectorStore:
            def add_chunks(self, chunks: list[Any], embeddings: list[list[float]]) -> None:
                pass

            def hybrid_search(
                self,
                query_text: str,
                query_vector: list[float],
                top_k: int = 30,
                where_filter: str | None = None,
            ) -> list[ScoredChunk]:
                return []

            def get_parent_chunk(self, parent_chunk_id: str) -> Any | None:
                return None

            def deterministic_regex_search(self, pattern: str) -> list[Any]:
                return []

            def delete_document(self, doc_id: str) -> None:
                pass

        class IncompleteVectorStore:
            def hybrid_search(
                self,
                query_text: str,
                query_vector: list[float],
                top_k: int = 30,
                where_filter: str | None = None,
            ) -> list[ScoredChunk]:
                return []

        assert isinstance(ValidVectorStore(), VectorStoreProtocol)
        assert not isinstance(IncompleteVectorStore(), VectorStoreProtocol)

    def test_reranker_protocol_conformance(self) -> None:
        class ValidReranker:
            def rerank(
                self,
                query: str,
                candidates: list[ScoredChunk],
                top_k: int = 5,
            ) -> list[ScoredChunk]:
                return candidates[:top_k]

        class IncompleteReranker:
            def rescore(self, query: str) -> list[Any]:
                return []

        assert isinstance(ValidReranker(), RerankerProtocol)
        assert not isinstance(IncompleteReranker(), RerankerProtocol)
