"""In-memory telemetry sink for testing, local offline execution, and fallback.

Implements TelemetrySinkProtocol and guarantees Telemetry Isolation (NFR-3.2).
Thread-safe, zero-dependency, and fail-open.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.core.registry import register_telemetry_sink

logger = logging.getLogger(__name__)


class TelemetryRecord(dict):
    """Thread-safe dictionary subclass allowing both key and attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'TelemetryRecord' object has no attribute {name!r}") from None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


@register_telemetry_sink("in_memory")
@register_telemetry_sink("memory")
class InMemoryTelemetrySink:
    """Thread-safe in-memory telemetry sink satisfying TelemetrySinkProtocol.

    Retains execution spans, diagnostic failure tags, and user feedback events
    in bounded deques. Serves as the primary test double and zero-dependency
    offline fallback when remote telemetry providers are unconfigured or unavailable.
    """

    def __init__(self, max_records: int = 10_000) -> None:
        self._max_records = max_records
        self._lock = threading.Lock()
        self._spans: deque[TelemetryRecord] = deque(maxlen=max_records)
        self._failures: deque[TelemetryRecord] = deque(maxlen=max_records)
        self._feedbacks: deque[TelemetryRecord] = deque(maxlen=max_records)

    def log_span(
        self,
        name: str | Any,
        attributes: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Log timed execution span with metadata attributes (fail-open)."""
        try:
            if hasattr(name, "span_name"):
                span_name = str(name.span_name)
                span_attrs = dict(getattr(name, "attributes", {}) or {})
                span_dur = float(getattr(name, "duration_ms", duration_ms))
                span_trace_id = str(getattr(name, "trace_id", ""))
                span_component = str(getattr(name, "component", ""))
            else:
                span_name = str(name)
                span_attrs = dict(attributes or {})
                span_dur = float(duration_ms)
                span_trace_id = str(span_attrs.get("trace_id", "") if span_attrs else "")
                span_component = str(span_attrs.get("component", "") if span_attrs else "")

            record = TelemetryRecord(
                name=span_name,
                span_name=span_name,
                attributes=span_attrs,
                duration_ms=span_dur,
                trace_id=span_trace_id,
                component=span_component,
                timestamp=datetime.now(UTC),
            )
            with self._lock:
                self._spans.append(record)
        except Exception as exc:  # Telemetry Isolation Invariant: Never crash callers
            logger.warning("InMemoryTelemetrySink.log_span failed (failing open): %s", exc)

    def record_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Record timed execution span (TelemetrySinkProtocol method)."""
        self.log_span(name=name, attributes=attributes, duration_ms=duration_ms)

    def flush(self) -> None:
        """Flush pending batches/events (no-op for in-memory)."""
        pass

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        """Emit mandatory diagnostic attribution code for degraded/failed requests (fail-open)."""
        try:
            # Normalize diagnostic code
            code = (
                diagnostic_code
                if isinstance(diagnostic_code, FailureDiagnosticCode)
                else FailureDiagnosticCode(str(diagnostic_code))
            )
            record = TelemetryRecord(
                trace_id=str(trace_id),
                diagnostic_code=code,
                details=dict(details or {}),
                component=str(details.get("component", "") if details else ""),
                error_message=str(details.get("error_message", "") if details else ""),
                timestamp=datetime.now(UTC),
            )
            with self._lock:
                self._failures.append(record)
        except Exception as exc:  # Telemetry Isolation Invariant: Never crash callers
            logger.warning("InMemoryTelemetrySink.tag_failure failed (failing open): %s", exc)

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Record user satisfaction rating and qualitative feedback (fail-open)."""
        try:
            record = TelemetryRecord(
                trace_id=str(trace_id),
                score=int(score),
                category=feedback_category,
                feedback_category=feedback_category,
                comment=comment,
                timestamp=datetime.now(UTC),
            )
            with self._lock:
                self._feedbacks.append(record)
        except Exception as exc:  # Telemetry Isolation Invariant: Never crash callers
            logger.warning("InMemoryTelemetrySink.record_feedback failed (failing open): %s", exc)

    def get_spans(self, trace_id: str | None = None) -> list[TelemetryRecord]:
        """Return a snapshot copy of logged spans, optionally filtered by trace_id."""
        with self._lock:
            if trace_id is None:
                return [TelemetryRecord(s) for s in self._spans]
            return [TelemetryRecord(s) for s in self._spans if s.get("trace_id") == trace_id]

    def get_failures(self, trace_id: str | None = None) -> list[TelemetryRecord]:
        """Return a snapshot copy of logged failures, optionally filtered by trace_id."""
        with self._lock:
            if trace_id is None:
                return [TelemetryRecord(f) for f in self._failures]
            return [TelemetryRecord(f) for f in self._failures if f.get("trace_id") == trace_id]

    def get_feedbacks(self, trace_id: str | None = None) -> list[TelemetryRecord]:
        """Return a snapshot copy of recorded feedbacks, optionally filtered by trace_id."""
        with self._lock:
            if trace_id is None:
                return [TelemetryRecord(fb) for fb in self._feedbacks]
            return [TelemetryRecord(fb) for fb in self._feedbacks if fb.get("trace_id") == trace_id]

    def clear(self) -> None:
        """Clear all stored spans, failures, and feedbacks."""
        with self._lock:
            self._spans.clear()
            self._failures.clear()
            self._feedbacks.clear()

    def count_spans(self) -> int:
        """Return total count of recorded spans."""
        with self._lock:
            return len(self._spans)

    def count_failures(self) -> int:
        """Return total count of recorded failures."""
        with self._lock:
            return len(self._failures)

    def count_feedbacks(self) -> int:
        """Return total count of recorded feedback events."""
        with self._lock:
            return len(self._feedbacks)

    def __len__(self) -> int:
        """Return sum of all stored records."""
        with self._lock:
            return len(self._spans) + len(self._failures) + len(self._feedbacks)


# Compile-time protocol compliance verification
assert isinstance(InMemoryTelemetrySink(), TelemetrySinkProtocol)
