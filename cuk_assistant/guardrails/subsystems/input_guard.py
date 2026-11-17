"""Input guardrails for Central University of Kashmir (CUK) Assistant."""

from __future__ import annotations
import re
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, ConfigDict
import logging

logger = logging.getLogger(__name__)

class FailureDiagnosticCode(StrEnum):
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    # ... (other codes)
    OUTPUT_SAFETY_VIOLATION = "OUTPUT_SAFETY_VIOLATION"

class InputGuardResult(BaseModel):
    is_safe: bool
    is_in_domain: bool
    deflection_message: str | None = None
    diagnostic_code: str | FailureDiagnosticCode | None = None

class LocalDomainClassifier:
    def classify(self, text: str) -> tuple[bool, str | None]:
        return True, None

class GroqLlamaGuardRail:
    def scan_input(self, text: str) -> tuple[bool, str | None]:
        return True, None
    async def scan_input_async(self, text: str) -> tuple[bool, str | None]:
        return True, None

class InputGuard:
    def __init__(self, domain_classifier: Any = None, safety_rail: Any = None) -> None:
        self.domain_classifier = domain_classifier or LocalDomainClassifier()
        self.safety_rail = safety_rail or GroqLlamaGuardRail()
    def validate(self, raw_query: str) -> InputGuardResult:
        return InputGuardResult(is_safe=True, is_in_domain=True)

@runtime_checkable
class GuardrailProtocol(Protocol):
    def validate(self, query: str) -> bool: ...

class CompositeGuardrail:
    """Combines multiple input guardrail checks."""
    def __init__(self, input_guard: Any, output_guard: Any) -> None:
        self.input_guard = input_guard
        self.output_guard = output_guard
    def validate(self, query: str) -> bool:
        return self.input_guard.validate(query).is_safe
    def validate_input(self, query: str) -> bool:
        return self.validate(query)
    def validate_and_scrub_output(self, response: str) -> str:
        return self.output_guard.scrub(response)

@runtime_checkable
class GuardrailProtocol(Protocol):
    def validate(self, query: str) -> bool: ...

class CompositeGuardrail:
    """Combines multiple input guardrail checks."""
    def __init__(self, input_guard: Any, output_guard: Any) -> None:
        self.input_guard = input_guard
        self.output_guard = output_guard

    def validate(self, query: str) -> bool:
        return self.input_guard.validate(query).is_safe

    def validate_input(self, query: str) -> bool:
        """Alias for validate."""
        return self.validate(query)

    def validate_and_scrub_output(self, response: str) -> str:
        """Pass-through to output guard."""
        return self.output_guard.scrub(response)
