"""PDF downloader + text extractor with rich metadata.

For each PDF URL:
  1. HEAD → record size and content-type.
  2. GET body (skip if > MAX_PDF_BYTES or sensitive_candidate).
  3. Extract with PyMuPDF: full text across all pages, table count, embedded dates,
     page count, text vs scanned ratio.
  4. Return a list containing exactly one Document dict representing the entire PDF.
     Chunking is handled downstream by HierarchicalChunker.

A Document dict has two top-level keys:
  "text"     — the extracted text (empty for sensitive PDFs)
  "metadata" — the full metadata dict (from metadata_builder + PDF-specific fields)
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime
from typing import Any

from cuk_assistant.core.config import Settings
from cuk_assistant.core.http_cache import CachedClient

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b")


def _extract_embedded_date(doc: Any) -> str:
    try:
        meta = doc.metadata
        for field in ("creationDate", "modDate"):
            val = meta.get(field, "")
            if val and val.startswith("D:"):
                raw = val[2:10]
                try:
                    return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
                except ValueError:
                    pass
        # Scan first page text
        if len(doc) > 0:
            text = doc[0].get_text()[:500]
            m = _DATE_RE.search(text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def _extract_title_from_pdf(doc: Any, fallback: str) -> str:
    try:
        t = (doc.metadata.get("title") or "").strip()
        if t and len(t) > 3:
            return t
    except Exception:
        pass
    return fallback


async def extract_pdf(
    url: str,
    base_metadata: dict,
    client: CachedClient,
    settings: Settings,
) -> list[dict]:
    """
    Download and extract a PDF. Returns a list of Document dicts.
    Returns empty list on failure or if PDF is too large.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed — cannot extract PDFs")
        return []

    # URL-encode spaces and other unsafe chars in the path (preserve scheme+host)
    parsed = urllib.parse.urlparse(url)
    safe_path = urllib.parse.quote(parsed.path, safe="/%")
    safe_url = urllib.parse.urlunparse(parsed._replace(path=safe_path))

    is_sensitive = base_metadata.get("is_sensitive", False)
    file_name = base_metadata.get("file_name", url.split("/")[-1])

    # Check local disk cache first
    raw_pdf_dir = settings.project_root / "data" / "raw" / "pdf"
    raw_pdf_dir.mkdir(parents=True, exist_ok=True)
    save_name = file_name or safe_url.split("/")[-1]
    save_name = save_name.split("?")[0]
    raw_pdf_path = raw_pdf_dir / save_name

    body: bytes | None = None
    if raw_pdf_path.exists() and raw_pdf_path.stat().st_size > 0:
        logger.debug("PDF cached on disk: %s", raw_pdf_path)
        body = raw_pdf_path.read_bytes()
    else:
        # HEAD first
        try:
            head = await client.head(safe_url)
            size_bytes = int(head.headers.get("content-length", 0) or 0)
            if size_bytes > settings.max_pdf_bytes:
                logger.info("PDF too large — skipping text", extra={"url": url, "size": size_bytes})
                meta = {
                    **base_metadata,
                    "pdf_pages": 0,
                    "page_count": 0,
                    "pdf_text_pages": 0,
                    "pdf_scanned_pages": 0,
                    "pdf_table_count": 0,
                    "pdf_embedded_date": "",
                    "pdf_size_bytes": size_bytes,
                    "pdf_title": "",
                    "skipped_reason": f"too_large ({size_bytes} bytes)",
                    "page_number": None,
                    "chunk_index": 0,
                }
                return [{"text": "", "metadata": meta}]
        except Exception as exc:
            logger.warning("HEAD failed for %s: %s", url, exc)

        # GET body
        try:
            resp = await client.get(safe_url)
            if resp.status != 200 or not resp.body:
                logger.warning("GET failed for %s: status %d", url, resp.status)
                return []
            body = resp.body
            if not body.startswith(b"%PDF"):
                logger.warning(
                    "Response for %s is not a PDF (%d bytes, starts: %r)", url, len(body), body[:20]
                )
                return []
            raw_pdf_path.write_bytes(body)
            logger.debug("Saved raw PDF: %s", raw_pdf_path)
        except Exception as exc:
            logger.warning("GET error for %s: %s", url, exc)
            return []

    # Parse PDF
    try:
        doc = fitz.open(stream=body, filetype="pdf")
    except Exception as exc:
        logger.warning("PDF parse failed for %s: %s", url, exc)
        return []

    total_pages = len(doc)
    text_pages = sum(1 for p in doc if len(p.get_text().strip()) >= 50)
    scanned_pages = total_pages - text_pages
    table_count = sum(len(p.find_tables().tables) for p in doc)
    embedded_date = _extract_embedded_date(doc)
    pdf_title = _extract_title_from_pdf(doc, base_metadata.get("title", file_name))

    pdf_meta_fields = {
        "pdf_pages": total_pages,
        "page_count": total_pages,
        "pdf_text_pages": text_pages,
        "pdf_scanned_pages": scanned_pages,
        "pdf_table_count": table_count,
        "pdf_embedded_date": embedded_date,
        "pdf_size_bytes": len(body),
        "pdf_title": pdf_title,
        "skipped_reason": "",
    }

    # B6: needs_ocr flag
    needs_ocr = scanned_pages > 0

    # Import here to avoid circular import
    from cuk_assistant.ingestion.crawl.metadata_builder import _content_hash
    from cuk_assistant.ingestion.crawl.metadata_builder import _doc_id as _make_doc_id

    base_doc_id_key = base_metadata.get("record_id", "")
    base_endpoint = base_metadata.get("raw_api_endpoint", "")

    if is_sensitive:
        # PII guard: store metadata only, no text
        doc.close()
        meta = {
            **base_metadata,
            **pdf_meta_fields,
            "page_number": None,
            "page_count": total_pages,
            "chunk_index": 0,
            "needs_ocr": needs_ocr,
            "content_hash": "",
            "doc_id": _make_doc_id(base_endpoint, base_doc_id_key, ""),
        }
        return [{"text": "[REDACTED — sensitive document]", "metadata": meta}]

    full_text = "\n\n".join(
        f"--- Page {i + 1} ---\n{page.get_text().strip()}"
        for i, page in enumerate(doc)
        if page.get_text().strip()
    ).strip()

    meta = {
        **base_metadata,
        **pdf_meta_fields,
        "page_number": None,
        "page_count": total_pages,
        "chunk_index": 0,
        "needs_ocr": needs_ocr,
        "content_hash": _content_hash(full_text),
        "doc_id": _make_doc_id(base_endpoint, base_doc_id_key, ""),
    }

    doc.close()

    logger.info(
        "PDF extracted",
        extra={
            "url": url,
            "pages": total_pages,
            "text_pages": text_pages,
            "chunks": 1,
        },
    )
    return [{"text": full_text, "metadata": meta}]
