"""Adaptive Query Router for Central University of Kashmir (CUK) Assistant.

Implements FR-3.1, FR-3.2, and Architecture Section 4:
1. Deterministic conversational classification (greetings, persona, small-talk) -> $0 latency.
2. Regex & rule entity preprocessing (circular IDs, academic years, course codes, negations).
3. Academic intent routing & faceted slot-filling disambiguation (FR-3.3).
4. Direct hybrid retrieval routing for general campus inquiries.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.agent.slot_filler import (
    AcademicIntentType,
    FacetedSlotFiller,
    QuickReplyPayload,
    SlotChipPayload,
    SlotFillingResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing Destinations & Models (Task 5.2 Specification)
# ---------------------------------------------------------------------------


class RouteDestination(StrEnum):
    """Target destination for an incoming user query."""

    DIRECT_CONVERSATIONAL = "direct_conversational"  # Greetings, bot persona, thanks
    FACETED_ACADEMIC = "faceted_academic"  # Syllabus, results, admissions needing slots
    HYBRID_RETRIEVAL = "hybrid_retrieval"  # General factual university queries
    DEFLECTED = "deflected"  # Handled by guardrail


class RoutingDecision(BaseModel):
    """Structured decision returned by the Adaptive Query Router."""

    model_config = ConfigDict(extra="forbid")

    destination: RouteDestination
    normalized_query: str
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    reason: str
    slot_chips: SlotChipPayload | None = None
    quick_replies: QuickReplyPayload | None = None
    metadata_filter: str | None = None
    slot_result: SlotFillingResult | None = None


# ---------------------------------------------------------------------------
# Regex Patterns for Entity Extraction (FR-3.2) & Intent Routing
# ---------------------------------------------------------------------------

# Circular and notification reference numbers (e.g. CUK/Acad/2023/123, CUKmr/Acad/24/09)
CIRCULAR_ID_RE = re.compile(
    r"\b((?:F\.?\s*No\.?\s*)?CUK(?:mr)?/[A-Za-z0-9_/.-]+)\b",
    re.IGNORECASE,
)
NOTIFICATION_NO_RE = re.compile(
    r"\b(?:Notification\s*(?:No\.?|Number)?\s*[:#-]?\s*)([A-Za-z0-9_/-]+)\b",
    re.IGNORECASE,
)

# Academic year formats (e.g. 2023-24, 2022-2023)
ACADEMIC_YEAR_RE = re.compile(r"\b(20\d{2})[-/](20\d{2}|\d{2})\b")

# Course code formats (e.g. BT-101, BT-CSE-401, CS-101, MEC-201)
COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{2,4}(?:-[A-Za-z]{2,4})?[- ]?\d{3}[A-Za-z]?)\b")

# Negation terms (FR-3.2)
NEGATION_TERMS_RE = re.compile(
    r"\b(not|except|excluding|without|other\s+than)\b",
    re.IGNORECASE,
)

# Substantive university keywords indicating non-conversational intent
UNIVERSITY_SUBSTANTIVE_KEYWORDS = re.compile(
    r"\b(campus|tulmulla|nunar|ganderbal|hostel|transport|fee|fees|admission|admissions|"
    r"syllabus|curriculum|result|results|exam|examination|datesheet|date\s*sheet|cutoff|"
    r"cut-off|department|school|faculty|vice\s*chancellor|vc|registrar|library|timing|timings|"
    r"counseling|merit|ordinance|statute|scholarship|convocation)\b",
    re.IGNORECASE,
)

# Conversational greetings & expressions
GREETING_RE = re.compile(
    r"^(hi|hello|hey|heya|hiya|howdy|greetings|assalam\s*u?\s*alaikum|"
    r"assalamu\s*alaikum|walaikum\s*assalam|salam|slaam|"
    r"good\s*(?:morning|afternoon|evening|day|night))"
    r"(\s+(?:there|bot|assistant|friend|everyone))?[\s.!,]*$",
    re.IGNORECASE,
)

# Conversational gratitude & appreciation
GRATITUDE_RE = re.compile(
    r"^(thank\s*you(?:\s+(?:so\s+much|very\s+much|a\s+lot))?|"
    r"thanks(?:\s+(?:a\s+lot|a\s+bunch|so\s+much|very\s+much|again))?|"
    r"thx|jazakallah|shukriya|much\s*appreciated|"
    r"many\s*thanks)[\s.!,]*$",
    re.IGNORECASE,
)

# Conversational farewells
FAREWELL_RE = re.compile(
    r"^(bye|goodbye|see\s*you|take\s*care|cya|good\s*night)[\s.!,]*$",
    re.IGNORECASE,
)

# Identity, persona, and meta queries
PERSONA_RE = re.compile(
    r"^(who\s*(?:are\s*you|created\s*you|made\s*you|built\s*you|developed\s*you|are\s*u)|"
    r"what\s*(?:are\s*you|is\s*your\s*name|can\s*you\s*do|do\s*you\s*do)|"
    r"tell\s*me\s*about\s*yourself|introduce\s*yourself|help\s*me|help)[\s.?!]*$",
    re.IGNORECASE,
)

# Small talk
SMALLTALK_RE = re.compile(
    r"^(how\s*are\s*you|how\s*do\s*you\s*do|what'?s\s*up|how\s*is\s*it\s*going)[\s.?!]*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# AdaptiveRouter Engine
# ---------------------------------------------------------------------------


class AdaptiveRouter:
    """Adaptive front-door query classifier and routing engine."""

    def __init__(
        self,
        slot_filler: FacetedSlotFiller | None = None,
        domain_classifier: Any | None = None,
        input_guard: Any | None = None,
    ) -> None:
        self.slot_filler = slot_filler or FacetedSlotFiller()
        self.domain_classifier = domain_classifier
        self.input_guard = input_guard

    def normalize_query(self, query: str) -> str:
        """Clean and normalize raw query text."""
        cleaned = query.strip()
        # Collapse multi-spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def extract_entities(self, query: str) -> dict[str, Any]:
        """Extract circular IDs, academic years, course codes, and negations (FR-3.2)."""
        entities: dict[str, Any] = {}

        # 1. Circular ID / Notification Number
        circ_match = CIRCULAR_ID_RE.search(query)
        if circ_match:
            entities["circular_id"] = circ_match.group(1).strip()
        else:
            notif_match = NOTIFICATION_NO_RE.search(query)
            if notif_match:
                entities["circular_id"] = notif_match.group(1).strip()

        # 2. Academic Year range (e.g. 2023-24)
        acad_match = ACADEMIC_YEAR_RE.search(query)
        if acad_match:
            entities["academic_year"] = acad_match.group(0).strip()

        # 3. Course Code (e.g. BT-101, BT-CSE-401, CS-101)
        code_match = COURSE_CODE_RE.search(query)
        if code_match:
            candidate_code = code_match.group(1).upper().replace(" ", "-")
            # Exclude false positives matching circular prefixes
            if not candidate_code.startswith("CUK") and "/" not in candidate_code:
                entities["course_code"] = candidate_code

        # 4. Negation terms
        neg_matches = NEGATION_TERMS_RE.findall(query)
        if neg_matches:
            entities["negations"] = [m.lower() for m in neg_matches]

        # 5. Extract domain slots (program, batch, semester) via slot filler
        slots = self.slot_filler.extract_slots(query)
        for k, v in slots.items():
            if v is not None and k not in entities:
                entities[k] = v

        return entities

    def is_conversational(self, normalized_query: str) -> tuple[bool, str]:
        """Check if query is purely conversational, persona, or small-talk."""
        # If query contains substantive university keywords or course codes, it requires retrieval
        if UNIVERSITY_SUBSTANTIVE_KEYWORDS.search(normalized_query):
            return False, "Contains substantive university terms"

        if COURSE_CODE_RE.search(normalized_query) and "details" in normalized_query.lower():
            return False, "Course code inquiry requires retrieval"

        if CIRCULAR_ID_RE.search(normalized_query):
            return False, "Circular inquiry requires retrieval"

        # Check conversational patterns
        if GREETING_RE.match(normalized_query):
            return True, "Greeting detected"

        if PERSONA_RE.match(normalized_query):
            return True, "Identity or persona query detected"

        if GRATITUDE_RE.match(normalized_query):
            return True, "Gratitude expression detected"

        if FAREWELL_RE.match(normalized_query):
            return True, "Farewell expression detected"

        if SMALLTALK_RE.match(normalized_query):
            return True, "Small-talk detected"

        return False, "Not purely conversational"

    def route(
        self,
        query: str,
        session_slots: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        """Route user query to appropriate pipeline destination."""
        normalized = self.normalize_query(query)
        extracted = self.extract_entities(normalized)

        # 1. Check Input Guard / Domain Classifier for safety and scope
        if self.input_guard is not None:
            guard_result = self.input_guard.validate(normalized)
            if not guard_result.is_safe or not guard_result.is_in_domain:
                return RoutingDecision(
                    destination=RouteDestination.DEFLECTED,
                    normalized_query=normalized,
                    extracted_entities=extracted,
                    reason=guard_result.deflection_message or "Guardrail deflection",
                )
        elif self.domain_classifier is not None:
            is_in_domain, deflection = self.domain_classifier.classify(normalized)
            if not is_in_domain:
                return RoutingDecision(
                    destination=RouteDestination.DEFLECTED,
                    normalized_query=normalized,
                    extracted_entities=extracted,
                    reason=deflection or "Out-of-domain deflection",
                )

        # 2. Conversational Intent Check (Greetings, Small-talk, Persona)
        is_conv, conv_reason = self.is_conversational(normalized)
        if is_conv:
            logger.debug("Routing to DIRECT_CONVERSATIONAL: %s (%s)", normalized, conv_reason)
            return RoutingDecision(
                destination=RouteDestination.DIRECT_CONVERSATIONAL,
                normalized_query=normalized,
                extracted_entities=extracted,
                reason=conv_reason,
            )

        # 3. Academic Faceted Intent Check (Syllabus, Results, Date sheets, Admissions)
        academic_intent = self.slot_filler.detect_academic_intent(normalized)
        if academic_intent in (
            AcademicIntentType.SYLLABUS,
            AcademicIntentType.RESULT,
            AcademicIntentType.DATESHEET,
            AcademicIntentType.ADMISSION,
        ):
            slot_res = self.slot_filler.fill_slots(
                normalized,
                session_slots=session_slots,
                force_intent=academic_intent,
            )

            # Update entities with extracted slots
            extracted.update(slot_res.extracted_slots)

            if not slot_res.is_complete:
                # Incomplete academic query: trigger interactive disambiguation chips
                reason = (
                    f"Incomplete {academic_intent.value} query; missing mandatory slot(s): "
                    f"{', '.join(slot_res.missing_slots)}"
                )
                logger.debug("Routing to FACETED_ACADEMIC: %s", reason)
                return RoutingDecision(
                    destination=RouteDestination.FACETED_ACADEMIC,
                    normalized_query=normalized,
                    extracted_entities=extracted,
                    reason=reason,
                    slot_chips=slot_res.chip_payload,
                    quick_replies=slot_res.quick_reply_payload,
                    slot_result=slot_res,
                )
            else:
                # All slots are satisfied: proceed directly to hybrid retrieval with filter
                reason = f"Complete {academic_intent.value} query with all required slots satisfied"
                logger.debug(
                    "Routing to HYBRID_RETRIEVAL with scoped filter: %s", slot_res.metadata_filter
                )
                return RoutingDecision(
                    destination=RouteDestination.HYBRID_RETRIEVAL,
                    normalized_query=normalized,
                    extracted_entities=extracted,
                    reason=reason,
                    metadata_filter=slot_res.metadata_filter,
                    slot_result=slot_res,
                )

        # 4. Default: General In-Domain University Inquiry (Locations, timings, general rules)
        logger.debug("Routing to HYBRID_RETRIEVAL: general university inquiry")
        return RoutingDecision(
            destination=RouteDestination.HYBRID_RETRIEVAL,
            normalized_query=normalized,
            extracted_entities=extracted,
            reason="General university inquiry ready for hybrid retrieval",
        )
