"""tests/unit/test_lancedb_store.py

Unit tests for LanceDBStore embedded hybrid vector store adapter.
"""

from pathlib import Path

import pytest

from cuk_assistant.core.protocols.storage import VectorStoreProtocol
from cuk_assistant.core.registry import get_vector_store_cls
from cuk_assistant.retrieval.lancedb_store import LanceDBStore
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType, ParentChunkContainer


@pytest.fixture
def temp_lancedb_store(tmp_path: Path) -> LanceDBStore:
    """Fixture providing a clean LanceDBStore in a temporary directory."""
    db_dir = tmp_path / "lancedb_test"
    return LanceDBStore(db_path=db_dir)


class TestLanceDBStore:
    """Validate LanceDBStore operations, hybrid search, filtering, and protocol conformance."""

    def test_protocol_conformance(self, temp_lancedb_store: LanceDBStore) -> None:
        assert isinstance(temp_lancedb_store, VectorStoreProtocol)

    def test_registered_in_registry(self) -> None:
        cls = get_vector_store_cls("lancedb")
        assert cls is LanceDBStore

    def test_empty_store_search(self, temp_lancedb_store: LanceDBStore) -> None:
        results = temp_lancedb_store.hybrid_search(
            query_text="admissions",
            query_vector=[0.1] * 384,
            top_k=5,
        )
        assert results == []

    def test_add_chunks_and_hybrid_search(self, temp_lancedb_store: LanceDBStore) -> None:
        chunk1 = ChunkRecord(
            chunk_id="doc1::c0",
            doc_id="doc1",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Central University of Kashmir admissions criteria for 2024 academic year.",
            token_count=12,
            metadata={
                "school": "School of Life Sciences",
                "department": "Department of Biotechnology",
                "doc_type": "admission",
                "title": "Admissions 2024",
                "is_university_wide": True,
            },
        )
        chunk2 = ChunkRecord(
            chunk_id="doc2::c0",
            doc_id="doc2",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Tender notice for cafeteria catering services at Tulmulla campus.",
            token_count=10,
            metadata={
                "school": "Administration",
                "department": "Estate Section",
                "doc_type": "tender",
                "title": "Cafeteria Tender",
                "is_university_wide": False,
            },
        )

        vec1 = [0.05] * 384
        vec2 = [-0.05] * 384

        temp_lancedb_store.add_chunks([chunk1, chunk2], [vec1, vec2])

        # Query for admissions
        results = temp_lancedb_store.hybrid_search(
            query_text="admissions criteria 2024",
            query_vector=vec1,
            top_k=2,
        )

        assert len(results) >= 1
        assert results[0].chunk_id == "doc1::c0"
        assert results[0].score > 0.0
        assert results[0].rrf_rank == 1

    def test_scoped_where_filtering(self, temp_lancedb_store: LanceDBStore) -> None:
        chunk_biotech = ChunkRecord(
            chunk_id="bio::c0",
            doc_id="bio",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Biotechnology lab syllabus and course outline.",
            token_count=8,
            metadata={"department": "Department of Biotechnology", "is_university_wide": False},
        )
        chunk_cs = ChunkRecord(
            chunk_id="cs::c0",
            doc_id="cs",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Computer Science algorithms syllabus and lab.",
            token_count=8,
            metadata={"department": "Department of Computer Science", "is_university_wide": False},
        )

        temp_lancedb_store.add_chunks(
            [chunk_biotech, chunk_cs],
            [[0.01] * 384, [0.02] * 384],
        )

        # Scoped search for Biotechnology only
        results = temp_lancedb_store.hybrid_search(
            query_text="syllabus",
            query_vector=[0.01] * 384,
            top_k=5,
            where_filter="department = 'Department of Biotechnology'",
        )

        assert len(results) == 1
        assert results[0].chunk_id == "bio::c0"

    def test_parent_chunk_storage_and_retrieval(self, temp_lancedb_store: LanceDBStore) -> None:
        parent = ParentChunkContainer(
            parent_chunk_id="doc1::p0",
            doc_id="doc1",
            heading_title="Unit 1: Genetics",
            heading_level=2,
            section_token_count=120,
            full_section_text="## Unit 1: Genetics\nFundamentals of molecular genetics.",
            child_chunk_ids=["doc1::c0"],
        )
        temp_lancedb_store.add_parent_chunks([parent])

        retrieved = temp_lancedb_store.get_parent_chunk("doc1::p0")
        assert retrieved is not None
        assert retrieved.parent_chunk_id == "doc1::p0"
        assert retrieved.heading_title == "Unit 1: Genetics"
        assert retrieved.full_section_text == parent.full_section_text

        # Nonexistent parent
        assert temp_lancedb_store.get_parent_chunk("nonexistent::p99") is None

    def test_deterministic_regex_search(self, temp_lancedb_store: LanceDBStore) -> None:
        chunk = ChunkRecord(
            chunk_id="notices::c1",
            doc_id="notices",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Administrative Order No: CUK/Acad/2023/102 regarding winter vacations.",
            token_count=12,
            metadata={"title": "Notice CUK/Acad/2023/102"},
        )
        temp_lancedb_store.add_chunks([chunk], [[0.0] * 384])

        matches = temp_lancedb_store.deterministic_regex_search("CUK/Acad/2023/102")
        assert len(matches) == 1
        assert matches[0].chunk_id == "notices::c1"

        # No match test
        no_matches = temp_lancedb_store.deterministic_regex_search("NONEXISTENT/CODE/999")
        assert len(no_matches) == 0

    def test_delete_document(self, temp_lancedb_store: LanceDBStore) -> None:
        c1 = ChunkRecord(
            chunk_id="del_doc::c0",
            doc_id="del_doc",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Content to be deleted.",
            token_count=5,
        )
        temp_lancedb_store.add_chunks([c1], [[0.0] * 384])

        parent = ParentChunkContainer(
            parent_chunk_id="del_doc::p0",
            doc_id="del_doc",
            heading_title="Section to delete",
            heading_level=1,
            section_token_count=5,
            full_section_text="Delete me",
            child_chunk_ids=["del_doc::c0"],
        )
        temp_lancedb_store.add_parent_chunks([parent])

        temp_lancedb_store.delete_document("del_doc")

        assert temp_lancedb_store.get_parent_chunk("del_doc::p0") is None
        assert temp_lancedb_store.deterministic_regex_search("Content to be deleted") == []
