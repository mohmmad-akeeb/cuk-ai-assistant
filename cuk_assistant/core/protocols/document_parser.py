"""cuk_assistant/core/protocols/document_parser.py

Abstract Document Parser Protocol and parsed document container.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.schemas.chunks import ChunkRecord


class ParsedDocument(BaseModel):
    """Output representation of raw PDF/HTML extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(..., description="Unique document identifier")
    markdown_content: str = Field(..., description="Extracted Markdown representation")
    chunks: list[ChunkRecord] = Field(default_factory=list, description="Structured chunk models")
    page_count: int = Field(default=1, description="Physical page count")
    tables_extracted: int = Field(default=0, description="Count of extracted tables")
    needs_ocr_fallback: bool = Field(
        default=False,
        description="Flag indicating scanned/low-quality PDF needing OCR fallback",
    )


@runtime_checkable
class DocumentParserProtocol(Protocol):
    """Abstract contract for document parsing engines (Docling, TableFormer, RapidOCR)."""

    def parse_pdf(self, file_path: Path, base_metadata: dict[str, Any]) -> ParsedDocument:
        """Parse digital or scanned PDF into Markdown and structured chunk models."""
        ...

    def parse_html(self, html_content: str, base_metadata: dict[str, Any]) -> ParsedDocument:
        """Parse static or dynamic HTML text into clean Markdown and chunks."""
        ...


__all__ = [
    "DocumentParserProtocol",
    "ParsedDocument",
]
