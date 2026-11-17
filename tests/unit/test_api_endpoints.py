"""Unit tests for FastAPI REST and Server-Sent Events (SSE) endpoints.

Governed by docs/api_contracts.md, docs/requirements.md (FR-7.2, FR-7.3, NFR-4.2), and Task 5.4.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.api.main import app
from cuk_assistant.api.middleware.rate_limiter import RateLimiterMiddleware
from cuk_assistant.api.routes.chat import get_telemetry_sink
from cuk_assistant.api.routes.sessions import get_session_store
from cuk_assistant.core.protocols.session import MessageRecord
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink


@pytest.fixture
def memory_session_store() -> Generator[SQLiteSessionStore, None, None]:
    """Provide an isolated in-memory SQLiteSessionStore."""
    store = SQLiteSessionStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def memory_telemetry_sink() -> InMemoryTelemetrySink:
    """Provide an isolated in-memory telemetry sink."""
    return InMemoryTelemetrySink()


@pytest.fixture
def test_client(
    memory_session_store: SQLiteSessionStore,
    memory_telemetry_sink: InMemoryTelemetrySink,
) -> Generator[TestClient, None, None]:
    """Provide TestClient with dependency overrides and reset rate limiter."""
    app.dependency_overrides[get_session_store] = lambda: memory_session_store
    app.dependency_overrides[get_telemetry_sink] = lambda: memory_telemetry_sink

    # Locate RateLimiterMiddleware in middleware stack and reset
    for middleware in app.user_middleware:
        if middleware.cls == RateLimiterMiddleware:
            pass

    client = TestClient(app)

    # Reset any rate limiter instances stored in middleware
    client.app.state.session_store = memory_session_store

    yield client

    app.dependency_overrides.clear()


def _get_rate_limiter_from_app() -> RateLimiterMiddleware | None:
    """Helper to locate the active RateLimiterMiddleware in the ASGI app stack."""
    current = app.middleware_stack
    while current:
        if isinstance(current, RateLimiterMiddleware):
            return current
        current = getattr(current, "app", None)
    return None


# ===========================================================================
# 1. Health & Readiness Probe Tests
# ===========================================================================


class TestHealthEndpoints:
    """Validate /api/v1/health and readiness checks."""

    def test_health_basic(self, test_client: TestClient) -> None:
        """Verify GET /api/v1/health returns 200 OK and expected structure."""
        resp = test_client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "cuk-assistant"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        assert resp.headers["Cache-Control"] == "no-cache, no-store"

    def test_health_root_alias(self, test_client: TestClient) -> None:
        """Verify root /health returns 200."""
        resp = test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_deep_check_success(self, test_client: TestClient) -> None:
        """Verify ?deep=true validates database connectivity."""
        resp = test_client.get("/api/v1/health?deep=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "components" in data
        assert "sqlite_session_db" in data["components"]
        assert data["components"]["sqlite_session_db"]["status"] == "ready"

    def test_readiness_probe_endpoint(self, test_client: TestClient) -> None:
        """Verify GET /health/ready returns deep readiness probe."""
        resp = test_client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "sqlite_session_db" in data["components"]


# ===========================================================================
# 2. Guided Starter Menu Tests
# ===========================================================================


class TestStarterMenuEndpoint:
    """Validate 2-level hierarchical starter menu navigation."""

    def test_get_starter_menu(self, test_client: TestClient) -> None:
        """Verify starter menu categories, items, and suggested slots."""
        resp = test_client.get("/api/v1/menu/starter")
        assert resp.status_code == 200
        assert "max-age=3600" in resp.headers.get("Cache-Control", "")

        data = resp.json()
        assert data["version"] == "1.0"
        categories = data["categories"]
        assert len(categories) >= 4

        cat_ids = [c["id"] for c in categories]
        assert "admissions" in cat_ids
        assert "examinations" in cat_ids

        # Validate admissions category
        admissions = next(c for c in categories if c["id"] == "admissions")
        assert len(admissions["items"]) >= 2
        for item in admissions["items"]:
            assert item["id"]
            assert item["title"]

        # Validate suggested slots structure
        for cat in categories:
            assert cat["icon"]
            for item in cat["items"]:
                assert item["id"]
                assert item["title"]
                assert item["default_query"]
                assert isinstance(item["suggested_slots"], dict)

    def test_get_starter_menu_default_fallback(self, test_client: TestClient) -> None:
        """Verify fallback to hardcoded default menu when config file is absent."""
        with patch.object(Path, "is_file", return_value=False):
            resp = test_client.get("/api/v1/menu/starter")
            assert resp.status_code == 200
            data = resp.json()
            assert data["version"] == "1.0"
            categories = data["categories"]
            assert len(categories) == 5

            cat_ids = [c["id"] for c in categories]
            assert cat_ids == ["admissions", "examinations", "curriculum", "fees", "facilities"]

            # Validate admissions category
            admissions = next(c for c in categories if c["id"] == "admissions")
            assert admissions["title"] == "Admissions & Cut-Offs"
            assert len(admissions["items"]) >= 2
            item_ids = [item["id"] for item in admissions["items"]]
            assert "cuet_ug_cutoffs" in item_ids
            assert "intake_capacity" in item_ids


# ===========================================================================
# 3. Session Management Tests
# ===========================================================================


class TestSessionEndpoints:
    """Validate conversation session retrieval and deletion."""

    def test_get_session_not_found(self, test_client: TestClient) -> None:
        """Verify GET /api/v1/sessions/{invalid_id} returns 404 ApiErrorEnvelope."""
        resp = test_client.get("/api/v1/sessions/non-existent-session-12345")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error_code"] == "SESSION_NOT_FOUND"
        assert "non-existent-session-12345" in data["message"]
        assert len(data["trace_id"]) == 32

    def test_session_lifecycle_and_history(
        self,
        test_client: TestClient,
        memory_session_store: SQLiteSessionStore,
    ) -> None:
        """Verify creating, appending messages, fetching history, and deleting session."""
        session_id = "test-session-abc"
        memory_session_store.get_or_create_session(
            session_id=session_id,
            ip_hash="test-ip-hash",
            user_type="student",
        )
        memory_session_store.append_message(
            MessageRecord(
                message_id="msg-1",
                session_id=session_id,
                role="user",
                content="What is the B.Tech syllabus?",
                tokens=6,
            )
        )
        memory_session_store.append_message(
            MessageRecord(
                message_id="msg-2",
                session_id=session_id,
                role="assistant",
                content="Here is the syllabus.",
                tokens=5,
                quoted_citations=[{"citation_id": "cite_1", "title": "Syllabus 2022"}],
            )
        )

        # Retrieve session
        resp = test_client.get(f"/api/v1/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "What is the B.Tech syllabus?"
        assert data["messages"][1]["role"] == "assistant"
        assert len(data["messages"][1]["quoted_citations"]) == 1

        # Delete session
        del_resp = test_client.delete(f"/api/v1/sessions/{session_id}")
        assert del_resp.status_code == 200
        assert del_resp.json() == {"status": "deleted", "session_id": session_id}

        # Subsequent retrieval must return 404
        resp_after = test_client.get(f"/api/v1/sessions/{session_id}")
        assert resp_after.status_code == 404
        assert resp_after.json()["error_code"] == "SESSION_NOT_FOUND"

    def test_delete_non_existent_session_returns_404(self, test_client: TestClient) -> None:
        """Verify deleting non-existent session returns 404 ApiErrorEnvelope."""
        resp = test_client.delete("/api/v1/sessions/absent-session-id")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "SESSION_NOT_FOUND"


# ===========================================================================
# 4. User Satisfaction Feedback Tests
# ===========================================================================


class TestFeedbackEndpoint:
    """Validate user feedback capture and telemetry logging."""

    def test_record_feedback_upvote(
        self,
        test_client: TestClient,
        memory_telemetry_sink: InMemoryTelemetrySink,
    ) -> None:
        """Verify positive score=1 feedback logging."""
        payload = {
            "trace_id": "a" * 32,
            "message_id": "msg-001",
            "score": 1,
            "feedback_category": "accurate_citation",
            "comment": "Very helpful syllabus information.",
        }
        resp = test_client.post("/api/v1/chat/feedback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "recorded_at" in data

        feedbacks = memory_telemetry_sink.get_feedbacks("a" * 32)
        assert len(feedbacks) == 1
        assert feedbacks[0]["score"] == 1
        assert feedbacks[0]["comment"] == "Very helpful syllabus information."

    def test_record_feedback_downvote(
        self,
        test_client: TestClient,
        memory_telemetry_sink: InMemoryTelemetrySink,
    ) -> None:
        """Verify negative score=-1 feedback logging."""
        payload = {
            "trace_id": "b" * 32,
            "score": -1,
            "feedback_category": "outdated_info",
        }
        resp = test_client.post("/api/v1/chat/feedback", json=payload)
        assert resp.status_code == 200

        feedbacks = memory_telemetry_sink.get_feedbacks("b" * 32)
        assert len(feedbacks) == 1
        assert feedbacks[0]["score"] == -1

    def test_record_feedback_invalid_score_rejected(self, test_client: TestClient) -> None:
        """Verify scores other than -1 and 1 return 422 validation error."""
        resp = test_client.post(
            "/api/v1/chat/feedback",
            json={"trace_id": "c" * 32, "score": 0},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"


# ===========================================================================
# 5. Sliding-Window IP Rate Limiter Tests
# ===========================================================================


class TestRateLimiterMiddleware:
    """Validate 20 req/hour sliding-window anti-abuse protection (NFR-4.2)."""

    def test_rate_limiter_quota_exhaustion_on_21st_request(
        self,
        test_client: TestClient,
    ) -> None:
        """Send 20 requests successfully; 21st must return HTTP 429 RATE_LIMIT_EXCEEDED."""
        mock_ip = "192.0.2.100"
        headers = {"X-Forwarded-For": mock_ip}

        # First 20 requests to rate-limited endpoint
        for i in range(20):
            resp = test_client.get("/api/v1/sessions/any-session", headers=headers)
            assert resp.status_code == 404  # Valid processing, session not found
            assert resp.headers.get("X-RateLimit-Limit") == "20"
            expected_remaining = str(19 - i)
            assert resp.headers.get("X-RateLimit-Remaining") == expected_remaining

        # 21st request must trigger HTTP 429
        resp_21 = test_client.get("/api/v1/sessions/any-session", headers=headers)
        assert resp_21.status_code == 429
        assert "Retry-After" in resp_21.headers
        assert resp_21.headers.get("X-RateLimit-Remaining") == "0"

        body = resp_21.json()
        assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert "Hourly query quota exceeded" in body["message"]
        assert len(body["trace_id"]) == 32
        assert body["details"]["limit"] == 20
        assert body["details"]["window"] == "1 hour"

    def test_exempt_endpoints_bypass_rate_limiter(self, test_client: TestClient) -> None:
        """Verify health and starter menu endpoints are exempt even if IP exhausted quota."""
        exhausted_ip = "192.0.2.200"
        headers = {"X-Forwarded-For": exhausted_ip}

        # Exhaust quota with 20 requests
        for _ in range(20):
            test_client.get("/api/v1/sessions/test", headers=headers)

        # 21st regular request is blocked
        assert test_client.get("/api/v1/sessions/test", headers=headers).status_code == 429

        # Exempt endpoints MUST succeed with 200
        health_resp = test_client.get("/api/v1/health", headers=headers)
        assert health_resp.status_code == 200

        menu_resp = test_client.get("/api/v1/menu/starter", headers=headers)
        assert menu_resp.status_code == 200


# ===========================================================================
# 6. Streaming Chat Route Tests (SSE)
# ===========================================================================


class TestChatStreamingEndpoint:
    """Validate Server-Sent Events (SSE) chat streaming, slot clarification, and grounding."""

    def test_stream_conversational_greeting(self, test_client: TestClient) -> None:
        """Verify streaming greeting emits valid token events and concludes with done event."""
        payload = {"message": "Hello there", "session_id": "sess-greeting-1"}
        resp = test_client.post(
            "/api/v1/chat/stream",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.1"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["Content-Type"]

        lines = resp.text.strip().split("\n\n")
        events: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)

        assert len(events) >= 2
        # Verify token events present
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) > 0
        full_text = "".join(e["token"] for e in token_events)
        assert "Central University of Kashmir" in full_text

        # Verify done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["session_id"] == "sess-greeting-1"
        assert done_events[0]["citations"] == []

    def test_stream_missing_slots_clarification_prompt(self, test_client: TestClient) -> None:
        """Verify academic inquiry without required slots yields slot_prompt event with chips."""
        payload = {
            "message": "What is the syllabus for B.Tech CSE?",
            "session_id": "sess-syllabus-1",
        }
        resp = test_client.post(
            "/api/v1/chat/stream",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.2"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["Content-Type"]

        events: list[dict[str, Any]] = []
        for line in resp.text.strip().split("\n\n"):
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        slot_events = [e for e in events if e.get("type") == "slot_prompt"]
        assert len(slot_events) == 1
        slot_event = slot_events[0]
        assert slot_event["target_slot"] == "batch_year"
        assert len(slot_event["options"]) >= 2
        assert "admission batch" in slot_event["prompt"].lower()

        # Must conclude with done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1

    def test_stream_with_slots_provided_serves_answer_with_citations(
        self,
        test_client: TestClient,
    ) -> None:
        """Verify academic inquiry with slots filled returns tokens and verified citations."""
        payload = {
            "message": "What is the syllabus for B.Tech CSE?",
            "slots": {"batch_year": 2022, "program": "B.Tech CSE", "semester": "Semester 4"},
            "session_id": "sess-syllabus-filled",
        }
        resp = test_client.post(
            "/api/v1/chat/stream",
            json=payload,
            headers={"X-Forwarded-For": "192.0.2.3"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["Content-Type"]

        events: list[dict[str, Any]] = []
        for line in resp.text.strip().split("\n\n"):
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        # No slot_prompt should be emitted since slots were provided
        slot_events = [e for e in events if e.get("type") == "slot_prompt"]
        assert len(slot_events) == 0

        # Verified citations should be delivered in done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert len(done_events[0]["citations"]) >= 1
        assert done_events[0]["citations"][0]["citation_id"] == "cite_1"

    def test_stream_empty_query_rejected(self, test_client: TestClient) -> None:
        """Verify empty message payload returns HTTP 400 Bad Request ApiErrorEnvelope."""
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": "   "},
            headers={"X-Forwarded-For": "192.0.2.4"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "EMPTY_QUERY"
        assert "cannot be empty" in data["message"]


# ===========================================================================
# 7. Synchronous Chat Route Tests
# ===========================================================================


class TestSyncChatEndpoint:
    """Validate synchronous POST /api/v1/chat for programmatic test callers."""

    def test_sync_chat_greeting(self, test_client: TestClient) -> None:
        """Verify sync chat greeting returns direct response."""
        resp = test_client.post(
            "/api/v1/chat",
            json={"query": "Hello"},
            headers={"X-Forwarded-For": "192.0.2.5"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert "Central University of Kashmir" in data["content"]

    def test_sync_chat_missing_slots_quick_replies(self, test_client: TestClient) -> None:
        """Verify sync chat returns quick replies when mandatory slots missing."""
        resp = test_client.post(
            "/api/v1/chat",
            json={"query": "What are the latest exam results?"},
            headers={"X-Forwarded-For": "192.0.2.6"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quick_replies"] is not None
        assert data["quick_replies"]["target_slot"] in ("program", "exam_session", "batch_year")


# ===========================================================================
# 8. CORS & Exception Handler Tests
# ===========================================================================


class TestAppInfrastructure:
    """Validate CORS headers and global exception envelopes."""

    def test_cors_headers(self, test_client: TestClient) -> None:
        """Verify CORS headers present for origin requests."""
        resp = test_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")

    def test_institutional_rate_limit_higher_quota(self, test_client: TestClient) -> None:
        """Verify institutional account (@cukashmir.ac.in) receives 100 limit."""
        resp = test_client.get(
            "/api/v1/sessions/inst-session",
            headers={
                "X-Forwarded-For": "192.0.2.77",
                "X-User-Email": "student@cukashmir.ac.in",
            },
        )
        assert resp.headers.get("X-RateLimit-Limit") == "100"
