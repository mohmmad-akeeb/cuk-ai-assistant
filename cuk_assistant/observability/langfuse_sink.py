"""Langfuse Telemetry Sink Adapter.

Implements TelemetrySinkProtocol for Langfuse observability.
Captures distributed trace spans, token latencies (TTFT), retrieval relevance,
and user satisfaction feedback without coupling business logic to external SDKs.
Fails open (never crashes caller) and supports both native HTTP/REST and Langfuse SDK if installed.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.core.registry import register_telemetry_sink

logger = logging.getLogger(__name__)


def _sanitize_trace_id(trace_id: str | None) -> str:
    """Ensure trace_id is a valid non-empty string."""
    if not trace_id:
        return uuid.uuid4().hex
    return str(trace_id).strip()


@register_telemetry_sink("langfuse")
class LangfuseTelemetrySink:
    """Production-grade Langfuse telemetry adapter implementing TelemetrySinkProtocol.

    Handles traces, generation observations, span observations, diagnostic failure tags,
    and user satisfaction feedback scoring. Conforms strictly to fail-open Telemetry Isolation (NFR-3.2).
    """

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        client: Any | None = None,
        max_batch_size: int = 50,
        flush_interval_seconds: float = 2.0,
    ) -> None:
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
        self.host = (
            host or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com"
        ).rstrip("/")
        self.client = client
        self.max_batch_size = max_batch_size
        self.flush_interval_seconds = flush_interval_seconds

        self._is_enabled = bool(self.client is not None or (self.public_key and self.secret_key))
        if not self._is_enabled:
            logger.warning(
                "LangfuseTelemetrySink: Missing credentials (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY). "
                "Operating in silent no-op / fail-open mode."
            )

        self._lock = threading.Lock()
        self._batch: deque[dict[str, Any]] = deque(maxlen=5000)
        self._last_flush: float = time.time()

    @property
    def is_enabled(self) -> bool:
        """Return True if Langfuse credentials or client are configured."""
        return self._is_enabled

    def log_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Log timed execution span with metadata attributes to Langfuse."""
        self.record_span(name=name, attributes=attributes, duration_ms=duration_ms)

    def record_span(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Record timed execution span (TelemetrySinkProtocol)."""
        if not self._is_enabled:
            return

        try:
            attrs = dict(attributes or {})
            trace_id = _sanitize_trace_id(attrs.get("trace_id"))
            span_id = str(attrs.get("span_id") or uuid.uuid4().hex[:16])

            end_time = datetime.now(UTC)
            start_time = datetime.fromtimestamp(
                end_time.timestamp() - (float(duration_ms) / 1000.0), tz=UTC
            )

            is_generation = (
                "model" in attrs
                or "model_name" in attrs
                or "prompt" in attrs
                or "completion" in attrs
                or name.startswith("llm")
                or name.startswith("generation")
            )

            # Route to client SDK if injected
            if self.client is not None and hasattr(self.client, "span"):
                try:
                    self.client.span(
                        name=name,
                        trace_id=trace_id,
                        id=span_id,
                        start_time=start_time,
                        end_time=end_time,
                        metadata=attrs,
                    )
                    return
                except Exception as sdk_exc:
                    logger.debug("Langfuse client.span failed: %s", sdk_exc)

            now_iso = datetime.now(UTC).isoformat()
            start_iso = start_time.isoformat()
            end_iso = end_time.isoformat()

            # Ensure trace-create event
            trace_event = {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now_iso,
                "body": {
                    "id": trace_id,
                    "name": attrs.get("session_name") or name,
                    "timestamp": start_iso,
                    "metadata": {
                        "component": attrs.get("component", "pipeline"),
                        **{k: v for k, v in attrs.items() if k not in ("trace_id", "span_id")},
                    },
                    "tags": attrs.get("tags", []),
                },
            }

            if is_generation:
                usage: dict[str, Any] = {}
                if "prompt_tokens" in attrs or "input_tokens" in attrs:
                    usage["input"] = int(
                        attrs.get("prompt_tokens") or attrs.get("input_tokens") or 0
                    )
                if "completion_tokens" in attrs or "output_tokens" in attrs:
                    usage["output"] = int(
                        attrs.get("completion_tokens") or attrs.get("output_tokens") or 0
                    )
                if "total_tokens" in attrs:
                    usage["total"] = int(attrs.get("total_tokens") or 0)

                obs_event = {
                    "id": str(uuid.uuid4()),
                    "type": "generation-create",
                    "timestamp": now_iso,
                    "body": {
                        "id": span_id,
                        "traceId": trace_id,
                        "name": name,
                        "startTime": start_iso,
                        "endTime": end_iso,
                        "model": attrs.get("model") or attrs.get("model_name"),
                        "modelParameters": attrs.get("model_parameters", {}),
                        "input": attrs.get("prompt") or attrs.get("input"),
                        "output": attrs.get("completion") or attrs.get("output"),
                        "usage": usage or None,
                        "metadata": {
                            "ttft_ms": attrs.get("ttft_ms"),
                            "component": attrs.get("component", "llm"),
                            **{
                                k: v
                                for k, v in attrs.items()
                                if k
                                not in (
                                    "trace_id",
                                    "span_id",
                                    "model",
                                    "model_name",
                                    "prompt",
                                    "completion",
                                    "prompt_tokens",
                                    "completion_tokens",
                                )
                            },
                        },
                    },
                }
            else:
                obs_event = {
                    "id": str(uuid.uuid4()),
                    "type": "span-create",
                    "timestamp": now_iso,
                    "body": {
                        "id": span_id,
                        "traceId": trace_id,
                        "name": name,
                        "startTime": start_iso,
                        "endTime": end_iso,
                        "input": attrs.get("input") or attrs.get("query"),
                        "output": attrs.get("output"),
                        "metadata": {
                            "component": attrs.get("component", "rag"),
                            "relevance_scores": attrs.get("relevance_scores"),
                            **{
                                k: v
                                for k, v in attrs.items()
                                if k not in ("trace_id", "span_id", "input", "output")
                            },
                        },
                    },
                }

            with self._lock:
                self._batch.append(trace_event)
                self._batch.append(obs_event)
                should_flush = (
                    len(self._batch) >= self.max_batch_size
                    or (time.time() - self._last_flush) >= self.flush_interval_seconds
                )

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("LangfuseTelemetrySink.record_span failed (fail-open): %s", exc)

    def tag_failure(
        self,
        trace_id: str,
        diagnostic_code: FailureDiagnosticCode,
        details: dict[str, Any],
    ) -> None:
        """Emit mandatory diagnostic attribution code for degraded or failed requests."""
        if not self._is_enabled:
            return

        try:
            tid = _sanitize_trace_id(trace_id)
            code = (
                diagnostic_code.value
                if isinstance(diagnostic_code, FailureDiagnosticCode)
                else str(diagnostic_code)
            )
            det = dict(details or {})
            now_iso = datetime.now(UTC).isoformat()

            if self.client is not None and hasattr(self.client, "score"):
                try:
                    self.client.score(
                        trace_id=tid,
                        name=f"failure.{code}",
                        value=1.0,
                        comment=det.get("error_message") or det.get("reason"),
                    )
                    return
                except Exception as sdk_exc:
                    logger.debug("Langfuse client.score failed: %s", sdk_exc)

            event = {
                "id": str(uuid.uuid4()),
                "type": "event-create",
                "timestamp": now_iso,
                "body": {
                    "id": str(uuid.uuid4()),
                    "traceId": tid,
                    "name": f"failure_tag:{code}",
                    "startTime": now_iso,
                    "metadata": {
                        "diagnostic_code": code,
                        "failure_attribution": True,
                        **det,
                    },
                },
            }

            score_event = {
                "id": str(uuid.uuid4()),
                "type": "score-create",
                "timestamp": now_iso,
                "body": {
                    "id": str(uuid.uuid4()),
                    "traceId": tid,
                    "name": "diagnostic_failure",
                    "value": 1.0,
                    "dataType": "CATEGORICAL",
                    "stringValue": code,
                    "comment": str(det.get("error_message") or det.get("message") or code),
                },
            }

            with self._lock:
                self._batch.append(event)
                self._batch.append(score_event)
                should_flush = len(self._batch) >= self.max_batch_size

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("LangfuseTelemetrySink.tag_failure failed (fail-open): %s", exc)

    def record_feedback(
        self,
        trace_id: str,
        score: int,
        feedback_category: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Record user satisfaction rating and qualitative commentary."""
        if not self._is_enabled:
            return

        try:
            tid = _sanitize_trace_id(trace_id)
            score_val = float(score)
            now_iso = datetime.now(UTC).isoformat()

            if self.client is not None and hasattr(self.client, "score"):
                try:
                    self.client.score(
                        trace_id=tid,
                        name="user_feedback",
                        value=score_val,
                        comment=comment,
                    )
                    return
                except Exception as sdk_exc:
                    logger.debug("Langfuse client.score feedback failed: %s", sdk_exc)

            score_event = {
                "id": str(uuid.uuid4()),
                "type": "score-create",
                "timestamp": now_iso,
                "body": {
                    "id": str(uuid.uuid4()),
                    "traceId": tid,
                    "name": "user_feedback",
                    "value": score_val,
                    "dataType": "NUMERIC",
                    "comment": comment,
                    "metadata": {
                        "category": feedback_category,
                    },
                },
            }

            with self._lock:
                self._batch.append(score_event)
                should_flush = len(self._batch) >= self.max_batch_size

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("LangfuseTelemetrySink.record_feedback failed (fail-open): %s", exc)

    def record_metric(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record numerical metric (latency, TTFT, token count, relevance score)."""
        if not self._is_enabled:
            return

        try:
            attrs = dict(attributes or {})
            trace_id = _sanitize_trace_id(attrs.get("trace_id"))
            now_iso = datetime.now(UTC).isoformat()

            score_event = {
                "id": str(uuid.uuid4()),
                "type": "score-create",
                "timestamp": now_iso,
                "body": {
                    "id": str(uuid.uuid4()),
                    "traceId": trace_id,
                    "name": name,
                    "value": float(value),
                    "dataType": "NUMERIC",
                    "metadata": attrs,
                },
            }

            with self._lock:
                self._batch.append(score_event)
                should_flush = len(self._batch) >= self.max_batch_size

            if should_flush:
                self.flush()

        except Exception as exc:
            logger.warning("LangfuseTelemetrySink.record_metric failed (fail-open): %s", exc)

    def flush(self) -> None:
        """Flush queued events to Langfuse batch ingestion endpoint."""
        if not self._is_enabled:
            return

        with self._lock:
            if not self._batch:
                return
            events_to_send = list(self._batch)
            self._batch.clear()
            self._last_flush = time.time()

        try:
            url = f"{self.host}/api/public/ingestion"
            payload = json.dumps({"batch": events_to_send}).encode("utf-8")
            auth_str = f"{self.public_key}:{self.secret_key}"
            basic_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")

            req = Request(
                url=url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {basic_auth}",
                    "User-Agent": "CUK-Assistant-LangfuseSink/1.0",
                },
                method="POST",
            )
            with urlopen(req, timeout=5.0) as resp:
                status_code = resp.status
                if status_code not in (200, 201, 207):
                    logger.warning("Langfuse ingestion returned unexpected status: %s", status_code)
        except (URLError, TimeoutError, OSError) as net_err:
            logger.warning("LangfuseTelemetrySink.flush network issue (failing open): %s", net_err)
        except Exception as exc:
            logger.warning("LangfuseTelemetrySink.flush failed (failing open): %s", exc)


# Compile-time protocol check
assert isinstance(LangfuseTelemetrySink(public_key="k", secret_key="s"), TelemetrySinkProtocol)
