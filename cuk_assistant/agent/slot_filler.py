"""Conversational Faceted Slot-Filling Engine for CUK RAG Assistant.

Implements FR-3.3 and API Contracts Section 5.1:
Deterministic extraction and disambiguation of mandatory academic slots
(program, batch_year, semester) with interactive quick-reply chip payloads.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quick-Reply & Chip Models (docs/api_contracts.md Section 5.1)
# ---------------------------------------------------------------------------


class QuickReplyOption(BaseModel):
    """Individual option for interactive quick-reply chips."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(..., description="Display title on chip (e.g. 'B.Tech CSE')")
    value: str = Field(..., description="Slot value passed back to server on click")
    description: str | None = Field(default=None, description="Optional tooltip text")


class QuickReplyPayload(BaseModel):
    """Payload schema for interactive quick-reply slot-filling chips."""

    model_config = ConfigDict(frozen=True)

    target_slot: str = Field(
        ..., description="Target slot name (e.g. 'program', 'batch_year', 'semester')"
    )
    prompt: str = Field(..., description="Clarification message displayed to user")
    options: list[QuickReplyOption] = Field(
        default_factory=list, description="Candidate quick-reply options"
    )
    is_multi_select: bool = Field(
        default=False, description="Whether multiple selections are permitted"
    )


class SlotChipPayload(BaseModel):
    """Compact slot-filling chip payload conforming to Task 5.2 specification."""

    model_config = ConfigDict(frozen=True)

    missing_slot: str = Field(..., description="Name of the missing slot (e.g. 'semester')")
    prompt_text: str = Field(
        ..., description="Disambiguation prompt (e.g. 'Which semester syllabus do you need?')"
    )
    chips: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of chips with 'label' and 'value' keys",
    )

    def to_quick_reply_payload(self) -> QuickReplyPayload:
        """Convert to API contract compliant QuickReplyPayload."""
        return QuickReplyPayload(
            target_slot=self.missing_slot,
            prompt=self.prompt_text,
            options=[QuickReplyOption(label=c["label"], value=c["value"]) for c in self.chips],
        )


class SlotFillingResult(BaseModel):
    """Comprehensive evaluation outcome of slot-filling analysis."""

    model_config = ConfigDict(extra="forbid")

    is_complete: bool = Field(
        ..., description="True if all mandatory slots for the target domain are satisfied"
    )
    doc_type: str | None = Field(
        default=None, description="Identified academic document domain (syllabus, result, etc.)"
    )
    target_slot: str | None = Field(
        default=None, description="The primary next missing slot needing clarification"
    )
    missing_slots: list[str] = Field(
        default_factory=list, description="Ordered list of missing mandatory slots"
    )
    extracted_slots: dict[str, Any] = Field(
        default_factory=dict, description="Dictionary of all recognized and normalized slots"
    )
    chip_payload: SlotChipPayload | None = Field(
        default=None, description="Interactive chip payload for user disambiguation"
    )
    quick_reply_payload: QuickReplyPayload | None = Field(
        default=None, description="Full QuickReplyPayload conforming to api_contracts.md"
    )
    metadata_filter: str | None = Field(
        default=None, description="Deterministic LanceDB / SQL filter clause when complete"
    )

    @property
    def missing_slot(self) -> str | None:
        """Convenience property for primary next missing slot."""
        return self.target_slot or (self.missing_slots[0] if self.missing_slots else None)


# ---------------------------------------------------------------------------
# Lexicons, Patterns & Program Knowledge Bases
# ---------------------------------------------------------------------------


class AcademicIntentType(StrEnum):
    """Academic intent classification categories."""

    SYLLABUS = "syllabus"
    RESULT = "result"
    DATESHEET = "datesheet"
    ADMISSION = "admission"
    GENERAL = "general"


# Canonical programs offered by Central University of Kashmir (CUK)
CANONICAL_PROGRAMS: tuple[str, ...] = (
    "B.Tech CSE",
    "MCA",
    "MBA",
    "B.Sc IT",
    "M.Sc IT",
    "BA LLB",
    "LLM",
    "B.Ed",
    "M.Ed",
    "M.A. English",
    "M.A. Urdu",
    "M.A. Economics",
    "M.A. Political Science",
    "M.Sc Physics",
    "M.Sc Chemistry",
    "M.Sc Mathematics",
    "M.Sc Zoology",
    "M.Sc Biotechnology",
    "Ph.D",
)

