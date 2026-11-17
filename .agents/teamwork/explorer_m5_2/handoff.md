# Investigation Report: Chainlit UI Mock Architecture (`tests/unit/test_chainlit_ui.py`)

## 1. Observation

### 1.1 Environment & Dependency State
- **Command**: `uv run python -c "import chainlit"`
- **Verbatim Output**:
  ```
  Traceback (most recent call last):
    File "<string>", line 1, in <module>
  ModuleNotFoundError: No module named 'chainlit'
  ```
- **File Inspection**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/pyproject.toml`
  - Dependencies in `[project.dependencies]` (lines 10-31) include:
    `beautifulsoup4`, `httpx`, `lxml`, `pymupdf`, `python-dotenv`, `tenacity`, `typer`, `rich`, `pandas`, `pydantic`, `fastapi`, `uvicorn`, `lancedb`, `fastembed`, `flashrank`, `pyarrow`, `tantivy`.
  - Dependencies in `[dependency-groups.dev]` (lines 53-57) include:
    `pytest`, `pytest-asyncio`, `ruff`.
  - `chainlit` is **NOT listed** in either `project.dependencies` or `dependency-groups.dev`.

### 1.2 Structure & Lifecycle in `cuk_assistant/ui/app.py`
Examining `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/cuk_assistant/ui/app.py` line-by-line:
- **Lines 24-43**:
  Lazy singletons `_orchestrator` and `_telemetry_sink` accessed via `get_ui_orchestrator()` and `get_ui_telemetry_sink()`.
- **Lines 49-51 & Line 254-256**:
  ```python
  try:
      import chainlit as cl
      ...
  except ImportError:
      cl = None
  ```
  When `chainlit` is not installed, importing `cuk_assistant.ui.app` raises `ModuleNotFoundError` on line 50. The exception is caught at line 254 (`except ImportError: cl = None`). Consequently, **lines 52–253 are skipped entirely**. When `cl is None`, the callbacks (`on_chat_start`, `on_starter_prompt`, `on_slot_selected`, `on_feedback_upvote`, `on_feedback_downvote`, `on_message`, `process_query`) are **never defined or exported** in `cuk_assistant.ui.app`.
- **Lines 52-93 (`on_chat_start`)**:
  - Initializes user session keys: `session_id` (format `sess_<hex>`) and `active_slots = {}`.
  - Sends initial welcome message with 4 starter prompt action chips (`Action(name="starter_prompt", ...)`).
- **Lines 94-101 (`on_starter_prompt`)**:
  - Removes clicked action (`await action.remove()`), sends echo user message, and invokes `await process_query(action.value)`.
- **Lines 102-117 (`on_slot_selected`)**:
  - Removes action, updates `active_slots[target_slot] = action.value`, saves to `cl.user_session`, echoes selection, and calls `await process_query(last_query, updated_slots=active_slots)`.
- **Lines 118-137 (`on_feedback_upvote` / `on_feedback_downvote`)**:
  - Extracts `trace_id = str(action.value)`.
  - Calls `sink.record_feedback(trace_id=trace_id, score=1 or -1, feedback_category="helpful" or "unhelpful")` on `get_ui_telemetry_sink()`.
  - Sends confirmation message and removes action button.
- **Lines 138-148 (`on_message`)**:
  - Guards against whitespace: `if not query_text: return`.
  - Updates `cl.user_session.set("last_query", query_text)`.
  - Dispatches `await process_query(query_text, updated_slots=active_slots)`.
- **Lines 149-253 (`process_query`)**:
  - Instantiates initial `cl.Message(content="")` and awaits `send()`.
  - Streams from `orchestrator.stream_turn(...)`.
  - Dispatches by event type:
    - `"token"`: `await msg.stream_token(token)`.
    - `"slot_prompt"`: creates interactive `cl.Action(name="fill_slot", ...)` buttons.
    - `"citation_card"`: creates side-panel `cl.Text(name=..., content=..., display="side")` supporting both plain text and markdown table snippets.
    - `"done"`: updates `turn_trace_id`.
  - Post-stream:
    - If `citation_elements`: assigns `msg.elements = citation_elements`.
    - If `slot_actions`: assigns `msg.actions = slot_actions` (slot clarification chips).
    - If no `slot_actions`: assigns `feedback_actions` (thumbs up/down `cl.Action` chips).
    - Awaits `msg.update()`.
- **Lines 263-300 (`run()`)**:
  - If `cl is None`: prints error to `sys.stderr` and executes `sys.exit(1)`.
  - Else: executes `subprocess.run([sys.executable, "-m", "chainlit", "run", ...], check=True)` catching `KeyboardInterrupt`.

---

## 2. Logic Chain

1. **Premise 1 (Execution Environment Independence)**:
   Unit tests (`tests/unit/`) in `cuk-assistant` must run cleanly via `uv run pytest tests/unit/ -q` without external network connections, browser drivers, or daemon processes. Furthermore, since `chainlit` is not currently in the environment or base dependencies, importing `app.py` directly without a mocked `chainlit` leaves all UI callbacks uninstantiated.

2. **Premise 2 (Module Injection via `sys.modules`)**:
   In Python, `import chainlit` queries `sys.modules["chainlit"]` before inspecting filesystem paths. If a mock module conforming to Chainlit's runtime surface (`user_session`, `Message`, `Action`, `Text`, and decorators `on_chat_start`, `action_callback`, `on_message`) is installed into `sys.modules["chainlit"]` and `cuk_assistant.ui.app` is imported or reloaded, Python executes the entire `try:` block (lines 52–253). This binds every callback to the module and decorators.

3. **Premise 3 (State Isolation & Teardown)**:
   Using a `pytest` fixture with yield-based cleanup guarantees that:
   - The mock `chainlit` module is injected before any test in `test_chainlit_ui.py` runs.
   - Session state (`user_session`) and sent message logs are isolated per test.
   - Singleton globals (`app._orchestrator` and `app._telemetry_sink`) are reset after each test.
   - `sys.modules` is restored upon completion of the test suite so subsequent test suites are unaffected.

4. **Premise 4 (Determinism of Orchestrator & Telemetry Mocking)**:
   By assigning a mock orchestrator to `app._orchestrator` with an async generator `stream_turn`, tests can deterministically simulate token streaming, single and multi-page text citation cards, markdown table citation cards, slot prompt action chips, and done events without executing LanceDB, ONNX FastEmbed, or LLM network requests.

---

## 3. Caveats

1. **No Real Browser / WebSocket Validation**:
   This mock architecture tests the Python event handling, session state management, message assembly, citation card formatting, and telemetry dispatch. It does not test frontend React component rendering, CSS layout, or actual WebSocket protocol framing (which belong in end-to-end browser tests or manual validation via `chainlit run`).
2. **CLI Runner Testing**:
   Testing `app.run()` tests the validation gate (`cl is None`), CLI argument assembly (`--host`, `--port`), and `subprocess.run` invocation with graceful `KeyboardInterrupt` handling. It does not spawn the actual Chainlit web server subprocess.

---

## 4. Conclusion & Concrete Implementation Proposal

### 4.1 Mock Architecture Design
The test architecture consists of:
1. **Mock Chainlit Module**:
   - `MockUserSession`: in-memory dict backing `get(key, default)` and `set(key, value)`.
   - `MockAction`: simulates `Action(name, value, label, description, payload)` with `async def remove()`.
   - `MockMessage`: simulates `Message(content, actions, elements)` with `async def send()`, `async def stream_token(token)`, and `async def update()`.
   - `MockText`: simulates `Text(name, content, display="side")`.
   - Decorators: pass-through identity wrappers registering callback functions.
2. **Pytest Fixtures**:
   - `mock_chainlit`: sets up `sys.modules["chainlit"]`, reloads `cuk_assistant.ui.app`, resets state on teardown.
   - `mock_orchestrator`: provides configurable `stream_turn` async generator.
   - `mock_telemetry_sink`: provides telemetry feedback spy.

### 4.2 Exact Proposed Implementation for `tests/unit/test_chainlit_ui.py`
The complete, self-contained test file ready for implementation by the serving worker:

```python
"""tests/unit/test_chainlit_ui.py

Unit tests for Chainlit Web Application (`cuk_assistant/ui/app.py`):
1. Import error fallback and CLI runner (`run()`) behavior.
2. Session initialization and starter recommendation chips (`on_chat_start`).
3. Quick-reply starter prompt button handling (`on_starter_prompt`).
4. Faceted slot-filling chip selection and re-querying (`on_slot_selected`).
5. Feedback telemetry upvote and downvote recording (`on_feedback_upvote`, `on_feedback_downvote`).
6. Chat message intake and whitespace filtering (`on_message`).
7. Real-time streaming response synthesis (`process_query`):
   - Token streaming.
   - Plain text citation cards.
   - Markdown table citation cards.
   - Slot-filling disambiguation action chips (suppressing feedback buttons).
   - Verified turn completion with thumbs up/down feedback buttons.
8. Singleton factory caching (`get_ui_orchestrator`, `get_ui_telemetry_sink`).
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock Chainlit Module Infrastructure
# ---------------------------------------------------------------------------


class MockUserSession:
    """In-memory mock for Chainlit user session."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def clear(self) -> None:
        self.state.clear()


