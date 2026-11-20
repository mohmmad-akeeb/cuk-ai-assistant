"""Arize Phoenix Telemetry Sink Adapter.

Implements TelemetrySinkProtocol for Arize Phoenix observability.
Exports spans, retrieval relevance metrics, and diagnostic failure attributions
to local or cloud Arize Phoenix collector via standard OTLP/HTTP.
Fails open (never crashes caller) without external vendor SDK coupling.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.core.registry import register_telemetry_sink

logger = logging.getLogger(__name__)


def _to_otlp_id(val: str | None, hex_len: int = 32) -> str:
    """Format an ID to valid lowercase hex string of exact length (32 for trace, 16 for span)."""
    if not val:
        return uuid.uuid4().hex[:hex_len].zfill(hex_len)
    clean = str(val).replace("-", "").lower()
    return clean[:hex_len].zfill(hex_len)


def _to_any_value(val: Any) -> dict[str, Any]:
    """Convert a Python value into an OTLP AnyValue structure."""
    if isinstance(val, bool):
        return {"boolValue": val}
    if isinstance(val, int):
        return {"intValue": str(val)}
    if isinstance(val, float):
        return {"doubleValue": float(val)}
    if isinstance(val, (list, tuple)):
        return {"arrayValue": {"values": [_to_any_value(x) for x in val]}}
    if isinstance(val, dict):
        kvlist = [{"key": k, "value": _to_any_value(v)} for k, v in val.items()]
        return {"kvlistValue": {"values": kvlist}}
    return {"stringValue": str(val)}


@register_telemetry_sink("phoenix")
class PhoenixTelemetrySink:
    """Arize Phoenix telemetry adapter implementing TelemetrySinkProtocol.

    Exports traces and spans via OTLP/HTTP to Phoenix local or cloud collector.
    Guarantees Telemetry Isolation (NFR-3.2) - fails open and silently logs warnings.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        project_name: str = "cuk-rag-assistant",
        max_batch_size: int = 50,
        flush_interval_seconds: float = 2.0,
    ) -> None:
        raw_endpoint = (
            endpoint
            or os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
            or os.environ.get("PHOENIX_ENDPOINT")
        )
        self.project_name = project_name
        self.max_batch_size = max_batch_size
        self.flush_interval_seconds = flush_interval_seconds

        self._is_enabled = bool(raw_endpoint)
        if not self._is_enabled:
            logger.warning(
                "PhoenixTelemetrySink: Missing PHOENIX_COLLECTOR_ENDPOINT. "
                "Operating in silent no-op / fail-open mode."
            )
            self.endpoint = ""
        else:
            base = raw_endpoint.rstrip("/")
            if base.endswith("/v1/traces"):
                self.endpoint = base
            else:
                self.endpoint = f"{base}/v1/traces"

        self._lock = threading.Lock()
        self._spans: deque[dict[str, Any]] = deque(maxlen=5000)
        self._last_flush: float = time.time()

    @property
    def is_enabled(self) -> bool:
        """Return True if collector endpoint is configured."""
        return self._is_enabled

    def log_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Log timed execution span to Phoenix (TelemetrySinkProtocol)."""
        self.record_span(name=name, attributes=attributes, duration_ms=duration_ms)

    def record_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Record timed execution span formatted for Phoenix trace trees."""
        if not self._is_enabled:
            return

        try:
            attrs = dict(attributes or {})
            trace_id = _to_otlp_id(attrs.get("trace_id"), hex_len=32)
            span_id = _to_otlp_id(attrs.get("span_id"), hex_len=16)

            end_ns = int(time.time() * 1e9)
            start_ns = end_ns - int(float(duration_ms) * 1e6)

            otlp_attrs = [
                {
                    "key": "openinference.span.kind",
                    "value": {"stringValue": self._infer_span_kind(name, attrs)},
                },
                {
                    "key": "cuk.component",
                    "value": {"stringValue": str(attrs.get("component", "pipeline"))},
                },
            ]

            for k, v in attrs.items():
                if k not in ("trace_id", "span_id") and v is not None:
                    otlp_attrs.append({"key": str(k), "value": _to_any_value(v)})

            span_record = {
                "traceId": trace_id,
                "spanId": span_id,
                "name": name,
                "kind": 1,  # SPAN_KIND_INTERNAL
                "startTimeUnixNano": str(start_ns),
                "endTimeUnixNano": str(end_ns),
                "attributes": otlp_attrs,
                "status": {"code": 1},  # STATUS_CODE_OK
            }

            with self._lock:
                self._spans.append(span_record)
                should_flush = (
                    len(self._spans) >= self.max_batch_size
                    or (time.time() - self._last_flush) >= self.flush_interval_seconds
                )

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("PhoenixTelemetrySink.record_span failed (fail-open): %s", exc)

    def _infer_span_kind(self, name: str, attrs: dict[str, Any]) -> str:
        """Map operation name/attributes to OpenInference semantic convention span kind."""
        if "model" in attrs or "prompt" in attrs or "llm" in name:
            return "LLM"
        if "retriev" in name or "rerank" in name:
            return "RETRIEVER"
        if "guard" in name:
            return "GUARDRAIL"
        if "agent" in name or "router" in name:
            return "AGENT"
        return "CHAIN"

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        """Emit mandatory diagnostic failure attribution span/event to Phoenix."""
        if not self._is_enabled:
            return

        try:
            tid = _to_otlp_id(trace_id, hex_len=32)
            sid = _to_otlp_id(uuid.uuid4().hex, hex_len=16)
            code = (
                diagnostic_code.value
                if isinstance(diagnostic_code, FailureDiagnosticCode)
                else str(diagnostic_code)
            )
            det = dict(details or {})

            now_ns = int(time.time() * 1e9)
            error_message = str(
                det.get("error_message") or det.get("message") or f"Attributed failure: {code}"
            )

            otlp_attrs = [
                {"key": "cuk.failure_diagnostic_code", "value": {"stringValue": code}},
                {"key": "error.type", "value": {"stringValue": code}},
                {"key": "error.message", "value": {"stringValue": error_message}},
                {"key": "openinference.span.kind", "value": {"stringValue": "EVALUATOR"}},
            ]
            for k, v in det.items():
                if v is not None:
                    otlp_attrs.append({"key": f"diagnostic.{k}", "value": _to_any_value(v)})

            span_record = {
                "traceId": tid,
                "spanId": sid,
                "name": f"failure:{code}",
                "kind": 1,
                "startTimeUnixNano": str(now_ns),
                "endTimeUnixNano": str(now_ns + 1_000_000),  # +1ms
                "attributes": otlp_attrs,
                "status": {
                    "code": 2,  # STATUS_CODE_ERROR
                    "message": error_message,
                },
            }

            with self._lock:
                self._spans.append(span_record)
                should_flush = len(self._spans) >= self.max_batch_size

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("PhoenixTelemetrySink.tag_failure failed (fail-open): %s", exc)

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Record user satisfaction rating as an evaluation span."""
        if not self._is_enabled:
            return

        try:
            tid = _to_otlp_id(trace_id, hex_len=32)
            sid = _to_otlp_id(uuid.uuid4().hex, hex_len=16)
            now_ns = int(time.time() * 1e9)

            attrs = [
                {"key": "openinference.span.kind", "value": {"stringValue": "EVALUATOR"}},
                {"key": "evaluation.name", "value": {"stringValue": "user_feedback"}},
                {"key": "evaluation.score", "value": {"doubleValue": float(score)}},
            ]
            if feedback_category:
                attrs.append(
                    {"key": "evaluation.category", "value": {"stringValue": feedback_category}}
                )
            if comment:
                attrs.append({"key": "evaluation.comment", "value": {"stringValue": comment}})

            span_record = {
                "traceId": tid,
                "spanId": sid,
                "name": "user_feedback",
                "kind": 1,
                "startTimeUnixNano": str(now_ns),
                "endTimeUnixNano": str(now_ns + 1_000_000),
                "attributes": attrs,
                "status": {"code": 1},
            }

            with self._lock:
                self._spans.append(span_record)
                should_flush = len(self._spans) >= self.max_batch_size

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("PhoenixTelemetrySink.record_feedback failed (fail-open): %s", exc)

    def flush(self) -> None:
        """Flush queued OTLP spans to Arize Phoenix collector endpoint."""
        if not self._is_enabled or not self.endpoint:
            return

        with self._lock:
            if not self._spans:
                return
            spans_to_send = list(self._spans)
            self._spans.clear()
            self._last_flush = time.time()

        try:
            otlp_payload = {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {"stringValue": "cuk-rag-assistant"},
                                },
                                {
                                    "key": "project.name",
                                    "value": {"stringValue": self.project_name},
                                },
                            ]
                        },
                        "scopeSpans": [
                            {
                                "scope": {
                                    "name": "cuk_assistant.observability",
                                    "version": "0.1.0",
                                },
                                "spans": spans_to_send,
                            }
                        ],
                    }
                ]
            }

            payload_bytes = json.dumps(otlp_payload).encode("utf-8")
            req = Request(
                url=self.endpoint,
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "CUK-Assistant-PhoenixSink/1.0",
                },
                method="POST",
            )
            with urlopen(req, timeout=5.0) as resp:
                status_code = resp.status
                if status_code not in (200, 201, 202):
                    logger.warning("Phoenix collector returned status: %s", status_code)
        except (URLError, TimeoutError, OSError) as net_err:
            logger.warning("PhoenixTelemetrySink.flush network issue (failing open): %s", net_err)
        except Exception as exc:
            logger.warning("PhoenixTelemetrySink.flush failed (failing open): %s", exc)


# Compile-time protocol check
assert isinstance(PhoenixTelemetrySink(endpoint="http://localhost:6006"), TelemetrySinkProtocol)
