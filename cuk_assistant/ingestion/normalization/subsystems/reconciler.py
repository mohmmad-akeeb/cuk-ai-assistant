"""Two-Tier Metadata Reconciliation Engine and Harmonizer.

Reconciles Tier 1 (Web Provenance) and Tier 2 (Document Intrinsic Facts) into
validated UniversalDocMetadata and polymorphic domain models.
Guarantees 100% universal ingestion (FR-1.5) by falling back to GeneralDocMetadata
on ambiguous or unparseable input with zero dropped records.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from pydantic import ValidationError

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.ingestion.normalization.subsystems.metadata_normalizer import (
    clean_guid,
    extract_batch_year,
    extract_circular_reference,
    extract_course_code,
    normalize_academic_year,
    normalize_iso_date,
    normalize_semester,
    normalize_title,
)
from cuk_assistant.schemas.metadata import (
    DocumentMetadataUnion,
    parse_document_metadata,
)

logger = logging.getLogger(__name__)

# Allowed fields per model to prevent extra="forbid" validation errors
_BASE_FIELDS = {
    "doc_id",
    "doc_type",
    "title",
    "normalized_title",
    "source_url",
    "page_url",
    "school",
    "school_master_id",
    "department",
    "department_master_id",
    "node_path",
    "published_date",
    "academic_year",
    "language",
    "is_university_wide",
    "audience",
    "is_sensitive",
    "content_hash",
    "etag",
    "last_modified",
    "scraped_at",
}

_DOMAIN_SPECIFIC_FIELDS: dict[str, set[str]] = {
    "general": set(),
    "syllabus": {"program", "batch_year", "semester", "course_code", "course_title", "credits"},
    "result": {"exam_session", "notification_number", "result_type", "program", "declaration_date"},
    "admission": {"admission_year", "program", "stage", "intake_capacity"},
    "notice": {"reference_number", "issuing_office", "is_urgent", "expiry_date"},
    "tender": {"tender_number", "nit_date", "closing_date", "emd_amount"},
    "ordinance": {"ordinance_number", "subject", "governing_body", "effective_date"},
    "faculty": {"employee_name", "designation", "email", "qualifications", "research_areas"},
}

# Regex patterns for heuristic domain classification
_SYLLABUS_RE = re.compile(
    r"\b(syllabus|curricul(?:um|a)|course\s+structure|scheme\s+of\s+(?:study|examination)|course\s+outline)\b",
    re.IGNORECASE,
)
_RESULT_RE = re.compile(
    r"\b(result\s+notification|examination\s+result|gazette\s+notification|statement\s+of\s+marks|marks\s+list|provisional\s+result)\b",
    re.IGNORECASE,
)
_TENDER_RE = re.compile(
    r"\b(tender|nit\s*(?:no\.?)?|e-tender|notice\s+inviting\s+tender|request\s+for\s+proposal|rfp)\b",
    re.IGNORECASE,
)
_ADMISSION_RE = re.compile(
    r"\b(cut[\s\-_]*off|merit\s+list|selection\s+list|counselling|admission\s+notification|counseling)\b",
    re.IGNORECASE,
)
_NOTICE_RE = re.compile(
    r"\b(circular|notice|office\s+order|notification|advisory|public\s+notice)\b",
    re.IGNORECASE,
)
_ORDINANCE_RE = re.compile(
    r"\b(ordinance|statute|regulation|act\b|executive\s+council\s+resolution)\b",
    re.IGNORECASE,
)
_FACULTY_RE = re.compile(
    r"\b(faculty\s+profile|assistant\s+professor|associate\s+professor|professor\b|dean\b|hod\b|head\s+of\s+department)\b",
    re.IGNORECASE,
)
_PROGRAM_RE = re.compile(
    r"\b(B\.?\s*Tech(?:\s+[A-Za-z &]+)?|M\.?\s*Tech(?:\s+[A-Za-z &]+)?|MCA|MBA|M\.?\s*Sc(?:\s+[A-Za-z &]+)?|M\.?\s*A(?:\s+[A-Za-z &]+)?|Integrated\s+[A-Za-z\-]+|LL\.?\s*M|B\.?\s*A\s+LL\.?\s*B|B\.?\s*Ed|M\.?\s*Ed|Ph\.?\s*D)\b",
    re.IGNORECASE,
)


class TwoTierReconciler:
    """Two-Tier Metadata Reconciliation Engine.

    Harmonizes Tier 1 (Web Provenance) and Tier 2 (Document Intrinsic Facts),
    dynamically backfills missing attributes, routes into 7 polymorphic domains,
    and guarantees safe fallback to GeneralDocMetadata (FR-1.5).
    """

    def __init__(
        self,
        telemetry_sink: TelemetrySinkProtocol | None = None,
    ) -> None:
        self.telemetry_sink = telemetry_sink

    def reconcile(
        self,
        tier1_record: dict[str, Any],
        tier2_facts: dict[str, Any] | None = None,
        raw_text: str | None = None,
    ) -> DocumentMetadataUnion:
        """Reconcile raw web crawl data and document extraction facts into a typed metadata model.

        Args:
            tier1_record: Web crawler provenance dictionary (school, dept, URLs, routing).
            tier2_facts: Intrinsic document facts parsed from document content or PDF.
            raw_text: Clean extracted document text/markdown for heuristic backfilling.

        Returns:
            Validated polymorphic DocumentMetadata model.
        """
        t1 = dict(tier1_record)
        t2 = dict(tier2_facts) if tier2_facts else {}
        text = raw_text.strip() if raw_text else ""

        # 1. Base Core Identifiers & Attribution
        title = self._resolve_title(t1, t2)
        norm_title = normalize_title(title)

        source_url = str(
            t1.get("source_url")
            or t1.get("file_url")
            or t1.get("url")
            or t2.get("source_url")
            or "https://cukashmir.ac.in/"
        )
        page_url = str(t1.get("page_url") or t1.get("url") or t2.get("page_url") or source_url)

        content_hash = self._resolve_content_hash(t1, t2, text, title)
        doc_id = self._resolve_doc_id(t1, t2, source_url, page_url, title)

        # 2. Tier 1 Web Provenance (Precedence for organizational hierarchy)
        school = str(t1.get("school") or t1.get("school_name") or t2.get("school") or "").strip()
        school_master_id = clean_guid(
            t1.get("school_master_id") or t2.get("school_master_id") or ""
        )
        department = str(
            t1.get("department") or t1.get("department_name") or t2.get("department") or ""
        ).strip()
        department_master_id = clean_guid(
            t1.get("department_master_id")
            or t1.get("department_id")
            or t2.get("department_master_id")
            or ""
        )

        node_path = t1.get("node_path") or t2.get("node_path") or []
        if isinstance(node_path, (list, tuple)):
            clean_node_path = [str(x).strip() for x in node_path if str(x).strip()]
        else:
            clean_node_path = [str(node_path).strip()] if str(node_path).strip() else []

        language = str(t1.get("language") or t2.get("language") or "en").strip()
        is_university_wide = bool(t1.get("is_university_wide", t2.get("is_university_wide", False)))
        audience = str(t1.get("audience") or t2.get("audience") or "general").strip()
        is_sensitive = bool(t1.get("is_sensitive", t2.get("is_sensitive", False)))
        etag = t1.get("etag") or t2.get("etag")
        last_modified = t1.get("last_modified") or t2.get("last_modified")

        # 3. Tier 2 Intrinsic Temporal & Reference Identifiers (Tier 2 precedence, with dynamic backfill)
        published_date = self._resolve_published_date(t1, t2, text, title)
        academic_year = self._resolve_academic_year(t1, t2, text, title)
        circular_ref = self._resolve_circular_reference(t1, t2, text, title)

        # Build baseline record dictionary
        base_payload: dict[str, Any] = {
            "doc_id": doc_id,
            "title": title,
            "normalized_title": norm_title,
            "source_url": source_url,
            "page_url": page_url,
            "school": school,
            "school_master_id": school_master_id,
            "department": department,
            "department_master_id": department_master_id,
            "node_path": clean_node_path,
            "published_date": published_date,
            "academic_year": academic_year,
            "language": language,
            "is_university_wide": is_university_wide,
            "audience": audience,
            "is_sensitive": is_sensitive,
            "content_hash": content_hash,
            "etag": etag,
            "last_modified": last_modified,
        }

        # 4. Polymorphic Domain Classification & Field Harvesting
        candidate_domain, domain_fields = self._classify_and_harvest(
            t1=t1,
            t2=t2,
            text=text,
            title=title,
            circular_ref=circular_ref,
            academic_year=academic_year,
            published_date=published_date,
            department=department,
            source_url=source_url,
            page_url=page_url,
            node_path=clean_node_path,
        )

        # 5. Model Validation & Universal Fallback Guarantee (FR-1.5)
        return self._instantiate_model(candidate_domain, base_payload, domain_fields)

    def _resolve_title(self, t1: dict[str, Any], t2: dict[str, Any]) -> str:
        raw_title = t1.get("title") or t2.get("title")
        if raw_title and str(raw_title).strip():
            return str(raw_title).strip()
        return "Untitled Document"

    def _resolve_content_hash(
        self, t1: dict[str, Any], t2: dict[str, Any], text: str, title: str
    ) -> str:
        if t1.get("content_hash"):
            return str(t1["content_hash"]).strip()
        if t2.get("content_hash"):
            return str(t2["content_hash"]).strip()
        if text:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()
        return hashlib.sha256(title.encode("utf-8")).hexdigest()

    def _resolve_doc_id(
        self,
        t1: dict[str, Any],
        t2: dict[str, Any],
        source_url: str,
        page_url: str,
        title: str,
    ) -> str:
        if t1.get("doc_id"):
            return str(t1["doc_id"]).strip()
        if t2.get("doc_id"):
            return str(t2["doc_id"]).strip()
        composite = f"{source_url}::{page_url}::{title}"
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()[:16]

    def _resolve_published_date(
        self, t1: dict[str, Any], t2: dict[str, Any], text: str, title: str
    ) -> str | None:
        # Tier 2 has precedence
        t2_date = t2.get("published_date") or t2.get("declaration_date") or t2.get("nit_date")
        if t2_date:
            norm = normalize_iso_date(str(t2_date))
            if norm:
                return norm

        # Tier 1 CMS attributes
        t1_date = t1.get("published_on") or t1.get("created_on") or t1.get("published_date")
        if t1_date:
            norm = normalize_iso_date(str(t1_date))
            if norm:
                return norm

        # Deep text extraction
        if title:
            norm = normalize_iso_date(title)
            if norm:
                return norm

        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    norm = normalize_iso_date(line_clean)
                    if norm:
                        return norm
            norm = normalize_iso_date(text[:3000])
            if norm:
                return norm

        return None

    def _resolve_academic_year(
        self, t1: dict[str, Any], t2: dict[str, Any], text: str, title: str
    ) -> str | None:
        # Tier 2 has precedence
        t2_ay = t2.get("academic_year") or t2.get("exam_session") or t2.get("session")
        if t2_ay:
            norm = normalize_academic_year(str(t2_ay))
            if norm:
                return norm

        # Tier 1 CMS attributes
        t1_ay = t1.get("academic_year") or t1.get("session")
        if t1_ay:
            norm = normalize_academic_year(str(t1_ay))
            if norm:
                return norm

        # Deep text extraction
        if title:
            norm = normalize_academic_year(title)
            if norm:
                return norm

        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    norm = normalize_academic_year(line_clean)
                    if norm:
                        return norm
            norm = normalize_academic_year(text[:3000])
            if norm:
                return norm

        return None

    def _resolve_circular_reference(
        self, t1: dict[str, Any], t2: dict[str, Any], text: str, title: str
    ) -> str | None:
        # Tier 2 has precedence
        t2_ref = (
            t2.get("reference_number")
            or t2.get("circular_reference")
            or t2.get("notification_number")
            or t2.get("tender_number")
            or t2.get("ordinance_number")
        )
        if t2_ref:
            cleaned = str(t2_ref).strip()
            if cleaned:
                return cleaned

        # Deep text extraction
        if title:
            extracted = extract_circular_reference(title)
            if extracted:
                return extracted

        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    extracted = extract_circular_reference(line_clean)
                    if extracted:
                        return extracted
            extracted = extract_circular_reference(text[:3000])
            if extracted:
                return extracted

        # Tier 1 fallback
        t1_ref = t1.get("reference_number") or t1.get("circular_reference")
        if t1_ref:
            return str(t1_ref).strip()

        return None

    def _extract_semester_from_content(self, text: str, title: str) -> str | None:
        if title:
            s = normalize_semester(title)
            if s:
                return s
        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    s = normalize_semester(line_clean)
                    if s:
                        return s
            return normalize_semester(text[:2000])
        return None

    def _extract_batch_year_from_content(self, text: str, title: str) -> str | None:
        if title:
            b = extract_batch_year(title)
            if b:
                return b
        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    b = extract_batch_year(line_clean)
                    if b:
                        return b
            return extract_batch_year(text[:2000])
        return None

    def _extract_course_code_from_content(self, text: str, title: str) -> str | None:
        if title:
            c = extract_course_code(title)
            if c:
                return c
        if text:
            for line in text.splitlines()[:50]:
                line_clean = line.strip()
                if line_clean:
                    c = extract_course_code(line_clean)
                    if c:
                        return c
            return extract_course_code(text[:2000])
        return None

    def _classify_and_harvest(
        self,
        t1: dict[str, Any],
        t2: dict[str, Any],
        text: str,
        title: str,
        circular_ref: str | None,
        academic_year: str | None,
        published_date: str | None,
        department: str,
        source_url: str,
        page_url: str,
        node_path: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Identify target domain and harvest required attributes."""
        # 1. Candidate hint from explicit type or route
        type_hint = (
            (t2.get("doc_type") or t1.get("doc_type") or t1.get("content_type") or "")
            .lower()
            .strip()
        )
        route_context = f"{source_url} {page_url} {' '.join(node_path)}".lower()
        combined_text = f"{title} {text[:3000]}".lower()

        # Check in order of specificity

        # --- A. Syllabus ---
        if (
            type_hint in ("syllabus", "syllabus_or_curriculum", "curriculum")
            or "/syllabus" in route_context
            or "/curriculum" in route_context
            or _SYLLABUS_RE.search(combined_text)
        ):
            program = (
                t2.get("program")
                or t1.get("program")
                or self._extract_program(title, text)
                or department
            )
            batch_year = (
                t2.get("batch_year")
                or self._extract_batch_year_from_content(text, title)
                or (academic_year.split("-")[0] if academic_year else None)
            )
            semester = t2.get("semester") or self._extract_semester_from_content(text, title)
            course_code = t2.get("course_code") or self._extract_course_code_from_content(
                text, title
            )
            course_title = t2.get("course_title")
            credits_val = t2.get("credits")

            if program and batch_year and semester:
                return "syllabus", {
                    "program": str(program).strip(),
                    "batch_year": str(batch_year).strip(),
                    "semester": str(semester).strip(),
                    "course_code": course_code,
                    "course_title": course_title,
                    "credits": credits_val,
                }

        # --- B. Result ---
        if (
            type_hint in ("result", "exam_result", "examination_result")
            or "/result" in route_context
            or "/examination" in route_context
            or _RESULT_RE.search(combined_text)
        ):
            notif_no = t2.get("notification_number") or circular_ref
            exam_session = (
                t2.get("exam_session")
                or t2.get("session")
                or academic_year
                or normalize_academic_year(text)
                or normalize_academic_year(title)
            )
            result_type = t2.get("result_type") or self._detect_result_type(combined_text)
            program = (
                t2.get("program")
                or t1.get("program")
                or self._extract_program(title, text)
                or department
            )
            decl_date = t2.get("declaration_date") or published_date

            if notif_no and exam_session and result_type and program:
                return "result", {
                    "notification_number": str(notif_no).strip(),
                    "exam_session": str(exam_session).strip(),
                    "result_type": str(result_type).strip(),
                    "program": str(program).strip(),
                    "declaration_date": decl_date,
                }

        # --- C. Tender ---
        if (
            type_hint in ("tender", "tender_notice", "nit")
            or "/tender" in route_context
            or "/procurement" in route_context
            or _TENDER_RE.search(combined_text)
        ):
            tender_num = t2.get("tender_number") or circular_ref
            nit_date = t2.get("nit_date") or published_date
            closing_date = t2.get("closing_date")
            emd_amount = t2.get("emd_amount")

            if tender_num:
                return "tender", {
                    "tender_number": str(tender_num).strip(),
                    "nit_date": nit_date,
                    "closing_date": closing_date,
                    "emd_amount": emd_amount,
                }

        # --- D. Admission ---
        if (
            type_hint in ("admission", "merit_list", "selection_list")
            or "/admission" in route_context
            or "/merit" in route_context
            or _ADMISSION_RE.search(combined_text)
        ):
            adm_year = (
                t2.get("admission_year")
                or self._extract_batch_year_from_content(text, title)
                or (academic_year.split("-")[0] if academic_year else None)
            )
            program = (
                t2.get("program")
                or t1.get("program")
                or self._extract_program(title, text)
                or department
            )
            stage = t2.get("stage") or self._detect_admission_stage(combined_text)
            intake_capacity = t2.get("intake_capacity")

            if adm_year and program:
                return "admission", {
                    "admission_year": str(adm_year).strip(),
                    "program": str(program).strip(),
                    "stage": stage,
                    "intake_capacity": intake_capacity,
                }

        # --- E. Faculty ---
        if (
            type_hint in ("faculty", "faculty_profile")
            or "/faculty" in route_context
            or "/profile" in route_context
            or _FACULTY_RE.search(combined_text)
        ):
            emp_name = t2.get("employee_name") or t1.get("employee_name") or t1.get("name")
            designation = t2.get("designation") or t1.get("designation")
            email = t2.get("email") or t1.get("email")
            qualifications = t2.get("qualifications", [])
            research_areas = t2.get("research_areas", [])

            if emp_name and designation:
                return "faculty", {
                    "employee_name": str(emp_name).strip(),
                    "designation": str(designation).strip(),
                    "email": email,
                    "qualifications": qualifications,
                    "research_areas": research_areas,
                }

        # --- F. Ordinance ---
        if (
            type_hint in ("ordinance", "statute", "regulation", "act")
            or "/ordinance" in route_context
            or "/statute" in route_context
            or _ORDINANCE_RE.search(combined_text)
        ):
            subject = t2.get("subject") or title
            ord_number = t2.get("ordinance_number") or circular_ref
            governing_body = t2.get("governing_body")
            effective_date = t2.get("effective_date") or published_date

            if subject:
                return "ordinance", {
                    "subject": str(subject).strip(),
                    "ordinance_number": ord_number,
                    "governing_body": governing_body,
                    "effective_date": effective_date,
                }

        # --- G. Notice ---
        if (
            type_hint in ("notice", "circular", "order", "notification")
            or "/notice" in route_context
            or "/circular" in route_context
            or "/order" in route_context
            or _NOTICE_RE.search(combined_text)
        ):
            issuing_office = t2.get("issuing_office") or department or None
            is_urgent = bool(t2.get("is_urgent", False)) or ("urgent" in combined_text)
            expiry_date = t2.get("expiry_date")

            return "notice", {
                "reference_number": circular_ref,
                "issuing_office": issuing_office,
                "is_urgent": is_urgent,
                "expiry_date": expiry_date,
            }

        # Fallback to general domain
        return "general", {}

    def _extract_program(self, title: str, text: str) -> str | None:
        m = _PROGRAM_RE.search(title)
        if m:
            return m.group(1).strip()
        if text:
            m = _PROGRAM_RE.search(text[:2000])
            if m:
                return m.group(1).strip()
        return None

    def _detect_result_type(self, text: str) -> str:
        if "re-evaluation" in text or "re_evaluation" in text or "re evaluation" in text:
            return "re_evaluation"
        if "backlog" in text:
            return "backlog"
        if "provisional" in text:
            return "provisional"
        return "regular"

    def _detect_admission_stage(self, text: str) -> str:
        if "cut_off" in text or "cut-off" in text or "cut off" in text:
            return "cut_off"
        if "selection" in text or "merit" in text:
            return "selection_list"
        if "counselling" in text or "counseling" in text:
            return "counselling"
        return "general"

    def _instantiate_model(
        self,
        domain: str,
        base_payload: dict[str, Any],
        domain_fields: dict[str, Any],
    ) -> DocumentMetadataUnion:
        """Validate candidate payload with strict field scoping and safe general fallback."""
        payload = dict(base_payload)
        payload["doc_type"] = domain

        allowed = _BASE_FIELDS | _DOMAIN_SPECIFIC_FIELDS.get(domain, set())
        for k, v in domain_fields.items():
            if k in allowed:
                payload[k] = v

        clean_payload = {k: v for k, v in payload.items() if k in allowed}

        try:
            return parse_document_metadata(clean_payload)
        except (ValidationError, Exception) as exc:
            logger.warning(
                "Domain validation failed for domain '%s' (doc_id=%s): %s. Falling back to GeneralDocMetadata (FR-1.5).",
                domain,
                base_payload.get("doc_id"),
                exc,
            )
            if self.telemetry_sink:
                self.telemetry_sink.tag_failure(
                    trace_id=str(base_payload.get("doc_id")),
                    diagnostic_code=FailureDiagnosticCode.PARSING_DEFECT,
                    details={
                        "failed_domain": domain,
                        "error": str(exc),
                        "fallback": "general",
                    },
                )

            # Guaranteed fallback to GeneralDocMetadata
            general_payload = {k: v for k, v in base_payload.items() if k in _BASE_FIELDS}
            general_payload["doc_type"] = "general"
            return parse_document_metadata(general_payload)
