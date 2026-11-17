"""Rich metadata builder for every content type served by cukapi.disgenweb.in.

Every document fed into the RAG pipeline gets a metadata dict with these fields:

  doc_id               — deterministic SHA-256 of (endpoint + record_key + chunk_key)
                         chunk_key is "" for non-chunked docs, "p{page}" for PDF pages
  source_url           — the canonical URL of the content (PDF URL or API URL)
  page_url             — the Angular page URL that surfaces this content
  content_type         — one of: notice | employment | result | admission | tender |
                         exam_datesheet | exam_result | university_doc | event |
                         initiative | video | what_new | student_zone | policy |
                         imp_link | additional_card | how_to_reach | promotion |
                         message | department_page | faculty | generic
  section              — top-level nav label (e.g. "Academics", "Administration")
  subsection           — sub-nav label (e.g. "Examinations > Controller")
  department_id        — raw DepartmentId GUID from API (empty string if absent)
  department_name      — resolved department name
  title                — human-readable title of the item
  description          — short description / summary from API
  published_on         — ISO-8601 date string (UTC) when the item was published
  created_on           — ISO-8601 date string (UTC) when the item was created
  visible_from         — first date the item is visible
  visible_to           — last date the item is visible
  file_url             — direct URL to attached PDF / file (empty if none)
  file_name            — filename part of file_url
  external_url         — external URL linked from the item
  is_pdf               — bool: True if file_url ends in .pdf
  is_sensitive         — bool: True if content is a personal-data document
  lang                 — 1 = English (default), 2 = Urdu
  record_id            — the RecordId / GUID from API
  raw_api_endpoint     — the API endpoint this came from
  scraped_at           — ISO-8601 UTC timestamp of when we scraped this
  text_format          — "markdown" | "plain"
  content_hash         — SHA-256 of the text field (hex, 24 chars)

  # Provenance additions (B7)
  school_master_id     — SchoolMasterId GUID
  school_name          — human name of the school
  department_master_id — DepartmentMasterId GUID (different from DepartmentId)
  menu_id              — DepartmentMasterId of the clicked menu item
  route_name           — Angular route name (departmentList | departlist | …)
  node_path            — breadcrumb as list of strings
  parent_node_id       — node_id of the parent in the node table
  api_endpoint         — canonical API endpoint called
  request_payload      — JSON string of the POST body sent
  found_on_page        — angular URL of the page where this PDF was discovered
  links_out            — list of {text, href, type} dicts from HTML content

  # Faculty-specific
  faculty_dept_id_sent — DepartmentId sent in the request payload
  department_id_matches_page — bool: row DeptId == sent DeptId
  faculty_dept_mismatch — bool: True when above is False

  # PDF-specific
  pdf_pages            — total page count
  pdf_text_pages       — pages with extractable text
  pdf_scanned_pages    — pages without text (likely scanned)
  pdf_table_count      — number of tables found
  pdf_embedded_date    — date extracted from PDF metadata
  pdf_size_bytes       — size of downloaded file
  pdf_title            — title from PDF metadata
  skipped_reason       — reason for skipping (e.g. "too_large")
  page_number          — 1-indexed page number (None for whole-doc chunks)
  chunk_index          — 0-indexed chunk number
  needs_ocr            — True if any scanned pages exist
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_RE = re.compile(
    # Narrow: only personal-data lists (roll numbers, selections, merit/provisional)
    # Ordinary result *notification* PDFs are NOT sensitive.
    r"selection[\s_\-]?list"
    r"|merit[\s_\-]?list"
    r"|provisional[\s_\-]?list"
    r"|waiting[\s_\-]?list"
    r"|waitlist"
    r"|roll[\s_\-]?number[\s_\-]?list"
    r"|\benrollment\s+list\b",
    re.IGNORECASE,
)

_PDF_RE = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)

_NOW_ISO = datetime.now(tz=UTC).isoformat()

# Maps API endpoint prefix → content_type label
_ENDPOINT_TYPE_MAP = {
    "noticeboard": "notice",
    "employments": "employment",
    "admission": "admission",
    "tender": "tender",
    "examinationresult": "exam_result",
    "scholarresults": "exam_result",
    "examdatesheet": "exam_datesheet",
    "examnotification": "notice",
    "itandservices": "notice",
    "universitydoc": "university_doc",
    "event": "event",
    "eventgallerymanage": "event_gallery",
    "universityinitiatives": "initiative",
    "videogallery": "video",
    "whatnew": "what_new",
    "studentzone": "student_zone",
    "policy": "policy",
    "implink": "imp_link",
    "publichomequicklinks": "university_doc",
    "additionalcard": "additional_card",
    "howtoreachcuk": "how_to_reach",
    "promotions": "promotion",
    "messages": "message",
    "banner": "banner",
    "headercategory": "navigation",
    "mediagallery": "media_gallery",
    "department": "department_page",
    "faculty": "faculty",
    "school": "school",
    "administrative": "administration",
}


def _doc_id(endpoint: str, record_key: str, chunk_key: str = "") -> str:
    """Deterministic doc_id stable across runs.

    For PDF pages, chunk_key = "p{page_number}" so each page gets a unique id.
    For non-chunked docs, chunk_key = "".
    Existing ids (endpoint + record_key, chunk_key="") remain unchanged.
    """
    raw = f"{endpoint}::{record_key}::{chunk_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _normalize_title(title: str) -> str:
    """Normalize title: lowercase, clean ASCII stripped of .pdf and collapsed whitespace."""
    if not title:
        return ""
    s = re.sub(r"\.pdf(\?.*)?$", "", title, flags=re.IGNORECASE)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _format_date(val: Any) -> str | None:
    """Format any date-like string or timestamp into ISO-8601 YYYY-MM-DD."""
    if not val:
        return None
    s = str(val).strip()
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        year, month, day = m.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def _extract_academic_year(*texts: str) -> str | None:
    r"""Extract academic session / year via regex r'\b20\d{2}(?:-\d{2,4})?\b'."""
    for t in texts:
        if not t:
            continue
        m = re.search(r"\b(20\d{2}(?:-\d{2,4})?)\b", t)
        if m:
            return m.group(1)
    return None


def _resolve_canonical_doc_type(endpoint: str, title: str, breadcrumb: list[str]) -> str:
    """Map endpoint and context to canonical discriminators:
    syllabus, result, admission, ordinance, notice, tender, faculty, general_official_document.
    """
    ep = endpoint.lower()
    t = title.lower()
    b_text = " ".join(b.lower() for b in breadcrumb)

    if "tender" in ep or "tender" in t or re.search(r"\bnit\b", t):
        return "tender"
    if "admission" in ep or "admission" in t:
        return "admission"
    if "faculty" in ep or "employeeprofile" in ep:
        return "faculty"
    if "examinationresult" in ep or "scholarresults" in ep or ("result" in ep and "exam" in ep):
        return "result"
    if "result" in t and ("notification" in t or "sem" in t or "exam" in t):
        return "result"
    if "syllabus" in t or "syllabus" in b_text or "curriculum" in t:
        return "syllabus"
    if "ordinance" in t or "ordinance" in ep or "statute" in t or "statute" in ep:
        return "ordinance"
    if any(
        k in ep
        for k in (
            "notice",
            "whatnew",
            "pressrelease",
            "moe",
            "examnotification",
            "itandservices",
            "datesheet",
            "event",
        )
    ):
        return "notice"
    if "notice" in t:
        return "notice"
    return "general_official_document"


def _resolve_audience(doc_type: str, endpoint: str, section: str) -> str:
    """Resolve target audience: students, faculty, staff, public."""
    if doc_type in ("syllabus", "result", "admission") or "student" in endpoint.lower():
        return "students"
    if doc_type == "faculty":
        return "faculty"
    if "employment" in endpoint.lower() or doc_type == "tender":
        return "public"
    if any(
        k in endpoint.lower() for k in ("press", "moe", "event", "howtoreach", "quicklink", "card")
    ):
        return "public"
    if "administration" in section.lower() or "administrative" in endpoint.lower():
        return "staff"
    return "students"


def _build_page_url(
    page_url: str,
    route_name: str,
    record_id: str,
    department_master_id: str,
    menu_id: str,
) -> str:
    """Build deterministic Angular SPA front-end URL (https://www.cukashmir.ac.in/#/<route>;id=...;menuid=...)."""
    if (
        page_url
        and page_url.strip()
        not in (
            "",
            "https://cukashmir.ac.in",
            "https://www.cukashmir.ac.in",
            "https://cukashmir.ac.in/",
            "https://www.cukashmir.ac.in/",
        )
        and "#/" in page_url
    ):
        return page_url.strip()

    base_prefix = "https://www.cukashmir.ac.in/#"
    r = route_name or "listing"

    target_id = menu_id or department_master_id or (record_id if r != "listing" else "")
    if target_id and menu_id and menu_id != target_id:
        return f"{base_prefix}/{r};id={target_id};menuid={menu_id}"
    elif target_id:
        return f"{base_prefix}/{r};id={target_id}"
    else:
        return f"{base_prefix}/{r}"


def _iso(val: Any) -> str:
    if not val:
        return ""
    s = str(val).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:19] + "Z" if "T" in s else s
    return s


