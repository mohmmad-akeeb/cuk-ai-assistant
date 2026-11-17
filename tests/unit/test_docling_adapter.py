"""tests/unit/test_docling_adapter.py

Unit tests for DoclingPdfParser / DoclingAdapter:
- Protocol conformance with DocumentParserProtocol
- Layout block extraction and chunking
- Graceful fallback to OfflinePdfParser (PyMuPDF)
- TableFormer and OCR fallback flags
- HTML parsing capability
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pymupdf as fitz
import pytest

from cuk_assistant.core.protocols.document_parser import (
    DocumentParserProtocol,
    ParsedDocument,
)
from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.ingestion.extract.docling_adapter import (
    DoclingAdapter,
    DoclingPdfParser,
)
from cuk_assistant.schemas.chunks import ChunkType


class TestDoclingAdapterProtocol:
    """Validate protocol compliance and aliasing."""

    def test_protocol_conformance(self) -> None:
        parser = DoclingPdfParser()
        assert isinstance(parser, DocumentParserProtocol)

    def test_docling_adapter_alias(self) -> None:
        assert DoclingAdapter is DoclingPdfParser
        adapter = DoclingAdapter()
        assert isinstance(adapter, DocumentParserProtocol)


class TestDoclingAdapterPdfParsing:
    """Validate PDF parsing via fast fallback / PyMuPDF."""

    @pytest.fixture
    def sample_pdf(self, tmp_path: Path) -> Path:
        pdf_path = tmp_path / "test_notice.pdf"
        doc = fitz.open()

        # Page 1: Heading and body
        page1 = doc.new_page()
        page1.insert_text(
            (50, 50),
            "# Central University of Kashmir\n\nNotification regarding admissions.\n\nAll candidates must report.",
        )

        # Page 2: Table and signatures
        page2 = doc.new_page()
        page2.insert_text(
            (50, 50),
            "Fee Details:\n| Category | Fee |\n|---|---|\n| General | 5000 |\n\nRegistrar\nCUK",
        )

        doc.save(pdf_path)
        doc.close()
        return pdf_path

    def test_parse_pdf_fallback(self, sample_pdf: Path) -> None:
        parser = DoclingPdfParser(prefer_fast=True)
        meta = {"doc_id": "notif_2024_01", "title": "Admission Notification"}
        result = parser.parse_pdf(sample_pdf, base_metadata=meta)

        assert isinstance(result, ParsedDocument)
        assert result.doc_id == "notif_2024_01"
        assert result.page_count == 2
        assert len(result.markdown_content) > 0
        assert "Central University of Kashmir" in result.markdown_content
        assert len(result.chunks) > 0
        assert any(c.doc_id == "notif_2024_01" for c in result.chunks)

    def test_parse_pdf_nonexistent_file(self, tmp_path: Path) -> None:
        telemetry = MagicMock()
        parser = DoclingPdfParser(telemetry_sink=telemetry)
        missing_file = tmp_path / "does_not_exist.pdf"

        result = parser.parse_pdf(missing_file, base_metadata={"doc_id": "missing_doc"})

        assert isinstance(result, ParsedDocument)
        assert result.doc_id == "missing_doc"
        assert result.page_count == 0
        assert result.chunks == []
        assert result.markdown_content == ""
        telemetry.tag_failure.assert_called_once_with(
            trace_id="missing_doc",
            diagnostic_code=FailureDiagnosticCode.PARSING_DEFECT,
            details={"file_path": str(missing_file), "error": "file_not_found"},
        )

    def test_parse_scanned_pdf_detects_ocr_fallback(self, tmp_path: Path) -> None:
        scanned_pdf = tmp_path / "scanned.pdf"
        doc = fitz.open()
        # Empty page with no text (simulates pure image scan)
        doc.new_page()
        doc.save(scanned_pdf)
        doc.close()

        parser = DoclingPdfParser(prefer_fast=True)
        result = parser.parse_pdf(scanned_pdf, base_metadata={"doc_id": "scanned_doc"})

        assert result.needs_ocr_fallback is True

    def test_mocked_docling_pipeline(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Mock docling import and converter
        mock_docling = MagicMock()
        mock_converter = MagicMock()
        mock_conversion = MagicMock()
        mock_conversion.document.export_to_markdown.return_value = (
            "# Docling Extracted Heading\n\nDocling paragraph content."
        )
        mock_conversion.document.tables = [MagicMock()]
        mock_conversion.document.pages = [MagicMock(), MagicMock()]
        mock_converter.convert.return_value = mock_conversion
        mock_docling.document_converter.DocumentConverter.return_value = mock_converter

        monkeypatch.setitem(sys.modules, "docling", mock_docling)
        monkeypatch.setitem(
            sys.modules, "docling.document_converter", mock_docling.document_converter
        )

        parser = DoclingPdfParser(prefer_fast=False)
        result = parser.parse_pdf(sample_pdf, base_metadata={"doc_id": "docling_doc"})

        assert result.doc_id == "docling_doc"
        assert "Docling Extracted Heading" in result.markdown_content
        assert result.tables_extracted == 1
        assert result.page_count == 2
        assert len(result.chunks) > 0

    def test_docling_exception_falls_back_gracefully(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_docling = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.side_effect = RuntimeError("Docling internal crash")
        mock_docling.document_converter.DocumentConverter.return_value = mock_converter

        monkeypatch.setitem(sys.modules, "docling", mock_docling)
        monkeypatch.setitem(
            sys.modules, "docling.document_converter", mock_docling.document_converter
        )

        telemetry = MagicMock()
        parser = DoclingPdfParser(prefer_fast=False, telemetry_sink=telemetry)
        result = parser.parse_pdf(sample_pdf, base_metadata={"doc_id": "crash_test"})

        # Falls back to offline parser
        assert result.doc_id == "crash_test"
        assert "Central University of Kashmir" in result.markdown_content
        telemetry.tag_failure.assert_called_once()
        assert (
            telemetry.tag_failure.call_args[1]["diagnostic_code"]
            == FailureDiagnosticCode.PARSING_DEFECT
        )


class TestDoclingAdapterHtmlParsing:
    """Validate HTML parsing through DoclingAdapter."""

    def test_parse_html_generates_markdown_and_chunks(self) -> None:
        html = """
        <html>
            <body>
                <h1>Department of Information Technology</h1>
                <p>Curriculum updates for Semester 3.</p>
                <table>
                    <tr><th>Course</th><th>Credits</th></tr>
                    <tr><td>IT-301 Algorithms</td><td>4</td></tr>
                </table>
            </body>
        </html>
        """
        parser = DoclingPdfParser()
        result = parser.parse_html(html, base_metadata={"doc_id": "it_dept_01"})

        assert isinstance(result, ParsedDocument)
        assert result.doc_id == "it_dept_01"
        assert "Department of Information Technology" in result.markdown_content
        assert "| Course | Credits |" in result.markdown_content
        assert result.tables_extracted >= 1
        assert len(result.chunks) >= 3

        types = [c.chunk_type for c in result.chunks]
        assert ChunkType.HEADING in types
        assert ChunkType.MARKDOWN_TABLE in types
