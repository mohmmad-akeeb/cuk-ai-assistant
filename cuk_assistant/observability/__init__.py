"""Observability, telemetry protocols, and 12-diagnostic failure attribution engine."""

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
    DiagnosticError,
    DiagnosticMetadata,
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
    TelemetryRecord,
)
from cuk_assistant.observability.langfuse_sink import LangfuseTelemetrySink
from cuk_assistant.observability.phoenix_sink import PhoenixTelemetrySink

__all__ = [
    "DIAGNOSTIC_REGISTRY",
    "ContextTruncationException",
    "CorpusMissingContentException",
    "DiagnosticAttributor",
    "DiagnosticError",
    "DiagnosticMetadata",
    "FailureDiagnosticCode",
    "FailureEvent",
    "FeedbackEvent",
    "GuardrailBlockedException",
    "InMemoryTelemetrySink",
    "LLMExtractionFailureException",
    "LLMFormatViolationException",
    "LLMHallucinationException",
    "LangfuseTelemetrySink",
    "MissedTopRankedException",
    "OutputSafetyViolationException",
    "ParsingDefectException",
    "PhoenixTelemetrySink",
    "QuestionParsingFailedException",
    "RetrievalEmptyException",
    "RetrievalRecallMissException",
    "SpanAttributes",
    "TelemetryRecord",
    "TelemetrySinkProtocol",
]
