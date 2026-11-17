"""Unit tests for OutputGuard, StudentPIIScrubber & Output Safety Rail (Task 4.5)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cuk_assistant.guardrails import (
    CompositeGuardrail,
    FailureDiagnosticCode,
    GuardrailProtocol,
    OutputGuard,
    OutputGuardResult,
    StudentPIIScrubber,
)
from cuk_assistant.guardrails.subsystems.output_guard import (
    DEFAULT_UNSAFE_OUTPUT_REDACTION,
    GroqLlamaGuardOutputRail,
)


class TestStudentPIIScrubber:
    """Test programmatic scrubbing of student PII and preservation of official emails."""

    def setup_method(self) -> None:
        self.scrubber = StudentPIIScrubber()

    def test_phone_numbers_redacted(self) -> None:
        cases = [
            ("Call helpline at +91 9876543210 for admissions.", "[REDACTED_PHONE]"),
            ("Emergency contact: +91-98765-43210 immediately.", "[REDACTED_PHONE]"),
            ("Coordinator mobile: 09876543210.", "[REDACTED_PHONE]"),
            ("Direct phone: 9876543210 available 10am-4pm.", "[REDACTED_PHONE]"),
            ("Reach out on 98765 43210 during office hours.", "[REDACTED_PHONE]"),
        ]
        for input_text, expected_tag in cases:
            scrubbed = self.scrubber.scrub(input_text)
            assert expected_tag in scrubbed, f"Failed for {input_text} -> {scrubbed}"
            assert "9876543210" not in scrubbed
            assert "98765 43210" not in scrubbed

    def test_official_cuk_emails_preserved(self) -> None:
        input_text = (
            "For queries, contact registrar@cukashmir.ac.in or dean.academic@cukashmir.ac.in. "
            "Helpline number is +91 9876543210."
        )
        scrubbed = self.scrubber.scrub(input_text)
        assert "registrar@cukashmir.ac.in" in scrubbed
        assert "dean.academic@cukashmir.ac.in" in scrubbed
        assert "[REDACTED_PHONE]" in scrubbed
        assert "9876543210" not in scrubbed

    def test_aadhaar_numbers_redacted(self) -> None:
        cases = [
            "Student Aadhaar: 1234 5678 9012 verified.",
            "Candidate UID: 1234-5678-9012 submitted.",
            "National ID number: 123456789012 recorded in system.",
        ]
        for input_text in cases:
            scrubbed = self.scrubber.scrub(input_text)
            assert "[REDACTED_ID]" in scrubbed
            assert "1234 5678 9012" not in scrubbed
            assert "123456789012" not in scrubbed

    def test_student_marks_and_grades_tied_to_roll_redacted(self) -> None:
        cases = [
            "Result declared: Roll No: 1904CUK012, Marks: 85/100 in Physics.",
            "Merit: Roll Number: 2024-5678, Grade: A+ awarded.",
            "Student Roll No. 200456 scored 92 marks in Mathematics.",
            "Score sheet: Marks: 78 for Roll No: CUK-9999 in Chemistry.",
        ]
        for input_text in cases:
            scrubbed = self.scrubber.scrub(input_text)
            assert "[REDACTED_MARKS]" in scrubbed, f"Expected [REDACTED_MARKS] in {scrubbed}"
            assert "85/100" not in scrubbed
            assert "92 marks" not in scrubbed


class TestGroqLlamaGuardOutputRail:
    """Test output safety screening and fallback mechanisms."""

    def test_local_heuristic_blocks_toxicity(self) -> None:
        rail = GroqLlamaGuardOutputRail(api_key=None)
        unsafe_text = "Instructions: bomb the university campus immediately."
        is_safe, reason = rail.scan_output(unsafe_text)
        assert is_safe is False
        assert reason is not None

    def test_safe_output_passes(self) -> None:
        rail = GroqLlamaGuardOutputRail(api_key=None)
        safe_text = "The Central University of Kashmir was established in March 2009."
        is_safe, reason = rail.scan_output(safe_text)
        assert is_safe is True
        assert reason is None

    @patch("httpx.Client.post")
    def test_groq_api_unsafe_output(self, mock_post: MagicMock) -> None:
        rail = GroqLlamaGuardOutputRail(api_key="gsk_test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "unsafe\nS1_violent_crimes"}}]
        }
        mock_post.return_value = mock_response

        is_safe, reason = rail.scan_output("Violent threatening response.")
        assert is_safe is False
        assert "unsafe" in reason.lower()


class TestOutputGuardOrchestration:
    """Test full OutputGuard pipeline: moderation, PII scrubbing, and grounding."""

    def setup_method(self) -> None:
        self.guard = OutputGuard(min_snippet_chars=15)
        self.context = [
            "Admissions to Integrated B.Sc-M.Sc Physics are based on CUET-UG score. "
            "The annual fee is Rs 18,500 payable at admission time."
        ]

    def test_safe_grounded_output_passes(self) -> None:
        generated = (
            "Admissions to Integrated B.Sc-M.Sc Physics are based on CUET-UG score. "
            "For assistance, email admissions@cukashmir.ac.in or call +91 9876543210."
        )
        quotes = ["Admissions to Integrated B.Sc-M.Sc Physics are based on CUET-UG score."]
        res: OutputGuardResult = self.guard.validate_and_scrub(
            generated_text=generated,
            quoted_snippets=quotes,
            context_chunks=self.context,
        )
        assert res.is_safe is True
        assert res.is_verbatim_grounded is True
        assert res.diagnostic_code is None
        assert "admissions@cukashmir.ac.in" in res.sanitized_text
        assert "[REDACTED_PHONE]" in res.sanitized_text
        assert "9876543210" not in res.sanitized_text

    def test_hallucinated_quote_triggers_diagnostic(self) -> None:
        generated = (
            "The annual fee is Rs 10,000 payable at admission time. "
            "Official statement: The annual fee is Rs 10,000 payable at admission time."
        )
        hallucinated_quotes = ["The annual fee is Rs 10,000 payable at admission time."]
        res: OutputGuardResult = self.guard.validate_and_scrub(
            generated_text=generated,
            quoted_snippets=hallucinated_quotes,
            context_chunks=self.context,
        )
        assert res.is_safe is True
        assert res.is_verbatim_grounded is False
        assert res.diagnostic_code == FailureDiagnosticCode.LLM_HALLUCINATION

    def test_unsafe_output_blocked_with_output_safety_diagnostic(self) -> None:
        toxic_text = "Go kill yourself and bomb the university."
        res: OutputGuardResult = self.guard.validate_and_scrub(
            generated_text=toxic_text,
            quoted_snippets=[],
            context_chunks=[],
        )
        assert res.is_safe is False
        assert res.sanitized_text == DEFAULT_UNSAFE_OUTPUT_REDACTION
        assert res.diagnostic_code == FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION

    def test_context_as_chunk_objects_with_text_attribute(self) -> None:
        chunk_obj = SimpleNamespace(text="The campus is located at Tulmulla, Ganderbal.")
        generated = "The campus is located at Tulmulla, Ganderbal."
        quotes = ["The campus is located at Tulmulla, Ganderbal."]

        res = self.guard.validate_and_scrub(
            generated_text=generated,
            quoted_snippets=quotes,
            context_chunks=[chunk_obj],
        )
        assert res.is_safe is True
        assert res.is_verbatim_grounded is True

    @pytest.mark.asyncio
    async def test_async_validate_and_scrub(self) -> None:
        generated = "Admissions to Integrated B.Sc-M.Sc Physics are based on CUET-UG score."
        quotes = ["Admissions to Integrated B.Sc-M.Sc Physics are based on CUET-UG score."]
        res = await self.guard.validate_and_scrub_async(
            generated_text=generated,
            quoted_snippets=quotes,
            context_chunks=self.context,
        )
        assert res.is_safe is True
        assert res.is_verbatim_grounded is True


class TestGuardrailProtocolConformance:
    """Verify runtime conformance with GuardrailProtocol."""

    def test_composite_guardrail_satisfies_protocol(self) -> None:
        from cuk_assistant.guardrails.subsystems.input_guard import InputGuard
    from cuk_assistant.guardrails.subsystems.output_guard import OutputGuard
    composite = CompositeGuardrail(input_guard=InputGuard(), output_guard=OutputGuard())
    assert isinstance(composite, GuardrailProtocol)

        # Test input path
    in_res = composite.validate_input("What is the fee for MBA at CUK?")
        assert in_res.is_safe is True
        assert in_res.is_in_domain is True

        # Test output path
        out_res = composite.validate_and_scrub_output(
            generated_text="CUK MBA fee is 50,000 per year.",
            quoted_snippets=[],
            context_chunks=[],
        )
        assert out_res.is_safe is True
        assert out_res.is_verbatim_grounded is True
