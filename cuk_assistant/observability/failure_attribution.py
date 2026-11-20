"""12-Diagnostic Failure Code Attribution Engine.

Implements FR-8.2 and GEMINI.md Mandatory Failure Attribution.
Standardizes diagnostic classification, error span tagging, severity attribution,
and user-safe messaging across all RAG pipeline stages.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    FailureEvent,
)


class DiagnosticMetadata(BaseModel):
    """Immutable metadata record for a canonical diagnostic failure code."""

    model_config = ConfigDict(frozen=True)

    code: FailureDiagnosticCode
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    subsystem: Literal["guardrails", "ingestion", "retrieval", "llm", "agent"]
    remediation_action: str
    user_safe_message: str


# =============================================================================
# Canonical 12-Diagnostic Failure Code Matrix
# =============================================================================

DIAGNOSTIC_REGISTRY: dict[FailureDiagnosticCode, DiagnosticMetadata] = {
    FailureDiagnosticCode.GUARDRAIL_BLOCKED: DiagnosticMetadata(
        code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
        severity="LOW",
        subsystem="guardrails",
        remediation_action="Request rejected with standardized policy disclaimer; retrieval bypassed.",
        user_safe_message="This query cannot be processed as it violates university usage guidelines or is outside academic scope.",
    ),
    FailureDiagnosticCode.PARSING_DEFECT: DiagnosticMetadata(
        code=FailureDiagnosticCode.PARSING_DEFECT,
        severity="HIGH",
        subsystem="ingestion",
        remediation_action="Mark document needs_ocr=True; dispatch fallback Tesseract pipeline.",
        user_safe_message="Unable to process document contents due to a layout or formatting defect.",
    ),
    FailureDiagnosticCode.QUESTION_PARSING_FAILED: DiagnosticMetadata(
        code=FailureDiagnosticCode.QUESTION_PARSING_FAILED,
        severity="LOW",
        subsystem="retrieval",
        remediation_action="Fallback to raw free-text BM25 search without metadata constraints.",
        user_safe_message="Could not extract structured query parameters; please clarify your question.",
    ),
    FailureDiagnosticCode.RETRIEVAL_EMPTY: DiagnosticMetadata(
        code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
        severity="MEDIUM",
        subsystem="retrieval",
        remediation_action="Trigger ScopeFallbackHandler to remove scoped filter and execute global search.",
        user_safe_message="No university documents matching your query could be found.",
    ),
    FailureDiagnosticCode.RETRIEVAL_RECALL_MISS: DiagnosticMetadata(
        code=FailureDiagnosticCode.RETRIEVAL_RECALL_MISS,
        severity="HIGH",
        subsystem="retrieval",
        remediation_action="Execute full-corpus deterministic regex fallback scan across LanceDB.",
        user_safe_message="The specific notification or document reference could not be located in immediate results.",
    ),
    FailureDiagnosticCode.MISSED_TOP_RANKED: DiagnosticMetadata(
        code=FailureDiagnosticCode.MISSED_TOP_RANKED,
        severity="MEDIUM",
        subsystem="retrieval",
        remediation_action="Log rank divergence for reranker calibration; expand context window to Top-7.",
        user_safe_message="Relevant documents were identified but were ranked lower than expected.",
    ),
    FailureDiagnosticCode.CONTEXT_TRUNCATION: DiagnosticMetadata(
        code=FailureDiagnosticCode.CONTEXT_TRUNCATION,
        severity="MEDIUM",
        subsystem="llm",
        remediation_action="Truncate lower-ranked chunks; prioritize Markdown tables and primary paragraph chunks.",
        user_safe_message="Context exceeded maximum token budget; response may be summarized.",
    ),
    FailureDiagnosticCode.LLM_EXTRACTION_FAILURE: DiagnosticMetadata(
        code=FailureDiagnosticCode.LLM_EXTRACTION_FAILURE,
        severity="HIGH",
        subsystem="llm",
        remediation_action="Switch to secondary LLM provider (Groq fallback from Gemini); flag prompt version.",
        user_safe_message="The assistant was unable to synthesize an answer from the retrieved university records.",
    ),
    FailureDiagnosticCode.LLM_HALLUCINATION: DiagnosticMetadata(
        code=FailureDiagnosticCode.LLM_HALLUCINATION,
        severity="HIGH",
        subsystem="guardrails",
        remediation_action="Redact unverified assertion; regenerate with stricter temperature (0.0).",
        user_safe_message="The generated answer could not be verified against official university documents.",
    ),
    FailureDiagnosticCode.LLM_FORMAT_VIOLATION: DiagnosticMetadata(
        code=FailureDiagnosticCode.LLM_FORMAT_VIOLATION,
        severity="HIGH",
        subsystem="llm",
        remediation_action="Trigger circuit-breaker retry on alternative provider with JSON schema constraint.",
        user_safe_message="An unexpected formatting error occurred. Please retry your request.",
    ),
    FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION: DiagnosticMetadata(
        code=FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION,
        severity="CRITICAL",
        subsystem="guardrails",
        remediation_action="Censor output completely; serve university safety notice; alert admin.",
        user_safe_message="The response was blocked due to safety guidelines or sensitive data protection.",
    ),
    FailureDiagnosticCode.CORPUS_MISSING_CONTENT: DiagnosticMetadata(
        code=FailureDiagnosticCode.CORPUS_MISSING_CONTENT,
        severity="LOW",
        subsystem="guardrails",
        remediation_action="Return authoritative negative confirmation: 'Document does not exist in official archives.'",
        user_safe_message="This document or notification does not exist in the official university archives.",
    ),
}


# =============================================================================
# Diagnostic Attributor Engine
# =============================================================================


class DiagnosticAttributor:
    """12-Diagnostic Failure Code Attribution Engine."""

    REGISTRY: dict[FailureDiagnosticCode, DiagnosticMetadata] = DIAGNOSTIC_REGISTRY

    @classmethod
    def get_metadata(cls, code: FailureDiagnosticCode) -> DiagnosticMetadata:
        """Retrieve full diagnostic metadata record for a code."""
        if code not in cls.REGISTRY:
            raise KeyError(f"Unknown diagnostic failure code: {code}")
        return cls.REGISTRY[code]

    @classmethod
    def get_severity(cls, code: FailureDiagnosticCode) -> str:
        """Return severity level ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')."""
        return cls.get_metadata(code).severity

    @classmethod
    def get_subsystem(cls, code: FailureDiagnosticCode) -> str:
        """Return responsible subsystem name."""
        return cls.get_metadata(code).subsystem

    @classmethod
    def get_remediation(cls, code: FailureDiagnosticCode) -> str:
        """Return actionable remediation action."""
        return cls.get_metadata(code).remediation_action

    @classmethod
    def get_user_safe_message(cls, code: FailureDiagnosticCode) -> str:
        """Return sanitized user-safe error message suitable for client display."""
        return cls.get_metadata(code).user_safe_message

    @classmethod
    def format_span_error_tags(cls, failure_event: FailureEvent) -> dict[str, Any]:
        """Format OpenTelemetry and Logfire compliant error span attributes."""
        meta = cls.get_metadata(failure_event.diagnostic_code)
        tags: dict[str, Any] = {
            "error": True,
            "cuk.diagnostic_code": failure_event.diagnostic_code.value,
            "cuk.remediation": failure_event.remediation_hint,
            "cuk.subsystem": meta.subsystem,
            "cuk.severity": meta.severity,
            "cuk.user_safe_message": meta.user_safe_message,
            "cuk.component": failure_event.component,
            "error.type": failure_event.diagnostic_code.value,
            "error.message": failure_event.error_message,
        }

        # Include details as flat namespaced span attributes when scalar
        for k, v in failure_event.details.items():
            if isinstance(v, (str, int, float, bool)):
                tags[f"cuk.details.{k}"] = v

        return tags


__all__ = [
    "DIAGNOSTIC_REGISTRY",
    "DiagnosticAttributor",
    "DiagnosticMetadata",
]
