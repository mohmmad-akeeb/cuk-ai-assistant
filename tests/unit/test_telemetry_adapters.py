"""Unit tests for Langfuse and Arize Phoenix telemetry sink adapters.

Validates:
1. Strict TelemetrySinkProtocol implementation (log_span, record_span, tag_failure, record_feedback, record_metric, flush)
2. Proper mapping of trace trees, generation metadata, TTFT, token latencies, failure diagnostic codes
3. User satisfaction feedback scoring (-1, +1, comments, categories)
4. Telemetry Isolation & fail-open behavior on network errors, timeouts, or missing credentials
5. Factory creation logic (auto, explicit, fallback)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from cuk_assistant.core.factory import create_telemetry_sink
from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink
from cuk_assistant.observability.langfuse_sink import LangfuseTelemetrySink
from cuk_assistant.observability.phoenix_sink import PhoenixTelemetrySink


class TestProtocolAdherence:
    """Validate runtime and static protocol compliance."""

    def test_in_memory_sink_implements_protocol(self) -> None:
        sink = InMemoryTelemetrySink()
        assert isinstance(sink, TelemetrySinkProtocol)

    def test_langfuse_sink_implements_protocol(self) -> None:
        sink = LangfuseTelemetrySink(public_key="pk", secret_key="sk")
        assert isinstance(sink, TelemetrySinkProtocol)

    def test_phoenix_sink_implements_protocol(self) -> None:
        sink = PhoenixTelemetrySink(endpoint="http://localhost:6006")
        assert isinstance(sink, TelemetrySinkProtocol)


class TestLangfuseTelemetrySink:
    """Test Langfuse telemetry adapter functionality, mapping, and resilience."""

    def test_unconfigured_operates_in_silent_noop_mode(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            sink = LangfuseTelemetrySink()
            assert not sink.is_enabled
            # Should not raise any exception
            sink.log_span("test", {"trace_id": "t1"}, 15.0)
            sink.record_span("test", {"trace_id": "t1"}, 15.0)
            sink.tag_failure("t1", FailureDiagnosticCode.RETRIEVAL_EMPTY, {"query": "fees"})
            sink.record_feedback("t1", 1, "helpfulness", "Great answer")
            sink.record_metric("ttft_ms", 120.0, {"trace_id": "t1"})
            sink.flush()

    @patch("cuk_assistant.observability.langfuse_sink.urlopen")
    def test_record_span_generation_and_flush(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sink = LangfuseTelemetrySink(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://test.langfuse.com",
            max_batch_size=10,
        )

        sink.record_span(
            name="llm.generation",
            attributes={
                "trace_id": "trace-123",
                "span_id": "span-456",
                "model": "gemini-1.5-flash",
                "prompt": "What are the B.Tech CSE fees?",
                "completion": "The fee is Rs 45,000 per year.",
                "prompt_tokens": 50,
                "completion_tokens": 15,
                "ttft_ms": 180.5,
                "component": "llm",
            },
            duration_ms=450.0,
        )

        sink.flush()
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://test.langfuse.com/api/public/ingestion"
        assert req.get_header("Content-type") == "application/json"
        assert "Basic " in req.get_header("Authorization")

        body = json.loads(req.data.decode("utf-8"))
        batch = body["batch"]
        assert len(batch) == 2

        # Trace event
        trace_event = next(e for e in batch if e["type"] == "trace-create")
        assert trace_event["body"]["id"] == "trace-123"

        # Generation event
        gen_event = next(e for e in batch if e["type"] == "generation-create")
        assert gen_event["body"]["traceId"] == "trace-123"
        assert gen_event["body"]["id"] == "span-456"
        assert gen_event["body"]["model"] == "gemini-1.5-flash"
        assert gen_event["body"]["usage"]["input"] == 50
        assert gen_event["body"]["usage"]["output"] == 15
        assert gen_event["body"]["metadata"]["ttft_ms"] == 180.5

    @patch("cuk_assistant.observability.langfuse_sink.urlopen")
    def test_tag_failure_and_user_feedback(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sink = LangfuseTelemetrySink(public_key="pk-test", secret_key="sk-test")

        sink.tag_failure(
            trace_id="trc-fail-1",
            diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
            details={
                "error_message": "Prompt injection attempt detected",
                "component": "guardrails",
            },
        )
        sink.record_feedback(
            trace_id="trc-fail-1",
            score=-1,
            feedback_category="accuracy",
            comment="Wrong circular cited",
        )
        sink.flush()

        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        batch = body["batch"]

        failure_event = next(e for e in batch if e["type"] == "event-create")
        assert failure_event["body"]["name"] == "failure_tag:GUARDRAIL_BLOCKED"
        assert failure_event["body"]["metadata"]["diagnostic_code"] == "GUARDRAIL_BLOCKED"

        feedback_event = next(
            e for e in batch if e["type"] == "score-create" and e["body"]["name"] == "user_feedback"
        )
        assert feedback_event["body"]["value"] == -1.0
        assert feedback_event["body"]["comment"] == "Wrong circular cited"
        assert feedback_event["body"]["metadata"]["category"] == "accuracy"

    def test_mocked_sdk_client_delegation(self) -> None:
        mock_client = MagicMock()
        sink = LangfuseTelemetrySink(client=mock_client)

        sink.record_span(
            name="retrieval.hybrid",
            attributes={"trace_id": "trc-client-1", "span_id": "spn-1", "component": "retrieval"},
            duration_ms=45.0,
        )
        assert mock_client.span.called

        sink.tag_failure(
            trace_id="trc-client-1",
            diagnostic_code=FailureDiagnosticCode.LLM_HALLUCINATION,
            details={"reason": "Fabricated citation"},
        )
        assert mock_client.score.called

        sink.record_feedback(
            trace_id="trc-client-1",
            score=1,
            comment="Accurate!",
        )
        assert mock_client.score.call_count >= 2

    @patch("cuk_assistant.observability.langfuse_sink.urlopen")
    def test_network_failure_fails_open_silently(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError("Connection refused")
        sink = LangfuseTelemetrySink(public_key="pk-test", secret_key="sk-test")

        sink.record_span("test", {"trace_id": "t1"}, 10.0)
        # Flush should handle URLError gracefully without raising
        sink.flush()


class TestPhoenixTelemetrySink:
    """Test Arize Phoenix OTLP adapter functionality, mapping, and resilience."""

    def test_unconfigured_operates_in_silent_noop_mode(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            sink = PhoenixTelemetrySink()
            assert not sink.is_enabled
            sink.log_span("test", {"trace_id": "t1"}, 20.0)
            sink.record_span("test", {"trace_id": "t1"}, 20.0)
            sink.tag_failure("t1", FailureDiagnosticCode.RETRIEVAL_RECALL_MISS, {})
            sink.record_feedback("t1", 1)
            sink.record_metric("relevance_score", 0.88, {"trace_id": "t1"})
            sink.flush()

    @patch("cuk_assistant.observability.phoenix_sink.urlopen")
    def test_record_span_otlp_format_and_flush(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sink = PhoenixTelemetrySink(endpoint="http://localhost:6006")
        assert sink.endpoint == "http://localhost:6006/v1/traces"

        sink.record_span(
            name="retrieval.hybrid",
            attributes={
                "trace_id": "0123456789abcdef0123456789abcdef",
                "span_id": "fedcba9876543210",
                "top_k": 5,
                "relevance_threshold": 0.35,
                "component": "retrieval",
            },
            duration_ms=75.0,
        )
        sink.flush()

        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:6006/v1/traces"
        assert req.get_header("Content-type") == "application/json"

        body = json.loads(req.data.decode("utf-8"))
        assert "resourceSpans" in body
        resource_spans = body["resourceSpans"][0]
        assert (
            resource_spans["resource"]["attributes"][0]["value"]["stringValue"]
            == "cuk-rag-assistant"
        )

        spans = resource_spans["scopeSpans"][0]["spans"]
        assert len(spans) == 1
        span = spans[0]
        assert span["name"] == "retrieval.hybrid"
        assert span["traceId"] == "0123456789abcdef0123456789abcdef"
        assert span["spanId"] == "fedcba9876543210"

        # Check OpenInference span kind inference
        attr_dict = {a["key"]: a["value"] for a in span["attributes"]}
        assert attr_dict["openinference.span.kind"]["stringValue"] == "RETRIEVER"
        assert attr_dict["top_k"]["intValue"] == "5"

    @patch("cuk_assistant.observability.phoenix_sink.urlopen")
    def test_tag_failure_and_eval_spans(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sink = PhoenixTelemetrySink(endpoint="http://localhost:6006")

        sink.tag_failure(
            trace_id="trc_fail_2",
            diagnostic_code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
            details={"query": "non-existent course", "error_message": "Zero candidates"},
        )
        sink.record_feedback(trace_id="trc_fail_2", score=-1, comment="Nothing found")
        sink.record_metric("precision@5", 0.0, {"trace_id": "trc_fail_2"})
        sink.flush()

        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 3

        fail_span = next(s for s in spans if s["name"].startswith("failure:"))
        assert fail_span["status"]["code"] == 2  # ERROR
        assert fail_span["status"]["message"] == "Zero candidates"

        feedback_span = next(s for s in spans if s["name"] == "user_feedback")
        fb_attrs = {a["key"]: a["value"] for a in feedback_span["attributes"]}
        assert fb_attrs["evaluation.score"]["doubleValue"] == -1.0
        assert fb_attrs["evaluation.comment"]["stringValue"] == "Nothing found"

    @patch("cuk_assistant.observability.phoenix_sink.urlopen")
    def test_phoenix_network_failure_fails_open_silently(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = TimeoutError("Endpoint timeout")
        sink = PhoenixTelemetrySink(endpoint="http://localhost:6006")

        sink.record_span("test", {"trace_id": "t1"}, 10.0)
        # Flush should handle network error without raising
        sink.flush()


class TestFactoryCreation:
    """Test create_telemetry_sink factory resolution logic."""

    def test_create_telemetry_sink_explicit_in_memory(self) -> None:
        sink = create_telemetry_sink(sink_type="in_memory")
        assert isinstance(sink, InMemoryTelemetrySink)

    def test_create_telemetry_sink_explicit_langfuse(self) -> None:
        sink = create_telemetry_sink(
            sink_type="langfuse",
            public_key="pk-test",
            secret_key="sk-test",
        )
        assert isinstance(sink, LangfuseTelemetrySink)
        assert sink.is_enabled

    def test_create_telemetry_sink_explicit_phoenix(self) -> None:
        sink = create_telemetry_sink(
            sink_type="phoenix",
            endpoint="http://localhost:6006",
        )
        assert isinstance(sink, PhoenixTelemetrySink)
        assert sink.is_enabled

    def test_create_telemetry_sink_auto_resolution_to_langfuse(self) -> None:
        with patch.dict(
            "os.environ",
            {"LANGFUSE_PUBLIC_KEY": "pk-1", "LANGFUSE_SECRET_KEY": "sk-1"},
            clear=True,
        ):
            sink = create_telemetry_sink(sink_type="auto")
            assert isinstance(sink, LangfuseTelemetrySink)
            assert sink.is_enabled

    def test_create_telemetry_sink_auto_resolution_to_phoenix(self) -> None:
        with patch.dict(
            "os.environ",
            {"PHOENIX_COLLECTOR_ENDPOINT": "http://localhost:6006"},
            clear=True,
        ):
            sink = create_telemetry_sink(sink_type="auto")
            assert isinstance(sink, PhoenixTelemetrySink)
            assert sink.is_enabled

    def test_create_telemetry_sink_auto_fallback_to_in_memory(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            sink = create_telemetry_sink(sink_type="auto")
            assert isinstance(sink, InMemoryTelemetrySink)
