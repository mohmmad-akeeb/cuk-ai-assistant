"""Output safety rail, PII scrubber, and grounding verification for CUK Assistant.

Provides:
1. Programmatic PII Scrubber redacting Indian phones, Aadhaar IDs, and student marks.
2. Groq Llama Guard 3 output moderation rail with local toxicity fallback.
3. Integration with VerbatimCitationVerifier for hallucination detection.
4. OutputGuard orchestrator returning OutputGuardResult.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.guardrails.subsystems.citation_verifier import verify_citations

logger = logging.getLogger(__name__)


class OutputGuardResult(BaseModel):
    """Result of output safety, PII scrubbing, and citation verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_safe: bool
    sanitized_text: str
    is_verbatim_grounded: bool
    diagnostic_code: str | FailureDiagnosticCode | None = None


DEFAULT_UNSAFE_OUTPUT_REDACTION: str = "[CONTENT REDACTED DUE TO SAFETY VIOLATION]"


class StudentPIIScrubber:
    """Programmatic PII scrubber (NFR-4.1).

    Redacts:
    - Indian mobile phone numbers (+91, 0, 10-digit mobile).
    - 12-digit Aadhaar / national identity numbers.
    - Student marks / grades tied to specific roll numbers.

    Preserves:
    - Official university email addresses (e.g. @cukashmir.ac.in).
    """

    REDACTED_PHONE: str = "[REDACTED_PHONE]"
    REDACTED_ID: str = "[REDACTED_ID]"
    REDACTED_MARKS: str = "[REDACTED_MARKS]"

    # Pattern for official and public email addresses to preserve
    _EMAIL_PATTERN: re.Pattern[str] = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    # Indian phone number patterns (starts with 6-9, 10 digits with optional +91/0 prefix and delimiters)
    _PHONE_PATTERNS: tuple[re.Pattern[str], ...] = (
        # +91 or 91 prefix with optional spaces/hyphens followed by 10 digits
        re.compile(r"(?:\+91[\-\s]?|91[\-\s])?[6-9]\d{4}[\-\s]?\d{5}\b"),
        # 0 prefix followed by 10 digits starting with 6-9
        re.compile(r"\b0[6-9]\d{9}\b"),
        # Formatted 10-digit numbers: e.g. 9876-543-210 or 98765-43210
        re.compile(r"\b[6-9]\d{2}[\-\s]\d{3}[\-\s]\d{4}\b"),
        # Standard 10-digit mobile number starting with 6, 7, 8, 9
        re.compile(r"\b[6-9]\d{9}\b"),
    )

    # 12-digit Aadhaar / National ID patterns
    _AADHAAR_PATTERNS: tuple[re.Pattern[str], ...] = (
        # 1234 5678 9012 or 1234-5678-9012
        re.compile(r"\b\d{4}[\-\s]\d{4}[\-\s]\d{4}\b"),
        # Explicit Aadhaar prefix followed by 12 digits
        re.compile(
            r"\b(?:aadhaar|aadhar|uidai|national\s*id)[\s:#\-]*(\d{12})\b",
            re.IGNORECASE,
        ),
        # Standalone 12 digits (with boundary)
        re.compile(r"\b\d{12}\b"),
    )

    # Marks / Grades tied to Roll Numbers
    _ROLL_MARKS_PATTERNS: tuple[re.Pattern[str], ...] = (
        # Roll No: 12345, Marks: 85/100 -> Roll No: 12345, Marks: [REDACTED_MARKS]
        re.compile(
            r"\b(Roll\s*(?:No|Number|#)?[.:\s]*[A-Za-z0-9\-]+[,\s]+\b(?:Marks|Score|Grade|Total)\b[.:\s]*)"
            r"(\d+(?:\.\d+)?(?:\s*/\s*\d+)?|[A-O][+\-]?)",
            re.IGNORECASE,
        ),
        # Roll No: 12345 scored 92 marks -> Roll No: 12345 scored [REDACTED_MARKS] marks
        re.compile(
            r"\b(Roll\s*(?:No|Number|#)?[.:\s]*[A-Za-z0-9\-]+\s+\b(?:scored|secured|obtained|got)\b\s+)"
            r"(\d+(?:\.\d+)?(?:\s*/\s*\d+)?(?:\s*marks|\s*points)?|[A-O][+\-]?(?:\s*grade)?)(?=\s|\.|\,|$)",
            re.IGNORECASE,
        ),
        # Marks: 85 for Roll No: 12345 -> Marks: [REDACTED_MARKS] for Roll No: 12345
        re.compile(
            r"\b(\b(?:Marks|Score|Grade|Total)\b[.:\s]*)"
            r"(\d+(?:\.\d+)?(?:\s*/\s*\d+)?|[A-O][+\-]?)"
            r"(\s*(?:for|of)?\s*Roll\s*(?:No|Number|#)?[.:\s]*[A-Za-z0-9\-]+)",
            re.IGNORECASE,
        ),
    )

    def scrub(self, text: str) -> str:
        """Scrub PII from text while preserving official email addresses."""
        if not text:
            return ""

        # Step 1: Temporarily protect email addresses so they are not corrupted by phone/ID regexes
        email_map: dict[str, str] = {}

        def _protect_email(match: re.Match[str]) -> str:
            placeholder = f"__EMAIL_PROTECTED_{len(email_map)}__"
            email_map[placeholder] = match.group(0)
            return placeholder

        scrubbed = self._EMAIL_PATTERN.sub(_protect_email, text)

        # Step 2: Redact marks / grades tied to roll numbers
        for pat in self._ROLL_MARKS_PATTERNS:
            # Notice the patterns have capture groups. If group 3 exists (Marks: X for Roll No: Y):
            if pat.pattern.endswith("+)"):
                scrubbed = pat.sub(rf"\g<1>{self.REDACTED_MARKS}\g<3>", scrubbed)
            else:
                scrubbed = pat.sub(rf"\g<1>{self.REDACTED_MARKS}", scrubbed)

        # Step 3: Redact 12-digit Aadhaar / National ID numbers
        for pat in self._AADHAAR_PATTERNS:
            scrubbed = pat.sub(self.REDACTED_ID, scrubbed)

        # Step 4: Redact Indian phone numbers
        for pat in self._PHONE_PATTERNS:
            scrubbed = pat.sub(self.REDACTED_PHONE, scrubbed)

        # Step 5: Restore protected email addresses
        for placeholder, original_email in email_map.items():
            scrubbed = scrubbed.replace(placeholder, original_email)

        return scrubbed