def _file_url_permissive(record: dict) -> str:
    for key in ("FileUrl", "HttpPath", "FilePath", "Url", "ExternalUrl", "ExternalLinkUrl"):
        v = str(record.get(key, "") or "").strip()
        if v.startswith("http"):
            if key in ("ExternalUrl", "ExternalLinkUrl"):
                if _PDF_RE.search(v):
                    return v
            else:
                return v
    return ""


def _resolve_content_type(endpoint: str, record: dict) -> str:
    for prefix, ct in _ENDPOINT_TYPE_MAP.items():
        if endpoint.startswith(prefix):
            return ct
    ct_field = record.get("ContentType", "")
    if ct_field:
        return ct_field.lower().replace(" ", "_")
    return "generic"


def build_metadata(
    endpoint: str,
    record: dict,
    *,
    section: str = "",
    subsection: str = "",
    page_url: str = "",
    department_name: str = "",
    index: int = 0,
    # B7 provenance
    school_master_id: str = "",
    school_name: str = "",
    department_master_id: str = "",
    menu_id: str = "",
    route_name: str = "",
    node_path: list[str] | None = None,
    parent_node_id: str = "",
    request_payload: str = "",
    found_on_page: str = "",
    links_out: list[dict] | None = None,
    # Faculty
    faculty_dept_id_sent: str = "",
    # Cache / HTTP headers
    etag: str | None = None,
    last_modified: str | None = None,
) -> dict:
    """Build the standard metadata dict for one API record conforming to UniversalDocMetadata."""
    record_id = str(
        record.get("RecordId")
        or record.get("Id")
        or record.get("RowId")
        or record.get("HeaderCategoryMasterId")
        or record.get("StudentZoneMasterId")
        or record.get("VideoId")
        or record.get("MessageId")
        or record.get("HowToReachCukId")
        or record.get("PromotionsId")
        or record.get("UniversitydocId")
        or record.get("AdditionalCardId")
        or record.get("DepartmentMasterId")
        or index
    )

    file_url = _file_url_permissive(record)
    file_name = file_url.split("/")[-1].split("?")[0] if file_url else ""
    external_url = record.get("ExternalUrl", "") or record.get("ExternalLinkUrl", "")
    if external_url and not str(external_url).startswith("http"):
        external_url = ""

    # In implink endpoints, the target portal URL is often stored in Description
    if endpoint.startswith("implink") and not external_url and not file_url:
        desc_candidate = str(record.get("Description", "") or "").strip()
        if desc_candidate.startswith(("http://", "https://", "/#/", "#/")):
            external_url = desc_candidate

    title = str(
        record.get("Title")
        or record.get("Name")
        or record.get("HeaderCategoryName")
        or record.get("StudentZoneName")
        or record.get("HeadTitle")
        or record.get("DepartmentName")
        or record.get("DepartmentTitle")
        or record.get("SchoolName")
        or record.get("Result_title")
        or ""
    ).strip()

    description = str(
        record.get("Description")
        or record.get("Descrition")  # API typo
        or record.get("ShortDescription")
        or record.get("StudentZoneDescription")
        or record.get("SubTitle")
        or record.get("Result_Description")
        or ""
    ).strip()

    is_pdf = bool(file_url and _PDF_RE.search(file_url))
    is_sensitive = bool(
        _SENSITIVE_RE.search(title)
        or _SENSITIVE_RE.search(file_name)
        or _SENSITIVE_RE.search(description)
    )

    # Faculty: row DeptId vs sent DeptId
    row_dept_id = str(record.get("DepartmentId", "") or "")
    faculty_mismatch = False
    dept_id_matches = True
    if faculty_dept_id_sent:
        dept_id_matches = row_dept_id.upper() == faculty_dept_id_sent.upper()
        faculty_mismatch = not dept_id_matches

    # Determine effective department_id
    dept_id = row_dept_id or str(record.get("DepartmentId", "") or "")

    # UniversalDocMetadata canonical fields
    canonical_doc_type = _resolve_canonical_doc_type(endpoint, title, node_path or [])
    canonical_page_url = _build_page_url(
        page_url, route_name, record_id, department_master_id, menu_id
    )
    canonical_published_date = _format_date(
        record.get("PublishedOn")
        or record.get("ApprovedOn")
        or record.get("UploadDate")
        or record.get("CreatedOn")
        or record.get("StartDate")
    )
    canonical_academic_year = _extract_academic_year(title, description, *(node_path or []))
    lang_val = int(record.get("LangType") or 1)
    canonical_language = "ur" if lang_val == 2 else "en"
    is_univ_wide = bool(not dept_id or str(dept_id).strip() == "")
    canonical_audience = _resolve_audience(canonical_doc_type, endpoint, section)
    etag_val = record.get("etag") or record.get("ETag") or etag
    last_mod_val = record.get("last_modified") or record.get("Last-Modified") or last_modified

    # Polymorphic domain hints
    tender_number = str(record.get("TenderNo") or record.get("RefId") or "").strip()
    if not tender_number and canonical_doc_type == "tender":
        t_m = re.search(
            r"(?:NIT|Tender|Bid)\s*(?:No\.?|Notice)\s*[:\-]?\s*([A-Za-z0-9\/\-_]+)",
            title,
            re.IGNORECASE,
        )
        if t_m:
            tender_number = t_m.group(1)
    nit_date = _format_date(
        record.get("StartDate") or record.get("PublishedOn") or record.get("UploadDate")
    )
    closing_date = _format_date(record.get("EndDate") or record.get("VisibleToDate"))
    emd_amount = str(record.get("EmdAmount") or "").strip() or None

    session_match = re.search(
        r"\b(Autumn|Spring|July|December|Dec|Winter|May|June|November|Nov)\s*(20\d{2})\b",
        title,
        re.IGNORECASE,
    )
    exam_session = (
        f"{session_match.group(1).capitalize()} {session_match.group(2)}" if session_match else None
    )
    notif_match = re.search(
        r"(?:Result\s+)?Notification\s+No\.?\s*([0-9A-Za-z\-_/]+)", title, re.IGNORECASE
    )
    notification_number = notif_match.group(1) if notif_match else None
    if re.search(r"re[- ]?evaluation", title, re.IGNORECASE):
        result_type = "re_evaluation"
    elif re.search(r"backlog", title, re.IGNORECASE):
        result_type = "backlog"
    elif re.search(r"provisional", title, re.IGNORECASE):
        result_type = "provisional"
    else:
        result_type = "regular"
    declaration_date = _format_date(record.get("UploadDate") or record.get("PublishedOn"))

    expiry_date = _format_date(record.get("VisibleToDate"))
    issuing_office = department_name or section or "Central Administration"
    is_urgent = bool(re.search(r"\b(urgent|priority|immediate)\b", title, re.IGNORECASE))
    subject_tags = [section] if section else ["General Notice"]

    designation = str(record.get("Designation") or "").strip() or (
        "Faculty Member" if canonical_doc_type == "faculty" else None
    )
    email = str(record.get("EmailId") or "").strip() or None
    qualifications = str(record.get("Qualifications") or "").strip() or None
    research_areas = [
        r.strip() for r in str(record.get("ResearchAreas") or "").split(",") if r.strip()
    ]

    batch_match = re.search(r"\b(?:Batch|Admitted)\s*[-:]?\s*(\d{4})\b", title, re.IGNORECASE)
    batch_year = int(batch_match.group(1)) if batch_match else None
    sem_match = re.search(r"\bSem(?:ester)?\s*([IVX\d]+)\b", title, re.IGNORECASE)
    semester = f"Semester {sem_match.group(1)}" if sem_match else None

    admission_year = int(canonical_academic_year[:4]) if canonical_academic_year else None
    if re.search(r"selection[\s_\-]?list|merit[\s_\-]?list", title, re.IGNORECASE):
        admission_stage = "merit_list"
    elif re.search(r"cut[\s_\-]?off|points", title, re.IGNORECASE):
        admission_stage = "cut_off"
    elif re.search(r"counsel(?:l)?ing", title, re.IGNORECASE):
        admission_stage = "counseling"
    elif re.search(r"seat[\s_\-]?matrix|intake", title, re.IGNORECASE):
        admission_stage = "seat_matrix"
    else:
        admission_stage = "guidelines"

    return {
        # UniversalDocMetadata canonical fields
        "doc_id": _doc_id(endpoint, record_id),
        "doc_type": canonical_doc_type,
        "title": title,
        "normalized_title": _normalize_title(title),
        "source_url": file_url or str(external_url) or canonical_page_url,
        "page_url": canonical_page_url,
        "school": school_name or None,
        "school_master_id": school_master_id or None,
        "department": department_name or None,
        "department_master_id": department_master_id or None,
        "node_path": node_path or [],
        "published_date": canonical_published_date,
        "academic_year": canonical_academic_year,
        "language": canonical_language,
        "is_university_wide": is_univ_wide,
        "audience": canonical_audience,
        "is_sensitive": is_sensitive,
        "content_hash": "",  # filled by caller after text is built
        "etag": etag_val,
        "last_modified": last_mod_val,
        # Polymorphic Domain Hints
        "tender_number": tender_number or None,
        "nit_date": nit_date,
        "closing_date": closing_date,
        "emd_amount": emd_amount,
        "exam_session": exam_session,
        "notification_number": notification_number,
        "result_type": result_type,
        "declaration_date": declaration_date,
        "expiry_date": expiry_date,
        "issuing_office": issuing_office,
        "subject_tags": subject_tags,
        "is_urgent": is_urgent,
        "designation": designation,
        "email": email,
        "qualifications": qualifications,
        "research_areas": research_areas,
        "program": department_name or None,
        "batch_year": batch_year,
        "semester": semester,
        "admission_year": admission_year,
        "stage": admission_stage,
        # Backwards-compatibility fields
        "content_type": _resolve_content_type(endpoint, record),
        "section": section,
        "subsection": subsection,
        "department_id": dept_id,
        "department_name": department_name,
        "description": description,
        "published_on": _iso(record.get("PublishedOn") or record.get("ApprovedOn") or ""),
        "created_on": _iso(record.get("CreatedOn") or record.get("CreatedDate") or ""),
        "visible_from": _iso(record.get("VisibleFromDate") or record.get("StartDate") or ""),
        "visible_to": _iso(record.get("VisibleToDate") or record.get("EndDate") or ""),
        "file_url": file_url,
        "file_name": file_name,
        "external_url": str(external_url),
        "is_pdf": is_pdf,
        "lang": lang_val,
        "record_id": record_id,
        "raw_api_endpoint": endpoint,
        "scraped_at": _NOW_ISO,
        "text_format": "markdown",
        "school_name": school_name,
        "menu_id": menu_id,
        "route_name": route_name,
        "parent_node_id": parent_node_id,
        "api_endpoint": endpoint,
        "request_payload": request_payload,
        "found_on_page": found_on_page,
        "links_out": links_out or [],
        "faculty_dept_id_sent": faculty_dept_id_sent,
        "department_id_matches_page": dept_id_matches,
        "faculty_dept_mismatch": faculty_mismatch,
    }