# Standard chip options per slot type
DEFAULT_PROGRAM_CHIPS: list[dict[str, str]] = [
    {"label": "B.Tech CSE", "value": "B.Tech CSE"},
    {"label": "MCA", "value": "MCA"},
    {"label": "MBA", "value": "MBA"},
    {"label": "B.Sc IT", "value": "B.Sc IT"},
    {"label": "BA LLB", "value": "BA LLB"},
    {"label": "M.A. English", "value": "M.A. English"},
]

DEFAULT_BATCH_CHIPS: list[dict[str, str]] = [
    {"label": "2024 (NEP)", "value": "2024"},
    {"label": "2023", "value": "2023"},
    {"label": "2022", "value": "2022"},
    {"label": "2021", "value": "2021"},
    {"label": "2020", "value": "2020"},
]

DEFAULT_SEMESTER_CHIPS: list[dict[str, str]] = [
    {"label": "Semester 1", "value": "Semester 1"},
    {"label": "Semester 2", "value": "Semester 2"},
    {"label": "Semester 3", "value": "Semester 3"},
    {"label": "Semester 4", "value": "Semester 4"},
    {"label": "Semester 5", "value": "Semester 5"},
    {"label": "Semester 6", "value": "Semester 6"},
    {"label": "Semester 7", "value": "Semester 7"},
    {"label": "Semester 8", "value": "Semester 8"},
]

DEFAULT_SESSION_CHIPS: list[dict[str, str]] = [
    {"label": "Autumn 2024", "value": "Autumn 2024"},
    {"label": "Spring 2024", "value": "Spring 2024"},
    {"label": "Autumn 2023", "value": "Autumn 2023"},
    {"label": "Spring 2023", "value": "Spring 2023"},
]

DEFAULT_ADMISSION_YEAR_CHIPS: list[dict[str, str]] = [
    {"label": "2025", "value": "2025"},
    {"label": "2024", "value": "2024"},
    {"label": "2023", "value": "2023"},
]

# Knowledge base linking well-known course titles to CUK programs
KNOWN_COURSE_PROGRAM_MAP: dict[str, tuple[str, str]] = {
    # key (lowercase): (canonical_course_title, canonical_program)
    "dbms": ("DBMS", "B.Tech CSE"),
    "database management systems": ("Database Management Systems", "B.Tech CSE"),
    "database management system": ("Database Management Systems", "B.Tech CSE"),
    "data structures": ("Data Structures", "B.Tech CSE"),
    "dsa": ("Data Structures & Algorithms", "B.Tech CSE"),
    "operating systems": ("Operating Systems", "B.Tech CSE"),
    "operating system": ("Operating Systems", "B.Tech CSE"),
    "os": ("Operating Systems", "B.Tech CSE"),
    "computer networks": ("Computer Networks", "B.Tech CSE"),
    "compiler design": ("Compiler Design", "B.Tech CSE"),
    "software engineering": ("Software Engineering", "B.Tech CSE"),
    "theory of computation": ("Theory of Computation", "B.Tech CSE"),
    "toc": ("Theory of Computation", "B.Tech CSE"),
    "artificial intelligence": ("Artificial Intelligence", "B.Tech CSE"),
    "machine learning": ("Machine Learning", "B.Tech CSE"),
    "computer organization": ("Computer Organization & Architecture", "B.Tech CSE"),
    "coa": ("Computer Organization & Architecture", "B.Tech CSE"),
    "corporate law": ("Corporate Law", "BA LLB"),
    "constitutional law": ("Constitutional Law", "BA LLB"),
    "criminal law": ("Criminal Law", "BA LLB"),
    "jurisprudence": ("Jurisprudence", "BA LLB"),
    "financial accounting": ("Financial Accounting", "MBA"),
    "marketing management": ("Marketing Management", "MBA"),
    "human resource management": ("Human Resource Management", "MBA"),
    "hrm": ("Human Resource Management", "MBA"),
    "quantum mechanics": ("Quantum Mechanics", "M.Sc Physics"),
    "classical mechanics": ("Classical Mechanics", "M.Sc Physics"),
    "organic chemistry": ("Organic Chemistry", "M.Sc Chemistry"),
}

# Number words to digit map
WORD_TO_DIGIT: dict[str, str] = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
}


# ---------------------------------------------------------------------------
# FacetedSlotFiller Engine
# ---------------------------------------------------------------------------


