"""Abstract BaseParser Protocol and intermediate dataclasses for offline ingestion transforms.

Pure transformation with zero external network or LLM dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LinkOut:
    """Hyperlink discovered within an HTML or document body."""

    text: str
    href: str
    type: str  # "pdf" | "internal_route" | "external"


@dataclass(frozen=True)
class ParsedHTML:
    """Structured representation of parsed HTML document."""

    text: str
    links_out: list[LinkOut] = field(default_factory=list)
    char_count: int = 0
    tables_extracted: int = 0


@dataclass(frozen=True)
class ParsedPdf:
    """Structured representation of parsed PDF binary."""

    text: str
    page_count: int
    text_pages: int
    scanned_pages: int
    table_count: int
    embedded_date: str
    pdf_title: str
    needs_ocr: bool


@dataclass(frozen=True)
class ParsedApiRecord:
    """Structured representation of normalized API JSON payload."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BaseParser(Protocol):
    """Abstract protocol for offline document parsers."""

    def parse_file(self, file_path: Path, **kwargs: Any) -> Any:
        """Parse an offline raw asset from disk."""
        ...


__all__ = [
    "BaseParser",
    "LinkOut",
    "ParsedApiRecord",
    "ParsedHTML",
    "ParsedPdf",
]
