"""Guardrails subsystem for Central University of Kashmir (CUK) Assistant.

Exports multi-layer input guards, output safety rails, PII scrubbers,
and verbatim citation verifiers conforming to GuardrailProtocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cuk_assistant.guardrails.subsystems.citation_verifier import (
    VerbatimCitationVerifier,
    verify_citations,
)
from cuk_assistant.guardrails.subsystems.input_guard import (
    DEFAULT_DOMAIN_DEFLECTION,
    DEFAULT_UNSAFE_DEFLECTION,
    FailureDiagnosticCode,
    GroqLlamaGuardRail,
    InputGuard,
    InputGuardResult,
    LocalDomainClassifier,
)
from cuk_assistant.guardrails.subsystems.output_guard import (
    DEFAULT_UNSAFE_OUTPUT_REDACTION,
    GroqLlamaGuardOutputRail,
    OutputGuard,
    OutputGuardResult,
    StudentPIIScrubber,
)


@runtime_checkable
class GuardrailProtocol(Protocol):
    """Abstract contract for multi-layer domain safety, PII scrubbing, and grounding."""

    def validate_input(self, raw_query: str) -> InputGuardResult:
        """Check domain relevance and evaluate prompt injection / jailbreak risks."""
        ...

    def validate_and_scrub_output(
        self,
        generated_text: str,
        quoted_snippets: list[str],
        context_chunks: list[Any],
    ) -> OutputGuardResult:
        """Screen toxicity, redact student PII, and verify verbatim grounding of quotes."""
        ...


class CompositeGuardrail:
    """Composite guardrail combining input and output rails satisfying GuardrailProtocol."""

    def __init__(
        self,
        input_guard: InputGuard | None = None,
        output_guard: OutputGuard | None = None,
    ) -> None:
        self.input_guard = input_guard or InputGuard()
        self.output_guard = output_guard or OutputGuard()

    def validate_input(self, raw_query: str) -> InputGuardResult:
        return self.input_guard.validate(raw_query)

    def validate_and_scrub_output(
        self,
        generated_text: str,
        quoted_snippets: list[str],
        context_chunks: list[Any],
    ) -> OutputGuardResult:
        return self.output_guard.validate_and_scrub(
            generated_text=generated_text,
            quoted_snippets=quoted_snippets,
            context_chunks=context_chunks,
        )


# Architectural convenience aliases
InputGuardrail = InputGuard
OutputGuardrail = OutputGuard
CitationVerifier = VerbatimCitationVerifier


__all__ = [
    "DEFAULT_DOMAIN_DEFLECTION",
    "DEFAULT_UNSAFE_DEFLECTION",
    "DEFAULT_UNSAFE_OUTPUT_REDACTION",
    "CitationVerifier",
    "CompositeGuardrail",
    "FailureDiagnosticCode",
    "GroqLlamaGuardOutputRail",
    "GroqLlamaGuardRail",
    "GuardrailProtocol",
    "InputGuard",
    "InputGuardResult",
    "InputGuardrail",
    "LocalDomainClassifier",
    "OutputGuard",
    "OutputGuardResult",
    "OutputGuardrail",
    "StudentPIIScrubber",
    "VerbatimCitationVerifier",
    "verify_citations",
]