class FacetedSlotFiller:
    """Deterministic slot extraction and faceted disambiguation chip engine."""

    # Intent detection patterns
    _SYLLABUS_RE = re.compile(
        r"\b(syllabus|curriculum|course\s*outline|course\s*content|scheme\s*of\s*study|units|credits)\b",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(
        r"\b(results?|marksheet|grade\s*sheet|scorecard|gazette|re-?evaluation|backlog)\b",
        re.IGNORECASE,
    )
    _DATESHEET_RE = re.compile(
        r"\b(date\s*sheet|datesheet|exam\s*schedule|examination\s*schedule|exam\s*timetable)\b",
        re.IGNORECASE,
    )
    _ADMISSION_RE = re.compile(
        r"\b(admissions?|cut-?offs?|merit\s*list|selection\s*list|seat\s*matrix|counseling|counselling)\b",
        re.IGNORECASE,
    )

    # Program extraction patterns
    _PROGRAM_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(
                r"\b(b\.?\s*tech\s*(?:in\s*)?cse|b\.?\s*tech\s*computer\s*science|b\.?\s*tech)\b",
                re.IGNORECASE,
            ),
            "B.Tech CSE",
        ),
        (
            re.compile(
                r"\b(m\.?\s*tech\s*(?:in\s*)?cs|m\.?\s*tech\s*computer\s*science|m\.?\s*tech)\b",
                re.IGNORECASE,
            ),
            "M.Tech",
        ),
        (
            re.compile(r"\b(mca|master\s*of\s*computer\s*applications)\b", re.IGNORECASE),
            "MCA",
        ),
        (
            re.compile(r"\b(mba|master\s*of\s*business\s*administration)\b", re.IGNORECASE),
            "MBA",
        ),
        (
            re.compile(r"\b(bba|bachelor\s*of\s*business\s*administration)\b", re.IGNORECASE),
            "BBA",
        ),
        (
            re.compile(
                r"\b(b\.?\s*sc\s*it|bsc\s*it|bachelor\s*of\s*science\s*in\s*it)\b", re.IGNORECASE
            ),
            "B.Sc IT",
        ),
        (
            re.compile(
                r"\b(m\.?\s*sc\s*it|msc\s*it|master\s*of\s*science\s*in\s*it)\b", re.IGNORECASE
            ),
            "M.Sc IT",
        ),
        (
            re.compile(r"\b(ba\s*llb|b\.?a\.?\s*ll\.?b|ballb)\b", re.IGNORECASE),
            "BA LLB",
        ),
        (
            re.compile(r"\b(llm|ll\.?m)\b", re.IGNORECASE),
            "LLM",
        ),
        (
            re.compile(r"\b(b\.?ed|bachelor\s*of\s*education)\b", re.IGNORECASE),
            "B.Ed",
        ),
        (
            re.compile(r"\b(m\.?ed|master\s*of\s*education)\b", re.IGNORECASE),
            "M.Ed",
        ),
        (
            re.compile(r"\b(m\.?a\.?\s*english|ma\s*english)\b", re.IGNORECASE),
            "M.A. English",
        ),
        (
            re.compile(r"\b(m\.?a\.?\s*urdu|ma\s*urdu)\b", re.IGNORECASE),
            "M.A. Urdu",
        ),
        (
            re.compile(r"\b(m\.?a\.?\s*economics|ma\s*economics)\b", re.IGNORECASE),
            "M.A. Economics",
        ),
        (
            re.compile(
                r"\b(m\.?a\.?\s*political\s*science|ma\s*political\s*science)\b", re.IGNORECASE
            ),
            "M.A. Political Science",
        ),
        (
            re.compile(r"\b(m\.?sc\s*physics|msc\s*physics)\b", re.IGNORECASE),
            "M.Sc Physics",
        ),
        (
            re.compile(r"\b(m\.?sc\s*chemistry|msc\s*chemistry)\b", re.IGNORECASE),
            "M.Sc Chemistry",
        ),
        (
            re.compile(r"\b(m\.?sc\s*mathematics|msc\s*mathematics)\b", re.IGNORECASE),
            "M.Sc Mathematics",
        ),
        (
            re.compile(r"\b(m\.?sc\s*zoology|msc\s*zoology)\b", re.IGNORECASE),
            "M.Sc Zoology",
        ),
        (
            re.compile(r"\b(m\.?sc\s*biotechnology|msc\s*biotechnology)\b", re.IGNORECASE),
            "M.Sc Biotechnology",
        ),
        (
            re.compile(r"\b(ph\.?d|phd|doctorate)\b", re.IGNORECASE),
            "Ph.D",
        ),
    )

    # Semester extraction patterns
    _SEMESTER_RE = re.compile(
        r"\b(?:sem(?:ester)?\s*([1-8]|one|two|three|four|five|six|seven|eight|i{1,3}|iv|v|vi{1,3}|viii)|"
        r"([1-8])(?:st|nd|rd|th)?\s*sem(?:ester)?)\b",
        re.IGNORECASE,
    )

    # Batch extraction patterns
    _BATCH_EXPLICIT_RE = re.compile(
        r"\b(?:batch\s*(?:of\s*)?|(?:for\s+)?cohort\s*(?:of\s*)?|(?:admission\s*)?regulation\s*(?:of\s*)?)(20\d{2})\b",
        re.IGNORECASE,
    )
    _BATCH_SUFFIX_RE = re.compile(
        r"\b(20\d{2})\s*(?:batch|cohort|regulation|\(nep\))\b",
        re.IGNORECASE,
    )
    _FOUR_DIGIT_YEAR_RE = re.compile(r"\b(201[5-9]|202[0-9])\b")

    # Exam session extraction pattern
    _EXAM_SESSION_RE = re.compile(
        r"\b(autumn|spring|winter|summer)\s*(20\d{2})\b",
        re.IGNORECASE,
    )

    # Course code extraction pattern (e.g. BT-101, BT-CSE-401, CS-101)
    _COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{2,4}(?:-[A-Za-z]{2,4})?[- ]?\d{3}[A-Za-z]?)\b")

    def detect_academic_intent(self, text: str) -> AcademicIntentType | None:
        """Detect academic category of inquiry."""
        if self._SYLLABUS_RE.search(text):
            return AcademicIntentType.SYLLABUS
        if self._RESULT_RE.search(text):
            return AcademicIntentType.RESULT
        if self._DATESHEET_RE.search(text):
            return AcademicIntentType.DATESHEET
        if self._ADMISSION_RE.search(text):
            return AcademicIntentType.ADMISSION
        # Check if known course title is present even without explicit keyword
        text_lower = text.lower()
        for course_key in KNOWN_COURSE_PROGRAM_MAP:
            if re.search(rf"\b{re.escape(course_key)}\b", text_lower):
                return AcademicIntentType.SYLLABUS
        return None

    def extract_slots(
        self,
        query: str,
        session_slots: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract academic slots from query and merge with session slots."""
        slots: dict[str, Any] = dict(session_slots) if session_slots else {}
        text_lower = query.lower()

        # 1. Course title extraction & program inference from known courses
        for course_key, (canon_title, canon_prog) in KNOWN_COURSE_PROGRAM_MAP.items():
            if re.search(rf"\b{re.escape(course_key)}\b", text_lower):
                slots.setdefault("course_title", canon_title)
                if "program" not in slots:
                    slots["program"] = canon_prog
                break

        # 2. Explicit Program extraction (overrides inferred program)
        for pattern, canonical_name in self._PROGRAM_PATTERNS:
            if pattern.search(query):
                slots["program"] = canonical_name
                break

        # 3. Semester extraction
        sem_match = self._SEMESTER_RE.search(query)
        if sem_match:
            val = sem_match.group(1) or sem_match.group(2)
            val_lower = val.lower()
            digit = WORD_TO_DIGIT.get(val_lower, val_lower)
            if digit in ("1", "2", "3", "4", "5", "6", "7", "8"):
                slots["semester"] = f"Semester {digit}"

        # 4. Batch Year extraction
        batch_match = self._BATCH_EXPLICIT_RE.search(query)
        if batch_match:
            slots["batch_year"] = batch_match.group(1)
        else:
            batch_suffix_match = self._BATCH_SUFFIX_RE.search(query)
            if batch_suffix_match:
                slots["batch_year"] = batch_suffix_match.group(1)
            elif "batch_year" not in slots:
                # Standalone 4-digit year check if not already captured
                year_match = self._FOUR_DIGIT_YEAR_RE.search(query)
                if year_match:
                    slots["batch_year"] = year_match.group(1)

        # 5. Course Code extraction (e.g. BT-101, BT-CSE-401)
        code_match = self._COURSE_CODE_RE.search(query)
        if code_match:
            raw_code = code_match.group(1).upper().replace(" ", "-")
            slots["course_code"] = raw_code

        # 6. Exam Session extraction (e.g. Autumn 2024)
        session_match = self._EXAM_SESSION_RE.search(query)
        if session_match:
            slots["exam_session"] = (
                f"{session_match.group(1).capitalize()} {session_match.group(2)}"
            )

        # 7. Admission Year (defaults to batch_year if found)
        if "batch_year" in slots and "admission_year" not in slots:
            slots["admission_year"] = str(slots["batch_year"])

        return slots

    def get_mandatory_slots(self, intent: AcademicIntentType) -> list[str]:
        """Retrieve required slots for a specific academic domain."""
        if intent == AcademicIntentType.SYLLABUS:
            return ["program", "batch_year", "semester"]
        elif intent in (AcademicIntentType.RESULT, AcademicIntentType.DATESHEET):
            return ["program", "semester"]
        elif intent == AcademicIntentType.ADMISSION:
            return ["program", "admission_year"]
        return []

    def _build_chip_payload(self, missing_slot: str, intent: AcademicIntentType) -> SlotChipPayload:
        """Construct interactive disambiguation chip payload for the missing slot."""
        if missing_slot == "program":
            prompt = "Which academic program are you inquiring about?"
            chips = list(DEFAULT_PROGRAM_CHIPS)
        elif missing_slot == "batch_year":
            prompt = "Which admission batch or regulation cohort year?"
            chips = list(DEFAULT_BATCH_CHIPS)
        elif missing_slot == "semester":
            domain_label = "syllabus" if intent == AcademicIntentType.SYLLABUS else "details"
            prompt = f"Which semester {domain_label} do you need?"
            chips = list(DEFAULT_SEMESTER_CHIPS)
        elif missing_slot == "exam_session":
            prompt = "Which examination session?"
            chips = list(DEFAULT_SESSION_CHIPS)
        elif missing_slot == "admission_year":
            prompt = "Which academic admission intake year?"
            chips = list(DEFAULT_ADMISSION_YEAR_CHIPS)
        else:
            prompt = f"Please specify the {missing_slot}:"
            chips = []

        return SlotChipPayload(
            missing_slot=missing_slot,
            prompt_text=prompt,
            chips=chips,
        )

    def _build_metadata_filter(self, intent: AcademicIntentType, slots: dict[str, Any]) -> str:
        """Generate scoped LanceDB / SQL filter clause from completed slots."""
        clauses: list[str] = [f"doc_type == '{intent.value}'"]

        if "program" in slots and slots["program"]:
            clauses.append(f"program == '{slots['program']}'")

        if intent == AcademicIntentType.SYLLABUS:
            if "batch_year" in slots and slots["batch_year"]:
                clauses.append(f"batch_year == '{slots['batch_year']}'")
            if "semester" in slots and slots["semester"]:
                clauses.append(f"semester == '{slots['semester']}'")
            if "course_code" in slots and slots["course_code"]:
                clauses.append(f"course_code == '{slots['course_code']}'")

        elif intent == AcademicIntentType.RESULT:
            if "semester" in slots and slots["semester"]:
                clauses.append(f"semester == '{slots['semester']}'")
            if "exam_session" in slots and slots["exam_session"]:
                clauses.append(f"exam_session == '{slots['exam_session']}'")

        elif intent == AcademicIntentType.DATESHEET:
            if "semester" in slots and slots["semester"]:
                clauses.append(f"semester == '{slots['semester']}'")

        elif intent == AcademicIntentType.ADMISSION:
            if "admission_year" in slots and slots["admission_year"]:
                clauses.append(f"admission_year == '{slots['admission_year']}'")

        return " AND ".join(clauses)

    def fill_slots(
        self,
        query: str,
        session_slots: dict[str, Any] | None = None,
        force_intent: AcademicIntentType | None = None,
    ) -> SlotFillingResult:
        """Evaluate slot completeness and construct disambiguation payload if missing."""
        intent = force_intent or self.detect_academic_intent(query)
        if intent is None:
            # Not an academic inquiry requiring structured faceted slots
            extracted = self.extract_slots(query, session_slots)
            return SlotFillingResult(
                is_complete=True,
                doc_type="general",
                extracted_slots=extracted,
            )

        extracted = self.extract_slots(query, session_slots)
        mandatory = self.get_mandatory_slots(intent)

        missing = [slot for slot in mandatory if slot not in extracted or not extracted[slot]]

        if not missing:
            # All mandatory slots filled!
            metadata_filter = self._build_metadata_filter(intent, extracted)
            logger.debug(
                "All slots filled for intent=%s: %s (filter: %s)",
                intent.value,
                extracted,
                metadata_filter,
            )
            return SlotFillingResult(
                is_complete=True,
                doc_type=intent.value,
                extracted_slots=extracted,
                metadata_filter=metadata_filter,
            )

        # Slots are missing: generate interactive disambiguation chips for first missing slot
        primary_missing = missing[0]
        chip_payload = self._build_chip_payload(primary_missing, intent)
        quick_reply = chip_payload.to_quick_reply_payload()

        logger.debug(
            "Missing slots for intent=%s: %s; primary=%s",
            intent.value,
            missing,
            primary_missing,
        )

        return SlotFillingResult(
            is_complete=False,
            doc_type=intent.value,
            target_slot=primary_missing,
            missing_slots=missing,
            extracted_slots=extracted,
            chip_payload=chip_payload,
            quick_reply_payload=quick_reply,
        )
