"""Unit tests for Telemetry Protocol, 12-Diagnostic Failure Attribution Engine, and InMemoryTelemetrySink.

Governed by FR-8.2, NFR-3.2, and GEMINI.md.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

import pytest

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    FailureEvent,
    FeedbackEvent,
    SpanAttributes,
    TelemetrySinkProtocol,
)
from cuk_assistant.observability.failure_attribution import (
    DIAGNOSTIC_REGISTRY,
    ContextTruncationException,
    CorpusMissingContentException,
    DiagnosticAttributor,
    GuardrailBlockedException,
    LLMExtractionFailureException,
    LLMFormatViolationException,
    LLMHallucinationException,
    MissedTopRankedException,
    OutputSafetyViolationException,
    ParsingDefectException,
    QuestionParsingFailedException,
    RetrievalEmptyException,
    RetrievalRecallMissException,
)
from cuk_assistant.observability.in_memory_sink import (
    InMemoryTelemetrySink,
)


class TestDiagnosticTaxonomyMatrix:
    """Validate completeness, severity levels, and subsystem attribution of the 12 failure codes."""

    EXPECTED_CODES = {
        "GUARDRAIL_BLOCKED",
        "PARSING_DEFECT",
        "QUESTION_PARSING_FAILED",
        "RETRIEVAL_EMPTY",
        "RETRIEVAL_RECALL_MISS",
        "MISSED_TOP_RANKED",
        "CONTEXT_TRUNCATION",
        "LLM_EXTRACTION_FAILURE",
        "LLM_HALLUCINATION",
        "LLM_FORMAT_VIOLATION",
        "OUTPUT_SAFETY_VIOLATION",
        "CORPUS_MISSING_CONTENT",
    }

    VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    VALID_SUBSYSTEMS = {"guardrails", "ingestion", "retrieval", "llm", "agent"}

    def test_canonical_12_codes_exist_in_enum(self) -> None:
        enum_members = {code.value for code in FailureDiagnosticCode}
        assert enum_members == self.EXPECTED_CODES
        assert len(FailureDiagnosticCode) == 12

    def test_all_12_codes_registered_in_dictionary(self) -> None:
        assert len(DIAGNOSTIC_REGISTRY) == 12
        for code in FailureDiagnosticCode:
            assert code in DIAGNOSTIC_REGISTRY
            meta = DIAGNOSTIC_REGISTRY[code]
            assert meta.code == code
            assert meta.severity in self.VALID_SEVERITIES
            assert meta.subsystem in self.VALID_SUBSYSTEMS
            assert isinstance(meta.remediation_action, str) and len(meta.remediation_action) > 10
            assert isinstance(meta.user_safe_message, str) and len(meta.user_safe_message) > 10

    def test_diagnostic_attributor_helper_getters(self) -> None:
        for code in FailureDiagnosticCode:
            meta = DiagnosticAttributor.get_metadata(code)
            assert DiagnosticAttributor.get_severity(code) == meta.severity
            assert DiagnosticAttributor.get_subsystem(code) == meta.subsystem
            assert DiagnosticAttributor.get_remediation(code) == meta.remediation_action
            assert DiagnosticAttributor.get_user_safe_message(code) == meta.user_safe_message

    def test_diagnostic_attributor_invalid_code_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="Unknown diagnostic failure code"):
            DiagnosticAttributor.get_metadata("UNKNOWN_CODE")  # type: ignore[arg-type]


class TestExceptionClassification:
    """Validate that classify_exception maps exceptions and contexts to exact diagnostic codes."""

    def test_empty_retrieval_candidates_assigned_retrieval_empty(self) -> None:
        # Via context candidates list
        event1 = DiagnosticAttributor.classify_exception(
            Exception("Empty search results"),
            context={"candidates": []},
        )
        assert event1.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_EMPTY
        assert event1.component == "retrieval"
        assert "candidates" in event1.details

        # Via custom typed exception
        event2 = DiagnosticAttributor.classify_exception(
            RetrievalEmptyException("Zero chunks returned")
        )
        assert event2.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_EMPTY
        assert event2.component == "retrieval"

        # Via exception message keyword
        event3 = DiagnosticAttributor.classify_exception(
            RuntimeError("0 candidate found in hybrid search")
        )
        assert event3.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_EMPTY

    def test_hallucinated_quotes_assigned_llm_hallucination(self) -> None:
        # Via context unverified quotes
        event1 = DiagnosticAttributor.classify_exception(
            ValueError("Fact check mismatch"),
            context={"unverified_quotes": ["Non-existent circular clause"]},
        )
        assert event1.diagnostic_code == FailureDiagnosticCode.LLM_HALLUCINATION
        assert event1.component == "guardrails"

        # Via custom exception
        event2 = DiagnosticAttributor.classify_exception(LLMHallucinationException())
        assert event2.diagnostic_code == FailureDiagnosticCode.LLM_HALLUCINATION
        assert event2.component == "guardrails"

        # Via exception message keyword
        event3 = DiagnosticAttributor.classify_exception(
            RuntimeError("Verbatim citation check failed: hallucination")
        )
        assert event3.diagnostic_code == FailureDiagnosticCode.LLM_HALLUCINATION

    def test_injection_block_assigned_guardrail_blocked(self) -> None:
        # Via context injection flag
        event1 = DiagnosticAttributor.classify_exception(
            PermissionError("Security policy rejection"),
            context={"is_injection": True},
        )
        assert event1.diagnostic_code == FailureDiagnosticCode.GUARDRAIL_BLOCKED
        assert event1.component == "guardrails"

        # Via custom exception
        event2 = DiagnosticAttributor.classify_exception(
            GuardrailBlockedException("Prompt injection detected")
        )
        assert event2.diagnostic_code == FailureDiagnosticCode.GUARDRAIL_BLOCKED
        assert event2.component == "guardrails"

        # Via exception message keyword
        event3 = DiagnosticAttributor.classify_exception(
            RuntimeError("Blocked by prompt_injection safety rule")
        )
        assert event3.diagnostic_code == FailureDiagnosticCode.GUARDRAIL_BLOCKED

    def test_output_toxicity_assigned_output_safety_violation(self) -> None:
        # Via context toxicity flag
        event1 = DiagnosticAttributor.classify_exception(
            ValueError("Output flagged"),
            context={"toxicity": True},
        )
        assert event1.diagnostic_code == FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION
        assert event1.component == "guardrails"

        # Via custom exception
        event2 = DiagnosticAttributor.classify_exception(OutputSafetyViolationException())
        assert event2.diagnostic_code == FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION
        assert event2.component == "guardrails"

        # Via exception message keyword
        event3 = DiagnosticAttributor.classify_exception(
            RuntimeError("Output safety violation: phone PII leaked")
        )
        assert event3.diagnostic_code == FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION

    def test_parsing_defect_classification(self) -> None:
        event1 = DiagnosticAttributor.classify_exception(
            ParsingDefectException("PDF stream corrupt")
        )
        assert event1.diagnostic_code == FailureDiagnosticCode.PARSING_DEFECT
        assert event1.component == "ingestion"

        event2 = DiagnosticAttributor.classify_exception(
            RuntimeError("Docling layout parse_pdf failed")
        )
        assert event2.diagnostic_code == FailureDiagnosticCode.PARSING_DEFECT

    def test_question_parsing_failed_classification(self) -> None:
        event1 = DiagnosticAttributor.classify_exception(QuestionParsingFailedException())
        assert event1.diagnostic_code == FailureDiagnosticCode.QUESTION_PARSING_FAILED
        assert event1.component == "retrieval"

        event2 = DiagnosticAttributor.classify_exception(
            ValueError("Cannot infer program or semester"),
            context={"missing_slots": ["program", "batch_year"]},
        )
        assert event2.diagnostic_code == FailureDiagnosticCode.QUESTION_PARSING_FAILED

    def test_retrieval_recall_miss_classification(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            RetrievalRecallMissException("Circular CUK/Acad/2024/09 absent"),
            context={"missing_circular_id": "CUK/Acad/2024/09"},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_RECALL_MISS
        assert event.component == "retrieval"

    def test_missed_top_ranked_classification(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            MissedTopRankedException(),
            context={"reason": "missed_top_ranked"},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.MISSED_TOP_RANKED
        assert event.component == "retrieval"

    def test_context_truncation_classification(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            ContextTruncationException(),
            context={"truncated_tokens": 1500},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.CONTEXT_TRUNCATION
        assert event.component == "llm"

    def test_llm_extraction_failure_classification(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            LLMExtractionFailureException(),
            context={"reason": "extraction_failure"},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.LLM_EXTRACTION_FAILURE
        assert event.component == "llm"

    def test_llm_format_violation_classification(self) -> None:
        event1 = DiagnosticAttributor.classify_exception(LLMFormatViolationException())
        assert event1.diagnostic_code == FailureDiagnosticCode.LLM_FORMAT_VIOLATION
        assert event1.component == "llm"

        event2 = DiagnosticAttributor.classify_exception(
            ValueError("JSON decode error in structured LLM response")
        )
        assert event2.diagnostic_code == FailureDiagnosticCode.LLM_FORMAT_VIOLATION

    def test_corpus_missing_content_classification(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            CorpusMissingContentException(),
            context={"reason": "corpus_missing"},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.CORPUS_MISSING_CONTENT
        assert event.component == "guardrails"

    def test_explicit_diagnostic_code_in_context(self) -> None:
        event = DiagnosticAttributor.classify_exception(
            Exception("Generic defect"),
            context={
                "diagnostic_code": FailureDiagnosticCode.RETRIEVAL_RECALL_MISS,
                "trace_id": "test_trc_001",
            },
        )
        assert event.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_RECALL_MISS
        assert event.trace_id == "test_trc_001"

    def test_trace_id_generation_and_preservation(self) -> None:
        event_auto = DiagnosticAttributor.classify_exception(RetrievalEmptyException())
        assert len(event_auto.trace_id) == 32  # UUID hex length

        event_explicit = DiagnosticAttributor.classify_exception(
            RetrievalEmptyException(),
            context={"trace_id": "custom-trace-uuid-123"},
        )
        assert event_explicit.trace_id == "custom-trace-uuid-123"


class TestSpanFormatting:
    """Validate OpenTelemetry-compliant span tags."""

    def test_format_span_error_tags(self) -> None:
        failure = FailureEvent(
            trace_id="trc_999",
            diagnostic_code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
            component="retrieval",
            error_message="Zero candidates returned for query",
            remediation_hint="Trigger ScopeFallbackHandler to remove scoped filter",
            details={"where_filter": "program=CSE", "query": "DBMS", "attempt": 1},
        )
        tags = DiagnosticAttributor.format_span_error_tags(failure)

        assert tags["error"] is True
        assert tags["cuk.diagnostic_code"] == "RETRIEVAL_EMPTY"
        assert tags["cuk.remediation"] == failure.remediation_hint
        assert tags["cuk.subsystem"] == "retrieval"
        assert tags["cuk.severity"] == "MEDIUM"
        assert tags["cuk.user_safe_message"] == DiagnosticAttributor.get_user_safe_message(
            FailureDiagnosticCode.RETRIEVAL_EMPTY
        )
        assert tags["cuk.component"] == "retrieval"
        assert tags["error.type"] == "RETRIEVAL_EMPTY"
        assert tags["error.message"] == failure.error_message
        assert tags["cuk.details.where_filter"] == "program=CSE"
        assert tags["cuk.details.attempt"] == 1


class TestInMemoryTelemetrySink:
    """Validate thread-safety, protocol satisfaction, and fail-open behavior of InMemoryTelemetrySink."""

    def test_implements_telemetry_sink_protocol(self) -> None:
        sink = InMemoryTelemetrySink()
        assert isinstance(sink, TelemetrySinkProtocol)

    def test_log_span_and_inspection(self) -> None:
        sink = InMemoryTelemetrySink()
        sink.log_span(
            "retrieval.hybrid_search", {"trace_id": "trc_1", "component": "retrieval"}, 12.5
        )
        sink.log_span("llm.generation", {"trace_id": "trc_2", "component": "llm"}, 240.0)

        spans = sink.get_spans()
        assert len(spans) == 2
        assert spans[0]["name"] == "retrieval.hybrid_search"
        assert spans[0].name == "retrieval.hybrid_search"
        assert spans[0]["duration_ms"] == 12.5
        assert spans[0].duration_ms == 12.5

        # Filter by trace_id
        trc_1_spans = sink.get_spans(trace_id="trc_1")
        assert len(trc_1_spans) == 1
        assert trc_1_spans[0]["name"] == "retrieval.hybrid_search"

    def test_tag_failure_and_inspection(self) -> None:
        sink = InMemoryTelemetrySink()
        sink.tag_failure(
            trace_id="trc_fail_1",
            diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
            details={"reason": "injection", "component": "guardrails"},
        )

        failures = sink.get_failures()
        assert len(failures) == 1
        assert failures[0]["trace_id"] == "trc_fail_1"
        assert failures[0].trace_id == "trc_fail_1"
        assert failures[0]["diagnostic_code"] == FailureDiagnosticCode.GUARDRAIL_BLOCKED
        assert failures[0].diagnostic_code == FailureDiagnosticCode.GUARDRAIL_BLOCKED

        # Filter by trace_id
        filtered = sink.get_failures(trace_id="non_existent")
        assert len(filtered) == 0

    def test_record_feedback_and_inspection(self) -> None:
        sink = InMemoryTelemetrySink()
        sink.record_feedback("trc_fb_1", 1, feedback_category="helpful", comment="Clear syllabus")
        sink.record_feedback("trc_fb_2", -1, feedback_category="incorrect", comment="Wrong date")

        feedbacks = sink.get_feedbacks()
        assert len(feedbacks) == 2
        assert feedbacks[0]["score"] == 1
        assert feedbacks[0].score == 1
        assert feedbacks[1]["score"] == -1
        assert feedbacks[1].score == -1

        # Filter by trace_id
        f1 = sink.get_feedbacks(trace_id="trc_fb_1")
        assert len(f1) == 1
        assert f1[0]["feedback_category"] == "helpful"

    def test_clear_resets_all_collections(self) -> None:
        sink = InMemoryTelemetrySink()
        sink.log_span("test.span", {}, 5.0)
        sink.tag_failure("trc_1", FailureDiagnosticCode.RETRIEVAL_EMPTY, {})
        sink.record_feedback("trc_1", 1)

        assert sink.count_spans() == 1
        assert sink.count_failures() == 1
        assert sink.count_feedbacks() == 1
        assert len(sink) == 3

        sink.clear()
        assert sink.count_spans() == 0
        assert sink.count_failures() == 0
        assert sink.count_feedbacks() == 0
        assert len(sink) == 0

    def test_concurrency_thread_safety(self) -> None:
        sink = InMemoryTelemetrySink(max_records=5000)
        num_threads = 10
        ops_per_thread = 50

        def worker(worker_id: int) -> None:
            for i in range(ops_per_thread):
                tid = f"trc_w{worker_id}_{i}"
                sink.log_span(f"span_{worker_id}", {"trace_id": tid}, 1.0)
                sink.tag_failure(tid, FailureDiagnosticCode.QUESTION_PARSING_FAILED, {"idx": i})
                sink.record_feedback(tid, 1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, wid) for wid in range(num_threads)]
            concurrent.futures.wait(futures)

        total_ops = num_threads * ops_per_thread
        assert sink.count_spans() == total_ops
        assert sink.count_failures() == total_ops
        assert sink.count_feedbacks() == total_ops
        assert len(sink) == total_ops * 3

    def test_fail_open_isolation_invariant(self) -> None:
        """NFR-3.2: Logging must fail-open and never raise unhandled exceptions."""
        sink = InMemoryTelemetrySink()

        class FaultyDict(dict[str, Any]):
            def __getitem__(self, key: str) -> Any:
                raise RuntimeError("Simulated memory error")

        # Passing corrupted / exploding payload should fail open without raising
        sink.log_span("faulty.span", FaultyDict(), 10.0)
        sink.tag_failure("trc_fault", "NOT_A_VALID_CODE", FaultyDict())  # type: ignore[arg-type]
        sink.record_feedback("trc_fault", "invalid_score")  # type: ignore[arg-type]

        # Verify sink remains functional
        sink.log_span("healthy.span", {}, 2.0)
        assert sink.count_spans() >= 1


class TestDataModels:
    """Validate Pydantic models for SpanAttributes, FailureEvent, and FeedbackEvent."""

    def test_span_attributes_instantiation(self) -> None:
        span = SpanAttributes(
            trace_id="trc_123",
            component="retrieval",
            duration_ms=45.2,
            span_name="fastembed.inference",
            attributes={"dim": 384},
        )
        assert span.trace_id == "trc_123"
        assert span.component == "retrieval"
        assert span.duration_ms == 45.2

    def test_failure_event_instantiation(self) -> None:
        event = FailureEvent(
            trace_id="trc_456",
            diagnostic_code=FailureDiagnosticCode.LLM_EXTRACTION_FAILURE,
            component="llm",
            error_message="Answer could not be synthesized",
            remediation_hint="Switch to secondary provider",
            details={"provider": "gemini"},
        )
        assert event.diagnostic_code == FailureDiagnosticCode.LLM_EXTRACTION_FAILURE
        assert event.component == "llm"

    def test_feedback_event_instantiation(self) -> None:
        fb = FeedbackEvent(
            trace_id="trc_789",
            score=1,
            category="accuracy",
            comment="Exact syllabus retrieved",
        )
        assert fb.score == 1
        assert fb.category == "accuracy"
