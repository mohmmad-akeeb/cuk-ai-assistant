"""Core Pydantic v2 metadata schemas with polymorphic discrimination.

Pure Pydantic v2 schemas: Zero database, vendor, or crawler imports.
Guarantees immutability (frozen=True) and strict field boundaries (extra="forbid").
Conforms to CUK-SPEC-META-002, database_schema.md, and FR-1.5 universal ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Base Schema: UniversalDocMetadata
# ---------------------------------------------------------------------------


class UniversalDocMetadata(BaseModel):
    """Universal Base Document Schema.

    Guarantees that every scraped web route or parsed document satisfies an
    immutable contract with zero field leakage (extra="forbid", frozen=True).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Core Identifiers
    doc_id: str = Field(
        ...,
        description="Deterministic SHA-256 hash or composite key",
    )
    doc_type: str = Field(
        default="general",
        description="Document type discriminator (e.g. syllabus, result, admission, notice, tender, ordinance, faculty, general)",
    )
    title: str = Field(
        ...,
        description="Document or page title",
    )
    normalized_title: str = Field(
        ...,
        description="Normalized lowercase title stripped of file extensions and noise",
    )
    source_url: str = Field(
        ...,
        description="Canonical source URL or direct download route",
    )
    page_url: str = Field(
        ...,
        description="Angular SPA front-end URL where document was discovered",
    )

    # University Hierarchy & Provenance
    school: str = Field(
        default="",
        description="Academic school name (e.g. School of Engineering & Technology)",
    )
    school_master_id: str = Field(
        default="",
        description="CMS SchoolMasterId GUID",
    )
    department: str = Field(
        default="",
        description="Academic department name (e.g. Department of Computer Science & Engineering)",
    )
    department_master_id: str = Field(
        default="",
        description="CMS DepartmentMasterId GUID",
    )
    node_path: list[str] = Field(
        default_factory=list,
        description="Hierarchical breadcrumb list from navigation tree",
    )

    # Temporal & Versioning Facts
    published_date: str | None = Field(
        default=None,
        description="ISO-8601 UTC date string (YYYY-MM-DD)",
    )
    academic_year: str | None = Field(
        default=None,
        description="Academic session or calendar year (e.g. 2023-2024)",
    )
    language: str = Field(
        default="en",
        description="Document language code (e.g. en, ur, hi)",
    )

    # Scope & Audience
    is_university_wide: bool = Field(
        default=False,
        description="True for central administrative circulars affecting all departments",
    )
    audience: str = Field(
        default="general",
        description="Target readership: students, faculty, staff, public, general",
    )

    # Security & Integrity
    is_sensitive: bool = Field(
        default=False,
        description="True if document contains sensitive personal information (PII guardrail)",
    )
    content_hash: str = Field(
        ...,
        description="SHA-256 hash of extracted clean markdown/text content",
    )
    etag: str | None = Field(
        default=None,
        description="HTTP ETag header captured during web ingestion",
    )
    last_modified: str | None = Field(
        default=None,
        description="HTTP Last-Modified header captured during web ingestion",
    )
    scraped_at: str = Field(
        default_factory=_utc_now_iso,
        description="ISO-8601 UTC timestamp of when this item was ingested",
    )

    @field_validator(
        "school", "school_master_id", "department", "department_master_id", mode="before"
    )
    @classmethod
    def _coerce_str_empty_on_none(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("node_path", mode="before")
    @classmethod
    def _coerce_node_path(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
        return [str(v)]


# ---------------------------------------------------------------------------
# Polymorphic Domain Schemas
# ---------------------------------------------------------------------------


class SyllabusDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for syllabi, curricula, and course outlines."""

    doc_type: Literal["syllabus"] = "syllabus"
    program: str = Field(..., description="Canonical degree program name")
    batch_year: str = Field(..., description="Batch or regulation cohort year")
    semester: str = Field(..., description="Target semester designation (e.g. Semester 3)")
    course_code: str | None = Field(
        default=None, description="Course identifier code (e.g. BT-101)"
    )
    course_title: str | None = Field(default=None, description="Official subject title")
    credits: int | None = Field(default=None, description="Credit rating for course")

    @field_validator("batch_year", mode="before")
    @classmethod
    def _coerce_batch_year(cls, v: Any) -> str:
        if v is None:
            raise ValueError("batch_year cannot be None")
        return str(v).strip()

    @field_validator("credits", mode="before")
    @classmethod
    def _coerce_credits(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            return int(float(v.strip()))
        return int(v)


class ResultDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for examination results and gazettes."""

    doc_type: Literal["result"] = "result"
    exam_session: str = Field(
        ..., description="Examination session term and year (e.g. Autumn 2024)"
    )
    notification_number: str = Field(..., description="Exam office notification ID")
    result_type: str = Field(
        ...,
        description="Examination result classification (regular, re_evaluation, backlog, provisional)",
    )
    program: str = Field(..., description="Program examined")
    declaration_date: str | None = Field(
        default=None, description="Formal declaration date (YYYY-MM-DD)"
    )

    @field_validator("notification_number", mode="before")
    @classmethod
    def _coerce_notif_str(cls, v: Any) -> str:
        if v is None:
            raise ValueError("notification_number cannot be None")
        return str(v).strip()


class AdmissionDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for merit lists, cut-offs, and admission notifications."""

    doc_type: Literal["admission"] = "admission"
    admission_year: str = Field(..., description="Academic intake session year (e.g. 2024)")
    program: str = Field(..., description="Program admitting candidates")
    stage: str = Field(
        default="general",
        description="Admission workflow stage (cut_off, selection_list, counselling, general)",
    )
    intake_capacity: int | None = Field(default=None, description="Total approved intake seats")

    @field_validator("admission_year", mode="before")
    @classmethod
    def _coerce_admission_year(cls, v: Any) -> str:
        if v is None:
            raise ValueError("admission_year cannot be None")
        return str(v).strip()

    @field_validator("intake_capacity", mode="before")
    @classmethod
    def _coerce_intake(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            return int(float(v.strip()))
        return int(v)


class NoticeDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for administrative notices, executive orders, and circulars."""

    doc_type: Literal["notice"] = "notice"
    reference_number: str | None = Field(
        default=None,
        description="Official circular or notification reference string",
    )
    issuing_office: str | None = Field(
        default=None,
        description="Administrative issuing office or section",
    )
    is_urgent: bool = Field(
        default=False,
        description="True for urgent or high-priority administrative circulars",
    )
    expiry_date: str | None = Field(
        default=None,
        description="Actionable expiry date (YYYY-MM-DD)",
    )


class TenderDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for tenders, RFPs, and procurement notices."""

    doc_type: Literal["tender"] = "tender"
    tender_number: str = Field(..., description="Official tender or NIT reference number")
    nit_date: str | None = Field(
        default=None, description="Notice Inviting Tender issue date (YYYY-MM-DD)"
    )
    closing_date: str | None = Field(default=None, description="Bid submission closing timestamp")
    emd_amount: str | None = Field(default=None, description="Earnest Money Deposit specified")

    @field_validator("tender_number", mode="before")
    @classmethod
    def _coerce_tender_number(cls, v: Any) -> str:
        if v is None:
            raise ValueError("tender_number cannot be None")
        return str(v).strip()


class OrdinanceDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for statutory ordinances, executive acts, and regulations."""

    doc_type: Literal["ordinance"] = "ordinance"
    ordinance_number: str | None = Field(default=None, description="Statutory ordinance identifier")
    subject: str = Field(..., description="Ordinance subject or title")
    governing_body: str | None = Field(default=None, description="Statutory enacting authority")
    effective_date: str | None = Field(default=None, description="Effective date or enactment year")


class FacultyDocMetadata(UniversalDocMetadata):
    """Polymorphic metadata schema for faculty directory profiles and designations."""

    doc_type: Literal["faculty"] = "faculty"
    employee_name: str = Field(..., description="Full employee name")
    designation: str = Field(..., description="Academic rank or administrative post")
    email: str | None = Field(default=None, description="Sanitized institutional email address")
    qualifications: list[str] = Field(
        default_factory=list,
        description="Degrees and educational qualifications",
    )
    research_areas: list[str] = Field(
        default_factory=list,
        description="Sanitized research interests and areas",
    )

    @field_validator("qualifications", "research_areas", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return [str(v)]


class GeneralDocMetadata(UniversalDocMetadata):
    """General official document metadata schema.

    Serves as the deterministic fallback ensuring the FR-1.5 Universal
    Ingestion Guarantee for any document that does not match a domain.
    """

    doc_type: Literal["general"] = "general"


# ---------------------------------------------------------------------------
# Discriminated Union & Helper
# ---------------------------------------------------------------------------

DocumentMetadataUnion = Annotated[
    SyllabusDocMetadata
    | ResultDocMetadata
    | AdmissionDocMetadata
    | NoticeDocMetadata
    | TenderDocMetadata
    | OrdinanceDocMetadata
    | FacultyDocMetadata
    | GeneralDocMetadata,
    Field(discriminator="doc_type"),
]

_DOC_METADATA_ADAPTER: TypeAdapter[DocumentMetadataUnion] = TypeAdapter(DocumentMetadataUnion)


def parse_document_metadata(data: dict[str, Any]) -> DocumentMetadataUnion:
    """Parse a dictionary into the appropriate polymorphic DocumentMetadata model.

    If doc_type is missing or matches general alias conventions
    ('general_official_document', 'generic'), it safely defaults to 'general'
    to satisfy the FR-1.5 Universal Ingestion Guarantee.
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data).__name__}")

    payload = dict(data)
    doc_type = payload.get("doc_type")
    if not doc_type or doc_type in ("general_official_document", "generic"):
        payload["doc_type"] = "general"

    return _DOC_METADATA_ADAPTER.validate_python(payload)
