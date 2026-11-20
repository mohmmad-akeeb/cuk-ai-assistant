"""Input guardrails for Central University of Kashmir (CUK) Assistant.

Provides:
1. Fast local regex/keyword domain classifier (<1ms).
2. Local prompt-injection safety rail.
3. InputGuard orchestrator returning InputGuardResult.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict

from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode

logger = logging.getLogger(__name__)


class InputGuardResult(BaseModel):
    """Result of evaluating user input against domain and safety guardrails."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_safe: bool
    is_in_domain: bool
    deflection_message: str | None = None
    diagnostic_code: str | FailureDiagnosticCode | None = None


DEFAULT_DOMAIN_DEFLECTION: str = (
    "I am the Central University of Kashmir (CUK) Assistant. I can only assist "
    "with university-related inquiries such as courses, syllabus, admissions, "
    "examinations, and official notifications."
)

DEFAULT_UNSAFE_DEFLECTION: str = (
    "This request violates university safety guidelines and cannot be processed."
)


class LocalDomainClassifier:
    """Fast deterministic domain router (<1ms)."""

    _IN_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(cuk|central university of kashmir|cukashmir|kashmir university)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(b\.?tech|m\.?tech|mba|bba|ba\s*llb|msc|m\.?sc|ma|m\.?a|phd|ph\.?d|syllabus|"
            r"course|courses|admission|admissions|entrance|exam|exams|result|results|fee|fees|"
            r"hostel|hostels)\b",
            re.IGNORECASE,
        ),
    )

    def classify(self, text: str) -> tuple[bool, str | None]:
        """Classify user queries as university in-domain or off-topic."""
        for pattern in self._IN_DOMAIN_PATTERNS:
            if pattern.search(text):
                return True, None
        return False, DEFAULT_DOMAIN_DEFLECTION


class GroqLlamaGuardRail:
    """Local prompt-injection safety rail (no remote calls)."""

    _INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"ignore all previous instructions", re.IGNORECASE),
        re.compile(r"reveal system prompt", re.IGNORECASE),
    )

    def scan_input(self, text: str) -> tuple[bool, str | None]:
        """Scan input text for prompt-injection patterns."""
        for pattern in self._INJECTION_PATTERNS:
            if pattern.search(text):
                return False, "Prompt injection detected"
        return True, None


class InputGuard:
    """Orchestrates domain classification and safety rail validation."""

    def __init__(
        self,
        domain_classifier: LocalDomainClassifier | None = None,
        safety_rail: GroqLlamaGuardRail | None = None,
    ) -> None:
        self.domain_classifier = domain_classifier or LocalDomainClassifier()
        self.safety_rail = safety_rail or GroqLlamaGuardRail()

    def validate(self, raw_query: str) -> InputGuardResult:
        is_in_domain, domain_deflection = self.domain_classifier.classify(raw_query)
        if not is_in_domain:
            return InputGuardResult(
                is_safe=True,
                is_in_domain=False,
                deflection_message=domain_deflection or DEFAULT_DOMAIN_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        is_safe, safety_reason = self.safety_rail.scan_input(raw_query)
        if not is_safe:
            return InputGuardResult(
                is_safe=False,
                is_in_domain=True,
                deflection_message=DEFAULT_UNSAFE_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        return InputGuardResult(
            is_safe=True,
            is_in_domain=True,
            deflection_message=None,
            diagnostic_code=None,
        )


__all__ = [
    "GroqLlamaGuardRail",
    "InputGuard",
    "InputGuardResult",
    "LocalDomainClassifier",
]
