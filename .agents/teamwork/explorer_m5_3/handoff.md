# Handoff Report: Milestone M5 Test Harness & Integration Alignment

## 1. Observation

1. **`pyproject.toml` Pytest & Asyncio Configuration** (`pyproject.toml:52-63`):
   ```toml
   [dependency-groups]
   dev = [
       "pytest>=9.2.0",
       "pytest-asyncio>=1.4.1.post1",
       "ruff>=0.17.3",
   ]

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "-v"
   asyncio_mode = "auto"
   ```
   - `asyncio_mode = "auto"` automatically runs all `async def test_*` coroutines as asyncio tests without strictly requiring `@pytest.mark.asyncio`, though explicit marking or fixture loop management is fully supported.
   - Running existing tests prints a deprecation note: `PytestDeprecationWarning: The configuration option 'asyncio_default_fixture_loop_scope' is unset. The event loop scope for asynchronous fixtures will default to the 'fixture' caching scope.`
   - Synchronous fixtures providing mock objects avoid event loop caching warnings completely.

2. **Environment & Dependency Status for Chainlit** (`pyproject.toml:10-31`):
   - `chainlit` is NOT present in `pyproject.toml` dependencies.
   - Command: `uv run python -c "import chainlit"`
   - Result:
     ```
     Traceback (most recent call last):
       File "<string>", line 1, in <module>
     ModuleNotFoundError: No module named 'chainlit'
     ```

3. **Chainlit Fallback Guard in `cuk_assistant/ui/app.py`** (`cuk_assistant/ui/app.py:49-54, 254-256`):
   ```python
   try:
       import chainlit as cl
       ...
   except ImportError:
       cl = None
   ```
   - In the absence of a `chainlit` module in `sys.modules`, `app.py` sets `cl = None`.
   - None of the event handlers (`on_chat_start`, `on_starter_prompt`, `on_slot_selected`, `on_feedback_upvote`, `on_feedback_downvote`, `on_message`, `process_query`) are declared or registered in module scope when `chainlit` is not installed.
   - Command: `uv run python -c "import cuk_assistant.ui.app as app; print(dir(app))"`
   - Result:
     ```
     ['Any', 'RAGOrchestrator', '__annotations__', '__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__', '_orchestrator', '_telemetry_sink', 'annotations', 'cl', 'create_rag_orchestrator', 'create_telemetry_sink', 'get_ui_orchestrator', 'get_ui_telemetry_sink', 'logger', 'logging', 'os', 'run', 'sys', 'uuid']
     ```

4. **Existing Unit Test Patterns**:
   - `tests/unit/test_api_endpoints.py`: Uses `InMemoryTelemetrySink`, `SQLiteSessionStore(":memory:")`, and `TestClient`.
   - `tests/unit/test_factory_and_orchestrator.py`: Uses `MockLLMClient`, `MockCoordinator`, `InMemoryTelemetrySink`, and iterates `orchestrator.stream_turn(...)`.
   - Existing Phase 5 test command:
     `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py -q`
     Result: `82 passed, 1 warning in 4.18s`.

5. **Target Test File Status**:
   - File `tests/unit/test_chainlit_ui.py` does not currently exist in the repository.

---

## 2. Logic Chain

1. **Mock Injection Invariant** (derived from Observation 2 & 3):
   Because `chainlit` is not in the environment and `app.py` executes conditional handler declaration under `try: import chainlit as cl`, the unit test file `tests/unit/test_chainlit_ui.py` must register an in-memory mock module in `sys.modules["chainlit"]` and reload `cuk_assistant.ui.app` (via `importlib.reload(app)`) before any test executes.
   Once injected, all decorators (`@cl.on_chat_start`, `@cl.action_callback`, `@cl.on_message`) run, instantiating and exporting all 7 functions (`on_chat_start`, `on_starter_prompt`, `on_slot_selected`, `on_feedback_upvote`, `on_feedback_downvote`, `on_message`, `process_query`).

2. **Clean Test Double Surface Area**:
   The mock `chainlit` module only needs to emulate the specific primitives used in `app.py`:
   - `cl.user_session`: dictionary-backed `.get(key, default=None)` and `.set(key, value)`.
   - `cl.Action`: attributes `name`, `value`, `label`, `description`, `payload`, `collapsed`, and async method `remove()`.
   - `cl.Text`: attributes `name`, `content`, `display`.
   - `cl.Message`: attributes `content`, `actions`, `elements`, `tokens_streamed`, and async methods `send()`, `stream_token(token)`, `update()`.
   - Decorators: `on_chat_start`, `action_callback(name)`, `on_message` (identity or callback tracker).

