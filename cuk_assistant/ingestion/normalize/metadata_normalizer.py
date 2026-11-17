"""Domain-specific metadata normalizers and heuristic rule engine.

Provides deterministic regex extractors and standardizers for:
- University circular and order reference numbers
- Academic years and sessions
- Course codes (e.g. BT-101, CS-C402)
- Academic semester representations (Roman numerals, ordinals, and Arabic numbers)
- Heterogeneous dates (Indian DD-MM-YYYY, textual formats) into ISO YYYY-MM-DD
- Academic batch cohorts
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Circular & Reference Extraction
# ---------------------------------------------------------------------------

_CIRCULAR_PATTERNS = [
    # Explicit File No / F.No: e.g. "F.No. CUKMR/Exam/22/45", "F. No. CUK/Admn/2021/10", "F.No. 123"
    re.compile(
        r"\b(F\.?\s*No\.?\s*[:\-]?(?:\s*[A-Za-z0-9_.\-]+(?:\/[A-Za-z0-9_\-./]+)*|[A-Za-z0-9_\-./]+))\b",
        re.IGNORECASE,
    ),
    # NIT No. e.g. "NIT No 04 of 2026", "NIT No. 04 of 2026", "NIT/CUK/2024/01"
    re.compile(
        r"\b(NIT\s*(?:No\.?)?\s*[:\-]?\s*[0-9A-Za-z_\-./]+(?:\s+of\s+\d{4})?)\b",
        re.IGNORECASE,
    ),
    # Notification No e.g. "Result Notification No. 2428", "Notification No. 123/2024"
    re.compile(
        r"\b((?:Result\s+)?Notification\s+No\.?\s*[:\-]?\s*[0-9A-Za-z_\-./]+)\b",
        re.IGNORECASE,
    ),
    # Direct CUK / CUKMR reference strings: "CUK/Acad/2023/123", "CUK/Admn/Notice/2024"
    re.compile(
        r"\b((?:CUK|CUKMR)[A-Za-z0-9_\-]*(?:\/[A-Za-z0-9_\-\.]+)+)\b",
        re.IGNORECASE,
    ),
    # General Ref No: e.g. "Ref. No. CUK/Gen/2023/50" -> captured via prefix stripping below
    re.compile(
        r"\b(?:Ref\.?\s*No\.?|Order\s+No\.?|Circular\s+No\.?)\s*[:\-]?\s*([A-Za-z0-9_.\-]+(?:\/[A-Za-z0-9_\-./]+)+)\b",
        re.IGNORECASE,
    ),
]


def extract_circular_reference(text: str) -> str | None:
    """Extract circular, order, or notification reference identifier.

    Handles patterns such as:
    - CUK/Acad/2023/123
    - F.No. CUKMR/Exam/22/45
    - CUK/Admn/Notice/2024
    - NIT No 04 of 2026
    - Result Notification No. 2428
    """
    if not text or not isinstance(text, str):
        return None

    clean_text = text.strip()
    for pattern in _CIRCULAR_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            val = match.group(1).strip()
            # Clean trailing punctuation
            val = re.sub(r"[\.,;:!\)\>\]]+$", "", val).strip()
            if val:
                return val
    return None


# ---------------------------------------------------------------------------
# Academic Year Normalization
# ---------------------------------------------------------------------------

_YEAR_SPAN_FULL_RE = re.compile(r"\b(20\d{2}|19\d{2})\s*[-/–]\s*(20\d{2}|19\d{2})\b")
_YEAR_SPAN_SHORT_RE = re.compile(r"\b(20\d{2}|19\d{2})\s*[-/–]\s*(\d{2})\b")
_SINGLE_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")


def normalize_academic_year(text: str) -> str | None:
    """Standardize academic session representations into canonical format.

    Examples:
    - "2023-24", "2023-2024", "2023/24", "2023/2024" -> "2023-2024"
    - "2024" -> "2024"
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()

    # 1. 4-digit to 4-digit span: "2023-2024", "2023/2024"
    m_full = _YEAR_SPAN_FULL_RE.search(s)
    if m_full:
        y1, y2 = m_full.group(1), m_full.group(2)
        return f"{y1}-{y2}"

    # 2. 4-digit to 2-digit span: "2023-24", "2023/24"
    m_short = _YEAR_SPAN_SHORT_RE.search(s)
    if m_short:
        y1_str = m_short.group(1)
        y2_short = int(m_short.group(2))
        century = (int(y1_str) // 100) * 100
        # Century crossover check: e.g. 1999-00 -> 2000
        y2_full = century + 100 if y2_short == 0 and y1_str.endswith("99") else century + y2_short
        return f"{y1_str}-{y2_full}"

    # 3. Single 4-digit year: "2024"
    m_single = _SINGLE_YEAR_RE.search(s)
    if m_single:
        return m_single.group(1)

    return None


# ---------------------------------------------------------------------------
# Course Code Extraction
# ---------------------------------------------------------------------------

_COURSE_CODE_RE = re.compile(
    r"\b([A-Za-z]{2,5}\s*[-/]\s*(?:[A-Za-z]{1,4}\s*[-/]\s*)?[A-Za-z]?\d{2,4}[A-Za-z]?)\b"
)


def extract_course_code(text: str) -> str | None:
    """Extract canonical academic course code.

    Examples:
    - "BT-101", "CS-C402", "MBA-201", "MTH-102", "BT-CSE-401"
    """
    if not text or not isinstance(text, str):
        return None

    m = _COURSE_CODE_RE.search(text)
    if m:
        raw = m.group(1).upper()
        # Standardize delimiter spaces and slashes to a single hyphen
        cleaned = re.sub(r"[\s/]+", "-", raw)
        cleaned = re.sub(r"-+", "-", cleaned)
        return cleaned
    return None


# ---------------------------------------------------------------------------
# Semester Normalization
# ---------------------------------------------------------------------------

_ROMAN_MAP: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
}

