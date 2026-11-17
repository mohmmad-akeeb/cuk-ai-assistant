"""Orchestrator for the full CUK site scrape.

Pipeline
--------
1.  Node table: walk school tree + nav tree; write data/processed/nodes.jsonl.
2.  Fetch department pages (departmentList route): HTML → Markdown, links_out,
    queue PDFs found in HTML.
3.  Faculty pages: per-department, flag DepartmentId mismatches, drop PII fields.
4.  Global list endpoints (noticeboard, employment, admission, tender, etc.):
    fetch once with seen/next paging, dedupe by row Id.
5.  Homepage widgets (additionalcard, whatnew, implink, etc.): same as before
    but with improved HTML handling.
6.  PDF extraction: all queued PDFs (from file_url AND from HTML links).
7.  Write data/processed/documents.jsonl + coverage report.

Output schema per JSONL line
-----------------------------
See metadata_builder.py for the full field list.
All existing field names and semantics are preserved.
New fields (B7): school_master_id, school_name, department_master_id,
  department_id, menu_id, route_name, node_path, parent_node_id,
  api_endpoint, request_payload, found_on_page, links_out,
  content_hash, text_format.
doc_id for PDF page-chunks now includes page number.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from cuk_assistant.core.config import Settings
from cuk_assistant.core.http_cache import CachedClient
from cuk_assistant.ingestion.crawl.direct_client import DirectApiClient
from cuk_assistant.ingestion.crawl.html_parser import LinkOut, parse_html
from cuk_assistant.ingestion.crawl.metadata_builder import (
    _content_hash,
    build_metadata,
)
from cuk_assistant.ingestion.crawl.node_crawler import (
    SiteNode,
    build_node_table,
    fetch_all_nodes,
    nodes_to_jsonl,
)
from cuk_assistant.ingestion.crawl.pdf_extractor import extract_pdf

logger = logging.getLogger(__name__)
console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Endpoints to skip entirely (noise / binary)
# ---------------------------------------------------------------------------
_SKIP_ENDPOINTS: set[str] = {
    "banner/getallbannersforwebsite",
    "auditlog/selectlastupdated",
    "languagesetting/languagesettingList",
    "mediagallery/getmediagalleryforwebsite2",
    "headercategory/headercategoryList",  # nav tree only
    "studentzone/getbreadcum",
    "administrative/getbreadcum",
    "headercategory/headercategoryListById",
    "administrative/spdepartlist",  # returns empty for all tested IDs
}

# ---------------------------------------------------------------------------
# Global list endpoints: fetched ONCE, paginated
# ---------------------------------------------------------------------------
_GLOBAL_LIST_ENDPOINTS: list[tuple[str, dict]] = [
    ("noticeboard/all", {"seen": 0, "next": 0}),
    ("admission/all", {"seen": 0, "next": 0}),
    ("employments/all", {"seen": 0, "next": 0}),
    ("tender/getalltender", {"langType": 1}),
    ("pressrelease/getAllPressReleasesForWebSite", {"seen": 0, "next": 0}),
    ("moe/getAllPressReleasesForWebSite", {"seen": 0, "next": 0}),
    ("examinationresult/ExaminationResultListForWebSite", {"seen": 0, "next": 0}),
    ("scholarresults/ScholarExaminationResultListForWebSite", {"seen": 0, "next": 0}),
    ("examdatesheet/ExamDateSheetList", {"seen": 0, "next": 0}),
    ("examnotification/getAllNotificationForWebSite", {"seen": 0, "next": 0}),
    ("itandservices/ItAndServicesNotificationListForWebSite", {"seen": 0, "next": 0}),
    ("whatnew/getAllWhatNewForWebSite", {"seen": 0, "next": 0}),
    ("event/getallupcomingeventsforwebsite", {"seen": 0, "next": 0}),
    ("eventgallerymanage/getallForWebSiteList", {"seen": 0, "next": 0}),
]

# ---------------------------------------------------------------------------
# Homepage / singleton widget endpoints: fetched ONCE, no paging
# ---------------------------------------------------------------------------
_SINGLETON_ENDPOINTS: list[str] = [
    "additionalcard/getallcards",
    "publichomequicklinks/getquicklinksForWebSite",
    "publichomequicklinks/getquicklinksForwebSite",  # case variant
    "universitydoc/selectforwebsite",
    "universityinitiatives/selectinitforwebsite",
    "implink/selectimplinksforwebsite",
    "policy/selectpolicyforwebsite",
    "promotions/getPromotionsForPublic",
    "messages/allmessagesforwebsite",
    "howtoreachcuk/gethowtoreachcuk",
    "videogallery/getvideosforwebsite",
    "studentzone/studentzoneListById",
]

# ---------------------------------------------------------------------------
# Fields to strip from faculty records (PII)
# ---------------------------------------------------------------------------
_FACULTY_PII_FIELDS: set[str] = {"DOB", "MobileNo", "PM_Address1", "Gender"}

# Regex to strip phone numbers from free-text Details field
_PHONE_RE = re.compile(
    r"\b(?:\+?91[\s\-]?)?[6-9]\d{9}\b"  # Indian mobile
    r"|\b0\d{2,4}[\s\-]\d{6,8}\b"  # STD landline
    r"|\b\(\d{2,5}\)\s*\d{4,8}\b",  # (area) number
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_phone_numbers(text: str) -> str:
    return _PHONE_RE.sub("[PHONE REDACTED]", text)


def _links_out_as_dicts(links: list[LinkOut]) -> list[dict]:
    return [{"text": lo.text, "href": lo.href, "type": lo.type} for lo in links]


def _write_jsonl(path: Path, documents: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for doc in documents:
            fh.write(json.dumps(doc, ensure_ascii=False, default=str) + "\n")


def _write_summary(path: Path, documents: list[dict]) -> None:
    from collections import Counter

    path.parent.mkdir(parents=True, exist_ok=True)

    ct_counts: Counter = Counter(d["metadata"].get("content_type", "unknown") for d in documents)
    section_counts: Counter = Counter(
        d["metadata"].get("section", "unknown") or "(root)" for d in documents
    )
    school_counts: Counter = Counter(
        d["metadata"].get("school_name", "") or "(none)" for d in documents
    )
    pdf_count = sum(1 for d in documents if d["metadata"].get("is_pdf"))
    sensitive_count = sum(1 for d in documents if d["metadata"].get("is_sensitive"))
    ocr_count = sum(1 for d in documents if d["metadata"].get("needs_ocr"))
    mismatch_count = sum(1 for d in documents if d["metadata"].get("faculty_dept_mismatch"))

    lines = [
        "# CUK Scrape Summary\n",
        f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}\n",
        f"Total documents: **{len(documents)}**\n",
        f"PDFs extracted: **{pdf_count}** | Sensitive: **{sensitive_count}** | Needs OCR: **{ocr_count}**\n",
        f"Faculty dept mismatches: **{mismatch_count}**\n",
        "",
        "## By Content Type\n",
        "| Content Type | Count |",
        "|---|---|",
    ]
    for ct, cnt in sorted(ct_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {ct} | {cnt} |")

    lines += ["", "## By Section\n", "| Section | Count |", "|---|---|"]
    for sec, cnt in sorted(section_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {sec} | {cnt} |")

    lines += ["", "## By School\n", "| School | Count |", "|---|---|"]
    for sch, cnt in sorted(school_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {sch} | {cnt} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Faculty document builder
# ---------------------------------------------------------------------------


def _build_faculty_doc(
    record: dict,
    *,
    node: SiteNode,
    dept_id_sent: str,
    index: int,
) -> dict | None:
    """Build one faculty document, flagging mismatches and stripping PII."""
    # Strip PII fields
    clean = {k: v for k, v in record.items() if k not in _FACULTY_PII_FIELDS}

    # Strip phone numbers from Details
    details = clean.get("Details", "") or ""
    if details:
        clean["Details"] = _strip_phone_numbers(details)

    name = " ".join(
        filter(
            None,
            [
                clean.get("FirstName", ""),
                clean.get("LasttName", ""),
            ],
        )
    ).strip()

    # Build text
    parts: list[str] = []
    if node.school_name:
        parts.append(f"School: {node.school_name}")
    parts.append(f"Department: {node.department_name}")
    if name:
        parts.append(f"Name: {name}")
    if clean.get("Designation"):
        parts.append(f"Designation: {clean['Designation']}")
    if clean.get("Education"):
        parts.append(f"Education: {clean['Education']}")
    if clean.get("Email"):
        parts.append(f"Email: {clean['Email']}")
    if clean.get("OfficeAddress"):
        parts.append(f"Office: {clean['OfficeAddress']}")
    if clean.get("Details"):
        # Parse HTML from Details if present
        raw = clean["Details"]
        if "<" in raw:
            parsed = parse_html(raw)
            parts.append(parsed.text)
        else:
            parts.append(raw)

    text = "\n".join(parts).strip()
    if not text:
        return None

    meta = build_metadata(
        "faculty/getallforwebsite",
        clean,
        section=node.school_name,
        subsection=node.department_name,
        page_url=node.angular_url,
        department_name=node.department_name,
        index=index,
        school_master_id=node.school_master_id,
        school_name=node.school_name,
        department_master_id=node.department_master_id,
        menu_id=node.menu_id,
        route_name=node.route_name,
        node_path=node.breadcrumb,
        parent_node_id=node.parent_node_id,
        request_payload=json.dumps({"langType": 1, "DepartmentId": dept_id_sent}),
        faculty_dept_id_sent=dept_id_sent,
    )
    meta["content_hash"] = _content_hash(text)
    return {"text": text, "metadata": meta}


# ---------------------------------------------------------------------------
# Department page document builder
# ---------------------------------------------------------------------------


def _build_dept_page_doc(
    record: dict,
    *,
    node: SiteNode,
) -> tuple[dict | None, list[tuple[str, str]]]:
    """Build a department page doc from DepartmentDescription HTML.

    Returns (doc_dict_or_None, pdf_links_to_queue).
    pdf_links_to_queue = list of (pdf_url, found_on_page_url).
    """
    html = (
        record.get("DepartmentDescription", "")
        or record.get("AdministrativeDescription", "")
        or record.get("Details", "")
        or record.get("Content", "")
        or record.get("LongDescription", "")
        or record.get("Description", "")
    )
    if not html or not html.strip():
        return None, []

    parsed = parse_html(html)
    if not parsed.text.strip():
        return None, []

    # Collect PDFs found in links_out
    pdf_links: list[tuple[str, str]] = []
    for link in parsed.links_out:
        if link.type == "pdf" and link.href.startswith("http"):
            pdf_links.append((link.href, node.angular_url))

    meta = build_metadata(
        "department/departmentListById",
        record,
        section=node.school_name,
        subsection=node.department_name,
        page_url=node.angular_url,
        department_name=node.department_name,
        school_master_id=node.school_master_id,
        school_name=node.school_name,
        department_master_id=node.department_master_id,
        menu_id=node.menu_id,
        route_name=node.route_name,
        node_path=node.breadcrumb,
        parent_node_id=node.parent_node_id,
        request_payload=node.request_payload,
        links_out=_links_out_as_dicts(parsed.links_out),
    )
    meta["content_hash"] = _content_hash(parsed.text)
    meta["text_format"] = "markdown"

    return {"text": parsed.text, "metadata": meta}, pdf_links


# ---------------------------------------------------------------------------
# Global list document builder
# ---------------------------------------------------------------------------


def _synthesise_text(record: dict, metadata: dict) -> str:
    """Build embedding text from a JSON-only record."""
    parts: list[str] = []

    if metadata.get("school_name"):
        parts.append(f"School: {metadata['school_name']}")
    if metadata.get("section"):
        parts.append(f"Section: {metadata['section']}")
    if metadata.get("subsection"):
        parts.append(f"Subsection: {metadata['subsection']}")
    if metadata.get("department_name"):
        parts.append(f"Department: {metadata['department_name']}")
    if metadata["title"]:
        parts.append(f"Title: {metadata['title']}")
    if metadata["description"]:
        desc_raw = metadata["description"]
        if "<" in desc_raw:
            parsed = parse_html(desc_raw)
            if parsed.text.strip():
                parts.append(parsed.text.strip())
        else:
            desc = re.sub(r"\s+", " ", desc_raw).strip()
            if desc:
                parts.append(desc)

    # Pull long HTML/text fields
    for key in (
        "LongDescription",
        "Content",
        "Body",
        "Text",
        "Details",
        "DepartmentDescription",
        "AdministrativeDescription",
    ):
        val = record.get(key, "")
        if val and len(str(val)) > 20:
            raw = str(val)
            if "<" in raw:
                parsed = parse_html(raw)
                if parsed.text.strip():
                    parts.append(parsed.text)
            else:
                clean = re.sub(r"\s+", " ", raw).strip()
                if clean:
                    parts.append(clean)

    if metadata["published_on"]:
        parts.append(f"Published: {metadata['published_on'][:10]}")
    if metadata["visible_from"] and metadata["visible_to"]:
        parts.append(f"Valid: {metadata['visible_from'][:10]} to {metadata['visible_to'][:10]}")
    if metadata["file_url"] and not metadata["is_pdf"]:
        parts.append(f"Attachment: {metadata['file_url']}")
    if metadata["external_url"]:
        parts.append(f"Link: {metadata['external_url']}")

    return "\n".join(parts).strip()


async def _fetch_content_detail_fallback(
    api: DirectApiClient, row: dict, endpoint: str
) -> dict | None:
    """Fetch single-record detail fallback if content is hosted under /content?type=...&id=... or if row points to it."""
    from urllib.parse import parse_qs

    # 1. Check if any URL field in row references /content
    content_url = ""
    for k in ("Url", "HttpPath", "ExternalUrl", "ExternalLinkUrl", "Link", "FilePath"):
        val = str(row.get(k) or "").strip()
        if "content?" in val or "content;" in val or "/content" in val:
            content_url = val
            break

    type_val = ""
    id_val = ""

    if content_url:
        frag = content_url.split("#/", 1)[1] if "#/" in content_url else content_url
        if "?" in frag:
            qs = parse_qs(frag.split("?", 1)[1])
            if "type" in qs and qs["type"]:
                type_val = qs["type"][0].lower()
            if "id" in qs and qs["id"]:
                id_val = qs["id"][0]
        if ";" in frag:
            for part in frag.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k.strip().lower() == "type":
                        type_val = v.strip().lower()
                    elif k.strip().lower() == "id" and not id_val:
                        id_val = v.strip()

    # If no URL reference, but row has an ID and lacks text/attachment, attempt fallback
    if not id_val:
        rec_id = str(row.get("RecordId") or row.get("Id") or row.get("RowId") or "").strip()
        has_content = bool(
            row.get("Description")
            or row.get("Content")
            or row.get("Details")
            or row.get("LongDescription")
            or row.get("FileUrl")
        )
        if rec_id and not has_content:
            id_val = rec_id
            type_val = endpoint.split("/")[0].lower()

    if not id_val:
        return None

    from cuk_assistant.ingestion.crawl.node_crawler import _resolve_content_endpoint_and_payload

    detail_ep, payload = _resolve_content_endpoint_and_payload(type_val, id_val)
    if not detail_ep:
        return None

    try:
        resp = await api._post(detail_ep, payload)
        if isinstance(resp, list) and resp and isinstance(resp[0], dict):
            return resp[0]
        elif isinstance(resp, dict):
            return resp
    except Exception as exc:
        logger.debug("Detail fallback fetch failed for %s (%s): %s", detail_ep, payload, exc)
    return None


# ---------------------------------------------------------------------------
# Main run()
# ---------------------------------------------------------------------------


async def run(settings: Settings, *, force: bool = False) -> None:  # noqa: C901 — complex but linear
    out_path = settings.processed_dir / "documents.jsonl"
    nodes_path = settings.processed_dir / "nodes.jsonl"
    summary_path = settings.reports_dir / "scrape_summary.md"
    coverage_path = settings.reports_dir / "coverage.md"

    if out_path.exists() and not force:
        console.print(
            f"[green]scrape: output already exists at {out_path}. Pass --force to re-run.[/green]"
        )
        return

    all_documents: list[dict] = []
    pdf_queue: list[tuple[str, dict]] = []  # (url, base_metadata)
    seen_doc_ids: set[str] = set()
    queued_pdf_urls: set[str] = set()

    def _add_doc(doc: dict) -> None:
        did = doc["metadata"]["doc_id"]
        # For PDF page chunks, the doc_id already includes page, so it's unique.
        # But check to be safe.
        if did in seen_doc_ids:
            return
        seen_doc_ids.add(did)
        all_documents.append(doc)

    def _queue_pdf(url: str, base_meta: dict) -> None:
        clean_url = url.strip()
        if not clean_url or clean_url in queued_pdf_urls:
            return
        queued_pdf_urls.add(clean_url)
        pdf_queue.append((clean_url, base_meta))

    # ── Phase 1: Build node table ─────────────────────────────────────────
    console.print("\n[bold]Phase 1:[/bold] Building node table …")
    async with CachedClient.from_settings(settings) as client:
        nodes = await build_node_table(settings, client)
        await fetch_all_nodes(nodes, client, settings)
    nodes_to_jsonl(nodes, nodes_path)
    console.print(f"  Nodes: {len(nodes)} total")

    # Build lookup structures from nodes
    school_lookup: dict[str, str] = {}  # school_master_id → school_name
    dept_name_lookup: dict[str, str] = {}  # department_master_id → department_name
    dept_id_lookup: dict[str, str] = {}  # department_id (DepartmentId) → department_name
    # Also record dept_id per dept_master_id from the department records
    dept_to_school: dict[
        str, tuple[str, str]
    ] = {}  # dept_master_id → (school_master_id, school_name)
    dept_id_to_master: dict[str, str] = {}  # DepartmentId → DepartmentMasterId

    for node in nodes:
        if node.school_master_id:
            school_lookup[node.school_master_id] = node.school_name
        if node.department_master_id and node.department_name:
            dept_name_lookup[node.department_master_id] = node.department_name
            dept_to_school[node.department_master_id] = (node.school_master_id, node.school_name)

    # ── Phase 2: Department page content ──────────────────────────────────
    console.print("\n[bold]Phase 2:[/bold] Building department page documents …")
    dept_nodes = [
        n
        for n in nodes
        if n.route_name in ("departmentList", "departlist")
        and n.status in ("fetched", "empty")
        and n.content_records
    ]
    console.print(f"  Department nodes with content: {len(dept_nodes)}")

    for node in dept_nodes:
        for record in node.content_records:
            doc, pdf_links = _build_dept_page_doc(record, node=node)
            if doc:
                _add_doc(doc)
            for pdf_url, found_on in pdf_links:
                # Build a minimal base_meta for the PDF
                pdf_meta = build_metadata(
                    "department/departmentListById",
                    record,
                    section=node.school_name,
                    subsection=node.department_name,
                    page_url=node.angular_url,
                    department_name=node.department_name,
                    school_master_id=node.school_master_id,
                    school_name=node.school_name,
                    department_master_id=node.department_master_id,
                    menu_id=node.menu_id,
                    route_name=node.route_name,
                    node_path=node.breadcrumb,
                    parent_node_id=node.parent_node_id,
                    request_payload=node.request_payload,
                    found_on_page=found_on,
                )
                # Override file_url with the discovered pdf_url
                import urllib.parse as _up

                p = _up.urlparse(pdf_url)
                pdf_meta["file_url"] = pdf_url
                pdf_meta["file_name"] = p.path.split("/")[-1]
                pdf_meta["is_pdf"] = True
                pdf_meta["source_url"] = pdf_url
                _queue_pdf(pdf_url, pdf_meta)

        # Also queue any PDFs stored on node.pdf_links during node discovery
        for pdf_item in getattr(node, "pdf_links", []):
            pdf_url = pdf_item.get("url") if isinstance(pdf_item, dict) else str(pdf_item)
            if not pdf_url or pdf_url in queued_pdf_urls:
                continue
            first_rec = node.content_records[0] if node.content_records else {}
            pdf_meta = build_metadata(
                node.api_endpoint or "department/departmentListById",
                first_rec,
                section=node.school_name,
                subsection=node.department_name,
                page_url=node.angular_url,
                department_name=node.department_name,
                school_master_id=node.school_master_id,
                school_name=node.school_name,
                department_master_id=node.department_master_id,
                menu_id=node.menu_id,
                route_name=node.route_name,
                node_path=node.breadcrumb,
                parent_node_id=node.parent_node_id,
                request_payload=node.request_payload,
                found_on_page=pdf_item.get("found_on", node.angular_url)
                if isinstance(pdf_item, dict)
                else node.angular_url,
            )
            import urllib.parse as _up

            p = _up.urlparse(pdf_url)
            pdf_meta["file_url"] = pdf_url
            pdf_meta["file_name"] = p.path.split("/")[-1]
            pdf_meta["is_pdf"] = True
            pdf_meta["source_url"] = pdf_url
            _queue_pdf(pdf_url, pdf_meta)

    # Queue PDFs from any external nodes that directly link to PDF files
    for node in nodes:
        if node.route_name not in ("departmentList", "departlist") and getattr(
            node, "pdf_links", None
        ):
            for pdf_item in node.pdf_links:
                pdf_url = pdf_item.get("url") if isinstance(pdf_item, dict) else str(pdf_item)
                if not pdf_url or pdf_url in queued_pdf_urls:
                    continue
                pdf_meta = build_metadata(
                    "external",
                    {},
                    section=node.school_name,
                    subsection=node.department_name,
                    page_url=node.angular_url,
                    department_name=node.department_name,
                    school_master_id=node.school_master_id,
                    school_name=node.school_name,
                    department_master_id=node.department_master_id,
                    menu_id=node.menu_id,
                    route_name=node.route_name,
                    node_path=node.breadcrumb,
                    parent_node_id=node.parent_node_id,
                    request_payload=node.request_payload,
                    found_on_page=node.angular_url,
                )
                import urllib.parse as _up

                p = _up.urlparse(pdf_url)
                pdf_meta["file_url"] = pdf_url
                pdf_meta["file_name"] = p.path.split("/")[-1]
                pdf_meta["is_pdf"] = True
                pdf_meta["source_url"] = pdf_url
                _queue_pdf(pdf_url, pdf_meta)

    # ── Phase 3: Faculty ─────────────────────────────────────────────────
    console.print("\n[bold]Phase 3:[/bold] Fetching faculty …")
    # Build set of unique (dept_master_id, dept_id) pairs from school-tree dept nodes
    fetched_faculty: set[str] = set()
    faculty_docs_count = 0

    async with CachedClient.from_settings(settings) as client:
        api = DirectApiClient(client)

        # Get DepartmentId (not DepartmentMasterId) for each dept in school tree
        # We need this to call faculty/getallforwebsite correctly.
        # Fetch each dept's menu to get the DepartmentId from first row.
        for node in nodes:
            if node.route_name not in ("departmentList",) or not node.department_master_id:
                continue
            if node.menu_id:  # skip sub-pages, only dept roots
                continue
            if node.department_master_id in fetched_faculty:
                continue
            fetched_faculty.add(node.department_master_id)

            # Get DepartmentId from the dept menu (first item = dept root)
            menu = await api.department_menu(node.department_master_id)
            dept_id_val = ""
            for item in menu:
                if item.get("ParentDepartmentMasterId") is None:
                    dept_id_val = item.get("DepartmentId", "")
                    break

            if not dept_id_val:
                continue

            # Store mapping for later use
            dept_id_lookup[dept_id_val] = node.department_name
            dept_id_to_master[dept_id_val] = node.department_master_id

            faculty_records = await api.faculty(dept_id_val)
            for i, rec in enumerate(faculty_records):
                doc = _build_faculty_doc(
                    rec,
                    node=node,
                    dept_id_sent=dept_id_val,
                    index=i,
                )
                if doc:
                    _add_doc(doc)
                    faculty_docs_count += 1

    console.print(f"  Faculty docs: {faculty_docs_count}")

    # ── Phase 4: Global list endpoints ───────────────────────────────────
    console.print("\n[bold]Phase 4:[/bold] Fetching global list endpoints …")
    async with CachedClient.from_settings(settings) as client:
        api = DirectApiClient(client)

        for endpoint, _params in _GLOBAL_LIST_ENDPOINTS:
            if endpoint == "tender/getalltender":
                rows = await api.all_tenders()
            else:
                rows = await api.fetch_all_paged(endpoint, page_size=200)
            ep_docs = 0
            for idx, row in enumerate(rows):
                # Single-item detail fallback for items hosted under /content?type=...&id=...
                detail = await _fetch_content_detail_fallback(api, row, endpoint)
                if detail:
                    for k, v in detail.items():
                        if v and (
                            not row.get(k)
                            or k
                            in (
                                "Content",
                                "Details",
                                "LongDescription",
                                "AdministrativeDescription",
                                "Description",
                            )
                        ):
                            row[k] = v
                # Determine department from row's DepartmentId
                row_dept_id = str(row.get("DepartmentId", "") or "")
                row_dept_name = str(row.get("DepartmentName", "") or "")
                if not row_dept_name and row_dept_id:
                    row_dept_name = dept_id_lookup.get(row_dept_id, "")
                row_dept_master_id = dept_id_to_master.get(row_dept_id, "")
                row_school_id, row_school_name = dept_to_school.get(row_dept_master_id, ("", ""))

                meta = build_metadata(
                    endpoint,
                    row,
                    section=_endpoint_section(endpoint),
                    page_url=settings.base_url,
                    department_name=row_dept_name,
                    school_master_id=row_school_id,
                    school_name=row_school_name,
                    department_master_id=row_dept_master_id,
                    route_name="listing",
                    node_path=[_endpoint_section(endpoint)],
                    request_payload=json.dumps(
                        {"langType": 1, "DepartmentId": "", "seen": 0, "next": 200}
                    ),
                    index=idx,
                )

                if meta["is_pdf"] and meta["file_url"]:
                    _queue_pdf(meta["file_url"], meta)
                else:
                    text = _synthesise_text(row, meta)
                    if text.strip():
                        meta["content_hash"] = _content_hash(text)
                        _add_doc({"text": text, "metadata": meta})
                        ep_docs += 1

                # Also extract any embedded PDF links in HTML fields (e.g. additionalcard downloads)
                desc_html = str(
                    row.get("Description")
                    or row.get("HeaderCategoryDescription")
                    or row.get("Content")
                    or row.get("AdministrativeDescription")
                    or ""
                )
                if desc_html and "<" in desc_html:
                    parsed_desc = parse_html(desc_html)
                    for lo in parsed_desc.links_out:
                        if lo.type == "pdf" and lo.href.startswith("http"):
                            child_pdf_meta = dict(meta)
                            child_pdf_meta["file_url"] = lo.href
                            child_pdf_meta["file_name"] = lo.href.split("/")[-1].split("?")[0]
                            child_pdf_meta["title"] = lo.text or meta.get("title", "")
                            child_pdf_meta["is_pdf"] = True
                            child_pdf_meta["source_url"] = lo.href
                            child_pdf_meta["found_on_page"] = meta.get(
                                "page_url", settings.base_url
                            )
                            _queue_pdf(lo.href, child_pdf_meta)

            console.print(f"  {endpoint}: {len(rows)} rows → {ep_docs} docs")

    # ── Phase 5: Singleton / homepage widgets ─────────────────────────────
    console.print("\n[bold]Phase 5:[/bold] Fetching homepage widgets …")
    async with CachedClient.from_settings(settings) as client:
        api = DirectApiClient(client)
        seen_singleton_eps: set[str] = set()

        for endpoint in _SINGLETON_ENDPOINTS:
            ep_norm = endpoint.lower()
            if ep_norm in seen_singleton_eps:
                continue
            seen_singleton_eps.add(ep_norm)

            # Try POST with standard payload
            try:
                rows = await api._post(endpoint, {"langType": 1})
            except Exception:
                rows = []

            if not isinstance(rows, list):
                rows = [rows] if rows else []

            ep_docs = 0
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue

                meta = build_metadata(
                    endpoint,
                    row,
                    section=_endpoint_section(endpoint),
                    page_url=settings.base_url,
                    route_name="home",
                    node_path=[_endpoint_section(endpoint)],
                    request_payload=json.dumps({"langType": 1}),
                    index=idx,
                )

                if meta["is_pdf"] and meta["file_url"]:
                    _queue_pdf(meta["file_url"], meta)
                else:
                    text = _synthesise_text(row, meta)
                    if text.strip():
                        meta["content_hash"] = _content_hash(text)
                        _add_doc({"text": text, "metadata": meta})
                        ep_docs += 1

                # Also extract any embedded PDF links in HTML fields (e.g. additionalcard downloads)
                desc_html = str(
                    row.get("Description")
                    or row.get("HeaderCategoryDescription")
                    or row.get("Content")
                    or row.get("AdministrativeDescription")
                    or ""
                )
                if desc_html and "<" in desc_html:
                    parsed_desc = parse_html(desc_html)
                    for lo in parsed_desc.links_out:
                        if lo.type == "pdf" and lo.href.startswith("http"):
                            child_pdf_meta = dict(meta)
                            child_pdf_meta["file_url"] = lo.href
                            child_pdf_meta["file_name"] = lo.href.split("/")[-1].split("?")[0]
                            child_pdf_meta["title"] = lo.text or meta.get("title", "")
                            child_pdf_meta["is_pdf"] = True
                            child_pdf_meta["source_url"] = lo.href
                            child_pdf_meta["found_on_page"] = meta.get(
                                "page_url", settings.base_url
                            )
                            _queue_pdf(lo.href, child_pdf_meta)

            if rows:
                console.print(f"  {endpoint}: {len(rows)} rows → {ep_docs} docs")

    console.print(f"\n  JSON/text documents: {len(all_documents)}")
    console.print(f"  PDFs queued: {len(pdf_queue)}")

    # ── Phase 6: PDF extraction ──────────────────────────────────────────
    if pdf_queue:
        console.print(f"\n[bold]Phase 6:[/bold] Extracting {len(pdf_queue)} PDFs …")
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Extracting PDFs …", total=len(pdf_queue))

            async with CachedClient.from_settings(settings) as client:
                for pdf_url, base_meta in pdf_queue:
                    fname = pdf_url.split("/")[-1][:40]
                    progress.update(task_id, description=f"PDF: {fname} …")
                    try:
                        docs = await extract_pdf(pdf_url, base_meta, client, settings)
                        for doc in docs:
                            _add_doc(doc)
                    except Exception as exc:
                        logger.warning("PDF extraction failed: %s — %s", pdf_url, exc)
                    progress.advance(task_id)

    # ── Phase 7: Write output ────────────────────────────────────────────
    console.print(f"\n[bold]Phase 7:[/bold] Writing {len(all_documents)} documents …")
    _write_jsonl(out_path, all_documents)
    _write_summary(summary_path, all_documents)
    _write_coverage(coverage_path, nodes, all_documents)

    pdf_docs = sum(1 for d in all_documents if d["metadata"].get("is_pdf"))
    sensitive = sum(1 for d in all_documents if d["metadata"].get("is_sensitive"))
    ocr_docs = sum(1 for d in all_documents if d["metadata"].get("needs_ocr"))
    mismatch = sum(1 for d in all_documents if d["metadata"].get("faculty_dept_mismatch"))
    schools_covered = len(
        {
            d["metadata"].get("school_name", "")
            for d in all_documents
            if d["metadata"].get("school_name")
        }
    )

    console.print("\n[green]✓ Scrape complete[/green]")
    console.print(f"  Total documents   : {len(all_documents)}")
    console.print(f"  PDF documents     : {pdf_docs}")
    console.print(f"  Sensitive         : {sensitive}")
    console.print(f"  Needs OCR         : {ocr_docs}")
    console.print(f"  Faculty mismatches: {mismatch}")
    console.print(f"  Schools covered   : {schools_covered}")
    console.print(f"  Output            : {out_path}")
    console.print(f"  Coverage          : {coverage_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENDPOINT_SECTION_MAP: dict[str, str] = {
    "noticeboard": "Notices",
    "employments": "Employment",
    "admission": "Admissions",
    "tender": "Tenders",
    "pressrelease": "Press Releases",
    "moe": "Ministry of Education",
    "examinationresult": "Examinations",
    "scholarresults": "Examinations",
    "examdatesheet": "Examinations",
    "examnotification": "Examinations",
    "itandservices": "IT & Services",
    "universitydoc": "University Documents",
    "publichomequicklinks": "University Documents",
    "event": "Events",
    "eventgallerymanage": "Events",
    "universityinitiatives": "Research",
    "videogallery": "Media Gallery",
    "whatnew": "News & Updates",
    "studentzone": "Student Zone",
    "policy": "Policies",
    "implink": "Important Links",
    "additionalcard": "Quick Links",
    "howtoreachcuk": "Contact",
    "promotions": "Announcements",
    "messages": "Messages",
    "administrative": "Administration",
    "department": "Academics",
    "faculty": "Academics",
    "school": "Academics",
}


def _endpoint_section(endpoint: str) -> str:
    prefix = endpoint.split("/")[0].lower()
    return _ENDPOINT_SECTION_MAP.get(prefix, "")


# ---------------------------------------------------------------------------
# Coverage report writer
# ---------------------------------------------------------------------------


def _write_coverage(
    path: Path,
    nodes: list[SiteNode],
    documents: list[dict],
) -> None:
    from collections import Counter

    path.parent.mkdir(parents=True, exist_ok=True)

    status_counts: Counter = Counter(n.status for n in nodes)
    route_counts: Counter = Counter(n.route_name for n in nodes)
    school_node_counts: Counter = Counter(
        (n.school_name, n.department_name)
        for n in nodes
        if n.school_name and n.route_name == "departmentList" and not n.menu_id
    )

    # Unmapped routes
    unmapped = [n for n in nodes if n.status == "unmapped_route"]
    unmapped_routes: dict[str, str] = {}
    for n in unmapped:
        if n.route_name not in unmapped_routes:
            unmapped_routes[n.route_name] = n.angular_url

    # Failed nodes
    failed = [n for n in nodes if n.status == "failed"]

    # External links from docs
    ext_links_total = sum(
        len([lo for lo in d["metadata"].get("links_out", []) if lo.get("type") == "external"])
        for d in documents
    )

    lines = [
        "# CUK Scrape — Coverage Report\n",
        f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}\n",
        "",
        "## Node counts by status\n",
        f"Total nodes: **{len(nodes)}**\n",
        "| Status | Count |",
        "|---|---|",
    ]
    for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {status} | {cnt} |")

    lines += ["", "## Node counts by route_name\n", "| Route | Count |", "|---|---|"]
    for route, cnt in sorted(route_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {route} | {cnt} |")

    lines += [
        "",
        "## Per-school, per-department coverage\n",
        "| School | Department | Expected menu items | Fetched nodes |",
        "|---|---|---|---|",
    ]
    # Group by school
    school_depts: dict[str, list[str]] = {}
    for sname, dname in school_node_counts:
        school_depts.setdefault(sname, []).append(dname)
    for sname in sorted(school_depts):
        for dname in sorted(school_depts[sname]):
            # Count menu children for this dept
            expected = sum(
                1
                for n in nodes
                if n.school_name == sname
                and n.department_name == dname
                and n.route_name == "departmentList"
                and n.menu_id
            )
            fetched = sum(
                1
                for n in nodes
                if n.school_name == sname
                and n.department_name == dname
                and n.route_name == "departmentList"
                and n.menu_id
                and n.status == "fetched"
            )
            lines.append(f"| {sname} | {dname} | {expected} | {fetched} |")

    lines += ["", "## Unmapped route names\n"]
    if unmapped_routes:
        lines += ["| Route | Example URL |", "|---|---|"]
        for route, url in sorted(unmapped_routes.items()):
            lines.append(f"| {route} | {url} |")
        lines += [
            "",
            "> **Action required:** Capture a HAR for each unmapped route to identify its API pattern.\n",
        ]
    else:
        lines.append("No unmapped routes.\n")

    lines += ["", "## Failed nodes\n"]
    if failed:
        lines += ["| Angular URL | Route | Reason |", "|---|---|---|"]
        for n in failed[:50]:
            lines.append(f"| {n.angular_url} | {n.route_name} | http_status={n.http_status} |")
    else:
        lines.append("No failures.\n")

    lines += [
        "",
        f"## External links recorded\n\nTotal: **{ext_links_total}** external links across all docs.\n",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
