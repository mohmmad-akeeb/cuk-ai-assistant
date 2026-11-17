"""Unit tests for TwoTierReconciler and metadata harmonization."""

from __future__ import annotations

import hashlib
from typing import Any

from cuk_assistant.core.protocols.ingestion import ReconcilerProtocol
from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.ingestion.normalize.reconciler import TwoTierReconciler
from cuk_assistant.schemas.metadata import (
    AdmissionDocMetadata,
    FacultyDocMetadata,
    GeneralDocMetadata,
    NoticeDocMetadata,
    OrdinanceDocMetadata,
    ResultDocMetadata,
    SyllabusDocMetadata,
    TenderDocMetadata,
)


class MockTelemetrySink(TelemetrySinkProtocol):
    """Telemetry sink mock for tracking reconciliation failures and diagnostics."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.feedbacks: list[dict[str, Any]] = []

    def log_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        self.spans.append({"name": name, "attributes": attributes, "duration_ms": duration_ms})

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        self.failures.append(
            {"trace_id": trace_id, "diagnostic_code": diagnostic_code, "details": details}
        )

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        self.feedbacks.append(
            {
                "trace_id": trace_id,
                "score": score,
                "feedback_category": feedback_category,
                "comment": comment,
            }
        )


class TestTwoTierReconcilerBasics:
    """Basic reconciliation, protocol conformance, and determinism tests."""

    def test_protocol_conformance(self) -> None:
        reconciler = TwoTierReconciler()
        assert isinstance(reconciler, ReconcilerProtocol)

    def test_reconciliation_tier1_only(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "General Advisory on Campus Timings",
            "source_url": "https://cukashmir.ac.in/docs/advisory.pdf",
            "page_url": "https://cukashmir.ac.in/#/notices",
            "school_name": "School of Engineering & Technology",
            "school_master_id": "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}",
            "department_name": "Department of Computer Science & Engineering",
            "department_id": "{11223344-5566-7788-99AA-BBCCDDEEFF00}",
            "node_path": ["Academics", "Engineering", "CSE"],
            "published_on": "15-11-2024",
            "session": "2024-25",
        }
        meta = reconciler.reconcile(tier1_record=t1)
        assert isinstance(meta, (GeneralDocMetadata, NoticeDocMetadata))
        assert meta.school == "School of Engineering & Technology"
        assert meta.school_master_id == "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        assert meta.department == "Department of Computer Science & Engineering"
        assert meta.department_master_id == "11223344-5566-7788-99AA-BBCCDDEEFF00"
        assert meta.node_path == ["Academics", "Engineering", "CSE"]
        assert meta.published_date == "2024-11-15"
        assert meta.academic_year == "2024-2025"
        assert len(meta.doc_id) == 16

    def test_deterministic_doc_id_and_content_hash(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Deterministic Test Document",
            "source_url": "https://cukashmir.ac.in/test.pdf",
            "page_url": "https://cukashmir.ac.in/#/test",
        }
        text = "Sample body text for computing hash."
        expected_hash = hashlib.sha256(text.encode()).hexdigest()
        expected_id = hashlib.sha256(
            f"{t1['source_url']}::{t1['page_url']}::{t1['title']}".encode()
        ).hexdigest()[:16]

        meta = reconciler.reconcile(tier1_record=t1, raw_text=text)
        assert meta.content_hash == expected_hash
        assert meta.doc_id == expected_id

    def test_attribution_precedence(self) -> None:
        """Verify Tier 1 wins for hierarchy, Tier 2 wins for internal facts."""
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "CUK Circular",
            "source_url": "https://cukashmir.ac.in/t1.pdf",
            "page_url": "https://cukashmir.ac.in/#/t1",
            "school": "Tier 1 School",
            "department": "Tier 1 Dept",
            "published_on": "2020-01-01",  # Web CMS date
            "academic_year": "2020-2021",
        }
        t2 = {
            "school": "Tier 2 Ignored School",
            "department": "Tier 2 Ignored Dept",
            "published_date": "2024-05-10",  # PDF header true gazette date
            "academic_year": "2023-2024",
            "reference_number": "CUK/Acad/2024/001",
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        # Web provenance retains Tier 1
        assert meta.school == "Tier 1 School"
        assert meta.department == "Tier 1 Dept"
        # Intrinsic facts adopt Tier 2
        assert meta.published_date == "2024-05-10"
        assert meta.academic_year == "2023-2024"


class TestPolymorphicDomainRouting:
    """Test resolution and schema validation for all 7 polymorphic domains."""

    def test_route_syllabus_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "B.Tech Computer Science Syllabus Semester 4",
            "source_url": "https://cukashmir.ac.in/syllabus/btech_cse_s4.pdf",
            "page_url": "https://cukashmir.ac.in/#/departmentList;id=123",
            "content_type": "syllabus_or_curriculum",
            "school": "School of Engineering & Technology",
            "department": "Department of Computer Science & Engineering",
        }
        t2 = {
            "program": "B.Tech CSE",
            "batch_year": "2022",
            "semester": "Semester 4",
            "course_code": "BT-CSE-402",
            "course_title": "Database Management Systems",
            "credits": 4,
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, SyllabusDocMetadata)
        assert meta.doc_type == "syllabus"
        assert meta.program == "B.Tech CSE"
        assert meta.batch_year == "2022"
        assert meta.semester == "Semester 4"
        assert meta.course_code == "BT-CSE-402"
        assert meta.credits == 4

    def test_route_syllabus_with_raw_text_backfill(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Curriculum Document",
            "source_url": "https://cukashmir.ac.in/syllabus/curriculum.pdf",
            "page_url": "https://cukashmir.ac.in/#/syllabus",
            "department": "Department of Mathematics",
        }
        raw_text = """
        CENTRAL UNIVERSITY OF KASHMIR
        Programme: M.Sc Mathematics
        Batch: 2023
        Sem-III Course Outline
        Course Code: MTH-301
        Credits: 4
        """
        meta = reconciler.reconcile(tier1_record=t1, raw_text=raw_text)
        assert isinstance(meta, SyllabusDocMetadata)
        assert meta.doc_type == "syllabus"
        assert meta.batch_year == "2023"
        assert meta.semester == "Semester 3"
        assert meta.course_code == "MTH-301"

    def test_route_result_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Result Gazette for B.Tech Semester 6",
            "source_url": "https://cukashmir.ac.in/results/res_2024.pdf",
            "page_url": "https://cukashmir.ac.in/#/examination/results",
            "content_type": "exam_result",
        }
        t2 = {
            "exam_session": "Autumn 2024",
            "notification_number": "Result Notification No. 2428",
            "result_type": "regular",
            "program": "B.Tech CSE",
            "declaration_date": "2024-09-12",
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, ResultDocMetadata)
        assert meta.doc_type == "result"
        assert meta.notification_number == "Result Notification No. 2428"
        assert meta.exam_session == "Autumn 2024"
        assert meta.result_type == "regular"
        assert meta.declaration_date == "2024-09-12"

    def test_route_tender_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Supply and Installation of Lab Equipment",
            "source_url": "https://cukashmir.ac.in/tenders/tender_04.pdf",
            "page_url": "https://cukashmir.ac.in/#/tenders",
        }
        raw_text = """
        CENTRAL UNIVERSITY OF KASHMIR
        NIT No. 04 of 2026
        Dated: 10-01-2026
        Closing Date: 30-01-2026
        EMD: Rs. 50,000
        """
        meta = reconciler.reconcile(tier1_record=t1, raw_text=raw_text)
        assert isinstance(meta, TenderDocMetadata)
        assert meta.doc_type == "tender"
        assert (
            "NIT No 04 of 2026" in meta.tender_number or "NIT No. 04 of 2026" in meta.tender_number
        )
        assert meta.nit_date == "2026-01-10"

    def test_route_admission_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Provisional Selection List for MCA Admission 2024",
            "source_url": "https://cukashmir.ac.in/admissions/mca_sel.pdf",
            "page_url": "https://cukashmir.ac.in/#/admissions",
        }
        t2 = {
            "admission_year": "2024",
            "program": "MCA",
            "stage": "selection_list",
            "intake_capacity": 40,
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, AdmissionDocMetadata)
        assert meta.doc_type == "admission"
        assert meta.admission_year == "2024"
        assert meta.program == "MCA"
        assert meta.stage == "selection_list"
        assert meta.intake_capacity == 40

    def test_route_notice_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Office Order regarding Winter Vacation",
            "source_url": "https://cukashmir.ac.in/notices/winter_vac.pdf",
            "page_url": "https://cukashmir.ac.in/#/notices",
            "content_type": "notice",
        }
        raw_text = """
        OFFICE OF THE REGISTRAR
        CUK/Admn/Notice/2024/88
        Dated: 20-12-2024
        It is hereby notified that university will observe winter break...
        """
        meta = reconciler.reconcile(tier1_record=t1, raw_text=raw_text)
        assert isinstance(meta, NoticeDocMetadata)
        assert meta.doc_type == "notice"
        assert meta.reference_number == "CUK/Admn/Notice/2024/88"
        assert meta.published_date == "2024-12-20"

    def test_route_ordinance_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Statute Governing the Board of Studies",
            "source_url": "https://cukashmir.ac.in/ordinances/bos_statute.pdf",
            "page_url": "https://cukashmir.ac.in/#/ordinances",
        }
        t2 = {
            "subject": "Statute 14: Powers and Functions of Board of Studies",
            "ordinance_number": "Statute 14",
            "governing_body": "Executive Council",
            "effective_date": "2021-06-01",
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, OrdinanceDocMetadata)
        assert meta.doc_type == "ordinance"
        assert meta.subject == "Statute 14: Powers and Functions of Board of Studies"
        assert meta.governing_body == "Executive Council"

    def test_route_faculty_metadata(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Profile of Dr. John Doe",
            "source_url": "https://cukashmir.ac.in/faculty/john_doe",
            "page_url": "https://cukashmir.ac.in/#/facultyList",
            "content_type": "faculty_profile",
        }
        t2 = {
            "employee_name": "Dr. John Doe",
            "designation": "Associate Professor",
            "email": "johndoe@cukashmir.ac.in",
            "qualifications": ["Ph.D in AI", "M.Tech CSE"],
            "research_areas": ["Natural Language Processing", "Information Retrieval"],
        }
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, FacultyDocMetadata)
        assert meta.doc_type == "faculty"
        assert meta.employee_name == "Dr. John Doe"
        assert meta.designation == "Associate Professor"
        assert "Information Retrieval" in meta.research_areas


class TestUniversalIngestionGuarantee:
    """Test FR-1.5: 100% universal ingestion without dropping or crashing on malformed input."""

    def test_fallback_on_unclassified_document(self) -> None:
        reconciler = TwoTierReconciler()
        t1 = {
            "title": "Miscellaneous Guidelines for Green Campus",
            "source_url": "https://cukashmir.ac.in/general/green.pdf",
            "page_url": "https://cukashmir.ac.in/#/about",
        }
        meta = reconciler.reconcile(tier1_record=t1)
        assert isinstance(meta, GeneralDocMetadata)
        assert meta.doc_type == "general"
        assert meta.title == "Miscellaneous Guidelines for Green Campus"

    def test_fallback_on_malformed_partial_syllabus(self) -> None:
        """A document hinting at syllabus but lacking required fields must fall back to GeneralDocMetadata."""
        sink = MockTelemetrySink()
        reconciler = TwoTierReconciler(telemetry_sink=sink)
        t1 = {
            "title": "Some partial curriculum announcement",
            "source_url": "https://cukashmir.ac.in/syllabus/partial.pdf",
            "page_url": "https://cukashmir.ac.in/#/syllabus",
            "doc_type": "syllabus",
        }
        # Missing required program, batch_year, semester
        t2 = {"credits": 4}
        meta = reconciler.reconcile(tier1_record=t1, tier2_facts=t2)
        assert isinstance(meta, GeneralDocMetadata)
        assert meta.doc_type == "general"

    def test_fallback_on_empty_record(self) -> None:
        """Completely empty record should not crash and return valid GeneralDocMetadata."""
        reconciler = TwoTierReconciler()
        meta = reconciler.reconcile(tier1_record={})
        assert isinstance(meta, GeneralDocMetadata)
        assert meta.doc_type == "general"
        assert meta.title == "Untitled Document"
        assert meta.normalized_title == "untitled document"
        assert meta.source_url == "https://cukashmir.ac.in/"
        assert len(meta.doc_id) == 16
        assert len(meta.content_hash) == 64
