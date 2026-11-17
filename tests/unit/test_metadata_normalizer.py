"""Unit tests for CUK RAG Assistant metadata normalizers and heuristic rule engine.

Covers 30+ parameter-driven test cases across:
- Circular and order reference extraction
- Academic year normalization
- Course code extraction
- Academic semester standardization (Roman numerals, ordinals, Arabic)
- Date normalization (Indian formats, textual formats, rejection of invalid dates)
- Batch year extraction
- Title normalization and GUID cleaning
"""

import pytest

from cuk_assistant.ingestion.normalize import (
    clean_guid,
    extract_batch_year,
    extract_circular_reference,
    extract_course_code,
    normalize_academic_year,
    normalize_iso_date,
    normalize_semester,
    normalize_title,
)


class TestCircularReferenceExtractor:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("CUK/Acad/2023/123", "CUK/Acad/2023/123"),
            ("F.No. CUKMR/Exam/22/45", "F.No. CUKMR/Exam/22/45"),
            ("CUK/Admn/Notice/2024", "CUK/Admn/Notice/2024"),
            ("F. No. CUK/Admn/2021/10", "F. No. CUK/Admn/2021/10"),
            ("Please refer to CUK/Acad/2023/F-102/445.", "CUK/Acad/2023/F-102/445"),
            ("NIT No 04 of 2026", "NIT No 04 of 2026"),
            ("NIT No. 04 of 2026 dated 10-01-2026", "NIT No. 04 of 2026"),
            ("Result Notification No. 2428 for B.Tech", "Result Notification No. 2428"),
            ("Notification No. 102/2024", "Notification No. 102/2024"),
            ("Ref. No. CUK/Gen/2023/50", "CUK/Gen/2023/50"),
            ("No reference number in this text", None),
            ("", None),
        ],
    )
    def test_extract_circular_reference(self, input_text: str, expected: str | None) -> None:
        assert extract_circular_reference(input_text) == expected


class TestAcademicYearNormalizer:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("2023-24", "2023-2024"),
            ("2023-2024", "2023-2024"),
            ("2023/24", "2023-2024"),
            ("2023/2024", "2023-2024"),
            ("Academic Session 2022-23 for all students", "2022-2023"),
            ("Admission for session 2024-2025", "2024-2025"),
            ("Session 1999-00", "1999-2000"),
            ("Notice dated 2024", "2024"),
            ("No year present here", None),
            ("", None),
        ],
    )
    def test_normalize_academic_year(self, input_text: str, expected: str | None) -> None:
        assert normalize_academic_year(input_text) == expected


class TestCourseCodeExtractor:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Course code BT-101 introductory biology", "BT-101"),
            ("Subject CS-C402 Database Systems", "CS-C402"),
            ("Syllabus for MBA-201 Marketing", "MBA-201"),
            ("Paper code MTH-102 Calculus", "MTH-102"),
            ("Advanced BT-CSE-401 Algorithms", "BT-CSE-401"),
            ("Law paper IL-201 Constitutional Law", "IL-201"),
            ("bt - 101 with spaces", "BT-101"),
            ("EDU/101 Education Foundations", "EDU-101"),
            ("General notice with no course code", None),
            ("", None),
        ],
    )
    def test_extract_course_code(self, input_text: str, expected: str | None) -> None:
        assert extract_course_code(input_text) == expected


class TestSemesterNormalizer:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Semester 3", "Semester 3"),
            ("Sem-III", "Semester 3"),
            ("3rd Semester", "Semester 3"),
            ("Sem 3rd", "Semester 3"),
            ("III", "Semester 3"),
            ("Sem I", "Semester 1"),
            ("Sem-II", "Semester 2"),
            ("Semester IV", "Semester 4"),
            ("4th Sem", "Semester 4"),
            ("Sem 5", "Semester 5"),
            ("Fifth Semester", "Semester 5"),
            ("VI", "Semester 6"),
            ("Semester VII", "Semester 7"),
            ("Sem-VIII", "Semester 8"),
            ("8th Semester", "Semester 8"),
            ("Semester 8", "Semester 8"),
            ("9th Semester", "Semester 9"),
            ("Semester X", "Semester 10"),
            ("Section 3", None),
            ("Random text without semester", None),
            ("", None),
        ],
    )
    def test_normalize_semester(self, input_text: str, expected: str | None) -> None:
        assert normalize_semester(input_text) == expected


class TestIsoDateNormalizer:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("15-11-2024", "2024-11-15"),
            ("15/11/2024", "2024-11-15"),
            ("15.11.2024", "2024-11-15"),
            ("15th Nov, 2024", "2024-11-15"),
            ("15th November 2024", "2024-11-15"),
            ("15 Nov 2024", "2024-11-15"),
            ("November 15, 2024", "2024-11-15"),
            ("Nov 15, 2024", "2024-11-15"),
            ("2024-11-15T10:00:00Z", "2024-11-15"),
            ("2024-11-15", "2024-11-15"),
            ("1-5-2024", "2024-05-01"),
            # Invalid dates:
            ("31-02-2024", None),  # Feb 31 does not exist
            ("31/04/2024", None),  # April has 30 days
            ("99-99-9999", None),
            ("invalid-date-string", None),
            ("", None),
        ],
    )
    def test_normalize_iso_date(self, input_text: str, expected: str | None) -> None:
        assert normalize_iso_date(input_text) == expected


class TestBatchYearExtractor:
    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Syllabus for Batch 2022", "2022"),
            ("Admitted Batch: 2021", "2021"),
            ("2023 Batch syllabus", "2023"),
            ("2022-26 Batch", "2022"),
            ("Batch (2020-2024)", "2020"),
            ("Admitted in 2024", "2024"),
            ("Cohort 2025", "2025"),
            ("2022", "2022"),
            ("General notice with no batch", None),
            ("", None),
        ],
    )
    def test_extract_batch_year(self, input_text: str, expected: str | None) -> None:
        assert extract_batch_year(input_text) == expected


class TestAncillaryNormalizers:
    def test_normalize_title(self) -> None:
        assert normalize_title("Syllabus_BTech_CSE_2022.pdf") == "syllabus_btech_cse_2022"
        assert (
            normalize_title("  Notice Regarding Winter Vacation 2024.PDF  ")
            == "notice regarding winter vacation 2024"
        )
        assert normalize_title("Page.html?id=123") == "page"
        assert normalize_title("") == ""

    def test_clean_guid(self) -> None:
        assert (
            clean_guid("{7022529F-5494-4B1E-9A76-EB211C56019A}")
            == "7022529F-5494-4B1E-9A76-EB211C56019A"
        )
        assert clean_guid("sch_eng_001") == "SCH_ENG_001"
        assert clean_guid(None) == ""
