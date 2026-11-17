"""tests/unit/test_protocols_chunk.py

Unit tests for ChunkRecord, ChunkType, ParsedDocument, and DocumentParserProtocol.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cuk_assistant.core.protocols.document_parser import (
    DocumentParserProtocol,
    ParsedDocument,
)
from cuk_assistant.schemas.chunks import (
    Chunk,
    ChunkRecord,
    ChunkType,
    ParentChunkContainer,
)


class TestChunkTypeEnum:
    """Validate ChunkType taxonomy."""

    def test_chunk_type_values(self) -> None:
        assert ChunkType.PARAGRAPH == "paragraph"
        assert ChunkType.MARKDOWN_TABLE == "markdown_table"
        assert ChunkType.HEADING == "heading"
        assert ChunkType.LIST_ITEM == "list_item"
        assert ChunkType.CODE_OR_FORMULA == "code_or_formula"

    def test_chunk_type_is_str_subclass(self) -> None:
        assert isinstance(ChunkType.PARAGRAPH, str)


class TestChunkRecordSchema:
    """Validate ChunkRecord Pydantic model invariants."""

    def test_valid_instantiation_minimal(self) -> None:
        chunk = ChunkRecord(
            chunk_id="doc1::c0",
            doc_id="doc1",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Introduction to Computer Science at CUK.",
            token_count=7,
        )
        assert chunk.chunk_id == "doc1::c0"
        assert chunk.doc_id == "doc1"
        assert chunk.chunk_index == 0
        assert chunk.chunk_type == ChunkType.PARAGRAPH
        assert chunk.text_content == "Introduction to Computer Science at CUK."
        assert chunk.token_count == 7
        assert chunk.page_number == 1
        assert chunk.start_line is None
        assert chunk.end_line is None
        assert chunk.table_bbox is None
        assert chunk.section_heading is None
        assert chunk.heading_path == []
        assert chunk.parent_chunk_id is None
        assert chunk.prev_chunk_id is None
        assert chunk.next_chunk_id is None
        assert chunk.metadata == {}

    def test_alias_chunk_is_chunk_record(self) -> None:
        assert Chunk is ChunkRecord

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ChunkRecord(  # type: ignore[call-arg]
                chunk_id="doc1::c0",
                doc_id="doc1",
                chunk_index=0,
                chunk_type=ChunkType.PARAGRAPH,
                text_content="Content",
                token_count=1,
                unsupported_extra_attribute="illegal",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_frozen_immutability(self) -> None:
        chunk = ChunkRecord(
            chunk_id="doc1::c0",
            doc_id="doc1",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Content",
            token_count=1,
        )
        with pytest.raises(ValidationError) as exc_info:
            chunk.text_content = "Modified Content"  # type: ignore[misc]
        assert "frozen_instance" in str(exc_info.value)

    def test_serialization_round_trip(self) -> None:
        original = ChunkRecord(
            chunk_id="doc1::c1",
            doc_id="doc1",
            chunk_index=1,
            chunk_type=ChunkType.MARKDOWN_TABLE,
            text_content="| Col 1 | Col 2 |\n|---|---|\n| A | B |",
            token_count=15,
            page_number=3,
            start_line=10,
            end_line=13,
            table_bbox=[10.0, 20.0, 100.0, 80.0],
            section_heading="Fee Structure",
            heading_path=["Admissions", "Fees", "Fee Structure"],
            parent_chunk_id="doc1::c0",
            prev_chunk_id="doc1::c0",
            next_chunk_id="doc1::c2",
            metadata={"academic_year": 2024},
        )
        raw_dict = original.model_dump()
        reconstructed = ChunkRecord.model_validate(raw_dict)
        assert reconstructed == original
        assert reconstructed.table_bbox == [10.0, 20.0, 100.0, 80.0]
        assert reconstructed.heading_path == ["Admissions", "Fees", "Fee Structure"]


class TestParentChunkContainer:
    """Validate ParentChunkContainer Pydantic model invariants."""

    def test_parent_chunk_container_instantiation(self) -> None:
        container = ParentChunkContainer(
            parent_chunk_id="doc1::p0",
            doc_id="doc1",
            heading_title="Department of Computer Science",
            heading_level=2,
            section_token_count=450,
            full_section_text="## Department of Computer Science\n\nFull section text...",
            child_chunk_ids=["doc1::c1", "doc1::c2"],
        )
        assert container.parent_chunk_id == "doc1::p0"
        assert container.heading_level == 2
        assert container.child_chunk_ids == ["doc1::c1", "doc1::c2"]

    def test_parent_chunk_container_frozen_and_extra_forbidden(self) -> None:
        container = ParentChunkContainer(
            parent_chunk_id="doc1::p0",
            doc_id="doc1",
            heading_title="Title",
            heading_level=1,
            section_token_count=10,
            full_section_text="# Title",
        )
        with pytest.raises(ValidationError):
            container.heading_title = "New Title"  # type: ignore[misc]

        with pytest.raises(ValidationError):
            ParentChunkContainer(  # type: ignore[call-arg]
                parent_chunk_id="doc1::p0",
                doc_id="doc1",
                heading_title="Title",
                heading_level=1,
                section_token_count=10,
                full_section_text="# Title",
                extra_field="disallowed",
            )


class TestParsedDocument:
    """Validate ParsedDocument container."""

    def test_parsed_document_defaults(self) -> None:
        doc = ParsedDocument(
            doc_id="doc_cuk_001",
            markdown_content="# Central University of Kashmir",
        )
        assert doc.doc_id == "doc_cuk_001"
        assert doc.markdown_content == "# Central University of Kashmir"
        assert doc.chunks == []
        assert doc.page_count == 1
        assert doc.tables_extracted == 0
        assert doc.needs_ocr_fallback is False

    def test_parsed_document_with_chunks(self) -> None:
        chunk = ChunkRecord(
            chunk_id="doc_cuk_001::c0",
            doc_id="doc_cuk_001",
            chunk_index=0,
            chunk_type=ChunkType.HEADING,
            text_content="# Central University of Kashmir",
            token_count=5,
        )
        doc = ParsedDocument(
            doc_id="doc_cuk_001",
            markdown_content="# Central University of Kashmir",
            chunks=[chunk],
            page_count=2,
            tables_extracted=1,
            needs_ocr_fallback=True,
        )
        assert len(doc.chunks) == 1
        assert doc.tables_extracted == 1
        assert doc.needs_ocr_fallback is True

    def test_parsed_document_frozen(self) -> None:
        doc = ParsedDocument(
            doc_id="doc1",
            markdown_content="content",
        )
        with pytest.raises(ValidationError):
            doc.page_count = 5  # type: ignore[misc]


class TestDocumentParserProtocol:
    """Validate runtime checkability of DocumentParserProtocol."""

    def test_conforming_adapter_isinstance(self) -> None:
        class MockParser:
            def parse_pdf(self, file_path: Path, base_metadata: dict[str, Any]) -> ParsedDocument:
                return ParsedDocument(
                    doc_id="mock_pdf",
                    markdown_content="mock content",
                )

            def parse_html(
                self, html_content: str, base_metadata: dict[str, Any]
            ) -> ParsedDocument:
                return ParsedDocument(
                    doc_id="mock_html",
                    markdown_content="mock content",
                )

        parser = MockParser()
        assert isinstance(parser, DocumentParserProtocol)

    def test_non_conforming_adapter_fails_isinstance(self) -> None:
        class IncompleteParser:
            def parse_pdf(self, file_path: Path, base_metadata: dict[str, Any]) -> ParsedDocument:
                return ParsedDocument(doc_id="incomplete", markdown_content="")

        incomplete = IncompleteParser()
        assert not isinstance(incomplete, DocumentParserProtocol)