_WORD_MAP: dict[str, int] = {
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
    "EIGHTH": 8,
    "NINTH": 9,
    "TENTH": 10,
    "ELEVENTH": 11,
    "TWELFTH": 12,
}

_ORDINAL_RE = re.compile(r"^(1ST|2ND|3RD|4TH|5TH|6TH|7TH|8TH|9TH|10TH|11TH|12TH)$")
_SEM_PATTERN = re.compile(
    r"(?:(?:Semester|Sem)\s*[-_.]?\s*(\d{1,2}(?:st|nd|rd|th)?|[IVXLCDM]+|[A-Za-z]+))"
    r"|(?:(\d{1,2}(?:st|nd|rd|th)?|[IVXLCDM]+|[A-Za-z]+)\s*[-_.]?\s*(?:Semester|Sem))",
    re.IGNORECASE,
)


def normalize_semester(text: str) -> str | None:
    """Standardize semester tokens into canonical format ('Semester N').

    Supports:
    - "Semester 3", "Sem-III", "3rd Semester", "Sem 3rd", "III" -> "Semester 3"
    - Roman numerals: "Sem I" through "Sem VIII" -> "Semester 1" through "Semester 8"
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    clean_upper = re.sub(r"[^\w\s]", "", s.upper()).strip()

    # 1. Exact Roman numeral standalone (e.g. "III", "IV")
    if clean_upper in _ROMAN_MAP:
        return f"Semester {_ROMAN_MAP[clean_upper]}"

    # 2. Exact word numeral standalone (e.g. "Third")
    if clean_upper in _WORD_MAP:
        return f"Semester {_WORD_MAP[clean_upper]}"

    # 3. Pattern match with "Sem" or "Semester" keyword
    match = _SEM_PATTERN.search(s)
    if match:
        token = (match.group(1) or match.group(2)).strip().upper()
        # Strip ordinal suffix (e.g. "3RD" -> "3")
        token_clean = re.sub(r"(ST|ND|RD|TH)$", "", token)

        if token_clean.isdigit():
            num = int(token_clean)
            if 1 <= num <= 12:
                return f"Semester {num}"
        if token in _ROMAN_MAP:
            return f"Semester {_ROMAN_MAP[token]}"
        if token_clean in _ROMAN_MAP:
            return f"Semester {_ROMAN_MAP[token_clean]}"
        if token in _WORD_MAP:
            return f"Semester {_WORD_MAP[token]}"
        if token_clean in _WORD_MAP:
            return f"Semester {_WORD_MAP[token_clean]}"

    # 4. Standalone digit within semester boundaries (e.g. "3")
    if s.isdigit():
        num = int(s)
        if 1 <= num <= 12:
            return f"Semester {num}"

    return None


# ---------------------------------------------------------------------------
# Date Normalization (ISO-8601 YYYY-MM-DD)
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, int] = {
    "JAN": 1,
    "JANUARY": 1,
    "FEB": 2,
    "FEBRUARY": 2,
    "MAR": 3,
    "MARCH": 3,
    "APR": 4,
    "APRIL": 4,
    "MAY": 5,
    "JUN": 6,
    "JUNE": 6,
    "JUL": 7,
    "JULY": 7,
    "AUG": 8,
    "AUGUST": 8,
    "SEP": 9,
    "SEPT": 9,
    "SEPTEMBER": 9,
    "OCT": 10,
    "OCTOBER": 10,
    "NOV": 11,
    "NOVEMBER": 11,
    "DEC": 12,
    "DECEMBER": 12,
}

_ISO_DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})[-/](\d{1,2})[-/](\d{1,2})")
_INDIAN_DATE_RE = re.compile(r"\b(\d{1,2})[-/. ](\d{1,2})[-/. ](20\d{2}|19\d{2})\b")
_TEXT_DMY_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s*[-/, ]\s*([A-Za-z]{3,9})\s*[-/, ]\s*(20\d{2}|19\d{2})\b"
)
_TEXT_MDY_RE = re.compile(
    r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-/, ]\s*(20\d{2}|19\d{2})\b"
)


def normalize_iso_date(text: str) -> str | None:
    """Normalize heterogeneous date strings to canonical ISO YYYY-MM-DD.

    Reconciles:
    - ISO strings: "2024-11-15", "2024-11-15T10:00:00Z"
    - Indian format: "15-11-2024", "15/11/2024", "15.11.2024"
    - Textual dates: "15th Nov, 2024", "November 15, 2024", "15 November 2024"
    - Rejects invalid calendar dates (e.g. 31-02-2024).
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()

    # 1. ISO format: YYYY-MM-DD
    m_iso = _ISO_DATE_RE.search(s)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            return None

    # 2. Indian numeric format: DD-MM-YYYY
    m_dmy = _INDIAN_DATE_RE.search(s)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            return None

    # 3. Day Month Year: "15th Nov, 2024", "15 November 2024"
    m_tdmy = _TEXT_DMY_RE.search(s)
    if m_tdmy:
        d = int(m_tdmy.group(1))
        month_str = m_tdmy.group(2).upper()
        y = int(m_tdmy.group(3))
        if month_str in _MONTH_MAP:
            try:
                return date(y, _MONTH_MAP[month_str], d).isoformat()
            except ValueError:
                return None

    # 4. Month Day Year: "November 15, 2024", "Nov 15, 2024"
    m_tmdy = _TEXT_MDY_RE.search(s)
    if m_tmdy:
        month_str = m_tmdy.group(1).upper()
        d = int(m_tmdy.group(2))
        y = int(m_tmdy.group(3))
        if month_str in _MONTH_MAP:
            try:
                return date(y, _MONTH_MAP[month_str], d).isoformat()
            except ValueError:
                return None

    return None


