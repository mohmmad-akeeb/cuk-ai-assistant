"""cuk_assistant.ingestion.parsers.subsystems/docling_adapter.py

Layout-aware PDF and document parser adapter conforming to DocumentParserProtocol.
Provides Docling layout parsing with TableFormer and OCR fallback, utilizing OfflinePdfParser
(PyMuPDF) when Docling is unavailable or when fast text extraction is requested.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from cuk_assistant.core.protocols.document_parser import (
    ParsedDocument,
)
from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.ingestion.chunking.hierarchical_chunker import HierarchicalChunker
from cuk_assistant.ingestion.parsers.html_parser import OfflineHtmlParser
from cuk_assistant.ingestion.parsers.pdf_parser import OfflinePdfParser

logger = logging.getLogger(__name__)


def _is_docling_available() -> bool:
    """Check whether docling library is installed in the current environment."""
    try:
        import docling  # noqa: F401

        return True
    except ImportError:
        return False


class DoclingPdfParser:
    """Document parser conforming to DocumentParserProtocol.

    Extracts layout blocks (headings, paragraphs, tables as Markdown).
    Falls back gracefully to PyMuPDF (OfflinePdfParser) when Docling is unavailable
    or when prefer_fast is enabled.
    """

    def __init__(
        self,
        prefer_fast: bool = False,
        chunker: HierarchicalChunker | None = None,
        telemetry_sink: Any | None = None,
    ) -> None:
        self.prefer_fast = prefer_fast
        self.chunker = chunker or HierarchicalChunker()
        self.telemetry_sink = telemetry_sink
        self.offline_pdf_parser = OfflinePdfParser()
        self.offline_html_parser = OfflineHtmlParser()

    def parse_pdf(self, file_path: Path, base_metadata: dict[str, Any]) -> ParsedDocument:
        """Parse local PDF file into Markdown and structured chunk models."""
        doc_id = str(
            base_metadata.get("doc_id")
            or hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:24]
        )

        if not file_path.exists():
            logger.warning("PDF file does not exist: %s", file_path)
            if self.telemetry_sink:
                self.telemetry_sink.tag_failure(
                    trace_id=doc_id,
                    diagnostic_code=FailureDiagnosticCode.PARSING_DEFECT,
                    details={"file_path": str(file_path), "error": "file_not_found"},
                )
            return ParsedDocument(
                doc_id=doc_id,
                markdown_content="",
                chunks=[],
                page_count=0,
                tables_extracted=0,
                needs_ocr_fallback=False,
            )

        # Fast path or fallback when Docling is not installed
        if self.prefer_fast or not _is_docling_available():
            return self._parse_pdf_offline(file_path, doc_id, base_metadata)

        # Docling layout extraction path
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            conversion_res = converter.convert(str(file_path))
            markdown_text = conversion_res.document.export_to_markdown()

            tables_count = 0
            if hasattr(conversion_res.document, "tables"):
                tables_count = len(conversion_res.document.tables)
            elif hasattr(conversion_res.document, "find_elements"):
                tables_count = len(conversion_res.document.find_elements(type="table"))

            page_count = 1
            if hasattr(conversion_res.document, "pages"):
                page_count = len(conversion_res.document.pages)

            needs_ocr = len(markdown_text.strip()) < 50 and page_count > 0

            chunks = (
                self.chunker.chunk_markdown(
                    doc_id=doc_id,
                    markdown_text=markdown_text,
                    base_metadata=base_metadata,
                )
                if markdown_text.strip()
                else []
            )

            return ParsedDocument(
                doc_id=doc_id,
                markdown_content=markdown_text,
                chunks=chunks,
                page_count=max(1, page_count),
                tables_extracted=tables_count,
                needs_ocr_fallback=needs_ocr,
            )
        except Exception as exc:
            logger.warning(
                "Docling parsing failed for %s (%s). Falling back to OfflinePdfParser.",
                file_path,
                exc,
            )
            if self.telemetry_sink:
                self.telemetry_sink.tag_failure(
                    trace_id=doc_id,
                    diagnostic_code=FailureDiagnosticCode.PARSING_DEFECT,
                    details={"file_path": str(file_path), "error": str(exc)},
                )
            return self._parse_pdf_offline(file_path, doc_id, base_metadata)

    def _parse_pdf_offline(
        self, file_path: Path, doc_id: str, base_metadata: dict[str, Any]
    ) -> ParsedDocument:
        """Fallback extraction using PyMuPDF (OfflinePdfParser)."""
        fallback_title = str(base_metadata.get("title", ""))
        parsed_pdf = self.offline_pdf_parser.parse_file(file_path, fallback_title=fallback_title)

        markdown_text = parsed_pdf.text
        chunks = (
            self.chunker.chunk_markdown(
                doc_id=doc_id,
                markdown_text=markdown_text,
                base_metadata=base_metadata,
            )
            if markdown_text.strip()
            else []
        )

        return ParsedDocument(
            doc_id=doc_id,
            markdown_content=markdown_text,
            chunks=chunks,
            page_count=max(1, parsed_pdf.page_count),
            tables_extracted=parsed_pdf.table_count,
            needs_ocr_fallback=parsed_pdf.needs_ocr,
        )

    def parse_html(self, html_content: str, base_metadata: dict[str, Any]) -> ParsedDocument:
        """Parse HTML string into clean Markdown and structured chunks."""
        doc_id = str(
            base_metadata.get("doc_id")
            or hashlib.sha256(html_content[:200].encode("utf-8")).hexdigest()[:24]
        )

        parsed_html = self.offline_html_parser.parse_string(html_content)
        markdown_text = parsed_html.text

        chunks = (
            self.chunker.chunk_markdown(
                doc_id=doc_id,
                markdown_text=markdown_text,
                base_metadata=base_metadata,
            )
            if markdown_text.strip()
            else []
        )

        return ParsedDocument(
            doc_id=doc_id,
            markdown_content=markdown_text,
            chunks=chunks,
            page_count=1,
            tables_extracted=parsed_html.tables_extracted,
            needs_ocr_fallback=False,
        )


# Alias for compatibility with roadmap and specifications
DoclingAdapter = DoclingPdfParser

__all__ = [
    "DoclingAdapter",
    "DoclingPdfParser",
]
