"""Unit tests for Adaptive Query Router and Conversational Faceted Slot-Filling Engine.

Governed by FR-3.1, FR-3.2, FR-3.3, and Task 5.2.
"""

from __future__ import annotations

from typing import Any

import pytest

from cuk_assistant.agent.router import (
    AdaptiveRouter,
    RouteDestination,
    RoutingDecision,
)
from cuk_assistant.agent.slot_filler import (
    FacetedSlotFiller,
    QuickReplyPayload,
    SlotChipPayload,
    SlotFillingResult,
)


class TestAdaptiveRouterBasics:
    """Test fundamental routing classifications (greetings, general search, academic)."""

    @pytest.fixture
    def router(self) -> AdaptiveRouter:
        return AdaptiveRouter()

    @pytest.mark.parametrize(
        "query",
        [
            "Hi",
            "hi",
            "Hello",
            "hey there",
            "Good morning",
            "Good evening",
            "good afternoon",
            "assalam u alaikum",
            "Assalamu Alaikum",
            "salam",
            "Who created you?",
            "who are you",
            "What can you do?",
            "introduce yourself",
            "Thank you",
            "thanks a lot",
            "bye",
            "goodbye",
            "how are you",
        ],
    )
    def test_greetings_and_persona_route_to_direct_conversational(
        self, router: AdaptiveRouter, query: str
    ) -> None:
        """Verify greetings ('Hi', 'Good evening', 'Who created you?') route to DIRECT_CONVERSATIONAL."""
        decision = router.route(query)
        assert isinstance(decision, RoutingDecision)
        assert decision.destination == RouteDestination.DIRECT_CONVERSATIONAL
        assert "retrieval" not in decision.reason.lower()

    @pytest.mark.parametrize(
        "query",
        [
            "Where is Green Campus located?",
            "How do I reach Tulmulla campus by bus?",
            "Who is the Vice Chancellor of CUK?",
            "What are the hostel facilities available at Ganderbal?",
            "Tell me about the central library timings.",
            "Is there any transport service from Srinagar to Nunar campus?",
        ],
    )
    def test_general_university_questions_route_to_hybrid_retrieval(
        self, router: AdaptiveRouter, query: str
    ) -> None:
        """Verify general university questions ('Where is Green Campus located?') route to HYBRID_RETRIEVAL."""
        decision = router.route(query)
        assert isinstance(decision, RoutingDecision)
        assert decision.destination == RouteDestination.HYBRID_RETRIEVAL
        assert decision.slot_chips is None

    def test_course_code_extraction(self, router: AdaptiveRouter) -> None:
        """Verify course code extraction ('BT-101 details') accurately captures course_code='BT-101'."""
        decision = router.route("BT-101 details")
        assert decision.destination == RouteDestination.HYBRID_RETRIEVAL
        assert decision.extracted_entities.get("course_code") == "BT-101"

    @pytest.mark.parametrize(
        ("query", "expected_code"),
        [
            ("Tell me about BT-CSE-401 course", "BT-CSE-401"),
            ("What is covered in CS-101?", "CS-101"),
            ("Syllabus outline for MEC-201", "MEC-201"),
        ],
    )
    def test_various_course_codes_extracted(
        self, router: AdaptiveRouter, query: str, expected_code: str
    ) -> None:
        decision = router.route(query)
        assert decision.extracted_entities.get("course_code") == expected_code