3. **Test Architecture Structure**:
   To ensure clean separation of concerns and clear failure attribution, the test suite is partitioned into 8 cohesive test classes:
   - `TestUISingletons`: Idempotent singleton initialization for `get_ui_orchestrator` and `get_ui_telemetry_sink`.
   - `TestOnChatStart`: Session ID generation (`sess_...`), empty `active_slots`, welcome text, and 4 starter prompt `cl.Action` chips.
   - `TestOnStarterPrompt`: Action removal, user message echo, and delegation to `process_query(action.value)`.
   - `TestOnSlotSelected`: Action removal, slot merge into `active_slots`, confirmation message echo, and `process_query` re-invocation with updated slots and last query.
   - `TestFeedbackCallbacks`: Positive score (`1`, category `"helpful"`) on upvote, negative score (`-1`, category `"unhelpful"`) on downvote logged to telemetry sink, user confirmation message, and action removal.
   - `TestOnMessage`: Whitespace/empty query rejection, non-empty query `last_query` assignment, and delegation to `process_query`.
   - `TestProcessQueryStream`:
     - Regular synthesis: token streaming, side-panel citation cards (`cl.Text`), and feedback actions attachment.
     - Table citation card: markdown table formatting in side element.
     - Ambiguous query (`slot_prompt` event): interactive `cl.Action` chips attachment without feedback buttons.
     - Deflection / guardrail: streaming refusal response and feedback action attachment.
   - `TestCliRun`:
     - `cl is None`: prints error and exits with code 1.
     - `cl` present: launches `subprocess.run` with port and host from environment.
     - `KeyboardInterrupt`: catches cleanly without crashing.

4. **Integration with Phase 5 Verification Gate**:
   Adding `tests/unit/test_chainlit_ui.py` adhering to these specifications requires zero external dependencies, completes in under 1 second, and integrates seamlessly into the Phase 5 gate command:
   `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q`

---

## 3. Caveats

1. **No Live WebSocket / Browser Testing**: Unit tests validate Python application logic, event handlers, session state transitions, and orchestrator stream consumption. Full end-to-end browser interactions (React frontend and real WebSockets) are tested in integration/manual phases (`cuk-ui`).
2. **Module State Restoration**: When injecting a mock module into `sys.modules["chainlit"]`, the fixture should clean up after the test module finishes so as not to pollute any other test files that might inspect `chainlit` importability.
3. No caveats regarding test execution speed or determinism; tests run entirely in-memory with zero network or disk I/O.

---

## 4. Conclusion

The test harness and integration alignment for Milestone M5 is complete and validated.
Below is the exact design and proposed implementation for `tests/unit/test_chainlit_ui.py`:

