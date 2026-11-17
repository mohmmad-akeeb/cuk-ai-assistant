"""Unit tests for CUK RAG Assistant Pydantic v2 metadata schemas.

Verifies:
- Round-trip serialization and deserialization across all schemas
- Strict field boundaries (extra="forbid")
- Immutability guarantees (frozen=True)
- Polymorphic discrimination and FR-1.5 universal fallback
"""

import pytest
from pydantic import ValidationError

from cuk_assistant.schemas.metadata import (
    AdmissionDocMetadata,
    FacultyDocMetadata,
    GeneralDocMetadata,
    NoticeDocMetadata,
    OrdinanceDocMetadata,
    ResultDocMetadata,
    SyllabusDocMetadata,
    TenderDocMetadata,
    UniversalDocMetadata,
    parse_document_metadata,
)


@pytest.fixture
def base_metadata_payload() -> dict:
    return {
        "doc_id": "sha256_universal_test_001",
        "doc_type": "general",
        "title": "Central University Notification",
        "normalized_title": "central university notification",
        "source_url": "https://cukashmir.ac.in/docs/notice.pdf",
        "page_url": "https://www.cukashmir.ac.in/#/notices",
        "school": "School of Engineering & Technology",
        "school_master_id": "SCH_ENG_001",
        "department": "Department of Computer Science & Engineering",
        "department_master_id": "DEPT_CSE_001",
        "node_path": ["Home", "Academics", "Engineering", "CSE"],
        "published_date": "2024-11-15",
        "academic_year": "2024-2025",
        "language": "en",
        "is_university_wide": False,
        "audience": "students",
        "is_sensitive": False,
        "content_hash": "sha256_clean_content_hash_123",
        "etag": 'W/"12345"',
        "last_modified": "Fri, 15 Nov 2024 10:00:00 GMT",
    }


class TestUniversalDocMetadata:
    def test_instantiation_and_serialization(self, base_metadata_payload: dict) -> None:
        doc = UniversalDocMetadata(**base_metadata_payload)
        assert doc.doc_id == "sha256_universal_test_001"
        assert doc.doc_type == "general"
        assert doc.school == "School of Engineering & Technology"
        assert doc.scraped_at is not None

        dumped = doc.model_dump()
        assert dumped["doc_id"] == doc.doc_id
        assert dumped["normalized_title"] == "central university notification"

    def test_extra_field_forbidden(self, base_metadata_payload: dict) -> None:
        payload = {**base_metadata_payload, "unexpected_field": "leak"}
        with pytest.raises(ValidationError) as exc_info:
            UniversalDocMetadata(**payload)
        assert "Extra inputs are not permitted" in str(exc_info.value)

    def test_immutability_frozen(self, base_metadata_payload: dict) -> None:
        doc = UniversalDocMetadata(**base_metadata_payload)
        with pytest.raises(ValidationError):
            doc.title = "New Mutated Title"

    def test_default_coercion_on_none(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "school": None,
            "school_master_id": None,
            "department": None,
            "department_master_id": None,
            "node_path": None,
        }
        doc = UniversalDocMetadata(**payload)
        assert doc.school == ""
        assert doc.school_master_id == ""
        assert doc.department == ""
        assert doc.department_master_id == ""
        assert doc.node_path == []


class TestSyllabusDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "syllabus",
            "program": "B.Tech Computer Science & Engineering",
            "batch_year": "2022",
            "semester": "Semester 4",
            "course_code": "BT-CSE-401",
            "course_title": "Database Management Systems",
            "credits": 4,
        }
        doc = SyllabusDocMetadata(**payload)
        assert doc.doc_type == "syllabus"
        assert doc.batch_year == "2022"
        assert doc.credits == 4

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, SyllabusDocMetadata)
        assert parsed.course_code == "BT-CSE-401"

    def test_batch_year_coercion(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "syllabus",
            "program": "M.Tech CSE",
            "batch_year": 2024,
            "semester": "Semester 1",
            "credits": "3",
        }
        doc = SyllabusDocMetadata(**payload)
        assert doc.batch_year == "2024"
        assert doc.credits == 3

    def test_extra_field_forbidden(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "syllabus",
            "program": "B.Tech CSE",
            "batch_year": "2022",
            "semester": "Semester 4",
            "unknown_extra": 99,
        }
        with pytest.raises(ValidationError):
            SyllabusDocMetadata(**payload)


class TestResultDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "result",
            "exam_session": "Autumn 2024",
            "notification_number": "2428",
            "result_type": "re_evaluation",
            "program": "B.Tech CSE",
            "declaration_date": "2025-01-15",
        }
        doc = ResultDocMetadata(**payload)
        assert doc.doc_type == "result"
        assert doc.result_type == "re_evaluation"

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, ResultDocMetadata)
        assert parsed.notification_number == "2428"


class TestAdmissionDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "admission",
            "admission_year": "2024",
            "program": "Master of Education (M.Ed)",
            "stage": "cut_off",
            "intake_capacity": 50,
        }
        doc = AdmissionDocMetadata(**payload)
        assert doc.doc_type == "admission"
        assert doc.stage == "cut_off"
        assert doc.intake_capacity == 50

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, AdmissionDocMetadata)
        assert parsed.admission_year == "2024"


class TestNoticeDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "notice",
            "reference_number": "CUK/Acad/2024/110",
            "issuing_office": "Dean Academic Affairs",
            "is_urgent": True,
            "expiry_date": "2024-12-31",
        }
        doc = NoticeDocMetadata(**payload)
        assert doc.doc_type == "notice"
        assert doc.is_urgent is True
        assert doc.reference_number == "CUK/Acad/2024/110"

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, NoticeDocMetadata)
        assert parsed.issuing_office == "Dean Academic Affairs"


class TestTenderDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "tender",
            "tender_number": "NIT/CUK/2024/09",
            "nit_date": "2024-10-01",
            "closing_date": "2024-11-01",
            "emd_amount": "INR 50,000",
        }
        doc = TenderDocMetadata(**payload)
        assert doc.doc_type == "tender"
        assert doc.tender_number == "NIT/CUK/2024/09"

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, TenderDocMetadata)
        assert parsed.emd_amount == "INR 50,000"


class TestOrdinanceDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "ordinance",
            "ordinance_number": "Ordinance 14-A",
            "subject": "Statute Governing Conduct of Examinations",
            "governing_body": "Executive Council",
            "effective_date": "2023-06-01",
        }
        doc = OrdinanceDocMetadata(**payload)
        assert doc.doc_type == "ordinance"
        assert doc.ordinance_number == "Ordinance 14-A"

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, OrdinanceDocMetadata)
        assert parsed.subject == "Statute Governing Conduct of Examinations"


class TestFacultyDocMetadata:
    def test_round_trip(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "faculty",
            "employee_name": "Dr. Sarah Khan",
            "designation": "Associate Professor",
            "email": "sarah.khan@cukashmir.ac.in",
            "qualifications": ["Ph.D. in Computer Science", "M.Tech CSE"],
            "research_areas": ["Natural Language Processing", "Machine Learning"],
        }
        doc = FacultyDocMetadata(**payload)
        assert doc.doc_type == "faculty"
        assert doc.employee_name == "Dr. Sarah Khan"
        assert len(doc.research_areas) == 2

        parsed = parse_document_metadata(doc.model_dump())
        assert isinstance(parsed, FacultyDocMetadata)
        assert parsed.designation == "Associate Professor"

    def test_qualifications_str_coercion(self, base_metadata_payload: dict) -> None:
        payload = {
            **base_metadata_payload,
            "doc_type": "faculty",
            "employee_name": "Dr. Sarah Khan",
            "designation": "Associate Professor",
            "qualifications": "Ph.D., M.Tech, B.Tech",
            "research_areas": "AI, ML, Robotics",
        }
        doc = FacultyDocMetadata(**payload)
        assert doc.qualifications == ["Ph.D.", "M.Tech", "B.Tech"]
        assert doc.research_areas == ["AI", "ML", "Robotics"]


class TestPolymorphicDiscriminationAndFallback:
    def test_universal_fallback_on_omitted_doc_type(self, base_metadata_payload: dict) -> None:
        payload = dict(base_metadata_payload)
        del payload["doc_type"]
        parsed = parse_document_metadata(payload)
        assert isinstance(parsed, GeneralDocMetadata)
        assert parsed.doc_type == "general"

    def test_universal_fallback_on_general_official_document(
        self, base_metadata_payload: dict
    ) -> None:
        payload = {**base_metadata_payload, "doc_type": "general_official_document"}
        parsed = parse_document_metadata(payload)
        assert isinstance(parsed, GeneralDocMetadata)
        assert parsed.doc_type == "general"

    def test_invalid_doc_type_raises_validation_error(self, base_metadata_payload: dict) -> None:
        payload = {**base_metadata_payload, "doc_type": "unrecognized_alien_type"}
        with pytest.raises(ValidationError):
            parse_document_metadata(payload)

    def test_non_dict_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            parse_document_metadata("not_a_dict")  # type: ignore[arg-type]