class TestFacetedSlotFiller:
    """Test slot extraction, completeness evaluation, and disambiguation chips."""

    @pytest.fixture
    def slot_filler(self) -> FacetedSlotFiller:
        return FacetedSlotFiller()

    def test_incomplete_academic_query_triggers_missing_slot_chips(
        self, slot_filler: FacetedSlotFiller
    ) -> None:
        """Verify incomplete academic query ('Show me the DBMS syllabus') triggers missing_slot='batch_year' or 'semester' with interactive chips."""
        result = slot_filler.fill_slots("Show me the DBMS syllabus")
        assert isinstance(result, SlotFillingResult)
        assert not result.is_complete
        assert result.doc_type == "syllabus"
        assert result.missing_slot in ("batch_year", "semester")
        assert result.chip_payload is not None
        assert isinstance(result.chip_payload, SlotChipPayload)
        assert result.chip_payload.missing_slot in ("batch_year", "semester")
        assert len(result.chip_payload.chips) > 0

        # Verify chip format
        for chip in result.chip_payload.chips:
            assert "label" in chip
            assert "value" in chip

        # Verify QuickReplyPayload API contract conformance
        assert result.quick_reply_payload is not None
        assert isinstance(result.quick_reply_payload, QuickReplyPayload)
        assert result.quick_reply_payload.target_slot in ("batch_year", "semester")
        assert len(result.quick_reply_payload.options) > 0

    def test_complete_academic_query_resolves_all_slots(
        self, slot_filler: FacetedSlotFiller
    ) -> None:
        """Verify complete academic query ('B.Tech CSE 2022 batch 4th semester DBMS syllabus') returns is_complete=True with filter."""
        query = "B.Tech CSE 2022 batch 4th semester DBMS syllabus"
        result = slot_filler.fill_slots(query)
        assert result.is_complete
        assert result.doc_type == "syllabus"
        assert result.missing_slots == []
        assert result.chip_payload is None
        assert result.extracted_slots["program"] == "B.Tech CSE"
        assert result.extracted_slots["batch_year"] == "2022"
        assert result.extracted_slots["semester"] == "Semester 4"
        assert result.metadata_filter is not None
        assert "doc_type == 'syllabus'" in result.metadata_filter
        assert "program == 'B.Tech CSE'" in result.metadata_filter
        assert "batch_year == '2022'" in result.metadata_filter
        assert "semester == 'Semester 4'" in result.metadata_filter

    def test_conversational_multi_turn_slot_accumulation(
        self, slot_filler: FacetedSlotFiller
    ) -> None:
        """Test multi-turn slot resolution across turns simulating session store context."""
        # Turn 1: Generic syllabus inquiry -> missing program
        t1 = slot_filler.fill_slots("Show me the syllabus")
        assert not t1.is_complete
        assert t1.missing_slot == "program"
        assert t1.chip_payload is not None
        assert any(c["value"] == "B.Tech CSE" for c in t1.chip_payload.chips)

        # Turn 2: User specifies program -> missing batch_year
        session = {"program": "B.Tech CSE"}
        t2 = slot_filler.fill_slots("syllabus", session_slots=session)
        assert not t2.is_complete
        assert t2.missing_slot == "batch_year"
        assert any(c["value"] == "2022" for c in t2.chip_payload.chips)  # type: ignore[union-attr]

        # Turn 3: User specifies batch_year -> missing semester
        session["batch_year"] = "2022"
        t3 = slot_filler.fill_slots("syllabus", session_slots=session)
        assert not t3.is_complete
        assert t3.missing_slot == "semester"
        assert any(c["value"] == "Semester 4" for c in t3.chip_payload.chips)  # type: ignore[union-attr]

        # Turn 4: User specifies semester -> complete!
        session["semester"] = "Semester 4"
        t4 = slot_filler.fill_slots("DBMS course", session_slots=session)
        assert t4.is_complete
        assert "doc_type == 'syllabus'" in t4.metadata_filter  # type: ignore[operator]