class MockAction:
    """In-memory mock for Chainlit Action."""

    def __init__(
        self,
        name: str = "",
        value: str = "",
        label: str = "",
        description: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self.label = label
        self.description = description
        self.payload = payload or {}
        self.removed = False

    async def remove(self) -> None:
        self.removed = True


class MockText:
    """In-memory mock for Chainlit Text element (citation cards)."""

    def __init__(self, name: str = "", content: str = "", display: str = "side") -> None:
        self.name = name
        self.content = content
        self.display = display


class MockMessage:
    """In-memory mock for Chainlit Message."""

    def __init__(
        self,
        content: str = "",
        actions: list[MockAction] | None = None,
        elements: list[MockText] | None = None,
    ) -> None:
        self.content = content
        self.actions = actions or []
        self.elements = elements or []
        self.sent = False
        self.tokens: list[str] = []
        self.updated = False

    async def send(self) -> MockMessage:
        self.sent = True
        return self

    async def stream_token(self, token: str) -> None:
        self.tokens.append(token)

    async def update(self) -> MockMessage:
        self.updated = True
        return self


@pytest.fixture(autouse=True)
def chainlit_env() -> Generator[types.ModuleType, None, None]:
    """Provide a mocked Chainlit module in sys.modules and reload app.py."""
    orig_chainlit = sys.modules.get("chainlit")

    mock_cl = types.ModuleType("chainlit")
    user_session = MockUserSession()
    mock_cl.user_session = user_session
    mock_cl.Action = MockAction
    mock_cl.Text = MockText
    mock_cl.Message = MockMessage
    mock_cl.on_chat_start = lambda fn: fn
    mock_cl.action_callback = lambda name: (lambda fn: fn)
    mock_cl.on_message = lambda fn: fn

    sys.modules["chainlit"] = mock_cl

    import cuk_assistant.ui.app as app

    importlib.reload(app)
    app.cl = mock_cl

    yield mock_cl

    # Teardown
    app._orchestrator = None
    app._telemetry_sink = None
    if orig_chainlit is not None:
        sys.modules["chainlit"] = orig_chainlit
    else:
        sys.modules.pop("chainlit", None)


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestChainlitUI:
    """Comprehensive test suite for cuk_assistant/ui/app.py."""

    # 1. Singleton Caching Tests
    def test_get_ui_orchestrator_initialization_and_caching(self) -> None:
        import cuk_assistant.ui.app as app

        app._orchestrator = None
        mock_orch = MagicMock()
        with patch("cuk_assistant.ui.app.create_rag_orchestrator", return_value=mock_orch) as mock_create:
            orch1 = app.get_ui_orchestrator()
            orch2 = app.get_ui_orchestrator()
            assert orch1 is orch2
            assert orch1 is mock_orch
            mock_create.assert_called_once()

    def test_get_ui_telemetry_sink_initialization_and_caching(self) -> None:
        import cuk_assistant.ui.app as app

        app._telemetry_sink = None
        mock_sink = MagicMock()
        with patch("cuk_assistant.ui.app.create_telemetry_sink", return_value=mock_sink) as mock_create:
            sink1 = app.get_ui_telemetry_sink()
            sink2 = app.get_ui_telemetry_sink()
            assert sink1 is sink2
            assert sink1 is mock_sink
            mock_create.assert_called_once()

    # 2. Lifecycle & Session Start
    @pytest.mark.asyncio
    async def test_on_chat_start_initializes_session_and_sends_welcome(self) -> None:
        import cuk_assistant.ui.app as app

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.on_chat_start()

        session_id = app.cl.user_session.get("session_id")
        active_slots = app.cl.user_session.get("active_slots")

        assert session_id is not None
        assert session_id.startswith("sess_")
        assert active_slots == {}

        assert len(sent_messages) == 1
        msg = sent_messages[0]
        assert "Welcome to Central University of Kashmir (CUK) AI Assistant!" in msg.content
        assert len(msg.actions) == 4
        action_names = [a.name for a in msg.actions]
        assert all(name == "starter_prompt" for name in action_names)
        labels = [a.label for a in msg.actions]
        assert any("B.Tech CSE Syllabus" in l for l in labels)
        assert any("Admissions & CUET" in l for l in labels)
        assert any("CBCS Ordinances" in l for l in labels)
        assert any("Exam Date Sheets" in l for l in labels)

    # 3. Quick Starter Prompt Callback
    @pytest.mark.asyncio
    async def test_on_starter_prompt_triggers_query(self) -> None:
        import cuk_assistant.ui.app as app

        action = MockAction(
            name="starter_prompt",
            value="What is the detailed syllabus for B.Tech CSE Semester 4?",
            label="📚 B.Tech CSE Syllabus",
        )

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True), \
             patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_starter_prompt(action)

            assert action.removed is True
            assert len(sent_messages) == 1
            assert sent_messages[0].content == action.value
            mock_process.assert_called_once_with(action.value)

    # 4. Slot Selection Callback
    @pytest.mark.asyncio
    async def test_on_slot_selected_updates_session_and_reprocesses(self) -> None:
        import cuk_assistant.ui.app as app

        app.cl.user_session.set("active_slots", {"department": "Computer Science"})
        app.cl.user_session.set("last_query", "Tell me the syllabus")

        action = MockAction(
            name="fill_slot",
            value="Semester 4",
            label="4th Semester",
            payload={"target_slot": "semester"},
        )

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True), \
             patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)

            assert action.removed is True
            slots = app.cl.user_session.get("active_slots")
            assert slots == {"department": "Computer Science", "semester": "Semester 4"}
            assert len(sent_messages) == 1
            assert "Selected: **4th Semester**" in sent_messages[0].content
            mock_process.assert_called_once_with(
                "Tell me the syllabus",
                updated_slots={"department": "Computer Science", "semester": "Semester 4"},
            )

    @pytest.mark.asyncio
    async def test_on_slot_selected_handles_empty_payload(self) -> None:
        import cuk_assistant.ui.app as app

        app.cl.user_session.set("active_slots", {})
        action = MockAction(name="fill_slot", value="val", label="lbl", payload=None)

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_slot_selected(action)
            assert action.removed is True
            mock_process.assert_called_once()

    # 5. Feedback Callbacks
    @pytest.mark.asyncio
    async def test_on_feedback_upvote_records_positive_telemetry(self) -> None:
        import cuk_assistant.ui.app as app

        mock_sink = MagicMock()
        app._telemetry_sink = mock_sink

        action = MockAction(name="feedback_upvote", value="trace_12345")
        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.on_feedback_upvote(action)

        mock_sink.record_feedback.assert_called_once_with(
            trace_id="trace_12345",
            score=1,
            feedback_category="helpful",
        )
        assert action.removed is True
        assert len(sent_messages) == 1
        assert "Marked as helpful 👍" in sent_messages[0].content

    @pytest.mark.asyncio
    async def test_on_feedback_downvote_records_negative_telemetry(self) -> None:
        import cuk_assistant.ui.app as app

        mock_sink = MagicMock()
        app._telemetry_sink = mock_sink

        action = MockAction(name="feedback_downvote", value="trace_67890")
        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.on_feedback_downvote(action)

        mock_sink.record_feedback.assert_called_once_with(
            trace_id="trace_67890",
            score=-1,
            feedback_category="unhelpful",
        )
        assert action.removed is True
        assert len(sent_messages) == 1
        assert "Marked as unhelpful 👎" in sent_messages[0].content

    @pytest.mark.asyncio
    async def test_feedback_handles_sink_without_record_feedback(self) -> None:
        import cuk_assistant.ui.app as app

        app._telemetry_sink = object()  # sink without record_feedback method
        action = MockAction(name="feedback_upvote", value="trace_none")
        await app.on_feedback_upvote(action)
        assert action.removed is True

    # 6. Chat Message Dispatching
    @pytest.mark.asyncio
    async def test_on_message_ignores_empty_query(self) -> None:
        import cuk_assistant.ui.app as app

        message = MockMessage(content="   \n\t  ")
        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_message(message)
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_dispatches_valid_query(self) -> None:
        import cuk_assistant.ui.app as app

        app.cl.user_session.set("active_slots", {"course": "B.Tech"})
        message = MockMessage(content="When are the semester exams?")

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_process:
            await app.on_message(message)
            assert app.cl.user_session.get("last_query") == "When are the semester exams?"
            mock_process.assert_called_once_with(
                "When are the semester exams?",
                updated_slots={"course": "B.Tech"},
            )

    # 7. Query Processing & Response Streaming
    @pytest.mark.asyncio
    async def test_process_query_streaming_tokens_and_feedback(self) -> None:
        import cuk_assistant.ui.app as app

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Central "}
            yield {"type": "token", "text": "University of Kashmir"}
            yield {"type": "done", "trace_id": "trace_turn_01"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream
        app._orchestrator = mock_orch

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.process_query("Tell me about the university")

        assert len(sent_messages) == 1
        msg = sent_messages[0]
        assert msg.tokens == ["Central ", "University of Kashmir"]
        assert msg.updated is True
        assert len(msg.actions) == 2
        assert msg.actions[0].name == "feedback_upvote"
        assert msg.actions[0].value == "trace_turn_01"
        assert msg.actions[1].name == "feedback_downvote"
        assert msg.actions[1].value == "trace_turn_01"

    @pytest.mark.asyncio
    async def test_process_query_with_text_and_table_citation_cards(self) -> None:
        import cuk_assistant.ui.app as app

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Syllabus details below."}
            yield {
                "type": "citation_card",
                "title": "B.Tech Ordinance",
                "source_url": "https://cukashmir.ac.in/ord.pdf",
                "page_number": 3,
                "section_heading": "Curriculum",
                "quoted_snippet": "Students must complete 160 credits.",
                "is_table": False,
            }
            yield {
                "type": "citation_card",
                "title": "Fee Matrix",
                "source_url": "https://cukashmir.ac.in/fee.pdf",
                "page_number": 1,
                "is_table": True,
                "table_markdown": "| Sem | Tuition |\n| 1 | 12000 |",
            }
            yield {"type": "done", "trace_id": "trace_turn_02"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream
        app._orchestrator = mock_orch

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.process_query("What is the fee and credits?")

        msg = sent_messages[0]
        assert len(msg.elements) == 2
        card1 = msg.elements[0]
        assert "B.Tech Ordinance" in card1.name
        assert "Students must complete 160 credits." in card1.content
        assert card1.display == "side"

        card2 = msg.elements[1]
        assert "Fee Matrix" in card2.name
        assert "| Sem | Tuition |" in card2.content
        assert card2.display == "side"

    @pytest.mark.asyncio
    async def test_process_query_with_slot_prompt_chips(self) -> None:
        import cuk_assistant.ui.app as app

        sent_messages: list[MockMessage] = []
        original_send = MockMessage.send

        async def capture_send(msg_self: MockMessage) -> MockMessage:
            sent_messages.append(msg_self)
            return await original_send(msg_self)

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "token": "Please select your semester:"}
            yield {
                "type": "slot_prompt",
                "target_slot": "semester",
                "options": [
                    {"value": "sem_1", "label": "Semester 1", "description": "First semester"},
                    {"value": "sem_4", "label": "Semester 4"},
                ],
            }
            yield {"type": "done", "trace_id": "trace_turn_03"}

        mock_orch = MagicMock()
        mock_orch.stream_turn = mock_stream
        app._orchestrator = mock_orch

        with patch.object(MockMessage, "send", side_effect=capture_send, autospec=True):
            await app.process_query("B.Tech syllabus")

        msg = sent_messages[0]
        assert len(msg.actions) == 2
        assert [a.name for a in msg.actions] == ["fill_slot", "fill_slot"]
        assert msg.actions[0].value == "sem_1"
        assert msg.actions[0].label == "Semester 1"
        assert msg.actions[0].payload == {"target_slot": "semester"}
        assert msg.actions[1].value == "sem_4"
        assert msg.actions[1].label == "Semester 4"
        assert msg.actions[1].description == "Select Semester 4"

    # 8. CLI Runner (`run()`) Tests
    def test_run_cli_missing_chainlit_exits_with_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        import cuk_assistant.ui.app as app

        app.cl = None
        with pytest.raises(SystemExit) as exc_info:
            app.run()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ERROR: 'chainlit' is not installed" in captured.err

    def test_run_cli_launches_subprocess(self) -> None:
        import cuk_assistant.ui.app as app

        with patch("subprocess.run") as mock_sub, \
             patch.dict(os.environ, {"CHAINLIT_PORT": "8080", "CHAINLIT_HOST": "127.0.0.1"}):
            app.run()
            mock_sub.assert_called_once()
            cmd = mock_sub.call_args[0][0]
            assert cmd[0] == sys.executable
            assert "-m" in cmd
            assert "chainlit" in cmd
            assert "run" in cmd
            assert "--host" in cmd and "127.0.0.1" in cmd
            assert "--port" in cmd and "8080" in cmd

    def test_run_cli_handles_keyboard_interrupt_gracefully(self) -> None:
        import cuk_assistant.ui.app as app

        with patch("subprocess.run", side_effect=KeyboardInterrupt):
            # Should not raise
            app.run()
```

---

## 5. Verification Method

To independently verify this mock architecture and test suite:

1. **Standalone Test Execution**:
   ```bash
   uv run pytest tests/unit/test_chainlit_ui.py -q
   ```
   *Expected outcome*: 16/16 tests pass in <0.2 seconds with 0 warnings or errors.

2. **Milestone M5 Test Gate Verification**:
   ```bash
   uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q
   ```
   *Expected outcome*: All M5 suites pass together with 0 failures.

3. **Code Quality and Style Conformance**:
   ```bash
   uv run ruff check tests/unit/test_chainlit_ui.py cuk_assistant/ui/app.py
   ```
   *Expected outcome*: Passes with 0 lint violations.

4. **Invalidation Conditions**:
   - Modifying event structure yielded by `RAGOrchestrator.stream_turn` without updating `process_query` event dispatch.
   - Removing the `sys.modules["chainlit"]` fixture, which would reintroduce `ModuleNotFoundError` in environments without Chainlit.
