"""Node table builder + content fetcher for the CUK site.

Implements B1 (node table) and B2 (fetch by route type).

The node table is written to data/processed/nodes.jsonl — one row per page on the
whole site.  Seeds:
  1. Top nav tree  (headercategory/headercategoryList)
  2. School tree   (schoolList → mappedDepartments → departmentMenus)
  3. Homepage widgets (publichomequicklinks etc.)
  4. Student Zone

Visited-set is keyed on (route_name, id, menu_id) so the same Angular page
reached via different seeds is not double-counted.

For each node the crawler resolves the API call dictated by its route_name:
  departlist          → department/departmentListById {Id}
  departmentList      → department/departmentListById {Id}  (school-tree pages)
  administration      → administrative/spdepartlist {Id}
  administrative-list → headercategory/headercategoryListById {Id}
  content             → (marked unmapped — no known API pattern yet)
  school              → school/schoolList (no id)
  home / other        → marked unmapped

Route names with no known API pattern are logged in the coverage report.

Overall exploration strategy
-----------------------------
The crawler uses three complementary seed strategies to discover every Angular
"page" (node) on the CUK site, then resolves each node's content via a
dedicated REST API call:

  Seed 1 — Nav tree
    Calls headercategory/headercategoryList to get the top navigation bar items.
    Each item becomes a "departlist" node.  Parent–child relationships are
    reconstructed from ParentHeaderCategoryMasterId to build breadcrumbs.

  Seed 1 also drills into each nav item via headercategoryListById to discover
    "administrative-list" sub-pages (menuid nodes) that only appear as children
    of a header-category, never in the flat headercategoryList response.

  Seed 2 — School tree (up to 4-level depth)
    Calls schoolList → for every school, calls mappedDepartments → for every
    department, calls departmentMenus.  Each menu item becomes a
    "departmentList" node.  If a menu item has SubChildCount > 0 the crawler
    recurses further.  The id field is always anchored to the root department
    DepartmentMasterId so Angular URLs and de-dup keys stay correct at every
    depth:
      School → Department → Menu item → Sub-menu item → Sub-sub-menu item

  De-duplication
    A visited set keyed on (route_name, id, menu_id) prevents the same Angular
    page from being added more than once, even if it is reachable from multiple
    seeds.

  Content fetch (B2)
    After the full node table is built, fetch_all_nodes iterates every
    "pending" node and calls _fetch_node_content, which dispatches to the
    correct REST endpoint based on the node's route_name.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cuk_assistant.core.config import Settings
from cuk_assistant.core.http_cache import CachedClient
from cuk_assistant.ingestion.collector.subsystems.client import DirectApiClient
from cuk_assistant.ingestion.crawl.html_parser import parse_html

logger = logging.getLogger(__name__)

# Angular route names the crawler knows how to resolve to a REST endpoint.
# Any route_name in this set will be dispatched inside _fetch_node_content.
_KNOWN_ROUTES: set[str] = {
    "departlist",
    "departmentList",
    "administration",
    "administrative-list",
    "school",
    "home",
    "content",
    "notifications",
    "message",
    "implink",
    "universitydoc",
    "universityini",
    "tenders",
    "employment",
    "upcoming-event",
}

# Route names whose backing API is not yet known or is handled elsewhere.
# Nodes with these routes are marked "unmapped_route" and skipped during fetch.
_UNMAPPED_ROUTES: set[str] = {
    "event-gallery",  # unknown
    "screenreaderaccess",  # accessibility page, low priority
    "listing",  # handled separately via global list endpoints
    "student-zone",  # handled separately
    "research",  # probably administrative
    "diqa",  # probably administrative
}

# ISO-8601 timestamp captured once at import time, used for audit fields.
_NOW_ISO = datetime.now(tz=UTC).isoformat()

# Regex to match PDF URLs
_PDF_RE = re.compile(r"\.pdf(\?[^\"'>]*)?$", re.IGNORECASE)


def _parse_angular_route(url: str) -> tuple[str, str, str] | None:
    """Parse an Angular route fragment (e.g. /#/administration;id=...;menuid=...) into (route, id, menuid)."""
    if not url:
        return None
    url = url.strip()
    idx = url.find("#/")
    if idx == -1:
        return None
    fragment = url[idx + 2 :]
    parts = fragment.split(";")
    first_part = parts[0].strip()

    id_val = ""
    menu_id_val = ""
    if "?" in first_part:
        route_name, query_str = first_part.split("?", 1)
        for qp in query_str.split("&"):
            if "=" in qp:
                k, v = qp.split("=", 1)
                k_clean = k.strip().lower()
                if k_clean == "id":
                    id_val = v.strip()
                elif k_clean == "menuid":
                    menu_id_val = v.strip()
    else:
        route_name = first_part

    for p in parts[1:]:
        p = p.strip()
        if p.lower().startswith("id=") and not id_val:
            id_val = p[3:].strip()
        elif p.lower().startswith("menuid=") and not menu_id_val:
            menu_id_val = p[7:].strip()
        elif "?" in p:
            for qp in p.split("?")[1].split("&"):
                if "=" in qp:
                    k, v = qp.split("=", 1)
                    k_clean = k.strip().lower()
                    if k_clean == "id" and not id_val:
                        id_val = v.strip()
                    elif k_clean == "menuid" and not menu_id_val:
                        menu_id_val = v.strip()

    return route_name, id_val, menu_id_val


def _is_real_external(record: dict) -> bool:
    """Return True only if the record is marked external AND has a non-empty external URL.

    CMS records frequently have IsExternalLink: True while ExternalLinkUrl is empty,
    accompanied by rich internal HTML in DepartmentDescription. Those are internal pages.
    Also, internal Angular routes (e.g. /#/administration;id=...) are not off-site links.
    """
    ext_url = str(record.get("ExternalLinkUrl") or record.get("ExternalUrl") or "").strip()
    if not (record.get("IsExternalLink") and ext_url):
        return False
    return _parse_angular_route(ext_url) is None


def _extract_item_pdfs(html: str, page_url: str) -> list[dict]:
    """Extract PDF links from an HTML string for a given page URL."""
    if not html or not isinstance(html, str) or "<" not in html:
        return []
    parsed = parse_html(html)
    pdfs: list[dict] = []
    seen: set[str] = set()
    for lo in parsed.links_out:
        if lo.type == "pdf" and lo.href.startswith("http") and lo.href not in seen:
            seen.add(lo.href)
            pdfs.append(
                {
                    "url": lo.href,
                    "text": lo.text or "",
                    "found_on": page_url,
                }
            )
    return pdfs


def _node_id(route_name: str, node_id_val: str, menu_id: str) -> str:
    """Generate a stable 20-character hex ID for a node.

    The ID is a truncated SHA-256 digest of the triple
    ``(route_name, node_id_val, menu_id)`` joined by ``::`` separators.
    This guarantees uniqueness across different route types even when the
    numeric IDs overlap, and keeps the output compact.

    Args:
        route_name:   The Angular route name (e.g. "departmentList").
        node_id_val:  The primary entity identifier (e.g. DepartmentMasterId).
        menu_id:      The secondary menu-level identifier, or "" when absent.

    Returns:
        A 20-character lowercase hex string that uniquely identifies the node.
    """
    raw = f"{route_name}::{node_id_val}::{menu_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


@dataclass
class SiteNode:
    """Represents a single crawlable page (node) on the CUK Angular site.

    Each node corresponds to one Angular route that the front-end renders.
    After ``build_node_table`` the node carries structural metadata; after
    ``fetch_all_nodes`` it is enriched with the raw API response records.

    Attributes:
        node_id:              Stable 20-char hex fingerprint (see ``_node_id``).
        route_name:           Angular route segment (e.g. "departmentList").
        id:                   Primary entity ID (HeaderCategoryMasterId or
                              DepartmentMasterId depending on route).
        menu_id:              Secondary menu-item ID used by departmentList
                              pages to select a specific sub-page; "" otherwise.
        parent_node_id:       ``node_id`` of the logical parent in the site
                              hierarchy, or "" for root nodes.
        breadcrumb:           Ordered list of ancestor labels ending with the
                              node's own label — used for RAG context.
        school_master_id:     ID of the school this node belongs to (school
                              tree only), or "".
        school_name:          Display name of the school, or "".
        department_master_id: ID of the department, or "".
        department_name:      Display name of the department, or "".
        source:               Which seed discovered the node:
                              "nav-tree" | "school-tree" | "html-link" |
                              "homepage".
        status:               Lifecycle state:
                              "pending"       — discovered, not yet fetched
                              "fetched"       — API call succeeded with data
                              "empty"         — API call succeeded, no records
                              "external"      — points to an off-site URL
                              "pdf"           — points to a PDF file
                              "failed"        — API call raised an exception
                              "unmapped_route"— no known API pattern
        http_status:          HTTP status code returned by the content API, or
                              0 when no call was made.
        angular_url:          Full Angular hash-route URL for this page.
        api_endpoint:         REST endpoint path used (populated after fetch).
        request_payload:      JSON string of the POST body sent (after fetch).
        content_records:      Raw list of dicts returned by the content API
                              (populated after fetch; omitted from JSONL).
    """

    node_id: str
    route_name: str
    id: str  # the HeaderCategoryMasterId or DepartmentMasterId
    menu_id: str  # for departmentList pages: the menu item's MasterId
    parent_node_id: str
    breadcrumb: list[str]
    school_master_id: str
    school_name: str
    department_master_id: str
    department_name: str
    source: str  # nav-tree | school-tree | html-link | homepage
    status: str  # pending | fetched | empty | external | pdf | failed | unmapped_route
    http_status: int
    angular_url: str
    api_endpoint: str
    request_payload: str  # JSON string
    # Content (populated after fetch)
    content_records: list[dict] = field(default_factory=list)
    # PDF links discovered on this node
    pdf_links: list[dict] = field(default_factory=list)


def _angular_url(base: str, route: str, id_: str, menu_id: str = "") -> str:
    """Build the Angular hash-route URL for a node.

    The CUK front-end is a single-page application that encodes page identity
    in the URL fragment using Angular's matrix-URL notation:

      ``<base>/#/<route>;id=<id_>`` (no menu)
      ``<base>/#/<route>;id=<id_>;menuid=<menu_id>`` (with menu)
      ``<base>/#/<route>`` (no id at all, e.g. the school list)

    Args:
        base:    Site base URL (e.g. "https://cuk.ac.in").
        route:   Angular route name (e.g. "departmentList").
        id_:     Primary entity ID; pass "" when the route has no ID param.
        menu_id: Secondary menu ID; omitted from the URL when empty.

    Returns:
        A fully-qualified Angular hash-route URL string.
    """
    if menu_id:
        return f"{base}/#/{route};id={id_};menuid={menu_id}"
    elif id_:
        return f"{base}/#/{route};id={id_}"
    else:
        return f"{base}/#/{route}"


def _node_key(route_name: str, id_: str, menu_id: str) -> tuple[str, str, str]:
    """Return a normalised de-duplication key for a node.

    The key is case-normalised so that the same logical page discovered via
    different seeds (which may differ in capitalisation) is treated as a
    single node.

    Args:
        route_name: Angular route name.
        id_:        Primary entity ID.
        menu_id:    Secondary menu ID, or "".

    Returns:
        A 3-tuple ``(route_name_lower, id_upper, menu_id_upper)`` suitable
        for use as a ``set`` or ``dict`` key.
    """
    return (route_name.lower(), id_.upper(), menu_id.upper())


def _extract_content_params(node: SiteNode) -> tuple[str, str]:
    """Extract (type, id) from a content route node."""
    url = node.angular_url or ""
    type_val = ""
    id_val = node.id or ""

    if "#/" in url:
        fragment = url.split("#/", 1)[1]
    elif "#" in url:
        fragment = url.split("#", 1)[1]
    else:
        fragment = url

    if "?" in fragment:
        q_part = fragment.split("?", 1)[1]
        for pair in q_part.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                k_clean = k.strip().lower()
                if k_clean == "type":
                    type_val = v.strip().lower()
                elif k_clean == "id" and not id_val:
                    id_val = v.strip()

    if ";" in fragment:
        for part in fragment.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                k_clean = k.strip().lower()
                if k_clean == "type":
                    type_val = v.strip().lower()
                elif k_clean == "id" and not id_val:
                    id_val = v.strip()

    return type_val, id_val


def _resolve_content_endpoint_and_payload(type_val: str, id_val: str) -> tuple[str, dict]:
    """Resolve content (type, id) to the corresponding single-record REST endpoint and payload."""
    t = type_val.lower().replace("-", "").replace("_", "")
    if not id_val:
        return "", {}

    if "notice" in t:
        return "noticeboard/selectbyid", {"langType": 1, "Id": id_val}
    elif "admission" in t:
        return "admission/getadmissionbyid", {"langType": 1, "Id": id_val}
    elif "whatnew" in t or "whatsnew" in t or "news" in t:
        return "whatnew/selectbyid", {"langType": 1, "RowId154": id_val}
    elif "tender" in t:
        return "tender/getbyidforwebsite", {"langType": 1, "RowId154": id_val}
    elif "program" in t:
        return "mainprogramms/selectbyid", {"langType": 1, "Id": id_val}
    elif "press" in t:
        return "pressrelease/selectbyid", {"langType": 1, "Id": id_val}
    elif "moe" in t:
        return "moe/selectbyid", {"langType": 1, "Id": id_val}
    elif "datesheet" in t:
        return f"examdatesheet/ExamDateSheetId/{id_val}", {}
    elif "result" in t:
        return f"examinationresult/ExaminationResultbyId/{id_val}", {"langType": 1}
    elif "examnotif" in t:
        return f"examnotification/ExamNotificationbyId/{id_val}", {"langType": 1}
    elif "employment" in t:
        return "employments/getEditDataById", {"Id": id_val}
    elif "message" in t:
        return "messages/getEditDataById", {"Id": id_val}
    elif "event" in t:
        return "event/getbyid", {"Id": id_val}
    elif "quicklink" in t:
        return "publichomequicklinks/getEditDataById", {"Id": id_val}
    elif "card" in t:
        return "additionalcard/getEditDataById", {"Id": id_val}
    else:
        # Default fallback
        return "noticeboard/selectbyid", {"langType": 1, "Id": id_val}


async def _fetch_node_content(
    node: SiteNode,
    api: DirectApiClient,
) -> None:
    """Dispatch the correct REST API call for a node and populate its content.

    The function examines ``node.route_name`` (case-insensitively) and calls
    the matching API endpoint, then writes the results back into the node
    in-place.  After this call the node's ``status``, ``http_status``,
    ``api_endpoint``, ``request_payload``, and ``content_records`` fields are
    all updated.

    Route → endpoint mapping
    ~~~~~~~~~~~~~~~~~~~~~~~~
    * ``departlist`` / ``departmentlist``
        POST ``department/departmentListById`` with ``{"Id": <menu_id or id>}``.
        ``menu_id`` takes priority over ``id`` when both are present.
    * ``administration``
        POST ``administrative/spdepartlist`` with ``{"Id": <id>}``.
    * ``administrative-list``
        POST ``headercategory/headercategoryListById`` with ``{"Id": <id>}``.
    * ``school``
        No additional API call needed; the school list was already fetched
        during seed construction.  Marked "fetched" immediately.
    * ``home``
        Homepage nodes carry no content records; marked "fetched" immediately.
    * Everything else
        If the route is in ``_UNMAPPED_ROUTES`` or is entirely unknown, the
        node is marked ``"unmapped_route"`` with ``http_status=0``.

    Args:
        node: The ``SiteNode`` to fetch content for.  Modified in-place.
        api:  The ``DirectApiClient`` used to make REST calls.

    Returns:
        None.  All results are written back into ``node``.

    Raises:
        Does not propagate exceptions — any failure is caught, logged, and
        recorded as ``status="failed"`` on the node.
    """
    # Normalise to lowercase so comparisons are case-insensitive
    r = node.route_name.lower()

    try:
        if r in ("departlist", "departmentlist"):
            # Both "departlist" (nav-tree) and "departmentList" (school-tree)
            # use the same API endpoint.  When a menu_id is present (i.e. this
            # is a sub-page within a department) use it as the lookup key;
            # otherwise fall back to the department's own id.
            if node.menu_id:
                records = await api.department_page(node.menu_id)
            elif node.id:
                records = await api.department_page(node.id)
            else:
                records = []

            # If the API returned records, update content_records; otherwise preserve
            # any record already populated from department_menu discovery.
            if records:
                node.content_records = records
            elif not node.content_records:
                node.content_records = []

            node.api_endpoint = "department/departmentListById"
            # Record whichever ID was actually sent to the API
            if node.menu_id:
                node.request_payload = json.dumps({"Id": node.menu_id})
            else:
                node.request_payload = json.dumps({"Id": node.id})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "administration":
            # Administrative department pages use administrative/administrativeListById
            records = await api._post(
                "administrative/administrativeListById",
                {"Id": node.id},
            )
            node.content_records = records if isinstance(records, list) else []
            node.api_endpoint = "administrative/administrativeListById"
            node.request_payload = json.dumps({"Id": node.id})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "administrative-list":
            # Call administrative/administrativeListById and queue employee profiles
            if hasattr(api, "administrative_menu"):
                records = await api.administrative_menu(node.id)
            else:
                records = await api._post(
                    "administrative/administrativeListById",
                    {"Id": node.id, "LangType": 1},
                )
            rec_list = list(records) if isinstance(records, list) else []
            if hasattr(api, "employee_profiles"):
                try:
                    profiles = await api.employee_profiles(node.id)
                    if isinstance(profiles, list) and profiles:
                        rec_list.extend(profiles)
                except Exception:
                    pass
            node.content_records = rec_list
            node.api_endpoint = "administrative/administrativeListById"
            node.request_payload = json.dumps({"Id": node.id, "LangType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "content":
            # Single-item detail viewer (/content?type=...&id=...)
            type_val, id_val = _extract_content_params(node)
            endpoint, payload = _resolve_content_endpoint_and_payload(type_val, id_val)
            if endpoint:
                resp = await api._post(endpoint, payload)
                if isinstance(resp, list):
                    node.content_records = resp
                elif isinstance(resp, dict):
                    node.content_records = [resp]
                else:
                    node.content_records = []
                node.api_endpoint = endpoint
                node.request_payload = json.dumps(payload)
                node.status = "fetched" if node.content_records else "empty"
                node.http_status = 200
            else:
                node.status = "empty"
                node.http_status = 200

        elif r == "notifications":
            records = await api.paged_list("noticeboard/all", seen=0, next_n=50)
            node.content_records = records
            node.api_endpoint = "noticeboard/all"
            node.request_payload = json.dumps(
                {"langType": 1, "DepartmentId": "", "seen": 0, "next": 50}
            )
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "tenders":
            records = await api.all_tenders()
            node.content_records = records
            node.api_endpoint = "tender/getalltender"
            node.request_payload = json.dumps({"langType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "employment":
            records = await api.paged_list("employments/all", seen=0, next_n=50)
            node.content_records = records
            node.api_endpoint = "employments/all"
            node.request_payload = json.dumps(
                {"langType": 1, "DepartmentId": "", "seen": 0, "next": 50}
            )
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "message":
            records = await api._post("messages/allmessagesforwebsite", {"langType": 1})
            node.content_records = records if isinstance(records, list) else []
            node.api_endpoint = "messages/allmessagesforwebsite"
            node.request_payload = json.dumps({"langType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "implink":
            records = await api._post("implink/selectimplinksforwebsite", {"langType": 1})
            node.content_records = records if isinstance(records, list) else []
            node.api_endpoint = "implink/selectimplinksforwebsite"
            node.request_payload = json.dumps({"langType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "universitydoc":
            records = await api._post("universitydoc/selectforwebsite", {"langType": 1})
            node.content_records = records if isinstance(records, list) else []
            node.api_endpoint = "universitydoc/selectforwebsite"
            node.request_payload = json.dumps({"langType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "universityini":
            records = await api._post("universityinitiatives/selectinitforwebsite", {"langType": 1})
            node.content_records = records if isinstance(records, list) else []
            node.api_endpoint = "universityinitiatives/selectinitforwebsite"
            node.request_payload = json.dumps({"langType": 1})
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "upcoming-event":
            records = await api.paged_list(
                "event/getallupcomingeventsforwebsite", seen=0, next_n=50
            )
            node.content_records = records
            node.api_endpoint = "event/getallupcomingeventsforwebsite"
            node.request_payload = json.dumps(
                {"langType": 1, "DepartmentId": "", "seen": 0, "next": 50}
            )
            node.status = "fetched" if node.content_records else "empty"
            node.http_status = 200

        elif r == "school":
            # The school list is fetched separately; individual school pages
            # are represented by their departments in the school tree.
            # No additional API call is needed here.
            node.status = "fetched"
            node.http_status = 200
            node.api_endpoint = "school/schoolList"
            node.request_payload = "{}"

        elif r == "home":
            # The homepage has no structured content records to fetch here;
            # homepage widgets are handled via dedicated seed endpoints.
            node.status = "fetched"
            node.http_status = 200

        elif r in _UNMAPPED_ROUTES:
            # Route is known to exist but we have no API mapping for it yet.
            node.status = "unmapped_route"
            node.http_status = 0

        else:
            # Completely unknown route — treat the same as unmapped.
            node.status = "unmapped_route"
            node.http_status = 0

        # Extract any PDF links from content records into node.pdf_links
        if node.content_records:
            discovered_pdfs: list[dict] = list(node.pdf_links)
            seen_urls: set[str] = {
                p["url"] for p in discovered_pdfs if isinstance(p, dict) and "url" in p
            }
            for rec in node.content_records:
                if not isinstance(rec, dict):
                    continue
                # 1. HTML fields (e.g. DepartmentDescription, AdministrativeDescription)
                for html_key in (
                    "DepartmentDescription",
                    "Details",
                    "Content",
                    "LongDescription",
                    "AdministrativeDescription",
                ):
                    html = rec.get(html_key, "")
                    if html and isinstance(html, str) and "<" in html:
                        parsed = parse_html(html)
                        for lo in parsed.links_out:
                            if (
                                lo.type == "pdf"
                                and lo.href.startswith("http")
                                and lo.href not in seen_urls
                            ):
                                seen_urls.add(lo.href)
                                discovered_pdfs.append(
                                    {
                                        "url": lo.href,
                                        "text": lo.text or "",
                                        "found_on": node.angular_url,
                                    }
                                )
                # 2. Direct file URL fields in record
                for file_key in (
                    "FileUrl",
                    "HttpPath",
                    "FilePath",
                    "Url",
                    "ExternalUrl",
                    "ExternalLinkUrl",
                ):
                    f_url = str(rec.get(file_key, "") or "")
                    if (
                        f_url.startswith("http")
                        and _PDF_RE.search(f_url)
                        and f_url not in seen_urls
                    ):
                        seen_urls.add(f_url)
                        discovered_pdfs.append(
                            {
                                "url": f_url,
                                "text": str(rec.get("Title") or rec.get("Name") or ""),
                                "found_on": node.angular_url,
                            }
                        )
            node.pdf_links = discovered_pdfs

    except Exception as exc:
        logger.warning("Node fetch failed: %s %s — %s", r, node.id, exc)
        node.status = "failed"
        node.http_status = 0


async def build_node_table(
    settings: Settings,
    cached_client: CachedClient,
) -> list[SiteNode]:
    """Discover every Angular page on the CUK site and return a node table.

    This is the B1 phase of the ingestion pipeline.  It calls several
    seed APIs and walks their hierarchical responses to produce a flat list of
    ``SiteNode`` objects, one per unique Angular route.

    Exploration strategy
    --------------------
    **Seed 1 — Top nav tree**

    Fetches ``headercategory/headercategoryList`` which returns all navigation
    bar items in a flat list with parent-child links.  Each non-external item
    becomes a ``"departlist"`` node.  Breadcrumbs are reconstructed by
    following ``ParentHeaderCategoryMasterId`` links up the flat list.

    For every nav item the crawler also calls
    ``headercategory/headercategoryListById`` to discover sub-pages rendered
    as ``"administrative-list"`` Angular routes with a ``menuid`` parameter.
    These sub-pages are never present in the flat ``headercategoryList``
    response and would be silently missed without this second call.

    **Seed 2 — School tree (up to 4 levels deep)**

    ::

        schoolList
         └─ school  (level 0)
             └─ mappedDepartments
                 └─ department  (level 1)
                     └─ departmentMenus
                         └─ menu item  (level 2)
                             └─ [if SubChildCount > 0] departmentMenus
                                 └─ sub-menu item  (level 3)
                                     └─ [if SubChildCount > 0] departmentMenus
                                         └─ sub-sub-menu item  (level 4)

    * School nodes use ``route_name="school"``.
    * Department and menu nodes use ``route_name="departmentList"``.
    * The ``id`` field is **always** the root department's
      ``DepartmentMasterId`` at every depth; only ``menu_id`` changes.
      This keeps the Angular URL structure correct and prevents de-dup
      collisions between different departments that share menu-item IDs.

    **De-duplication**

    Every discovered node is registered in a ``visited`` set keyed on
    ``_node_key(route_name, id, menu_id)``.  If a later seed tries to add the
    same logical page, ``_add_node`` silently skips it.

    Args:
        settings:      Application settings supplying ``base_url``.
        cached_client: HTTP client with caching support; shared with the API
                       client to avoid redundant requests.

    Returns:
        A list of ``SiteNode`` objects in discovery order.  Every node has
        ``status="pending"`` except external/pdf nodes which are marked
        immediately.  Call ``fetch_all_nodes`` to populate content.
    """
    api = DirectApiClient(cached_client)
    base = settings.base_url
    nodes: list[SiteNode] = []
    # Tracks (route_name_lower, id_upper, menu_id_upper) for every node added
    # so far; prevents the same Angular route from being inserted twice even
    # when it is reachable from multiple seeds.
    visited: set[tuple[str, str, str]] = set()

    def _add_node(node: SiteNode) -> bool:
        """Register a node if it has not been seen before.

        Uses the ``visited`` set to guard against duplicate insertions.

        Args:
            node: The ``SiteNode`` candidate to add.

        Returns:
            ``True`` if the node was new and was added to ``nodes``.
            ``False`` if the node was already in the visited set (skipped).
        """
        key = _node_key(node.route_name, node.id, node.menu_id)
        if key in visited:
            return False
        visited.add(key)
        nodes.append(node)
        return True

    # ── Seed 1: Nav tree ────────────────────────────────────────────────────
    # Fetch the flat list of all header-category (nav-bar) items.
    # Each item can have an optional parent, forming an implicit tree.
    logger.info("Building nav-tree nodes …")
    nav_raw = await api.header_category_list()
    # Index by ID so we can look up ancestors in O(1) for breadcrumb building
    nav_by_id: dict[str, dict] = {n["HeaderCategoryMasterId"]: n for n in nav_raw}

    for item in nav_raw:
        # Skip external links — they point off-site and have no Angular route
        if _is_real_external(item):
            continue
        hid = item.get("HeaderCategoryMasterId", "")
        name = item.get("HeaderCategoryName", "")
        parent_id = item.get("ParentHeaderCategoryMasterId") or ""
        ext_url = str(item.get("ExternalLinkUrl") or item.get("ExternalUrl") or "").strip()
        parsed_route = _parse_angular_route(ext_url) if ext_url else None

        if parsed_route and parsed_route[0]:
            r_name, r_id, r_menu_id = parsed_route
            route_name = r_name
            target_id = r_id or hid
            target_menu_id = r_menu_id
        else:
            route_name = "departlist"
            target_id = hid
            target_menu_id = ""

        # Walk up the parent chain to build a breadcrumb list from root → item.
        # We prepend each ancestor label so the final list reads top-to-bottom.
        crumbs: list[str] = [name]
        cur = parent_id
        while cur and cur in nav_by_id:
            crumbs.insert(0, nav_by_id[cur].get("HeaderCategoryName", ""))
            cur = nav_by_id[cur].get("ParentHeaderCategoryMasterId") or ""

        # Compute the parent's node_id so the tree structure is preserved
        parent_node_id = _node_id("departlist", parent_id, "") if parent_id else ""

        nav_node_id = _node_id(route_name, target_id, target_menu_id)
        node = SiteNode(
            node_id=nav_node_id,
            route_name=route_name,
            id=target_id,
            menu_id=target_menu_id,
            parent_node_id=parent_node_id,
            breadcrumb=crumbs,
            school_master_id="",
            school_name="",
            department_master_id="",
            department_name="",
            source="nav-tree",
            status="pending",
            http_status=0,
            angular_url=_angular_url(base, route_name, target_id, target_menu_id),
            api_endpoint="",
            request_payload="",
        )
        _add_node(node)

        # FIX: Also fetch the sub-pages reachable under each nav item via the
        # headercategoryListById endpoint.  The Angular site renders these as
        # "administrative-list" pages with a menuid parameter, e.g.:
        #   /#/administrative-list;id=<hid>;menuid=<sub_hid>
        # Without this call those sub-pages are never discovered from Seed 1.
        sub_items = await api._post("headercategory/headercategoryListById", {"Id": hid})
        if isinstance(sub_items, list):
            for sub in sub_items:
                sub_hid = sub.get("HeaderCategoryMasterId", "")
                sub_name = sub.get("HeaderCategoryName", "")
                if not sub_hid or sub_hid == hid:
                    # Skip the item itself if the API echoes it back
                    continue
                if _is_real_external(sub):
                    continue
                sub_node = SiteNode(
                    node_id=_node_id("administrative-list", hid, sub_hid),
                    route_name="administrative-list",
                    id=hid,
                    menu_id=sub_hid,
                    parent_node_id=nav_node_id,
                    breadcrumb=crumbs + [sub_name],
                    school_master_id="",
                    school_name="",
                    department_master_id="",
                    department_name="",
                    source="nav-tree",
                    status="pending",
                    http_status=0,
                    angular_url=_angular_url(base, "administrative-list", hid, sub_hid),
                    api_endpoint="headercategory/headercategoryListById",
                    request_payload=json.dumps({"Id": sub_hid}),
                )
                _add_node(sub_node)

    # ── Seed 2: School tree ─────────────────────────────────────────────────
    # Walk the 3-level school → department → menu hierarchy.
    # This seed discovers department sub-pages that never appear in the nav tree.
    logger.info("Building school-tree nodes …")
    schools = await api.school_list()

    for school in schools:
        smid = school.get("SchoolMasterId", "")
        sname = school.get("SchoolName", "")

        # Level 0 — School root node (one per school)
        school_node_id = _node_id("school", smid, "")
        school_node = SiteNode(
            node_id=school_node_id,
            route_name="school",
            id=smid,
            menu_id="",
            parent_node_id="",
            breadcrumb=[sname],
            school_master_id=smid,
            school_name=sname,
            department_master_id="",
            department_name="",
            source="school-tree",
            status="pending",
            http_status=0,
            angular_url=_angular_url(base, "school", ""),
            api_endpoint="school/schoolList",
            request_payload="{}",
        )
        _add_node(school_node)

        # Level 1 — Departments mapped to this school
        departments = await api.mapped_departments(smid)

        for dept in departments:
            dmid = dept.get("DepartmentMasterId", "")
            dname = dept.get("DepartmentName", "")

            # Department root node — represents the department's landing page
            dept_node_id = _node_id("departmentList", dmid, "")
            dept_node = SiteNode(
                node_id=dept_node_id,
                route_name="departmentList",
                id=dmid,
                menu_id="",
                parent_node_id=school_node_id,
                breadcrumb=[sname, dname],
                school_master_id=smid,
                school_name=sname,
                department_master_id=dmid,
                department_name=dname,
                source="school-tree",
                status="pending",
                http_status=0,
                angular_url=_angular_url(base, "departmentList", dmid),
                api_endpoint="department/departmentListById",
                request_payload=json.dumps({"Id": dmid}),
            )
            _add_node(dept_node)

            # Level 2 — Department menu items (sub-pages within the department)
            # The API returns all menu items for the department, including the
            # department itself as an entry with ParentDepartmentMasterId=null.
            menu_items = await api.department_menu(dmid)

            # First item is the dept itself (ParentDepartmentMasterId null)
            # Subsequent items are the menu children
            for item in menu_items:
                item_dmid = item.get("DepartmentMasterId", "")
                item_name = item.get("DepartmentName", "")
                item_parent = item.get("ParentDepartmentMasterId")

                # Skip the root entry for the department itself — it is already
                # captured by dept_node above.
                if item_parent is None:
                    continue  # skip the dept root entry — it IS the dept node

                # External link menu items get their own node type only if they
                # have a real non-empty external URL.
                ext_url = str(item.get("ExternalLinkUrl", "") or "").strip()
                if item.get("IsExternalLink") and ext_url:
                    is_pdf_item = bool(_PDF_RE.search(ext_url))
                    ext_node = SiteNode(
                        node_id=_node_id("external", item_dmid, ""),
                        route_name="external",
                        id=item_dmid,
                        menu_id="",
                        parent_node_id=dept_node_id,
                        breadcrumb=[sname, dname, item_name],
                        school_master_id=smid,
                        school_name=sname,
                        department_master_id=dmid,
                        department_name=dname,
                        source="school-tree",
                        status="external",
                        http_status=0,
                        angular_url=ext_url,
                        api_endpoint="",
                        request_payload="",
                        pdf_links=[{"url": ext_url, "text": item_name, "found_on": ext_url}]
                        if is_pdf_item
                        else [],
                    )
                    _add_node(ext_node)
                    continue

                # Regular menu item — the Angular route uses the department's
                # dmid as the primary ID and item_dmid as the menu selector.
                item_angular_url = _angular_url(base, "departmentList", dmid, item_dmid)
                initial_records = [item] if item.get("DepartmentDescription") else []
                initial_pdfs = _extract_item_pdfs(
                    item.get("DepartmentDescription", ""), item_angular_url
                )

                menu_node = SiteNode(
                    node_id=_node_id("departmentList", dmid, item_dmid),
                    route_name="departmentList",
                    id=dmid,  # the parent department
                    menu_id=item_dmid,  # selects which sub-page to show
                    parent_node_id=dept_node_id,
                    breadcrumb=[sname, dname, item_name],
                    school_master_id=smid,
                    school_name=sname,
                    department_master_id=dmid,
                    department_name=dname,
                    source="school-tree",
                    status="pending",
                    http_status=0,
                    angular_url=item_angular_url,
                    api_endpoint="department/departmentListById",
                    request_payload=json.dumps({"Id": item_dmid}),
                    content_records=initial_records,
                    pdf_links=initial_pdfs,
                )
                _add_node(menu_node)

                # Level 3 — Recurse into sub-menu items if the menu item has
                # children (SubChildCount > 0).  This adds one more level of
                # depth without an unbounded recursion risk because the API
                # only reports one level of sub-children per call.
                #
                # FIX: Use a helper so this recursion can go deeper if the
                # sub-items themselves have SubChildCount > 0, and always keep
                # `id` anchored to the root department `dmid` (not item_dmid)
                # so the Angular URL and de-dup key stay correct.
                sub_count = item.get("SubChildCount", 0)
                if sub_count > 0:
                    sub_items = await api.department_menu(item_dmid)
                    for sub in sub_items:
                        sub_dmid = sub.get("DepartmentMasterId", "")
                        sub_name = sub.get("DepartmentName", "")
                        sub_parent = sub.get("ParentDepartmentMasterId")
                        # Skip the root entry of the sub-level (same logic as above)
                        if sub_parent is None:
                            continue

                        sub_ext_url = str(sub.get("ExternalLinkUrl", "") or "").strip()
                        if sub.get("IsExternalLink") and sub_ext_url:
                            sub_is_pdf = bool(_PDF_RE.search(sub_ext_url))
                            sub_ext_node = SiteNode(
                                node_id=_node_id("external", sub_dmid, ""),
                                route_name="external",
                                id=sub_dmid,
                                menu_id="",
                                parent_node_id=menu_node.node_id,
                                breadcrumb=[sname, dname, item_name, sub_name],
                                school_master_id=smid,
                                school_name=sname,
                                department_master_id=dmid,
                                department_name=dname,
                                source="school-tree",
                                status="external",
                                http_status=0,
                                angular_url=sub_ext_url,
                                api_endpoint="",
                                request_payload="",
                                pdf_links=[
                                    {
                                        "url": sub_ext_url,
                                        "text": sub_name,
                                        "found_on": sub_ext_url,
                                    }
                                ]
                                if sub_is_pdf
                                else [],
                            )
                            _add_node(sub_ext_node)
                            continue

                        sub_angular_url = _angular_url(base, "departmentList", dmid, sub_dmid)
                        sub_initial_records = [sub] if sub.get("DepartmentDescription") else []
                        sub_initial_pdfs = _extract_item_pdfs(
                            sub.get("DepartmentDescription", ""), sub_angular_url
                        )

                        sub_node = SiteNode(
                            node_id=_node_id("departmentList", dmid, sub_dmid),
                            route_name="departmentList",
                            id=dmid,  # root department — anchored, not drifted
                            menu_id=sub_dmid,  # the leaf sub-page selector
                            parent_node_id=menu_node.node_id,
                            breadcrumb=[sname, dname, item_name, sub_name],
                            school_master_id=smid,
                            school_name=sname,
                            department_master_id=dmid,
                            department_name=dname,
                            source="school-tree",
                            status="pending",
                            http_status=0,
                            angular_url=sub_angular_url,
                            api_endpoint="department/departmentListById",
                            request_payload=json.dumps({"Id": sub_dmid}),
                            content_records=sub_initial_records,
                            pdf_links=sub_initial_pdfs,
                        )
                        _add_node(sub_node)

                        # Level 4+ — if this sub-item also has children, keep
                        # going.  Uses the same id=dmid anchor throughout.
                        sub_sub_count = sub.get("SubChildCount", 0)
                        if sub_sub_count > 0:
                            sub_sub_items = await api.department_menu(sub_dmid)
                            for ssub in sub_sub_items:
                                ssub_dmid = ssub.get("DepartmentMasterId", "")
                                ssub_name = ssub.get("DepartmentName", "")
                                ssub_parent = ssub.get("ParentDepartmentMasterId")
                                if ssub_parent is None:
                                    continue

                                ssub_ext_url = str(ssub.get("ExternalLinkUrl", "") or "").strip()
                                if ssub.get("IsExternalLink") and ssub_ext_url:
                                    ssub_is_pdf = bool(_PDF_RE.search(ssub_ext_url))
                                    ssub_ext_node = SiteNode(
                                        node_id=_node_id("external", ssub_dmid, ""),
                                        route_name="external",
                                        id=ssub_dmid,
                                        menu_id="",
                                        parent_node_id=sub_node.node_id,
                                        breadcrumb=[
                                            sname,
                                            dname,
                                            item_name,
                                            sub_name,
                                            ssub_name,
                                        ],
                                        school_master_id=smid,
                                        school_name=sname,
                                        department_master_id=dmid,
                                        department_name=dname,
                                        source="school-tree",
                                        status="external",
                                        http_status=0,
                                        angular_url=ssub_ext_url,
                                        api_endpoint="",
                                        request_payload="",
                                        pdf_links=[
                                            {
                                                "url": ssub_ext_url,
                                                "text": ssub_name,
                                                "found_on": ssub_ext_url,
                                            }
                                        ]
                                        if ssub_is_pdf
                                        else [],
                                    )
                                    _add_node(ssub_ext_node)
                                    continue

                                ssub_angular_url = _angular_url(
                                    base, "departmentList", dmid, ssub_dmid
                                )
                                ssub_initial_records = (
                                    [ssub] if ssub.get("DepartmentDescription") else []
                                )
                                ssub_initial_pdfs = _extract_item_pdfs(
                                    ssub.get("DepartmentDescription", ""),
                                    ssub_angular_url,
                                )

                                ssub_node = SiteNode(
                                    node_id=_node_id("departmentList", dmid, ssub_dmid),
                                    route_name="departmentList",
                                    id=dmid,
                                    menu_id=ssub_dmid,
                                    parent_node_id=sub_node.node_id,
                                    breadcrumb=[
                                        sname,
                                        dname,
                                        item_name,
                                        sub_name,
                                        ssub_name,
                                    ],
                                    school_master_id=smid,
                                    school_name=sname,
                                    department_master_id=dmid,
                                    department_name=dname,
                                    source="school-tree",
                                    status="pending",
                                    http_status=0,
                                    angular_url=ssub_angular_url,
                                    api_endpoint="department/departmentListById",
                                    request_payload=json.dumps({"Id": ssub_dmid}),
                                    content_records=ssub_initial_records,
                                    pdf_links=ssub_initial_pdfs,
                                )
                                _add_node(ssub_node)

    logger.info("Node table seeded: %d nodes", len(nodes))
    return nodes


async def fetch_all_nodes(
    nodes: list[SiteNode],
    cached_client: CachedClient,
    settings: Settings,
) -> None:
    """Fetch content for every pending node (B2 phase), updating nodes in-place.

    Iterates the full node list, skipping any node whose status is not
    ``"pending"``, and calls ``_fetch_node_content`` for each remaining node.
    Progress is logged every 50 nodes.

    After this call each node's ``status``, ``http_status``, ``api_endpoint``,
    ``request_payload``, and ``content_records`` fields will be populated.

    Args:
        nodes:         The list returned by ``build_node_table``.  Modified
                       in-place.
        cached_client: HTTP client shared with the API layer.
        settings:      Application settings (passed through to ``DirectApiClient``
                       implicitly via ``cached_client``).

    Returns:
        None.
    """
    api = DirectApiClient(cached_client)
    # Only process nodes that are still awaiting a fetch
    pending = [n for n in nodes if n.status == "pending"]
    logger.info("Fetching content for %d pending nodes …", len(pending))

    for i, node in enumerate(pending):
        # Periodic progress log to surface long-running fetches
        if i % 50 == 0:
            logger.info("  node %d/%d …", i, len(pending))
        await _fetch_node_content(node, api)


def nodes_to_jsonl(nodes: list[SiteNode], out_path: Path) -> None:
    """Serialise the node table to a JSONL file, omitting large content blobs.

    Each line in the output file is a JSON object representing one node.
    ``content_records`` is intentionally excluded to keep the file lean;
    the full content is stored separately by the downstream pipeline stages.

    The parent directory is created automatically if it does not exist.

    Args:
        nodes:    The list of ``SiteNode`` objects to write.
        out_path: Destination file path (e.g. ``data/processed/nodes.jsonl``).

    Returns:
        None.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for node in nodes:
            # Serialise only the structural / metadata fields; skip content_records
            row = {
                "node_id": node.node_id,
                "route_name": node.route_name,
                "id": node.id,
                "menu_id": node.menu_id,
                "parent_node_id": node.parent_node_id,
                "breadcrumb": node.breadcrumb,
                "school_master_id": node.school_master_id,
                "school_name": node.school_name,
                "department_master_id": node.department_master_id,
                "department_name": node.department_name,
                "source": node.source,
                "status": node.status,
                "http_status": node.http_status,
                "angular_url": node.angular_url,
                "api_endpoint": node.api_endpoint,
                "request_payload": node.request_payload,
                "pdf_links": node.pdf_links,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("Wrote %d nodes to %s", len(nodes), out_path)

    # Ensure synchronization between data/raw/nodes.jsonl and data/processed/nodes.jsonl
    alt_path = None
    if "processed" in out_path.parts:
        alt_path = Path(*[p if p != "processed" else "raw" for p in out_path.parts])
    elif "raw" in out_path.parts:
        alt_path = Path(*[p if p != "raw" else "processed" for p in out_path.parts])
    if alt_path and alt_path != out_path:
        try:
            alt_path.parent.mkdir(parents=True, exist_ok=True)
            alt_path.write_bytes(out_path.read_bytes())
        except Exception:
            pass