class TestAdaptiveRouterIntegration:
    """Test full routing decisions across academic and non-academic paths."""

    @pytest.fixture
    def router(self) -> AdaptiveRouter:
        return AdaptiveRouter()

    def test_incomplete_academic_query_routes_to_faceted_academic(
        self, router: AdaptiveRouter
    ) -> None:
        """Incomplete syllabus query routes to FACETED_ACADEMIC with chips."""
        decision = router.route("Show me the DBMS syllabus")
        assert decision.destination == RouteDestination.FACETED_ACADEMIC
        assert decision.slot_chips is not None
        assert decision.slot_chips.missing_slot in ("batch_year", "semester")
        assert len(decision.slot_chips.chips) > 0
        assert decision.quick_replies is not None

    def test_complete_academic_query_routes_to_hybrid_retrieval(
        self, router: AdaptiveRouter
    ) -> None:
        """Complete academic query routes to HYBRID_RETRIEVAL with metadata filter."""
        query = "B.Tech CSE 2022 batch 4th semester DBMS syllabus"
        decision = router.route(query)
        assert decision.destination == RouteDestination.HYBRID_RETRIEVAL
        assert decision.metadata_filter is not None
        assert "program == 'B.Tech CSE'" in decision.metadata_filter
        assert decision.extracted_entities["program"] == "B.Tech CSE"
        assert decision.extracted_entities["batch_year"] == "2022"
        assert decision.extracted_entities["semester"] == "Semester 4"

    def test_entity_preprocessing_circular_id_and_academic_year(
        self, router: AdaptiveRouter
    ) -> None:
        """Verify FR-3.2 circular ID and academic year extraction."""
        query = "Details regarding circular CUKmr/Acad/24/09 for academic session 2023-24"
        decision = router.route(query)
        assert decision.destination == RouteDestination.HYBRID_RETRIEVAL
        assert decision.extracted_entities.get("circular_id") == "CUKmr/Acad/24/09"
        assert decision.extracted_entities.get("academic_year") == "2023-24"

    def test_entity_preprocessing_negation_terms(self, router: AdaptiveRouter) -> None:
        """Verify FR-3.2 negation terms extraction."""
        query = "Show elective courses excluding BT-101 and not requiring lab without prerequisites"
        decision = router.route(query)
        assert "negations" in decision.extracted_entities
        negations = decision.extracted_entities["negations"]
        assert "excluding" in negations
        assert "not" in negations
        assert "without" in negations

    def test_exam_result_query_slot_filling(self, router: AdaptiveRouter) -> None:
        """Test examination result query routing and slot handling."""
        # Missing semester / program
        d1 = router.route("Check exam results")
        assert d1.destination == RouteDestination.FACETED_ACADEMIC
        assert d1.slot_chips is not None
        assert d1.slot_chips.missing_slot == "program"

        # Complete result query
        d2 = router.route("B.Tech CSE 6th semester exam results Autumn 2024")
        assert d2.destination == RouteDestination.HYBRID_RETRIEVAL
        assert d2.extracted_entities.get("program") == "B.Tech CSE"
        assert d2.extracted_entities.get("semester") == "Semester 6"

    def test_datesheet_query_slot_filling(self, router: AdaptiveRouter) -> None:
        """Test date sheet query routing."""
        d1 = router.route("Give me the datesheet for B.Tech CSE")
        assert d1.destination == RouteDestination.FACETED_ACADEMIC
        assert d1.slot_chips is not None
        assert d1.slot_chips.missing_slot == "semester"

        d2 = router.route("Give me the datesheet for B.Tech CSE 4th semester")
        assert d2.destination == RouteDestination.HYBRID_RETRIEVAL

    def test_deflection_integration(self) -> None:
        """Verify guardrail deflection yields RouteDestination.DEFLECTED."""

        class MockInputGuard:
            def validate(self, _text: str) -> Any:
                class GuardRes:
                    is_safe = False
                    is_in_domain = False
                    deflection_message = "Content blocked by safety rail"

                return GuardRes()

        deflected_router = AdaptiveRouter(input_guard=MockInputGuard())
        decision = deflected_router.route("Explosives in chemistry lab")
        assert decision.destination == RouteDestination.DEFLECTED
        assert "safety rail" in decision.reason

    @pytest.mark.asyncio
    async def test_route_async(self, router: AdaptiveRouter) -> None:
        """Verify async routing interface."""
        decision = await router.route_async("Hello")
        assert decision.destination == RouteDestination.DIRECT_CONVERSATIONAL
