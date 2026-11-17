"""Offline Parsing and Normalization Pipeline.

Reads data/raw/manifest.jsonl, dispatches assets across offline parsers
via a worker pool, applies multi-route reference aggregation and PII sanitization,
validates against cuk_assistant.schemas.document.Document, and writes canonical
documents to data/processed/documents.jsonl.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cuk_assistant.ingestion.normalization.subsystems.aggregator import aggregate_asset_references
from cuk_assistant.ingestion.normalization.subsystems.sanitizer import scrub_pii
from cuk_assistant.ingestion.parsers.html_parser import OfflineHtmlParser
from cuk_assistant.ingestion.parsers.pdf_parser import OfflinePdfParser
from cuk_assistant.schemas.document import Document

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParseStats:
    total_assets: int
    pdf_count: int
    html_count: int
    api_count: int
    output_count: int
    errors: int


def _resolve_asset_path(local_rel: str, project_root: Path) -> Path:
    if not local_rel:
        return project_root / "unknown"
    p = Path(local_rel)
    if p.is_file():
        return p
    if (project_root / local_rel).is_file():
        return project_root / local_rel
    unquoted = urllib.parse.unquote(local_rel)
    if Path(unquoted).is_file():
        return Path(unquoted)
    if (project_root / unquoted).is_file():
        return project_root / unquoted
    return project_root / local_rel


def _infer_doc_type(rec: dict, entry: dict) -> str:
    raw_meta = entry.get("raw_meta", {})
    endpoint = (raw_meta.get("endpoint") or raw_meta.get("api_endpoint") or "").lower()
    content_type = (rec.get("content_type") or raw_meta.get("content_type") or "").lower()
    if content_type:
        return content_type
    if "faculty" in endpoint or "FirstName" in rec or "Designation" in rec:
        return "faculty"
    if "tender" in endpoint or "TenderNo" in rec or "TenderTitle" in rec:
        return "tender"
    if "admission" in endpoint:
        return "admission"
    if "employment" in endpoint:
        return "employment"
    if "notice" in endpoint or "NoticeTitle" in rec:
        return "notice"
    if "pressrelease" in endpoint:
        return "press_release"
    return "api_record"


def _parse_single_html(
    entry: dict[str, Any],
    local_path: Path,
) -> dict[str, Any] | None:
    html_parser = OfflineHtmlParser()
    raw_meta = dict(entry.get("raw_meta", {}))
    prov = entry.get("provenance", {})

    parsed = html_parser.parse_file(local_path)
    text = parsed.text or raw_meta.get("text", "")
    text = scrub_pii(text)
    if not text.strip():
        return None

    meta = dict(raw_meta)
    for k, v in prov.items():
        if k not in meta:
            meta[k] = v

    now_iso = datetime.now(tz=UTC).isoformat()
    meta["scraped_at"] = now_iso
    meta["source_url"] = entry.get("source_url") or meta.get("page_url", "")
    meta["page_url"] = meta.get("page_url") or meta.get("source_url", "")
    meta["api_endpoint"] = meta.get("api_endpoint") or meta.get("route_name") or "html"
    meta["raw_api_endpoint"] = meta["api_endpoint"]
    meta["content_hash"] = _content_hash(text)
    meta["doc_id"] = hashlib.sha256(
        f"html::{entry.get('asset_id')}::{local_path.name}".encode()
    ).hexdigest()[:24]
    meta["page_number"] = None
    meta["chunk_index"] = 0
    if "content_type" not in meta:
        meta["content_type"] = (
            "department_page"
            if "department" in meta.get("route_name", "").lower()
            or "depart" in meta.get("route_name", "").lower()
            else "administrative_page"
        )

    if parsed.links_out:
        meta["links_out"] = [
            {"text": lo.text, "href": lo.href, "type": lo.type} for lo in parsed.links_out
        ]

    # Validate against Document schema
    doc = Document(text=text, metadata=meta)
    return doc.model_dump()


def _parse_single_api(
    entry: dict[str, Any],
    local_path: Path,
) -> list[dict[str, Any]]:
    api_parser = OfflineApiParser()
    raw_meta = dict(entry.get("raw_meta", {}))
    prov = entry.get("provenance", {})

    if not local_path.is_file():
        return []

    try:
        data = json.loads(local_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read JSON %s: %s", local_path, exc)
        return []

    records = (
        data.get("records")
        if isinstance(data, dict)
        else (data if isinstance(data, list) else None)
    )
    if records is None:
        records = [data] if isinstance(data, dict) else []

    results: list[dict[str, Any]] = []
    now_iso = datetime.now(tz=UTC).isoformat()

    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        text = api_parser.format_record_text(rec)
        if not text.strip():
            continue
        text = scrub_pii(text)

        doc_type = _infer_doc_type(rec, entry)
        meta = dict(raw_meta)
        for k, v in prov.items():
            if k not in meta:
                meta[k] = v

        for rk, rv in rec.items():
            if isinstance(rv, (str, int, float, bool)) and len(str(rv)) < 500:
                meta[rk] = rv

        meta["doc_type"] = doc_type
        meta["content_type"] = doc_type
        meta["content_hash"] = _content_hash(text)
        meta["scraped_at"] = now_iso
        meta["source_url"] = entry.get("source_url") or meta.get("page_url", "")
        meta["page_url"] = meta.get("page_url") or meta.get("source_url", "")
        meta["api_endpoint"] = meta.get("api_endpoint") or meta.get("endpoint") or "api"
        meta["raw_api_endpoint"] = meta["api_endpoint"]
        meta["source_asset_id"] = entry.get("asset_id")
        meta["record_index"] = idx

        if doc_type == "faculty":
            dept_id = str(
                rec.get("DepartmentId")
                or meta.get("department_id")
                or meta.get("DepartmentId")
                or ""
            )
            page_dept_id = str(meta.get("department_master_id") or meta.get("department_id") or "")
            meta["faculty_dept_mismatch"] = (
                False
                if dept_id == page_dept_id
                else bool(dept_id and page_dept_id and dept_id != page_dept_id)
            )
            meta["department_id_matches_page"] = (
                (dept_id == page_dept_id) if (dept_id and page_dept_id) else True
            )
            meta["record_id"] = str(rec.get("FacultyId") or rec.get("Id") or idx)

        rec_title = (
            rec.get("Title")
            or rec.get("NoticeTitle")
            or rec.get("TenderTitle")
            or rec.get("FirstName")
            or meta.get("title")
            or f"{doc_type}_{idx}"
        )
        if rec.get("LastName") or rec.get("LasttName"):
            rec_title = (
                f"{rec.get('FirstName', '')} {rec.get('LastName') or rec.get('LasttName')}"
            ).strip()
        meta["title"] = rec_title

        doc_id = hashlib.sha256(
            f"{entry.get('asset_id')}::{idx}::{text[:100]}".encode()
        ).hexdigest()[:24]
        meta["doc_id"] = doc_id
        meta["page_number"] = None
        meta["chunk_index"] = 0

        doc = Document(text=text, metadata=meta)
        results.append(doc.model_dump())

    return results


def _parse_grouped_pdf(
    key: str,
    items: list[dict[str, Any]],
    pdf_parser: OfflinePdfParser,
) -> dict[str, Any] | None:
    base_item = items[0]
    local_path = base_item["local_path"]

    # Multi-route reference aggregation
    merged_meta = aggregate_asset_references([i["entry"] for i in items])

    if merged_meta.get("is_sensitive"):
        text = "[REDACTED — sensitive document]"
        page_count = merged_meta.get("pdf_pages") or 1
    else:
        parsed_pdf = pdf_parser.parse_file(local_path, fallback_title=merged_meta.get("title", key))
        text = scrub_pii(parsed_pdf.text)
        page_count = parsed_pdf.page_count
        merged_meta["pdf_pages"] = parsed_pdf.page_count
        merged_meta["pdf_text_pages"] = parsed_pdf.text_pages
        merged_meta["pdf_scanned_pages"] = parsed_pdf.scanned_pages
        merged_meta["pdf_table_count"] = parsed_pdf.table_count
        merged_meta["pdf_embedded_date"] = parsed_pdf.embedded_date
        merged_meta["needs_ocr"] = parsed_pdf.needs_ocr

    canonical_doc_id = hashlib.sha256(f"pdf::{key}".encode()).hexdigest()[:24]
    merged_meta["doc_id"] = canonical_doc_id
    merged_meta["content_hash"] = _content_hash(text)
    merged_meta["page_count"] = page_count
    merged_meta["page_number"] = None
    merged_meta["chunk_index"] = 0
    now_iso = datetime.now(tz=UTC).isoformat()
    merged_meta["scraped_at"] = now_iso
    merged_meta["source_url"] = merged_meta.get("file_url") or merged_meta.get("source_url") or key
    merged_meta["page_url"] = (
        merged_meta.get("found_on") or merged_meta.get("page_url") or merged_meta["source_url"]
    )
    merged_meta["found_on_page"] = merged_meta["page_url"]
    merged_meta["api_endpoint"] = merged_meta.get("api_endpoint") or "pdf"
    merged_meta["raw_api_endpoint"] = merged_meta["api_endpoint"]

    doc = Document(text=text, metadata=merged_meta)
    return doc.model_dump()


def parse_manifest(
    manifest_path: Path,
    output_path: Path,
    project_root: Path | None = None,
    max_workers: int | None = None,
) -> ParseStats:
    """Parse all assets listed in manifest.jsonl and write documents.jsonl."""
    if project_root is None:
        project_root = Path.cwd()

    if max_workers is None:
        max_workers = min(32, (os.cpu_count() or 1) + 4)

    pdf_groups: dict[str, list[dict]] = {}
    documents: list[dict] = []

    total_assets = 0
    pdf_count = 0
    html_count = 0
    api_count = 0
    errors = 0

    if not manifest_path.exists():
        logger.error("Manifest not found: %s", manifest_path)
        return ParseStats(0, 0, 0, 0, 0, 1)

    html_items: list[tuple[dict, Path]] = []
    api_items: list[tuple[dict, Path]] = []
    seen_assets: set[str] = set()

    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            total_assets += 1
            try:
                entry = json.loads(line_str)
            except Exception as exc:
                logger.warning("Failed to parse manifest line: %s", exc)
                errors += 1
                continue

            asset_id = entry.get("asset_id") or ""
            local_rel = entry.get("local_path", "")
            asset_key = f"{asset_id}::{local_rel}"
            if asset_key in seen_assets:
                continue
            seen_assets.add(asset_key)

            asset_type = entry.get("asset_type")
            local_path = _resolve_asset_path(local_rel, project_root)

            if asset_type == "pdf":
                pdf_count += 1
                raw_meta = dict(entry.get("raw_meta", {}))
                file_name = raw_meta.get("file_name") or Path(local_rel).name
                key = file_name.split("?")[0]
                if key not in pdf_groups:
                    pdf_groups[key] = []
                pdf_groups[key].append({"entry": entry, "local_path": local_path, "meta": raw_meta})
            elif asset_type == "html":
                html_count += 1
                html_items.append((entry, local_path))
            elif asset_type == "api_json":
                api_count += 1
                api_items.append((entry, local_path))
            else:
                html_count += 1
                html_items.append((entry, local_path))

    # Concurrently parse HTML and API assets
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        html_futures = [
            executor.submit(_parse_single_html, entry, path) for entry, path in html_items
        ]
        api_futures = [executor.submit(_parse_single_api, entry, path) for entry, path in api_items]

        for fut in concurrent.futures.as_completed(html_futures):
            try:
                doc = fut.result()
                if doc:
                    documents.append(doc)
            except Exception as exc:
                logger.warning("HTML parse error: %s", exc)
                errors += 1

        for fut in concurrent.futures.as_completed(api_futures):
            try:
                res = fut.result()
                if isinstance(res, list):
                    documents.extend(res)
                elif res:
                    documents.append(res)
            except Exception as exc:
                logger.warning("API parse error: %s", exc)
                errors += 1

    # Concurrently parse grouped PDFs
    pdf_parser = OfflinePdfParser()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        pdf_futures = {
            executor.submit(_parse_grouped_pdf, key, items, pdf_parser): key
            for key, items in pdf_groups.items()
        }
        for fut in concurrent.futures.as_completed(pdf_futures):
            try:
                doc = fut.result()
                if doc:
                    documents.append(doc)
            except Exception as exc:
                logger.warning("PDF parse error for %s: %s", pdf_futures[fut], exc)
                errors += 1

    # Deduplicate documents by doc_id
    seen_doc_ids: set[str] = set()
    deduped_docs: list[dict] = []
    for doc in documents:
        did = doc.get("metadata", {}).get("doc_id")
        if did and did in seen_doc_ids:
            continue
        if did:
            seen_doc_ids.add(did)
        deduped_docs.append(doc)
    documents = deduped_docs

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for doc in documents:
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return ParseStats(
        total_assets=total_assets,
        pdf_count=len(pdf_groups),
        html_count=html_count,
        api_count=api_count,
        output_count=len(documents),
        errors=errors,
    )


__all__ = [
    "ParseStats",
    "parse_manifest",
]
