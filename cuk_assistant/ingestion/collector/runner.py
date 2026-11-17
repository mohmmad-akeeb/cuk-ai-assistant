"""Pure Raw Collector Orchestrator for CUK website and API lake.

Extracts pristine HTTP/API assets and writes:
  - data/raw/html/{route_hash}.html
  - data/raw/api/{endpoint_hash}.json
  - data/raw/pdf/{filename_or_hash}.pdf
  - data/raw/nodes.jsonl
  - data/raw/manifest.jsonl

Performs ZERO markdown conversion, ZERO regex stripping, and ZERO parsing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any

from rich.console import Console

from cuk_assistant.core.config import Settings
from cuk_assistant.core.http_cache import CachedClient
from cuk_assistant.ingestion.collector.subsystems.client import (
    API_BASE,
    DirectApiClient,
    download_pdf_cached,
)
from cuk_assistant.ingestion.collector.subsystems.manifest import ManifestEntry, ManifestWriter
from cuk_assistant.ingestion.collector.subsystems.route_walker import (
    build_node_table,
    fetch_all_nodes,
    nodes_to_jsonl,
)

logger = logging.getLogger(__name__)
console = Console(stderr=True)

# Endpoints to skip entirely (noise / binary)
_SKIP_ENDPOINTS: set[str] = {
    "banner/getallbannersforwebsite",
    "auditlog/selectlastupdated",
    "languagesetting/languagesettingList",
    "mediagallery/getmediagalleryforwebsite2",
    "headercategory/headercategoryList",
    "studentzone/getbreadcum",
    "administrative/getbreadcum",
    "headercategory/headercategoryListById",
    "administrative/spdepartlist",
}

_GLOBAL_LIST_ENDPOINTS: list[tuple[str, dict]] = [
    ("noticeboard/all", {"seen": 0, "next": 0}),
    ("admission/all", {"seen": 0, "next": 0}),
    ("employments/all", {"seen": 0, "next": 0}),
    ("tender/getalltender", {"langType": 1}),
    ("pressrelease/getAllPressReleasesForWebSite", {"seen": 0, "next": 0}),
]

_HOMEPAGE_WIDGET_ENDPOINTS: list[tuple[str, dict]] = [
    ("publichomequicklinks/getallpublichomequicklinksforwebsite", {}),
    ("additionalcard/getalladditionalcardsforwebsite", {}),
    ("whatnew/getallwhatnewforwebsite", {}),
    ("implink/getallimplinksforwebsite", {}),
    ("latestnews/getalllatestnewsforwebsite", {}),
    ("officerorders/getallofficerordersforwebsite", {}),
    ("upcomingevent/getallupcomingeventsforwebsite", {}),
]


def _hash_key(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:24]


def _sanitize_filename(name: str) -> str:
    name = Path(name).name.split("?")[0]
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    return cleaned if cleaned and cleaned != ".pdf" else "document.pdf"


_HTML_TAG_RE = re.compile(
    r"<(?:p|div|table|h[1-6]|ul|ol|li|hr|span|article|section|header|footer|b|i|strong|em|br)[^>]*>",
    re.IGNORECASE,
)
_HTML_KEYS = (
    "DepartmentDescription",
    "AdministrativeDescription",
    "Details",
    "Content",
    "LongDescription",
    "Description",
)


def _contains_html(val: Any) -> bool:
    if not isinstance(val, str) or not val.strip():
        return False
    return bool(_HTML_TAG_RE.search(val))


async def _fetch_content_detail_fallback(
    api: DirectApiClient,
    endpoint: str,
    row: dict,
) -> dict | None:
    rec_id = row.get("Id") or row.get("id") or ""
    id_val: str = ""
    type_val: str = ""

    if endpoint == "headercategory/subCategoryListByHeaderCategoryId":
        rec_id = row.get("Id") or ""
        id_val = str(rec_id)
        type_val = "content"
    elif endpoint == "department/departmentListById":
        menu_id = row.get("MenuId") or ""
        id_val = str(menu_id) if menu_id else str(rec_id)
        type_val = "departlist"
    else:
        has_content = bool(
            row.get("Description")
            or row.get("Content")
            or row.get("Details")
            or row.get("LongDescription")
            or row.get("FileUrl")
        )
        if rec_id and not has_content:
            id_val = str(rec_id)
            type_val = endpoint.split("/")[0].lower()

    if not id_val:
        return None

    from cuk_assistant.ingestion.collector.route_walker import (
        _resolve_content_endpoint_and_payload,
    )

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


async def run(
    settings: Settings,
    *,
    force: bool = False,
    skip_pdf: bool = False,
) -> None:
    """Run pure raw extraction and loading to data/raw/."""
    raw_dir = getattr(settings, "raw_dir", settings.project_root / "data" / "raw")
    html_dir = raw_dir / "html"
    api_dir = raw_dir / "api"
    pdf_dir = raw_dir / "pdf"
    manifest_path = raw_dir / "manifest.jsonl"
    nodes_path = raw_dir / "nodes.jsonl"
    processed_nodes_path = settings.processed_dir / "nodes.jsonl"

    for d in (html_dir, api_dir, pdf_dir):
        d.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        manifest_path.unlink()

    manifest_writer = ManifestWriter(manifest_path)

    queued_pdf_urls: set[str] = set()
    pdf_tasks: list[tuple[str, dict, dict]] = []  # (url, provenance, raw_meta)

    def _queue_pdf(url_or_obj: Any, prov: dict, meta: dict) -> None:
        if isinstance(url_or_obj, dict):
            raw_url = (
                url_or_obj.get("url")
                or url_or_obj.get("file_url")
                or url_or_obj.get("FilePath")
                or url_or_obj.get("FileUrl")
                or url_or_obj.get("href")
                or ""
            )
            link_title = (
                url_or_obj.get("text")
                or url_or_obj.get("title")
                or url_or_obj.get("Title")
                or meta.get("title")
                or ""
            )
            meta = {**meta, "title": link_title, **url_or_obj}
        else:
            raw_url = str(url_or_obj or "")

        clean = raw_url.strip()
        if not clean or clean in queued_pdf_urls:
            return
        if clean.startswith("/"):
            clean = urllib.parse.urljoin("https://cukashmir.ac.in/", clean)
        queued_pdf_urls.add(clean)
        pdf_tasks.append((clean, prov, meta))

    console.print("\n[bold]Phase 1:[/bold] Discovering Angular routes and building node table …")
    async with CachedClient.from_settings(settings) as client:
        nodes = await build_node_table(settings, client)
        await fetch_all_nodes(nodes, client, settings)

    nodes_to_jsonl(nodes, nodes_path)
    nodes_to_jsonl(nodes, processed_nodes_path)
    console.print(f"  Nodes saved to {nodes_path} ({len(nodes)} total)")

    async with CachedClient.from_settings(settings) as client:
        api = DirectApiClient(client)

        console.print("\n[bold]Phase 2:[/bold] Extracting pristine node assets (HTML & API) …")
        for node in nodes:
            prov = {
                "school": node.school_name,
                "school_master_id": node.school_master_id,
                "department": node.department_name,
                "department_master_id": node.department_master_id,
                "node_path": node.breadcrumb,
                "menu_id": node.menu_id,
                "route_name": node.route_name,
                "node_id": node.node_id,
                "page_url": node.angular_url,
            }

            # Queue PDFs from node.pdf_links
            for plink in node.pdf_links:
                _queue_pdf(
                    plink,
                    prov,
                    {
                        "file_url": plink if isinstance(plink, str) else plink.get("url", ""),
                        "title": node.breadcrumb[-1] if node.breadcrumb else "",
                    },
                )

            # Separate rich HTML assets from pure structured API records
            if node.content_records:
                non_html_records: list[dict] = []

                for rec in node.content_records:
                    if not isinstance(rec, dict):
                        continue

                    html_key = next((k for k in _HTML_KEYS if _contains_html(rec.get(k))), None)
                    if html_key:
                        html_content = rec[html_key]
                        rec_title = (
                            rec.get("Title")
                            or rec.get("AdministrativeName")
                            or rec.get("DepartmentName")
                            or (node.breadcrumb[-1] if node.breadcrumb else "")
                            or node.route_name
                        ).strip()

                        clean_slug = (
                            re.sub(r"[^a-zA-Z0-9_]+", "_", rec_title.lower()).strip("_")[:40]
                            or "page"
                        )
                        content_hash = _hash_key(f"{node.angular_url}::{rec_title}::{html_content}")
                        html_filename = f"{node.route_name}_{clean_slug}_{content_hash}.html"
                        html_file = html_dir / html_filename

                        wrapped_html = (
                            f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
                            f'  <meta charset="utf-8">\n'
                            f"  <title>{rec_title}</title>\n"
                            f"</head>\n<body>\n{html_content}\n</body>\n</html>\n"
                        )
                        html_file.write_text(wrapped_html, encoding="utf-8")

                        manifest_writer.append(
                            ManifestEntry(
                                asset_id=f"html_{content_hash}",
                                asset_type="html",
                                source_url=node.angular_url,
                                local_path=str(html_file.relative_to(settings.project_root)),
                                provenance={
                                    **prov,
                                    "title": rec_title,
                                },
                                raw_meta={
                                    "title": rec_title,
                                    "route_name": node.route_name,
                                    "page_url": node.angular_url,
                                    "source_url": node.angular_url,
                                    "api_endpoint": node.api_endpoint or f"node_{node.route_name}",
                                    "raw_api_endpoint": node.api_endpoint
                                    or f"node_{node.route_name}",
                                    "html_key": html_key,
                                    "content_hash": content_hash,
                                    "content_type": (
                                        "department_page"
                                        if "department" in node.route_name.lower()
                                        or "depart" in node.route_name.lower()
                                        else "administrative_page"
                                    ),
                                    **{k: v for k, v in rec.items() if not _contains_html(v)},
                                },
                            )
                        )

                        # Extract embedded PDF links in the HTML
                        for pdf_href in re.findall(
                            r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',
                            html_content,
                            re.IGNORECASE,
                        ):
                            full_pdf_url = urllib.parse.urljoin(
                                "https://cukashmir.ac.in/", pdf_href.strip()
                            )
                            _queue_pdf(
                                full_pdf_url,
                                prov,
                                {
                                    "title": rec_title,
                                    "found_on": node.angular_url,
                                    "found_on_page": node.angular_url,
                                },
                            )
                    else:
                        non_html_records.append(rec)

                # Save pure non-HTML records as pristine API JSON
                if non_html_records:
                    ep_clean = (node.api_endpoint or f"node_{node.route_name}").replace("/", "_")
                    endpoint_hash = _hash_key(f"{node.api_endpoint}::{node.request_payload}")
                    api_file = api_dir / f"{ep_clean}_{endpoint_hash}.json"
                    raw_payload = {
                        "api_endpoint": node.api_endpoint,
                        "request_payload": node.request_payload,
                        "records": non_html_records,
                    }
                    api_file.write_text(
                        json.dumps(raw_payload, ensure_ascii=False), encoding="utf-8"
                    )

                    manifest_writer.append(
                        ManifestEntry(
                            asset_id=f"api_{endpoint_hash}",
                            asset_type="api_json",
                            source_url=f"{API_BASE}/{node.api_endpoint}"
                            if node.api_endpoint
                            else node.angular_url,
                            local_path=str(api_file.relative_to(settings.project_root)),
                            provenance=prov,
                            raw_meta={
                                "endpoint": node.api_endpoint,
                                "api_endpoint": node.api_endpoint or f"node_{node.route_name}",
                                "raw_api_endpoint": node.api_endpoint or f"node_{node.route_name}",
                                "page_url": node.angular_url,
                                "source_url": f"{API_BASE}/{node.api_endpoint}"
                                if node.api_endpoint
                                else node.angular_url,
                                "request_payload": node.request_payload,
                                "records_count": len(non_html_records),
                                "title": node.breadcrumb[-1] if node.breadcrumb else "",
                            },
                        )
                    )

                    for rec in non_html_records:
                        furl = rec.get("FileUrl") or rec.get("file_url") or rec.get("FilePath")
                        if furl:
                            full_furl = urllib.parse.urljoin("https://cukashmir.ac.in/", str(furl))
                            _queue_pdf(full_furl, prov, rec)

        console.print("\n[bold]Phase 3:[/bold] Collecting global lists & departmental faculty …")
        # Global list endpoints
        for ep, payload in _GLOBAL_LIST_ENDPOINTS:
            ep_hash = _hash_key(f"{ep}::{json.dumps(payload, sort_keys=True)}")
            ep_clean = ep.replace("/", "_")
            api_file = api_dir / f"{ep_clean}_{ep_hash}.json"

            records = await api._post(ep, payload)
            if records:
                api_file.write_text(
                    json.dumps(
                        {"endpoint": ep, "payload": payload, "records": records}, ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                manifest_writer.append(
                    ManifestEntry(
                        asset_id=f"api_{ep_hash}",
                        asset_type="api_json",
                        source_url=f"{API_BASE}/{ep}",
                        local_path=str(api_file.relative_to(settings.project_root)),
                        provenance={
                            "school": "Central",
                            "department": "University Administration",
                            "node_path": [ep],
                        },
                        raw_meta={
                            "endpoint": ep,
                            "api_endpoint": ep,
                            "raw_api_endpoint": ep,
                            "page_url": f"https://cukashmir.ac.in/#/{ep}",
                            "source_url": f"{API_BASE}/{ep}",
                            "payload": payload,
                            "records_count": len(records),
                            "is_university_wide": True,
                        },
                    )
                )
                for rec in records:
                    if isinstance(rec, dict):
                        furl = rec.get("FileUrl") or rec.get("file_url")
                        if furl:
                            full_furl = urllib.parse.urljoin("https://cukashmir.ac.in/", str(furl))
                            _queue_pdf(
                                full_furl,
                                {
                                    "school": "Central",
                                    "department": "Administration",
                                    "node_path": [ep],
                                },
                                rec,
                            )

        # Faculty by department
        seen_dept_ids: set[str] = set()
        for node in nodes:
            if not node.id or node.id in seen_dept_ids:
                continue
            seen_dept_ids.add(node.id)
            fac_records = await api.faculty_by_dept(node.id)
            if fac_records:
                f_hash = _hash_key(f"faculty_{node.id}")
                api_file = api_dir / f"faculty_{node.id}_{f_hash}.json"
                api_file.write_text(
                    json.dumps(
                        {
                            "endpoint": "faculty/getallforwebsite",
                            "DepartmentId": node.id,
                            "records": fac_records,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifest_writer.append(
                    ManifestEntry(
                        asset_id=f"faculty_{f_hash}",
                        asset_type="api_json",
                        source_url=f"{API_BASE}/faculty/getallforwebsite",
                        local_path=str(api_file.relative_to(settings.project_root)),
                        provenance={
                            "school": node.school_name,
                            "department": node.department_name,
                            "node_path": node.breadcrumb,
                            "department_id": node.id,
                            "department_master_id": node.department_master_id,
                        },
                        raw_meta={
                            "endpoint": "faculty/getallforwebsite",
                            "api_endpoint": "faculty/getallforwebsite",
                            "raw_api_endpoint": "faculty/getallforwebsite",
                            "page_url": node.angular_url,
                            "source_url": f"{API_BASE}/faculty/getallforwebsite",
                            "DepartmentId": node.id,
                            "department_id": node.id,
                            "department_master_id": node.department_master_id,
                            "faculty_dept_id_sent": node.id,
                            "department_name": node.department_name,
                            "school_name": node.school_name,
                            "records_count": len(fac_records),
                            "content_type": "faculty",
                        },
                    )
                )

        console.print(
            f"\n[bold]Phase 4:[/bold] Processing PDF downloads ({len(pdf_tasks)} queued, skip_pdf={skip_pdf}) …"
        )
        for purl, prov, meta in pdf_tasks:
            fname = _sanitize_filename(purl.split("/")[-1])
            if not fname.lower().endswith(".pdf"):
                fname += ".pdf"
            pdf_hash = _hash_key(purl)
            local_pdf = pdf_dir / f"{pdf_hash}_{fname}"

            rel_path = str(local_pdf.relative_to(settings.project_root))
            if not skip_pdf:
                await download_pdf_cached(purl, local_pdf, client, skip_pdf=skip_pdf)

            manifest_writer.append(
                ManifestEntry(
                    asset_id=f"pdf_{pdf_hash}",
                    asset_type="pdf",
                    source_url=purl,
                    local_path=rel_path,
                    provenance=prov,
                    raw_meta={
                        "title": meta.get("title") or meta.get("Title") or fname,
                        "file_name": fname,
                        "is_pdf": True,
                        **meta,
                    },
                )
            )

    console.print(f"[bold green]Crawl complete![/bold green] Assets written to {manifest_path}")


__all__ = [
    "_GLOBAL_LIST_ENDPOINTS",
    "_HOMEPAGE_WIDGET_ENDPOINTS",
    "_fetch_content_detail_fallback",
    "run",
]
