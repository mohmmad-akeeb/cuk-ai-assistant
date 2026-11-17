"""12-Diagnostic Failure Code Attribution Engine.

Implements FR-8.2 and GEMINI.md Mandatory Failure Attribution.
Standardizes diagnostic classification, error span tagging, severity attribution,
and user-safe messaging across all RAG pipeline stages.
"""

from __future__ import annotations

import uuid
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
# Standard Domain Exceptions with Typed Attribution
# =============================================================================


class DiagnosticError(Exception):
    """Base exception for all diagnostically attributed pipeline errors."""

    def __init__(
        self,
        message: str,
        diagnostic_code: FailureDiagnosticCode,
        component: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostic_code = diagnostic_code
        self.component = component
        self.details = details or {}


class GuardrailBlockedException(DiagnosticError):
    """Raised when user prompt fails safety, anti-injection, or domain rules."""

    def __init__(
        self,
        message: str = "Query rejected by university guardrail policy",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
            component="guardrails",
            details=details,
        )


class ParsingDefectException(DiagnosticError):
    """Raised when document ingestion or PDF extraction crashes or yields corrupt text."""

    def __init__(
        self,
        message: str = "Document parsing defect encountered",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.PARSING_DEFECT,
            component="ingestion",
            details=details,
        )


class QuestionParsingFailedException(DiagnosticError):
    """Raised when query parsing or slot extraction cannot resolve mandatory filters."""

    def __init__(
        self,
        message: str = "Failed to parse question or extract required slots",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.QUESTION_PARSING_FAILED,
            component="retrieval",
            details=details,
        )


class RetrievalEmptyException(DiagnosticError):
    """Raised when vector and lexical retrieval return 0 candidate chunks."""

    def __init__(
        self,
        message: str = "Retrieval returned 0 candidates",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
            component="retrieval",
            details=details,
        )


class RetrievalRecallMissException(DiagnosticError):
    """Raised when explicitly cited circular/notification is absent from Top-30."""

    def __init__(
        self,
        message: str = "Target document absent from retrieved candidates",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.RETRIEVAL_RECALL_MISS,
            component="retrieval",
            details=details,
        )


class MissedTopRankedException(DiagnosticError):
    """Raised when relevant candidate chunk is depressed outside Top-5 by reranker."""

    def __init__(
        self,
        message: str = "Relevant chunk fell outside reranker Top-5",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.MISSED_TOP_RANKED,
            component="retrieval",
            details=details,
        )


class ContextTruncationException(DiagnosticError):
    """Raised when candidate chunks exceed LLM token context budget and are trimmed."""

    def __init__(
        self,
        message: str = "Context chunks truncated to fit model token budget",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.CONTEXT_TRUNCATION,
            component="llm",
            details=details,
        )


class LLMExtractionFailureException(DiagnosticError):
    """Raised when LLM fails to synthesize factual answer despite present context."""

    def __init__(
        self,
        message: str = "LLM failed to extract factual answer from context",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.LLM_EXTRACTION_FAILURE,
            component="llm",
            details=details,
        )


class LLMHallucinationException(DiagnosticError):
    """Raised when generated response fails verbatim citation verification."""

    def __init__(
        self,
        message: str = "Generated quote or assertion failed citation verification",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.LLM_HALLUCINATION,
            component="guardrails",
            details=details,
        )


class LLMFormatViolationException(DiagnosticError):
    """Raised when LLM output violates Pydantic schema or returns invalid JSON."""

    def __init__(
        self,
        message: str = "LLM response violated schema formatting",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.LLM_FORMAT_VIOLATION,
            component="llm",
            details=details,
        )


class OutputSafetyViolationException(DiagnosticError):
    """Raised when generated text contains PII leakage or toxic content."""

    def __init__(
        self,
        message: str = "Generated output violated safety or PII protection policies",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION,
            component="guardrails",
            details=details,
        )


class CorpusMissingContentException(DiagnosticError):
    """Raised when deterministic corpus audit confirms query subject does not exist."""

    def __init__(
        self,
        message: str = "Subject confirmed absent from official university corpus",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            diagnostic_code=FailureDiagnosticCode.CORPUS_MISSING_CONTENT,
            component="guardrails",
            details=details,
        )


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
    def classify_exception(
        cls,
        exc: Exception,
        context: dict[str, Any] | None = None,
    ) -> FailureEvent:
        """Map standard Python exceptions and context to a canonical FailureEvent.

        Args:
            exc: Originating exception (diagnostic or generic).
            context: Optional contextual dictionary containing details such as
                     trace_id, component, candidates, unverified_quotes, etc.

        Returns:
            A populated FailureEvent with canonical diagnostic code, subsystem,
            remediation hint, and diagnostic attributes.
        """
        ctx = dict(context or {})

        # 1. Direct DiagnosticError or attribute resolution
        if isinstance(exc, DiagnosticError):
            code = exc.diagnostic_code
            component = exc.component or cls.get_subsystem(code)
            details = {**exc.details, **ctx}
        elif hasattr(exc, "diagnostic_code") and isinstance(
            exc.diagnostic_code, FailureDiagnosticCode
        ):
            code = exc.diagnostic_code
            component = getattr(exc, "component", None) or cls.get_subsystem(code)
            details = dict(ctx)
        elif "diagnostic_code" in ctx:
            raw_code = ctx["diagnostic_code"]
            code = (
                raw_code
                if isinstance(raw_code, FailureDiagnosticCode)
                else FailureDiagnosticCode(str(raw_code))
            )
            component = ctx.get("component") or cls.get_subsystem(code)
            details = dict(ctx)
        else:
            # 2. Heuristic Context & Exception Pattern Classification
            code, component = cls._infer_code_and_component(exc, ctx)
            details = dict(ctx)

        # Ensure exception info is tracked in details
        details["exception_type"] = type(exc).__name__
        details["exception_message"] = str(exc)

        # Resolve trace_id, component, and remediation_hint
        trace_id = ctx.get("trace_id") or uuid.uuid4().hex
        resolved_component = component or cls.get_subsystem(code)
        remediation_hint = ctx.get("remediation_hint") or cls.get_remediation(code)
        error_message = str(exc) if str(exc) else f"Diagnostic attribution: {code.value}"

        return FailureEvent(
            trace_id=trace_id,
            diagnostic_code=code,
            component=resolved_component,
            error_message=error_message,
            remediation_hint=remediation_hint,
            details=details,
        )

    @classmethod
    def _infer_code_and_component(
        cls,
        exc: Exception,
        ctx: dict[str, Any],
    ) -> tuple[FailureDiagnosticCode, str]:
        """Infer canonical diagnostic code and subsystem from exception and context."""
        msg = str(exc).lower()
        cls_name = type(exc).__name__.lower()
        reason = str(ctx.get("reason", "")).lower()

        # A. Guardrail blocked (injection, prompt hack, out-of-domain)
        if (
            ctx.get("is_injection")
            or ctx.get("blocked_by") == "guardrail"
            or reason in ("injection", "jailbreak", "off_domain", "guardrail_blocked")
            or any(
                kw in msg or kw in cls_name
                for kw in ("injection", "jailbreak", "prompt_injection", "off_domain", "guardrail")
            )
        ):
            return FailureDiagnosticCode.GUARDRAIL_BLOCKED, "guardrails"

        # B. Output safety violation (PII leakage, toxicity, hate speech)
        if (
            ctx.get("output_violation")
            or ctx.get("toxicity")
            or ctx.get("pii_leak")
            or reason in ("toxicity", "output_safety", "pii_violation")
            or any(
                kw in msg or kw in cls_name
                for kw in (
                    "toxic",
                    "pii",
                    "hate",
                    "output safety",
                    "output_safety",
                    "safety violation",
                )
            )
        ):
            return FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION, "guardrails"

        # C. LLM Hallucination (unverified citations, grounding mismatch)
        if (
            ctx.get("unverified_quotes")
            or ctx.get("hallucination") is True
            or reason in ("hallucination", "unverified_quotes", "citation_mismatch")
            or any(
                kw in msg or kw in cls_name
                for kw in (
                    "hallucination",
                    "unverified quote",
                    "unverified citation",
                    "grounding",
                    "citationverification",
                )
            )
        ):
            return FailureDiagnosticCode.LLM_HALLUCINATION, "guardrails"

        # D. Retrieval Empty (0 candidates from dense/sparse fusion)
        if (
            ctx.get("candidates") == []
            or ctx.get("candidates_count") == 0
            or reason in ("empty_retrieval", "no_candidates", "retrieval_empty")
            or any(
                kw in msg or kw in cls_name
                for kw in (
                    "empty retrieval",
                    "no candidate",
                    "0 candidate",
                    "retrieval_empty",
                    "empty_results",
                    "no documents found",
                )
            )
        ):
            return FailureDiagnosticCode.RETRIEVAL_EMPTY, "retrieval"

        # E. Retrieval Recall Miss
        if (
            reason in ("recall_miss", "missing_circular")
            or ctx.get("missing_circular_id")
            or ctx.get("target_doc_missing")
            or any(
                kw in msg or kw in cls_name
                for kw in ("recall miss", "circular not found", "recall_miss")
            )
        ):
            return FailureDiagnosticCode.RETRIEVAL_RECALL_MISS, "retrieval"

        # F. Missed Top Ranked (reranker anomaly)
        if reason in ("missed_top_ranked", "rerank_miss") or any(
            kw in msg or kw in cls_name for kw in ("missed top", "missed_top_ranked", "rerank")
        ):
            return FailureDiagnosticCode.MISSED_TOP_RANKED, "retrieval"

        # G. Context Truncation
        if (
            reason in ("context_truncation", "token_budget_exceeded")
            or ctx.get("truncated_tokens")
            or any(
                kw in msg or kw in cls_name
                for kw in (
                    "token budget",
                    "context_truncation",
                    "context length exceeded",
                    "max_tokens",
                )
            )
        ):
            return FailureDiagnosticCode.CONTEXT_TRUNCATION, "llm"

        # H. LLM Extraction Failure
        if reason in ("extraction_failure", "extraction_failed") or any(
            kw in msg or kw in cls_name
            for kw in (
                "extraction failure",
                "empty answer",
                "extraction_failed",
                "llm failed to extract",
            )
        ):
            return FailureDiagnosticCode.LLM_EXTRACTION_FAILURE, "llm"

        # I. Question Parsing Failed
        if (
            reason in ("question_parsing_failed", "slot_missing", "ambiguous_query")
            or ctx.get("missing_slots")
            or any(
                kw in msg or kw in cls_name
                for kw in ("slot", "question parse", "query parse", "ambiguous query")
            )
        ):
            return FailureDiagnosticCode.QUESTION_PARSING_FAILED, "retrieval"

        # J. Parsing Defect (PDF / HTML parser crash)
        if reason in ("parsing_defect", "docling_error", "corrupt_pdf") or any(
            kw in msg or kw in cls_name
            for kw in ("pdf", "layout", "docling", "corrupted", "parse_pdf", "parsing_defect")
        ):
            return FailureDiagnosticCode.PARSING_DEFECT, "ingestion"

        # K. Corpus Missing Content
        if reason in ("corpus_missing", "archive_empty") or any(
            kw in msg or kw in cls_name
            for kw in (
                "corpus missing",
                "document does not exist",
                "not found in official archives",
            )
        ):
            return FailureDiagnosticCode.CORPUS_MISSING_CONTENT, "guardrails"

        # L. LLM Format Violation (JSON decode error, Pydantic validation error)
        if any(
            kw in msg or kw in cls_name
            for kw in ("json", "validation", "pydantic", "schema", "format_violation", "decode")
        ):
            return FailureDiagnosticCode.LLM_FORMAT_VIOLATION, "llm"

        # Stage-based or default fallback
        stage = str(ctx.get("stage", "")).lower()
        if stage in ("guardrails", "guardrail"):
            return FailureDiagnosticCode.GUARDRAIL_BLOCKED, "guardrails"
        if stage in ("ingestion", "crawl"):
            return FailureDiagnosticCode.PARSING_DEFECT, "ingestion"
        if stage in ("llm", "generation"):
            return FailureDiagnosticCode.LLM_FORMAT_VIOLATION, "llm"

        return FailureDiagnosticCode.RETRIEVAL_EMPTY, "retrieval"

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
