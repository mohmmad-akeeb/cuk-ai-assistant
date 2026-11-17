"""Unit tests for Chainlit Web Application (`cuk_assistant/ui/app.py`).

Governed by docs/api_contracts.md (Section 5), PROJECT.md (Feature 25), and Milestone M5.
Validates:
1. Singleton factory caching (get_ui_orchestrator, get_ui_telemetry_sink).
2. Session initialization and starter prompt action chips (on_chat_start).
3. Starter prompt callback execution (on_starter_prompt).
4. Interactive faceted slot selection callback (on_slot_selected).
5. Feedback upvote and downvote recording (on_feedback_upvote, on_feedback_downvote).
6. Chat message intake and whitespace filtering (on_message).
7. Real-time streaming response synthesis, side-panel citation cards, and slot chips (process_query).
8. CLI runner entrypoint and argument forwarding (run).
9. Teardown module isolation (teardown_module).
10. MockUserSession context isolation, copy-on-write semantics, and concurrent task safety.
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib
import os
import subprocess
import sys
import types
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cuk_assistant.ui.app as app

# ---------------------------------------------------------------------------
# In-Memory Chainlit Test Doubles
# ---------------------------------------------------------------------------


class MockUserSession:
    """Task-isolated in-memory dictionary mock emulating cl.user_session."""

    def __init__(self) -> None:
        self._var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
            "user_session_store", default=None
        )

    def _store(self) -> dict[str, Any]:
        store = self._var.get()
        if store is None:
            store = {}
            self._var.set(store)
        return store

    def get(self, key: str, default: Any = None) -> Any:
        return self._store().get(key, default)

    def set(self, key: str, value: Any) -> None:
        store = dict(self._store())
        store[key] = value
        self._var.set(store)

    def clear(self) -> None:
        self._var.set({})


class MockAction:
    """Action button or chip emulating cl.Action."""

    def __init__(
        self,
        name: str = "",
        value: Any = "",
        label: str | None = None,
        description: str | None = None,
        payload: Any = None,
        collapsed: bool = False,
    ) -> None:
        self.name = name
        self.value = value
        self.label = label or name
        self.description = description
        self.payload = payload
        self.collapsed = collapsed
        self.removed = False

    async def remove(self) -> None:
        self.removed = True


class MockText:
    """Side-panel text element emulating cl.Text."""

    def __init__(
        self,
        name: str = "",
        content: str = "",
        display: str = "side",
    ) -> None:
        self.name = name
        self.content = content
        self.display = display


class MockMessage:
    """Chat timeline message emulating cl.Message."""

    sent_messages: list[MockMessage] = []

    def __init__(
        self,
        content: str = "",
        actions: list[MockAction] | None = None,
        elements: list[MockText] | None = None,
    ) -> None:
        self.content = content
        self.actions = actions or []
        self.elements = elements or []
        self.tokens_streamed: list[str] = []
        self.sent = False
        self.updated = False

    async def send(self) -> MockMessage:
        self.sent = True
        MockMessage.sent_messages.append(self)
        return self

    async def stream_token(self, token: str) -> None:
        self.tokens_streamed.append(token)
        self.content += token

    async def update(self) -> MockMessage:
        self.updated = True
        return self


# ---------------------------------------------------------------------------
# Module Injection & State Fixtures
# ---------------------------------------------------------------------------

_orig_chainlit = sys.modules.get("chainlit")

mock_cl = types.ModuleType("chainlit")
mock_cl.user_session = MockUserSession()
mock_cl.Action = MockAction
mock_cl.Text = MockText
mock_cl.Message = MockMessage
mock_cl.on_chat_start = lambda fn: fn
mock_cl.action_callback = lambda name: lambda fn: fn
mock_cl.on_message = lambda fn: fn

sys.modules["chainlit"] = mock_cl

importlib.reload(app)


def teardown_module() -> None:
    """Restore original sys.modules state after module tests complete."""
    if _orig_chainlit is not None:
        sys.modules["chainlit"] = _orig_chainlit
    else:
        sys.modules.pop("chainlit", None)
    app._orchestrator = None
    app._telemetry_sink = None
    importlib.reload(app)


@pytest.fixture(autouse=True)
def clean_mock_state() -> Generator[None, None, None]:
    """Isolate session state, sent messages, and singletons for each test."""
    mock_cl.user_session.clear()
    MockMessage.sent_messages.clear()
    app._orchestrator = None
    app._telemetry_sink = None
    yield
    mock_cl.user_session.clear()
    MockMessage.sent_messages.clear()
    app._orchestrator = None
    app._telemetry_sink = None


# ---------------------------------------------------------------------------
# 1. UI Singleton Management Tests
# ---------------------------------------------------------------------------


class TestUISingletons:
    """Verify lazy singleton resolution for UI orchestrator and telemetry sink."""

    def test_get_ui_orchestrator_initialization_and_caching(self) -> None:
        mock_orch = MagicMock()
        with patch(
            "cuk_assistant.ui.app.create_rag_orchestrator", return_value=mock_orch
        ) as mock_create:
            orch1 = app.get_ui_orchestrator()
            orch2 = app.get_ui_orchestrator()
            assert orch1 is orch2
            assert orch1 is mock_orch
            mock_create.assert_called_once()

    def test_get_ui_telemetry_sink_initialization_and_caching(self) -> None:
        mock_sink = MagicMock()
        with patch(
            "cuk_assistant.ui.app.create_telemetry_sink", return_value=mock_sink
        ) as mock_create:
            sink1 = app.get_ui_telemetry_sink()
            sink2 = app.get_ui_telemetry_sink()
            assert sink1 is sink2
            assert sink1 is mock_sink
            mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Chat Start Initialization Tests
# ---------------------------------------------------------------------------


class TestOnChatStart:
    """Verify session initialization and starter recommendation chips."""

    @pytest.mark.asyncio
    async def test_on_chat_start_initializes_session_and_sends_welcome(self) -> None:
        await app.on_chat_start()

        session_id = mock_cl.user_session.get("session_id")
        active_slots = mock_cl.user_session.get("active_slots")

        assert session_id is not None
        assert session_id.startswith("sess_")
        assert active_slots == {}

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert "Welcome to Central University of Kashmir (CUK) AI Assistant!" in msg.content
        assert len(msg.actions) == 4

        action_names = [a.name for a in msg.actions]
        assert all(name == "starter_prompt" for name in action_names)

        labels = [a.label for a in msg.actions]
        assert "📚 B.Tech CSE Syllabus" in labels
        assert "📝 Admissions & CUET" in labels
        assert "⚖️ CBCS Ordinances" in labels
        assert "📅 Exam Date Sheets" in labels

        descriptions = [a.description for a in msg.actions]
        assert "Explore course syllabus and credits" in descriptions
        assert "Check entrance requirements and seat matrix" in descriptions
        assert "University academic rules and regulations" in descriptions
        assert "Examination schedules and alerts" in descriptions


# ---------------------------------------------------------------------------
# 3. Starter Prompt Callback Tests
# ---------------------------------------------------------------------------


class TestOnStarterPrompt:
    """Verify quick starter recommendation action execution."""

    @pytest.mark.asyncio
    async def test_on_starter_prompt_triggers_query(self) -> None:
        action = MockAction(
            name="starter_prompt",
            value="What is the detailed syllabus for B.Tech CSE Semester 4?",
            label="📚 B.Tech CSE Syllabus",
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_starter_prompt(action)

            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1
            assert MockMessage.sent_messages[0].content == action.value
            mock_process.assert_awaited_once_with(action.value)


# ---------------------------------------------------------------------------
# 4. Slot Selection Callback Tests
# ---------------------------------------------------------------------------


class TestOnSlotSelected:
    """Verify faceted slot-filling disambiguation chip interactions."""

    @pytest.mark.asyncio
    async def test_on_slot_selected_with_target_slot(self) -> None:
        mock_cl.user_session.set("active_slots", {"department": "Computer Science"})
        mock_cl.user_session.set("last_query", "Tell me the syllabus")

        action = MockAction(
            name="fill_slot",
            value="Semester 4",
            label="4th Semester",
            payload={"target_slot": "semester"},
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            slots = mock_cl.user_session.get("active_slots")
            assert slots == {"department": "Computer Science", "semester": "Semester 4"}
            assert len(MockMessage.sent_messages) == 1
            assert "Selected: **4th Semester**" in MockMessage.sent_messages[0].content
            mock_process.assert_awaited_once_with(
                "Tell me the syllabus",
                updated_slots={"department": "Computer Science", "semester": "Semester 4"},
            )

    @pytest.mark.asyncio
    async def test_on_slot_selected_without_target_slot(self) -> None:
        mock_cl.user_session.set("active_slots", {})
        action = MockAction(
            name="fill_slot", value="General", label="General Category", payload=None
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            assert mock_cl.user_session.get("active_slots") == {}
            assert len(MockMessage.sent_messages) == 1
            assert "Selected: **General Category**" in MockMessage.sent_messages[0].content
            mock_process.assert_awaited_once_with("General", updated_slots={})

    @pytest.mark.asyncio
    async def test_on_slot_selected_fallback_to_action_value_when_no_last_query(self) -> None:
        action = MockAction(
            name="fill_slot",
            value="2024",
            label="Batch 2024",
            payload={"target_slot": "batch_year"},
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            assert mock_cl.user_session.get("active_slots") == {"batch_year": "2024"}
            mock_process.assert_awaited_once_with(
                "2024",
                updated_slots={"batch_year": "2024"},
            )

    @pytest.mark.asyncio
    async def test_on_slot_selected_with_string_payload_does_not_crash(self) -> None:
        """Verify on_slot_selected handles non-dictionary (string) payload gracefully."""
        mock_cl.user_session.set("active_slots", {"program": "B.Tech"})
        mock_cl.user_session.set("last_query", "Tell me the syllabus")

        action = MockAction(
            name="fill_slot",
            value="Semester 4",
            label="4th Semester",
            payload="malformed_string_payload",
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            assert mock_cl.user_session.get("active_slots") == {"program": "B.Tech"}
            assert len(MockMessage.sent_messages) == 1
            assert "Selected: **4th Semester**" in MockMessage.sent_messages[0].content
            mock_process.assert_awaited_once_with(
                "Tell me the syllabus",
                updated_slots={"program": "B.Tech"},
            )

    @pytest.mark.asyncio
    async def test_on_slot_selected_with_none_active_slots_in_session(self) -> None:
        """Verify on_slot_selected initializes active_slots if user_session returns None."""
        mock_cl.user_session.set("active_slots", None)
        mock_cl.user_session.set("last_query", "Check eligibility")

        action = MockAction(
            name="fill_slot",
            value="B.Tech CSE",
            label="B.Tech Computer Science",
            payload={"target_slot": "program"},
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            slots = mock_cl.user_session.get("active_slots")
            assert slots == {"program": "B.Tech CSE"}
            mock_process.assert_awaited_once_with(
                "Check eligibility",
                updated_slots={"program": "B.Tech CSE"},
            )


# ---------------------------------------------------------------------------
# 5. User Feedback Callbacks Tests
# ---------------------------------------------------------------------------


class TestFeedbackCallbacks:
    """Verify positive and negative satisfaction feedback logging."""

    @pytest.mark.asyncio
    async def test_on_feedback_upvote_records_positive_score(self) -> None:
        mock_sink = MagicMock()
        action = MockAction(name="feedback_upvote", value="trace_up_123")

        with patch.object(app, "get_ui_telemetry_sink", return_value=mock_sink):
            await app.on_feedback_upvote(action)

            mock_sink.record_feedback.assert_called_once_with(
                trace_id="trace_up_123",
                score=1,
                feedback_category="helpful",
            )
            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1
            assert "Marked as helpful 👍" in MockMessage.sent_messages[0].content

    @pytest.mark.asyncio
    async def test_on_feedback_downvote_records_negative_score(self) -> None:
        mock_sink = MagicMock()
        action = MockAction(name="feedback_downvote", value="trace_down_456")

        with patch.object(app, "get_ui_telemetry_sink", return_value=mock_sink):
            await app.on_feedback_downvote(action)

            mock_sink.record_feedback.assert_called_once_with(
                trace_id="trace_down_456",
                score=-1,
                feedback_category="unhelpful",
            )
            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1
            assert "Marked as unhelpful 👎" in MockMessage.sent_messages[0].content

    @pytest.mark.asyncio
    async def test_feedback_handles_sink_without_record_feedback_gracefully(self) -> None:
        mock_sink = object()  # sink without record_feedback method
        action = MockAction(name="feedback_upvote", value="trace_none")

        with patch.object(app, "get_ui_telemetry_sink", return_value=mock_sink):
            await app.on_feedback_upvote(action)
            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1


# ---------------------------------------------------------------------------
# 6. Main Chat Message Dispatch Tests
# ---------------------------------------------------------------------------


class TestOnMessage:
    """Verify incoming user query handling and sanitization."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_input", ["", "   ", "\t\n  \r\n"])
    async def test_on_message_ignores_empty_or_whitespace_queries(self, empty_input: str) -> None:
        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_message(MockMessage(content=empty_input))
            mock_process.assert_not_called()
            assert mock_cl.user_session.get("last_query") is None

    @pytest.mark.asyncio
    async def test_on_message_dispatches_valid_query(self) -> None:
        mock_cl.user_session.set("active_slots", {"program": "B.Tech CSE"})
        message = MockMessage(content="  What is the attendance requirement?  ")

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_message(message)

            assert mock_cl.user_session.get("last_query") == "What is the attendance requirement?"
            mock_process.assert_awaited_once_with(
                "What is the attendance requirement?",
                updated_slots={"program": "B.Tech CSE"},
            )