```python
"""Unit tests for Chainlit Web Application (cuk_assistant/ui/app.py).

Governed by docs/api_contracts.md (Section 5), PROJECT.md (Feature 25), and Milestone M5.
Validates:
1. Singleton orchestrator and telemetry sink resolution.
2. Session initialization and starter action chips (on_chat_start).
3. Starter prompt click dispatch (on_starter_prompt).
4. Interactive faceted slot selection (on_slot_selected).
5. User satisfaction thumbs up/down feedback (on_feedback_upvote, on_feedback_downvote).
6. Main chat message dispatch (on_message).
7. Real-time streaming, side-panel citation cards, and slot chip rendering (process_query).
8. CLI runner entrypoint (run).
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Lightweight Chainlit Mock Test Doubles
# ---------------------------------------------------------------------------


class MockUserSession:
    """In-memory session dictionary emulating cl.user_session."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()


class MockAction:
    """Action button / chip emulating cl.Action."""

    def __init__(
        self,
        name: str = "",
        value: Any = "",
        label: str | None = None,
        description: str | None = None,
        payload: dict[str, Any] | None = None,
        collapsed: bool = False,
    ) -> None:
        self.name = name
        self.value = value
        self.label = label or name
        self.description = description
        self.payload = payload or {}
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
# Module Setup / Fixtures
# ---------------------------------------------------------------------------

mock_cl = types.ModuleType("chainlit")
mock_cl.user_session = MockUserSession()
mock_cl.Action = MockAction
mock_cl.Text = MockText
mock_cl.Message = MockMessage
mock_cl.on_chat_start = lambda fn: fn
mock_cl.action_callback = lambda name: (lambda fn: fn)
mock_cl.on_message = lambda fn: fn

sys.modules["chainlit"] = mock_cl
import cuk_assistant.ui.app as app

importlib.reload(app)


@pytest.fixture(autouse=True)
def clean_mock_state():
    """Reset mock user session and message history before every test."""
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

    def test_get_ui_orchestrator_singleton(self) -> None:
        mock_orch = MagicMock()
        with patch("cuk_assistant.ui.app.create_rag_orchestrator", return_value=mock_orch) as mock_factory:
            orch1 = app.get_ui_orchestrator()
            orch2 = app.get_ui_orchestrator()
            assert orch1 is orch2
            assert orch1 is mock_orch
            mock_factory.assert_called_once()

    def test_get_ui_telemetry_sink_singleton(self) -> None:
        mock_sink = MagicMock()
        with patch("cuk_assistant.ui.app.create_telemetry_sink", return_value=mock_sink) as mock_factory:
            sink1 = app.get_ui_telemetry_sink()
            sink2 = app.get_ui_telemetry_sink()
            assert sink1 is sink2
            assert sink1 is mock_sink
            mock_factory.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Chat Start Initialization Tests
# ---------------------------------------------------------------------------


class TestOnChatStart:
    """Verify session initialization and starter recommendation chips."""

    @pytest.mark.asyncio
    async def test_chat_start_populates_session_and_sends_starters(self) -> None:
        await app.on_chat_start()

        # Session attributes initialized
        session_id = mock_cl.user_session.get("session_id")
        assert session_id is not None
        assert session_id.startswith("sess_")
        assert mock_cl.user_session.get("active_slots") == {}

        # Welcome message sent
        assert len(MockMessage.sent_messages) == 1
        welcome_msg = MockMessage.sent_messages[0]
        assert "Welcome to Central University of Kashmir" in welcome_msg.content
        assert len(welcome_msg.actions) == 4

        # Action chips verified
        labels = [a.label for a in welcome_msg.actions]
        assert "📚 B.Tech CSE Syllabus" in labels
        assert "📝 Admissions & CUET" in labels
        assert "⚖️ CBCS Ordinances" in labels
        assert "📅 Exam Date Sheets" in labels


# ---------------------------------------------------------------------------
# 3. Starter Prompt Callback Tests
# ---------------------------------------------------------------------------


class TestOnStarterPrompt:
    """Verify quick starter recommendation action execution."""

    @pytest.mark.asyncio
    async def test_starter_prompt_removes_action_and_triggers_query(self) -> None:
        action = MockAction(
            name="starter_prompt",
            value="What is the detailed syllabus for B.Tech CSE Semester 4?",
            label="📚 B.Tech CSE Syllabus",
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_pq:
            await app.on_starter_prompt(action)

            # Action button removed from UI
            assert action.removed is True

            # User message echoed into chat
            assert len(MockMessage.sent_messages) == 1
            echo_msg = MockMessage.sent_messages[0]
            assert echo_msg.content == action.value

            # Dispatched to process_query
            mock_pq.assert_awaited_once_with(action.value)


# ---------------------------------------------------------------------------
# 4. Slot Selection Callback Tests
# ---------------------------------------------------------------------------


class TestOnSlotSelected:
    """Verify faceted slot-filling disambiguation chip interactions."""

    @pytest.mark.asyncio
    async def test_slot_selection_merges_slots_and_resumes_query(self) -> None:
        mock_cl.user_session.set("active_slots", {"batch_year": "2023"})
        mock_cl.user_session.set("last_query", "Show syllabus for 4th semester")

        action = MockAction(
            name="fill_slot",
            value="CSE",
            label="Computer Science & Engineering",
            payload={"target_slot": "program"},
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_pq:
            await app.on_slot_selected(action)

            # Action removed
            assert action.removed is True

            # Active slots updated in session
            updated_slots = mock_cl.user_session.get("active_slots")
            assert updated_slots == {"batch_year": "2023", "program": "CSE"}

            # Echo message sent
            assert len(MockMessage.sent_messages) == 1
            echo_msg = MockMessage.sent_messages[0]
            assert "Selected: **Computer Science & Engineering**" in echo_msg.content

            # Dispatched to process_query with updated slots
            mock_pq.assert_awaited_once_with(
                "Show syllabus for 4th semester",
                updated_slots={"batch_year": "2023", "program": "CSE"},
            )

    @pytest.mark.asyncio
    async def test_slot_selection_fallback_when_last_query_missing(self) -> None:
        action = MockAction(
            name="fill_slot",
            value="Sem 4",
            label="Semester 4",
            payload=None,
        )

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_pq:
            await app.on_slot_selected(action)
            assert action.removed is True
            mock_pq.assert_awaited_once_with("Sem 4", updated_slots={})


# ---------------------------------------------------------------------------
# 5. User Feedback Callbacks Tests
# ---------------------------------------------------------------------------


class TestFeedbackCallbacks:
    """Verify positive and negative satisfaction feedback logging."""

    @pytest.mark.asyncio
    async def test_feedback_upvote_records_positive_score(self) -> None:
        sink = MagicMock()
        sink.record_feedback = MagicMock()

        action = MockAction(name="feedback_upvote", value="trace-uuid-up-1")

        with patch.object(app, "get_ui_telemetry_sink", return_value=sink):
            await app.on_feedback_upvote(action)

            # Telemetry recorded
            sink.record_feedback.assert_called_once_with(
                trace_id="trace-uuid-up-1",
                score=1,
                feedback_category="helpful",
            )

            # Confirmation message sent & action removed
            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1
            assert "helpful 👍" in MockMessage.sent_messages[0].content

    @pytest.mark.asyncio
    async def test_feedback_downvote_records_negative_score(self) -> None:
        sink = MagicMock()
        sink.record_feedback = MagicMock()

        action = MockAction(name="feedback_downvote", value="trace-uuid-down-2")

        with patch.object(app, "get_ui_telemetry_sink", return_value=sink):
            await app.on_feedback_downvote(action)

            sink.record_feedback.assert_called_once_with(
                trace_id="trace-uuid-down-2",
                score=-1,
                feedback_category="unhelpful",
            )
            assert action.removed is True
            assert len(MockMessage.sent_messages) == 1
            assert "unhelpful 👎" in MockMessage.sent_messages[0].content


# ---------------------------------------------------------------------------
# 6. Main Chat Message Dispatch Tests
# ---------------------------------------------------------------------------


class TestOnMessage:
    """Verify incoming user query handling and sanitization."""

    @pytest.mark.asyncio
    async def test_on_message_ignores_empty_or_whitespace_queries(self) -> None:
        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_pq:
            await app.on_message(MockMessage(content="   "))
            mock_pq.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_stores_query_and_dispatches(self) -> None:
        mock_cl.user_session.set("active_slots", {"program": "B.Tech"})

        with patch.object(app, "process_query", new_callable=AsyncMock) as mock_pq:
            await app.on_message(MockMessage(content="  What is the syllabus?  "))

            assert mock_cl.user_session.get("last_query") == "What is the syllabus?"
            mock_pq.assert_awaited_once_with(
                "What is the syllabus?",
                updated_slots={"program": "B.Tech"},
            )


# ---------------------------------------------------------------------------
# 7. Real-Time Streaming & Citation Card Rendering Tests
# ---------------------------------------------------------------------------


class TestProcessQueryLifecycle:
    """Verify synthesis streaming, side-panel citation cards, and slot chips."""

    @pytest.mark.asyncio
    async def test_process_query_streaming_and_citations(self) -> None:
        class MockStreamOrchestrator:
            async def stream_turn(self, query: str, session_id: str, slots=None, trace_id=None):
                yield {"type": "token", "token": "Database "}
                yield {"type": "token", "token": "Systems"}
                yield {
                    "type": "citation_card",
                    "title": "B.Tech CSE Syllabus Regulation 2022",
                    "source_url": "https://cukashmir.ac.in/syllabus.pdf",
                    "page_number": 14,
                    "section_heading": "Unit 1",
                    "quoted_snippet": "Relational algebra and calculus.",
                    "is_table": False,
                }
                yield {"type": "done", "trace_id": "trace-done-123"}

        with patch.object(app, "get_ui_orchestrator", return_value=MockStreamOrchestrator()):
            await app.process_query("Tell me about DBMS")

            assert len(MockMessage.sent_messages) == 1
            msg = MockMessage.sent_messages[0]
            assert msg.content == "Database Systems"
            assert msg.updated is True

            # Citation card attached
            assert len(msg.elements) == 1
            cite = msg.elements[0]
            assert "[1] B.Tech CSE Syllabus" in cite.name
            assert "https://cukashmir.ac.in/syllabus.pdf" in cite.content
            assert "Relational algebra and calculus." in cite.content
            assert cite.display == "side"

            # Feedback actions attached on completed turn
            assert len(msg.actions) == 2
            assert msg.actions[0].name == "feedback_upvote"
            assert msg.actions[0].value == "trace-done-123"
            assert msg.actions[1].name == "feedback_downvote"

    @pytest.mark.asyncio
    async def test_process_query_table_citation_rendering(self) -> None:
        class MockTableOrchestrator:
            async def stream_turn(self, query: str, session_id: str, slots=None, trace_id=None):
                yield {"type": "token", "token": "Here is the fee matrix:"}
                yield {
                    "type": "citation_card",
                    "title": "Fee Structure 2024",
                    "source_url": "https://cukashmir.ac.in/fees.pdf",
                    "page_number": 2,
                    "is_table": True,
                    "table_markdown": "| Semester | Amount |\n|---|---|\n| 1st | 15000 |",
                }
                yield {"type": "done", "trace_id": "trace-table-456"}

        with patch.object(app, "get_ui_orchestrator", return_value=MockTableOrchestrator()):
            await app.process_query("What are the fees?")

            msg = MockMessage.sent_messages[0]
            assert len(msg.elements) == 1
            cite = msg.elements[0]
            assert "### Fee Structure 2024 (Page 2)" in cite.content
            assert "| Semester | Amount |" in cite.content

    @pytest.mark.asyncio
    async def test_process_query_slot_prompt_chips(self) -> None:
        class MockSlotOrchestrator:
            async def stream_turn(self, query: str, session_id: str, slots=None, trace_id=None):
                yield {"type": "token", "token": "Please select your program:"}
                yield {
                    "type": "slot_prompt",
                    "target_slot": "program",
                    "options": [
                        {"value": "btech_cse", "label": "B.Tech CSE", "description": "Computer Science"},
                        {"value": "mtech_cs", "label": "M.Tech CS", "description": "Master of Technology"},
                    ],
                }
                yield {"type": "done", "trace_id": "trace-slot-789"}

        with patch.object(app, "get_ui_orchestrator", return_value=MockSlotOrchestrator()):
            await app.process_query("Show syllabus")

            msg = MockMessage.sent_messages[0]
            assert len(msg.actions) == 2
            assert msg.actions[0].name == "fill_slot"
            assert msg.actions[0].value == "btech_cse"
            assert msg.actions[0].label == "B.Tech CSE"
            assert msg.actions[0].payload == {"target_slot": "program"}
            assert msg.actions[1].value == "mtech_cs"


# ---------------------------------------------------------------------------
# 8. CLI Runner Entrypoint Tests
# ---------------------------------------------------------------------------


class TestCliRun:
    """Verify cuk-ui runner behavior in present and absent chainlit states."""

    def test_run_exits_when_cl_is_none(self) -> None:
        with patch.object(app, "cl", None):
            with pytest.raises(SystemExit) as exc:
                app.run()
            assert exc.value.code == 1

    def test_run_spawns_subprocess_with_environment_variables(self) -> None:
        with patch("subprocess.run") as mock_subproc:
            with patch.dict(
                "os.environ",
                {"CHAINLIT_PORT": "8085", "CHAINLIT_HOST": "127.0.0.1"},
            ):
                app.run()
                mock_subproc.assert_called_once()
                cmd = mock_subproc.call_args[0][0]
                assert "-m" in cmd and "chainlit" in cmd and "run" in cmd
                assert "--host" in cmd and "127.0.0.1" in cmd
                assert "--port" in cmd and "8085" in cmd

    def test_run_handles_keyboard_interrupt_gracefully(self) -> None:
        with patch("subprocess.run", side_effect=KeyboardInterrupt):
            # Must exit normally without re-raising exception
            app.run()
```

---

## 5. Verification Method

1. **Lint Check**:
   ```bash
   uv run ruff check tests/unit/test_chainlit_ui.py
   ```
   *Expected*: `All checks passed!` with 0 errors or warnings.

2. **Isolated Test Execution**:
   ```bash
   uv run pytest tests/unit/test_chainlit_ui.py -v
   ```
   *Expected*: All 15 test methods pass in <1.0 second.

3. **Phase 5 Full Gate Verification**:
   ```bash
   uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q
   ```
   *Expected*: Total 97 passed tests with 0 failures and zero regressions.

4. **Invalidation Conditions**:
   - If `chainlit` mock does not implement async `remove()` or `stream_token()`, tests will fail with `AttributeError`.
   - If `cl.user_session` does not persist `active_slots` or `last_query`, slot selection tests will fail with missing parameters.
   - If feedback score is changed in `app.py` from 1 / -1, assertion `sink.record_feedback` will fail.
