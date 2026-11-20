"""Telemetry and Observability Protocol interfaces and canonical failure taxonomies.

Governed by GEMINI.md and docs/architecture.md: Zero external vendor dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class FailureDiagnosticCode(StrEnum):
    """Canonical 12-diagnostic failure attribution taxonomy codes.

    Enforced across all pipeline stages, guardrails, retrieval, and LLM tiers.
    """

    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    PARSING_DEFECT = "PARSING_DEFECT"
    QUESTION_PARSING_FAILED = "QUESTION_PARSING_FAILED"
    RETRIEVAL_EMPTY = "RETRIEVAL_EMPTY"
    RETRIEVAL_RECALL_MISS = "RETRIEVAL_RECALL_MISS"
    MISSED_TOP_RANKED = "MISSED_TOP_RANKED"
    CONTEXT_TRUNCATION = "CONTEXT_TRUNCATION"
    LLM_EXTRACTION_FAILURE = "LLM_EXTRACTION_FAILURE"
    LLM_HALLUCINATION = "LLM_HALLUCINATION"
    LLM_FORMAT_VIOLATION = "LLM_FORMAT_VIOLATION"
    OUTPUT_SAFETY_VIOLATION = "OUTPUT_SAFETY_VIOLATION"
    CORPUS_MISSING_CONTENT = "CORPUS_MISSING_CONTENT"


class SpanAttributes(BaseModel):
    """Key-value metadata with duration, component, and trace IDs."""

    model_config = ConfigDict(extra="allow", frozen=True)

    trace_id: str = Field(..., description="Unique trace identifier")
    component: str = Field(..., description="Subsystem or component name")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    span_name: str = Field(default="", description="Name of the execution span")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Metadata key-value pairs")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of span recording",
    )


class FailureEvent(BaseModel):
    """Structured failure or degradation event captured during pipeline execution."""

    model_config = ConfigDict(extra="allow", frozen=True)

    trace_id: str = Field(..., description="Trace identifier of originating request")
    diagnostic_code: FailureDiagnosticCode = Field(
        ...,
        description="Canonical failure diagnostic code",
    )
    component: str = Field(..., description="Subsystem or component reporting failure")
    error_message: str = Field(
        ...,
        description="Human-readable description of error or degradation",
    )
    remediation_hint: str = Field(
        ...,
        description="Actionable troubleshooting instructions or automated fallback triggered",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed diagnostic context and attributes",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC event timestamp",
    )


class FeedbackEvent(BaseModel):
    """User satisfaction feedback rating and qualitative commentary."""

    model_config = ConfigDict(extra="allow", frozen=True)

    trace_id: str = Field(..., description="Trace identifier for the rated turn")
    score: int = Field(..., description="User feedback score (-1 for downvote, +1 for upvote)")
    category: str | None = Field(default=None, description="Optional categorization of feedback")
    comment: str | None = Field(default=None, description="Optional qualitative feedback comment")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC event timestamp",
    )


@runtime_checkable
class TelemetrySinkProtocol(Protocol):
    """Abstract contract for observability sinks (Logfire, Langfuse, Arize Phoenix, InMemory)."""

    def log_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Log timed execution span with metadata attributes."""
        ...

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        """Emit mandatory diagnostic attribution code for degraded or failed requests."""
        ...

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Record user thumbs up/down score and feedback comment."""
        ...

    def record_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Alias for log_span for standardized span recording."""
        ...

    def flush(self) -> None:
        """Flush pending batches/events to destination collectors."""
        ...