# ---------------------------------------------------------------------------
# Batch Year Extraction
# ---------------------------------------------------------------------------

_BATCH_PATTERNS = [
    # "Batch 2022", "Admitted Batch 2021", "Batch: 2023", "Batch (2020)"
    re.compile(r"\b(?:Admitted\s+)?Batch\s*[-:\(]?\s*(20\d{2})\b", re.IGNORECASE),
    # "2022 Batch", "2022-26 Batch", "2022-2026 Batch"
    re.compile(r"\b(20\d{2})\s*(?:[-–/]\s*(?:20)?\d{2})?\s*Batch\b", re.IGNORECASE),
    # "Admitted in 2022", "Admitted 2022"
    re.compile(r"\bAdmitted\s*(?:in\s*)?[-:]?\s*(20\d{2})\b", re.IGNORECASE),
    # "Cohort 2022", "Class of 2022"
    re.compile(r"\b(?:Cohort|Class\s+of)\s*[-:]?\s*(20\d{2})\b", re.IGNORECASE),
]


def extract_batch_year(text: str) -> str | None:
    """Extract 4-digit academic batch cohort year.

    Examples:
    - "Syllabus for Batch 2022" -> "2022"
    - "Admitted Batch: 2021" -> "2021"
    - "2023 Batch" -> "2023"
    - "2024" -> "2024"
    """
    if not text or not isinstance(text, str):
        return None

    s = text.strip()
    if re.fullmatch(r"20\d{2}", s):
        return s

    for pattern in _BATCH_PATTERNS:
        match = pattern.search(s)
        if match:
            return match.group(1)

    return None


# ---------------------------------------------------------------------------
# Ancillary Helpers
# ---------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    """Normalize raw title by stripping file extensions, noise, and collapsing whitespace."""
    if not title or not isinstance(title, str):
        return ""
    t = title.strip()
    # Strip file extensions
    t = re.sub(r"\.(pdf|docx?|html?|xlsx?)(\?.*)?$", "", t, flags=re.IGNORECASE)
    # Collapse multiple whitespaces
    t = re.sub(r"\s+", " ", t)
    # Strip non-alphanumeric edges
    t = t.strip(" -_.,:;|")
    return t.lower()


def clean_guid(guid: Any) -> str:
    """Sanitize GUID strings (trim, uppercase, remove braces)."""
    if not guid:
        return ""
    s = str(guid).strip().upper()
    return s.strip("{}")