class GroqLlamaGuardOutputRail:
    """Local output toxicity safety rail (no remote calls)."""

    _TOXICITY_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(kill yourself|commit suicide|bomb the university|terrorist attack|"
            r"hate all (muslims|hindus|sikhs|christians|kashmiris|indians)|defamatory libel)\b",
            re.IGNORECASE,
        ),
    )

    def scan_output(self, text: str) -> tuple[bool, str | None]:
        """Scan output text for severe toxicity / hate speech / defamation."""
        for pattern in self._TOXICITY_PATTERNS:
            match = pattern.search(text)
            if match:
                return False, f"local_heuristic_toxicity:{match.group(0)}"
        return True, None


class OutputGuard:
    """Orchestrates output safety screening, PII scrubbing, and citation verification."""

    def __init__(
        self,
        pii_scrubber: StudentPIIScrubber | None = None,
        safety_rail: GroqLlamaGuardOutputRail | None = None,
        min_snippet_chars: int = 15,
    ) -> None:
        self.pii_scrubber = pii_scrubber or StudentPIIScrubber()
        self.safety_rail = safety_rail or GroqLlamaGuardOutputRail()
        self.min_snippet_chars = min_snippet_chars

    @staticmethod
    def _extract_context_strings(context_chunks: list[Any]) -> list[str]:
        """Extract text strings from chunks whether they are ChunkRecord objects or raw strings."""
        result: list[str] = []
        for c in context_chunks:
            if hasattr(c, "text"):
                result.append(c.text)
            elif isinstance(c, str):
                result.append(c)
            else:
                result.append(str(c))
        return result

    def scrub(self, text: str) -> str:
        """Programmatically scrub PII (phone numbers, Aadhaar IDs, roll-based marks)."""
        return self.pii_scrubber.scrub(text)

    def validate_and_scrub(
        self,
        generated_text: str,
        quoted_snippets: list[str] | None = None,
        context_chunks: list[Any] | None = None,
    ) -> OutputGuardResult:
        """Synchronously validate, scrub PII, and verify citations for generated response."""
        snippets = quoted_snippets or []
        contexts = self._extract_context_strings(context_chunks or [])

        # 1. Output safety screening
        is_safe, safety_reason = self.safety_rail.scan_output(generated_text)
        if not is_safe:
            return OutputGuardResult(
                is_safe=False,
                sanitized_text=DEFAULT_UNSAFE_OUTPUT_REDACTION,
                is_verbatim_grounded=False,
                diagnostic_code=FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION.value,
            )

        # 2. PII Scrubbing
        sanitized_text = self.pii_scrubber.scrub(generated_text)

        # 3. Verbatim Citation Verification
        is_grounded, offending = verify_citations(
            quoted_snippets=snippets,
            retrieved_contexts=contexts,
            min_snippet_chars=self.min_snippet_chars,
        )

        if not is_grounded:
            return OutputGuardResult(
                is_safe=True,
                sanitized_text=sanitized_text,
                is_verbatim_grounded=False,
                diagnostic_code=FailureDiagnosticCode.LLM_HALLUCINATION.value,
            )

        return OutputGuardResult(
            is_safe=True,
            sanitized_text=sanitized_text,
            is_verbatim_grounded=True,
            diagnostic_code=None,
        )