# ---------------------------------------------------------------------------
# 7. Real-Time Streaming & Citation Card Rendering Tests
# ---------------------------------------------------------------------------


class TestProcessQuery:
    """Verify synthesis streaming, side-panel citation cards, and slot chips."""

    @pytest.mark.asyncio
    async def test_process_query_streaming_tokens_and_feedback(self) -> None:
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Central "}
            yield {"type": "token", "text": "University of Kashmir"}
            yield {"type": "done", "trace_id": "trace_turn_01"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Tell me about CUK")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert msg.tokens_streamed == ["Central ", "University of Kashmir"]
        assert msg.content == "Central University of Kashmir"
        assert msg.updated is True

        # Verified completed turn gets feedback upvote/downvote buttons
        assert len(msg.actions) == 2
        assert msg.actions[0].name == "feedback_upvote"
        assert msg.actions[0].value == "trace_turn_01"
        assert msg.actions[0].label == "👍 Helpful"
        assert msg.actions[1].name == "feedback_downvote"
        assert msg.actions[1].value == "trace_turn_01"
        assert msg.actions[1].label == "👎 Inaccurate"

    @pytest.mark.asyncio
    async def test_process_query_with_text_and_table_citation_cards(self) -> None:
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Here is the syllabus and fee structure."}
            yield {
                "type": "citation_card",
                "title": "B.Tech CSE Regulations",
                "source_url": "https://cukashmir.ac.in/syllabus.pdf",
                "page_number": 12,
                "section_heading": "Unit 3",
                "quoted_snippet": "Minimum attendance required is 75 percent.",
                "is_table": False,
            }
            yield {
                "type": "citation_card",
                "title": "Fee Matrix 2024",
                "source_url": "https://cukashmir.ac.in/fees.pdf",
                "page_number": 2,
                "is_table": True,
                "table_markdown": "| Semester | Amount |\n|---|---|\n| 1st | 15000 |",
            }
            yield {"type": "done", "trace_id": "trace_citations_02"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("What are the attendance and fees?")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert len(msg.elements) == 2

        # Text citation element
        card1 = msg.elements[0]
        assert "[1] B.Tech CSE Regulations" in card1.name
        assert "(p. 12)" in card1.name
        assert (
            "**Document:** [B.Tech CSE Regulations](https://cukashmir.ac.in/syllabus.pdf)"
            in card1.content
        )
        assert "**Page:** 12 | **Section:** Unit 3" in card1.content
        assert '> "Minimum attendance required is 75 percent."' in card1.content
        assert card1.display == "side"

        # Table citation element
        card2 = msg.elements[1]
        assert "[2] Fee Matrix 2024" in card2.name
        assert "(p. 2)" in card2.name
        assert "### Fee Matrix 2024 (Page 2)" in card2.content
        assert (
            "**Source:** [https://cukashmir.ac.in/fees.pdf](https://cukashmir.ac.in/fees.pdf)"
            in card2.content
        )
        assert "| Semester | Amount |" in card2.content
        assert card2.display == "side"

    @pytest.mark.asyncio
    async def test_process_query_citation_card_defaults_when_optional_fields_missing(self) -> None:
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {
                "type": "citation_card",
                # missing title, source_url, page_number, section_heading, quoted_snippet
            }
            yield {"type": "done"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Query")

        msg = MockMessage.sent_messages[0]
        assert len(msg.elements) == 1
        card = msg.elements[0]
        assert "Official University Document" in card.name
        assert "(p. 1)" in card.name
        assert "**Section:** General" in card.content

    @pytest.mark.asyncio
    async def test_process_query_with_slot_prompt_chips(self) -> None:
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Please choose your semester:"}
            yield {
                "type": "slot_prompt",
                "target_slot": "semester",
                "options": [
                    {"value": "sem_1", "label": "Semester 1", "description": "1st Semester"},
                    {"value": "sem_4", "label": "Semester 4"},
                ],
            }
            yield {"type": "done", "trace_id": "trace_slot_03"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Syllabus for B.Tech")

        msg = MockMessage.sent_messages[0]
        # When slot clarification actions exist, feedback buttons are suppressed
        assert len(msg.actions) == 2
        assert [a.name for a in msg.actions] == ["fill_slot", "fill_slot"]
        assert msg.actions[0].value == "sem_1"
        assert msg.actions[0].label == "Semester 1"
        assert msg.actions[0].description == "1st Semester"
        assert msg.actions[0].payload == {"target_slot": "semester"}

        assert msg.actions[1].value == "sem_4"
        assert msg.actions[1].label == "Semester 4"
        assert msg.actions[1].description == "Select Semester 4"
        assert msg.actions[1].payload == {"target_slot": "semester"}

    @pytest.mark.asyncio
    async def test_process_query_generates_fresh_session_id_if_none(self) -> None:
        captured_session_id: list[str] = []

        async def spy_stream(
            query: str,
            session_id: str,
            slots: Any = None,
            trace_id: Any = None,
        ) -> AsyncIterator[dict[str, Any]]:
            captured_session_id.append(session_id)
            yield {"type": "token", "token": "Hi"}
            yield {"type": "done", "trace_id": "trace_gen_04"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = spy_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Hello")

        assert len(captured_session_id) == 1
        assert captured_session_id[0].startswith("sess_")

    @pytest.mark.asyncio
    async def test_process_query_citation_card_with_explicit_none_fields(self) -> None:
        """Verify citation card rendering when optional fields are explicitly None."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {
                "type": "citation_card",
                "title": None,
                "source_url": None,
                "page_number": None,
                "section_heading": None,
                "quoted_snippet": None,
                "is_table": False,
            }
            yield {"type": "done"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Tell me about the rules")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert len(msg.elements) == 1
        card = msg.elements[0]
        assert "[1] Official University Document" in card.name
        assert "(p. 1)" in card.name
        assert (
            "**Document:** [Official University Document](https://cukashmir.ac.in)" in card.content
        )
        assert "**Page:** 1 | **Section:** General" in card.content
        assert card.display == "side"

    @pytest.mark.asyncio
    async def test_process_query_table_citation_card_with_explicit_none_fields(self) -> None:
        """Verify table citation card rendering when title, source_url, page_number are None."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {
                "type": "citation_card",
                "title": None,
                "source_url": None,
                "page_number": None,
                "is_table": True,
                "table_markdown": "| Col A | Col B |\n|---|---|\n| 1 | 2 |",
            }
            yield {"type": "done"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Show me fee table")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert len(msg.elements) == 1
        card = msg.elements[0]
        assert "[1] Official University Document" in card.name
        assert "(p. 1)" in card.name
        assert "### Official University Document (Page 1)" in card.content
        assert "**Source:** [https://cukashmir.ac.in](https://cukashmir.ac.in)" in card.content
        assert "| Col A | Col B |" in card.content
        assert card.display == "side"

    @pytest.mark.asyncio
    async def test_process_query_with_string_list_slot_options(self) -> None:
        """Verify slot prompt rendering when options are a list of strings."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Please select your program:"}
            yield {
                "type": "slot_prompt",
                "target_slot": "program",
                "options": ["B.Tech CSE", "MCA"],
            }
            yield {"type": "done"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("What is the syllabus?")

        msg = MockMessage.sent_messages[0]
        assert len(msg.actions) == 2
        assert [a.name for a in msg.actions] == ["fill_slot", "fill_slot"]

        assert msg.actions[0].value == "B.Tech CSE"
        assert msg.actions[0].label == "B.Tech CSE"
        assert msg.actions[0].description == "Select B.Tech CSE"
        assert msg.actions[0].payload == {"target_slot": "program"}

        assert msg.actions[1].value == "MCA"
        assert msg.actions[1].label == "MCA"
        assert msg.actions[1].description == "Select MCA"
        assert msg.actions[1].payload == {"target_slot": "program"}

    @pytest.mark.asyncio
    async def test_process_query_with_slot_prompt_options_none(self) -> None:
        """Verify slot prompt rendering when options key is explicitly None."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Please specify:"}
            yield {
                "type": "slot_prompt",
                "target_slot": "batch",
                "options": None,
            }
            yield {"type": "done", "trace_id": "trace_opt_none"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Admissions info")

        msg = MockMessage.sent_messages[0]
        # When options is None, no slot actions should be created; falls back to feedback buttons
        assert len(msg.actions) == 2
        assert [a.name for a in msg.actions] == ["feedback_upvote", "feedback_downvote"]

    @pytest.mark.asyncio
    async def test_process_query_streaming_token_none_with_text_fallback(self) -> None:
        """Verify token extraction falls back to text when token is explicitly None."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": None, "text": "Fallback text chunk "}
            yield {"type": "token", "token": None, "text": None}  # Both None: safely ignored
            yield {"type": "token", "token": "Regular token"}
            yield {"type": "done", "trace_id": "trace_fallback_01"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Stream test")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert msg.tokens_streamed == ["Fallback text chunk ", "Regular token"]
        assert msg.content == "Fallback text chunk Regular token"
        assert msg.updated is True

    @pytest.mark.asyncio
    async def test_process_query_handles_stream_exception_gracefully(self) -> None:
        """Verify stream exceptions do not crash process_query and finalize the message."""

        async def mock_crashing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Starting response..."}
            raise RuntimeError("Database connection lost")

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_crashing_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("What is CBCS?")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert "Starting response..." in msg.content
        assert "⚠️" in msg.content
        assert msg.updated is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error_event", "expected_substring"),
        [
            ({"type": "error", "error": "Rate limit exceeded"}, "Rate limit exceeded"),
            (
                {"type": "error", "message": "Failed to connect to model"},
                "Failed to connect to model",
            ),
            ({"type": "error"}, "An error occurred"),
        ],
    )
    async def test_process_query_handles_error_event(
        self,
        error_event: dict[str, Any],
        expected_substring: str,
    ) -> None:
        """Verify error events emitted by orchestrator are streamed and displayed to user."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield error_event
            yield {"type": "done"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Will cause error")

        assert len(MockMessage.sent_messages) == 1
        msg = MockMessage.sent_messages[0]
        assert expected_substring in msg.content
        assert msg.updated is True

    @pytest.mark.asyncio
    async def test_process_query_preserves_generated_trace_id_when_done_trace_id_is_none(
        self,
    ) -> None:
        """Verify valid UUID trace_id is preserved when done event has trace_id=None."""

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Grounded answer text."}
            yield {"type": "done", "trace_id": None}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream

        with patch.object(app, "get_ui_orchestrator", return_value=mock_orch):
            await app.process_query("Tell me about admission")

        msg = MockMessage.sent_messages[0]
        assert len(msg.actions) == 2
        upvote = msg.actions[0]
        downvote = msg.actions[1]

        assert upvote.name == "feedback_upvote"
        assert upvote.value is not None
        assert upvote.value != "None"
        assert len(str(upvote.value)) == 32  # 32-character hex UUID
        assert downvote.value == upvote.value


# ---------------------------------------------------------------------------
# 8. CLI Runner Entrypoint Tests
# ---------------------------------------------------------------------------


class TestCliRun:
    """Verify cuk-ui runner behavior in present and absent chainlit states."""

    def test_run_missing_chainlit_exits_with_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(app, "cl", None):
            with pytest.raises(SystemExit) as exc_info:
                app.run()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "ERROR: 'chainlit' is not installed" in captured.err

    def test_run_spawns_subprocess_with_environment_variables(self) -> None:
        with (
            patch("subprocess.run") as mock_subproc,
            patch.dict(os.environ, {"CHAINLIT_PORT": "8085", "CHAINLIT_HOST": "127.0.0.1"}),
        ):
            app.run()
            mock_subproc.assert_called_once()
            cmd = mock_subproc.call_args[0][0]
            assert cmd[0] == sys.executable
            assert "-m" in cmd
            assert "chainlit" in cmd
            assert "run" in cmd
            assert "--host" in cmd and "127.0.0.1" in cmd
            assert "--port" in cmd and "8085" in cmd

    def test_run_spawns_subprocess_with_default_arguments(self) -> None:
        """Verify default CLI runner arguments match specification (port 8001, host 0.0.0.0)."""
        with patch("subprocess.run") as mock_subproc, patch.dict(os.environ, {}, clear=True):
            app.run()
            mock_subproc.assert_called_once()
            cmd = mock_subproc.call_args[0][0]
            assert "--host" in cmd and "0.0.0.0" in cmd
            assert "--port" in cmd and "8001" in cmd

    def test_run_handles_keyboard_interrupt_gracefully(self) -> None:
        with patch("subprocess.run", side_effect=KeyboardInterrupt):
            # Must exit cleanly without re-raising exception
            app.run()

    @pytest.mark.parametrize("empty_or_invalid_port", ["", "   ", "abc", "99999", "-1"])
    def test_run_falls_back_to_default_port_8001_on_invalid_env(
        self, empty_or_invalid_port: str
    ) -> None:
        """Verify invalid or empty CHAINLIT_PORT falls back safely to default 8001."""
        with (
            patch("subprocess.run") as mock_subproc,
            patch.dict(os.environ, {"CHAINLIT_PORT": empty_or_invalid_port}),
        ):
            app.run()
            cmd = mock_subproc.call_args[0][0]
            port_index = cmd.index("--port")
            assert cmd[port_index + 1] == "8001"

    def test_run_handles_subprocess_called_process_error(self) -> None:
        """Verify non-zero exit from Chainlit server is cleanly handled with SystemExit."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(2, ["chainlit", "run"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                app.run()
            assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# 9. Teardown Module Isolation Tests
# ---------------------------------------------------------------------------


class TestModuleTeardown:
    """Verify teardown_module restores sys.modules and cleans app.cl state."""

    def test_teardown_module_restores_chainlit_state(self) -> None:
        """Verify teardown_module sets app.cl to None when chainlit is not installed."""
        teardown_module()
        try:
            if _orig_chainlit is None:
                assert app.cl is None
                assert "chainlit" not in sys.modules
            else:
                assert app.cl is _orig_chainlit
        finally:
            # Re-establish mock for test isolation within session
            sys.modules["chainlit"] = mock_cl
            importlib.reload(app)


# ---------------------------------------------------------------------------
# 10. Mock User Session Isolation and Concurrency Tests
# ---------------------------------------------------------------------------


class TestMockUserSessionIsolation:
    """Verify MockUserSession context isolation, copy-on-write semantics, and concurrency."""

    @pytest.fixture
    def session(self) -> MockUserSession:
        """Provide a clean MockUserSession instance for each test."""
        s = MockUserSession()
        s.clear()
        return s

    def test_default_value_and_nonexistent_keys(self, session: MockUserSession) -> None:
        """Verify default value fallback and non-existent key retrieval."""
        assert session.get("missing") is None
        assert session.get("missing_str", "fallback") == "fallback"
        assert session.get("missing_int", 42) == 42
        assert session.get("missing_dict", {"k": "v"}) == {"k": "v"}
        assert session.get("missing_none", None) is None

        # Key explicitly set to None must return None, not the fallback default
        session.set("explicit_none", None)
        assert session.get("explicit_none") is None
        assert session.get("explicit_none", "fallback") is None

        # Sequential overwrites within same context
        session.set("counter", 1)
        assert session.get("counter") == 1
        session.set("counter", 2)
        assert session.get("counter") == 2

    def test_clear_resets_current_context(self, session: MockUserSession) -> None:
        """Verify clear empties the session store in the active context."""
        session.set("alpha", 1)
        session.set("beta", "two")
        assert session.get("alpha") == 1
        assert session.get("beta") == "two"

        session.clear()
        assert session.get("alpha") is None
        assert session.get("beta") is None

        session.set("gamma", 3)
        assert session.get("gamma") == 3

    def test_copy_context_isolation_independent_keys(self, session: MockUserSession) -> None:
        """Verify independent keys set in copied contexts do not cross-contaminate."""
        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.set, "user", "Alice")
        ctx2.run(session.set, "role", "admin")

        assert ctx1.run(session.get, "user") == "Alice"
        assert ctx1.run(session.get, "role") is None
        assert ctx2.run(session.get, "role") == "admin"
        assert ctx2.run(session.get, "user") is None
        assert session.get("user") is None
        assert session.get("role") is None

    def test_copy_context_isolation_identical_keys(self, session: MockUserSession) -> None:
        """Verify identical keys modified in copied contexts maintain copy-on-write isolation."""
        session.set("session_id", "root_session")

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.set, "session_id", "session_alpha")
        ctx2.run(session.set, "session_id", "session_beta")

        assert ctx1.run(session.get, "session_id") == "session_alpha"
        assert ctx2.run(session.get, "session_id") == "session_beta"
        assert session.get("session_id") == "root_session"

    def test_copy_context_clear_isolation_across_siblings(self, session: MockUserSession) -> None:
        """Verify clear() in one copied context leaves sibling and parent contexts intact."""
        session.set("shared_key", "shared_val")
        session.set("active_slots", {"cohort": "2024"})

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.clear)

        assert ctx1.run(session.get, "shared_key") is None
        assert ctx1.run(session.get, "active_slots") is None
        assert ctx2.run(session.get, "shared_key") == "shared_val"
        assert ctx2.run(session.get, "active_slots") == {"cohort": "2024"}
        assert session.get("shared_key") == "shared_val"
        assert session.get("active_slots") == {"cohort": "2024"}

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_tasks_identical_keys(self, session: MockUserSession) -> None:
        """Verify concurrent async tasks writing to the same key maintain isolated values."""

        async def worker(worker_id: int) -> str:
            session.set("user_id", f"user_{worker_id}")
            await asyncio.sleep(0.005 * (worker_id % 3 + 1))
            return str(session.get("user_id"))

        results = await asyncio.gather(*(worker(i) for i in range(10)))
        for i, val in enumerate(results):
            assert val == f"user_{i}", f"Expected user_{i}, got {val}"
        assert session.get("user_id") is None

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_tasks_independent_keys(
        self, session: MockUserSession
    ) -> None:
        """Verify concurrent async tasks modifying independent keys do not leak across tasks."""

        async def worker(worker_id: int) -> tuple[Any, list[Any]]:
            session.set(f"task_key_{worker_id}", f"val_{worker_id}")
            await asyncio.sleep(0.005 * (worker_id % 3 + 1))
            my_val = session.get(f"task_key_{worker_id}")
            other_vals = [session.get(f"task_key_{j}") for j in range(6) if j != worker_id]
            return my_val, other_vals

        results = await asyncio.gather(*(worker(i) for i in range(6)))
        for i, (my_val, other_vals) in enumerate(results):
            assert my_val == f"val_{i}"
            assert all(v is None for v in other_vals), f"Worker {i} leaked keys: {other_vals}"

        for i in range(6):
            assert session.get(f"task_key_{i}") is None

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_clear_isolation(self, session: MockUserSession) -> None:
        """Verify clear() in one async task does not clobber session state in concurrent sibling tasks."""
        session.set("common_flag", "initial_state")

        async def task_clear() -> tuple[Any, Any]:
            await asyncio.sleep(0.002)
            session.clear()
            session.set("cleared_task_flag", "done")
            await asyncio.sleep(0.01)
            return session.get("common_flag"), session.get("cleared_task_flag")

        async def task_reader() -> tuple[Any, Any]:
            val1 = session.get("common_flag")
            await asyncio.sleep(0.008)
            val2 = session.get("common_flag")
            session.set("reader_flag", "active")
            return val1, val2

        (c_shared, c_flag), (r_val1, r_val2) = await asyncio.gather(task_clear(), task_reader())
        assert c_shared is None
        assert c_flag == "done"
        assert r_val1 == "initial_state"
        assert r_val2 == "initial_state"
        assert session.get("common_flag") == "initial_state"
        assert session.get("cleared_task_flag") is None
        assert session.get("reader_flag") is None

    @pytest.mark.asyncio
    async def test_child_task_mutation_does_not_mutate_parent(
        self, session: MockUserSession
    ) -> None:
        """Verify mutations in child asyncio.create_task do not leak back to parent context."""
        session.set("initial", "val0")

        async def child() -> tuple[Any, Any]:
            session.set("initial", "mutated_in_child")
            session.set("child_only", "child_val")
            return session.get("initial"), session.get("child_only")

        c_init, c_child = await asyncio.create_task(child())
        assert c_init == "mutated_in_child"
        assert c_child == "child_val"
        assert session.get("initial") == "val0"
        assert session.get("child_only") is None

    @pytest.mark.asyncio
    async def test_child_task_clear_does_not_clear_parent(self, session: MockUserSession) -> None:
        """Verify session.clear() in child task does not clear parent session."""
        session.set("token", "secret123")

        async def child() -> Any:
            session.clear()
            return session.get("token")

        c_tok = await asyncio.create_task(child())
        assert c_tok is None
        assert session.get("token") == "secret123"

    @pytest.mark.asyncio
    async def test_mock_cl_user_session_concurrency(self) -> None:
        """Verify global mock_cl.user_session instance isolates concurrent task sessions."""

        async def task_a() -> Any:
            mock_cl.user_session.set("user", "Alice")
            await asyncio.sleep(0.005)
            return mock_cl.user_session.get("user")

        async def task_b() -> Any:
            mock_cl.user_session.set("user", "Bob")
            await asyncio.sleep(0.005)
            return mock_cl.user_session.get("user")

        r_a, r_b = await asyncio.gather(task_a(), task_b())
        assert r_a == "Alice"
        assert r_b == "Bob"
        assert mock_cl.user_session.get("user") is None
