"""Offline PDF parser using PyMuPDF.

Extracts continuous Markdown text with page demarcations (--- Page X ---),
fast table extraction avoiding CPU hangs, embedded dates, and OCR detection.
Emits exactly 1 canonical document per PDF.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cuk_assistant.ingestion.parsers.base import BaseParser, ParsedPdf

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b")


class OfflinePdfParser(BaseParser):
    """Parses local raw PDF files into structured Markdown and metadata."""

    @staticmethod
    def _extract_embedded_date(doc: Any) -> str:
        try:
            meta = doc.metadata or {}
            for field in ("creationDate", "modDate"):
                val = meta.get(field, "")
                if val and val.startswith("D:"):
                    raw = val[2:10]
                    try:
                        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
                    except ValueError:
                        pass
            if len(doc) > 0:
                first_text = doc[0].get_text()[:500]
                m = _DATE_RE.search(first_text)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_title(doc: Any, fallback: str) -> str:
        try:
            t = ((doc.metadata or {}).get("title") or "").strip()
            if t and len(t) > 3:
                return t
        except Exception:
            pass
        return fallback

    def parse_file(self, file_path: Path, fallback_title: str = "", **kwargs: Any) -> ParsedPdf:
        """Parse local PDF file into ParsedPdf result."""
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                logger.error("PyMuPDF not installed — cannot parse PDF %s", file_path)
                return ParsedPdf(
                    text="",
                    page_count=0,
                    text_pages=0,
                    scanned_pages=0,
                    table_count=0,
                    embedded_date="",
                    pdf_title=fallback_title,
                    needs_ocr=False,
                )

        if not file_path.exists():
            logger.warning("PDF file does not exist: %s", file_path)
            return ParsedPdf(
                text="",
                page_count=0,
                text_pages=0,
                scanned_pages=0,
                table_count=0,
                embedded_date="",
                pdf_title=fallback_title,
                needs_ocr=False,
            )

        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            logger.warning("Failed to open PDF %s: %s", file_path, exc)
            return ParsedPdf(
                text="",
                page_count=0,
                text_pages=0,
                scanned_pages=0,
                table_count=0,
                embedded_date="",
                pdf_title=fallback_title,
                needs_ocr=False,
            )

        total_pages = len(doc)
        text_pages = 0
        table_count = 0
        page_texts: list[str] = []

        for i, page in enumerate(doc):
            ptext = page.get_text().strip()
            if len(ptext) >= 50:
                text_pages += 1
            if ptext:
                page_texts.append(f"--- Page {i + 1} ---\n{ptext}")

            # Fast table extraction: only check pages with text and reasonable drawings count
            if i < 5:  # sample first few pages to avoid CPU hangs on massive vector drawings
                try:
                    tables = page.find_tables(strategy="lines")
                    table_count += len(tables.tables)
                except Exception:
                    pass

        scanned_pages = total_pages - text_pages
        embedded_date = self._extract_embedded_date(doc)
        pdf_title = self._extract_title(doc, fallback_title)
        needs_ocr = scanned_pages > 0 and text_pages == 0

        full_text = "\n\n".join(page_texts).strip()
        doc.close()

        return ParsedPdf(
            text=full_text,
            page_count=total_pages,
            text_pages=text_pages,
            scanned_pages=scanned_pages,
            table_count=table_count,
            embedded_date=embedded_date,
            pdf_title=pdf_title,
            needs_ocr=needs_ocr,
        )


__all__ = [
    "OfflinePdfParser",
    "ParsedPdf",
]
