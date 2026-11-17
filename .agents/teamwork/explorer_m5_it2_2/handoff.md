# Milestone M5 Iteration 2: Test Extension & Teardown Restoration Report

**Role**: Test Extension Explorer (`explorer_m5_it2_2`)  
**Target File**: `tests/unit/test_chainlit_ui.py`  
**Related Source**: `cuk_assistant/ui/app.py`  
**Status**: Complete Investigation & Concrete Test Design  

---

## 1. Observation

Direct observations and empirical probes conducted across `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`:

### Observation 1.1: Teardown Fails to Reset `app.cl` to `None`
- **Location**: `tests/unit/test_chainlit_ui.py:124-146`
```python
140: def teardown_module() -> None:
141:     """Restore original sys.modules state after module tests complete."""
142:     if _orig_chainlit is not None:
143:         sys.modules["chainlit"] = _orig_chainlit
144:     else:
145:         sys.modules.pop("chainlit", None)
```
- **Direct Probe Execution**:
```bash
uv run python -c "
import cuk_assistant.ui.app as app
import tests.unit.test_chainlit_ui as tui
print('Initial app.cl:', app.cl)
tui.teardown_module()
print('After teardown, app.cl:', app.cl)
assert app.cl is None
"
```
- **Result**:
```text
Initial app.cl: <module 'chainlit'>
After teardown, app.cl: <module 'chainlit'>
AssertionError: assert <module 'chainlit'> is None
```
- **Impact**: In environments where `chainlit` is not installed, running `app.run()` (or invoking `cuk-ui` CLI) after `test_chainlit_ui.py` skips the `if cl is None:` branch and crashes with `CalledProcessError` instead of gracefully notifying the user that Chainlit is missing.

### Observation 1.2: Citation Card Crashes on `title=None` or `page_number=None`
- **Location**: `cuk_assistant/ui/app.py:195, 218`
```python
195: title = event.get("title", "Official University Document")
...
218: cl.Text(name=f"[{idx}] {title[:32]}... (p. {page_num})", ...)
```
- **Error Output**:
```text
TypeError: 'NoneType' object is not subscriptable
```
When an event provides `{"type": "citation_card", "title": None}`, `event.get("title", ...)` evaluates to `None`, causing `title[:32]` to crash.

### Observation 1.3: Slot Prompts Crash on String List or `options=None`
- **Location**: `cuk_assistant/ui/app.py:178-180`
```python
178: options = event.get("options", [])
179: for opt in options:
180:     val = opt.get("value", "")
```
- **Error Output**:
```text
AttributeError: 'str' object has no attribute 'get'
TypeError: 'NoneType' object is not iterable
```
When `options=["B.Tech CSE", "MCA"]`, calling `.get()` on a string raises `AttributeError`. When `options=None`, iterating raises `TypeError`.

### Observation 1.4: Token Streaming Crashes When `token=None`
- **Location**: `cuk_assistant/ui/app.py:173-174`
```python
173: token = event.get("token", event.get("text", ""))
174: await msg.stream_token(token)
```
- **Error Output**:
```text
TypeError: can only concatenate str (not "NoneType") to str
```
When `event={"type": "token", "token": None, "text": "Fallback"}`, `"token"` key exists with value `None`, bypassing the `text` default and calling `msg.stream_token(None)`.

### Observation 1.5: Non-Dict Payload Crashes in `on_slot_selected`
- **Location**: `cuk_assistant/ui/app.py:106-107`
```python
106: active_slots: dict[str, Any] = cl.user_session.get("active_slots", {})
107: target_slot = (action.payload or {}).get("target_slot")
```
- **Error Output**:
```text
AttributeError: 'str' object has no attribute 'get'
TypeError: 'NoneType' object does not support item assignment
```
If `action.payload` is `"semester"`, `("semester" or {})` evaluates to `"semester"`, causing `AttributeError`. If `user_session.get("active_slots")` is `None`, assigning `active_slots[target_slot]` raises `TypeError`.

### Observation 1.6: Unhandled Stream Exceptions and Dropped `error` Events
- **Location**: `cuk_assistant/ui/app.py:164-226`
- **Error Output**:
```text
RuntimeError: LLM connection broken (uncaught, msg.update() never called)
AssertionError: assert 'Rate limit exceeded' in '' (empty message with feedback buttons)
```
Exceptions during `stream_turn` bubble uncaught, leaving `msg.update()` uncalled. `error` events are dropped silently, yielding an empty message box with feedback buttons attached.

### Observation 1.7: Done Event Overwrites `trace_id` with `None`
- **Location**: `cuk_assistant/ui/app.py:162, 224-225`
```python
162: turn_trace_id: str = uuid.uuid4().hex
...
224: elif ev_type == "done":
225:     turn_trace_id = event.get("trace_id", turn_trace_id)
```
- **Error Output**:
```text
assert None is not None (feedback buttons attached with value=None)
```
When `event={"type": "done", "trace_id": None}`, the pre-generated valid UUID is overwritten with `None`.

### Observation 1.8: Incorrect Port Default in Existing Test Suite
- **Location**: `tests/unit/test_chainlit_ui.py:608`
```python
608: assert "--port" in cmd and "8000" in cmd
```
- **System Contract**: `PROJECT.md:41` and `ORIGINAL_REQUEST.md:72, 94` mandate Chainlit UI runs on port `8001`, while FastAPI runs on `8000`. The test currently enforces the conflicting port `8000`.

---

## 2. Logic Chain

1. **Test Suite Isolation (O1.1)**: `test_chainlit_ui.py` sets `sys.modules["chainlit"] = mock_cl` and calls `importlib.reload(app)`. In `teardown_module()`, removing `"chainlit"` from `sys.modules` without reloading `app` leaves `app.cl` bound to the mock module. Reloading `app` in `teardown_module()` triggers `except ImportError: cl = None`, restoring true environment state.
2. **Defensive Edge Case Coverage (O1.2 - O1.7)**: Real serialization pipelines, LLM timeouts, and API contracts frequently yield explicit `None` fields, string-list options, non-dict payloads, and error events. The current test suite only provided happy-path dictionary fixtures, leaving these fatal edge paths untested.
3. **Architectural Port Alignment (O1.8)**: The test asserting port `"8000"` contradicts `ORIGINAL_REQUEST.md` and `PROJECT.md` which allocate port `8001` to Chainlit. Updating the test assertion to `"8001"` and adding validation for port fallback (`""`, invalid strings) ensures configuration consistency and prevents runtime port binding conflicts with FastAPI.
4. **Mock Concurrency Isolation**: Upgrading `MockUserSession` with `contextvars.ContextVar` ensures that asynchronous coroutines running concurrently do not bleed session keys into each other.
5. **Conclusion**: Extending `tests/unit/test_chainlit_ui.py` with 17 new/updated test methods across these 8 domains closes all blind spots and guarantees regression safety.

---

## 3. Caveats

- Full browser WebSocket lifecycle cannot be simulated without the official `chainlit` package installed in the environment; the in-memory test doubles accurately emulate Chainlit's runtime API (`cl.Action`, `cl.Message`, `cl.Text`, `cl.user_session`).
- The `TestModuleTeardown` test momentarily reloads `app` to verify `app.cl is None`, then re-injects `mock_cl` within a `finally:` block so that test execution order remains completely decoupled.

---

## 4. Conclusion & Concrete Test Design

The test suite in `tests/unit/test_chainlit_ui.py` should be updated with the following additions and modifications:

### 4.1. Test Doubles & Teardown Module Fixes
In `tests/unit/test_chainlit_ui.py`:
1. **MockUserSession Concurrency Isolation**:
```python
import contextvars

class MockUserSession:
    """Task-isolated in-memory dictionary mock emulating cl.user_session."""

    def __init__(self) -> None:
        self._var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
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
        self._store()[key] = value

    def clear(self) -> None:
        store = self._var.get()
        if store is not None:
            store.clear()
        else:
            self._var.set({})
```

2. **MockAction Generic Payload Support**:
```python
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
```

3. **`teardown_module()` Reload Restoration**:
```python
def teardown_module() -> None:
    """Restore original sys.modules state and reload app after module tests complete."""
    if _orig_chainlit is not None:
        sys.modules["chainlit"] = _orig_chainlit
    else:
        sys.modules.pop("chainlit", None)
    app._orchestrator = None
    app._telemetry_sink = None
    importlib.reload(app)
```

---

### 4.2. Concrete Test Additions

#### In `TestOnSlotSelected`:
Add tests for non-dict payloads and None active slots:
```python
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
```

#### In `TestProcessQuery`:
Add tests for citation cards with `None` fields:
```python
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
        assert "**Document:** [Official University Document](https://cukashmir.ac.in)" in card.content
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
```

Add tests for slot prompts with string-list and None options:
```python
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
```

Add test for token=None with text fallback:
```python
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
```

Add tests for stream exceptions and error events:
```python
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
            ({"type": "error", "message": "Failed to connect to model"}, "Failed to connect to model"),
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
```

Add test for preserving trace_id on done event:
```python
    @pytest.mark.asyncio
    async def test_process_query_preserves_generated_trace_id_when_done_trace_id_is_none(self) -> None:
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
```

#### In `TestCliRun`:
Update default port assertion and add CLI resilience tests:
```python
    def test_run_spawns_subprocess_with_default_arguments(self) -> None:
        """Verify default CLI runner arguments match specification (port 8001, host 0.0.0.0)."""
        with patch("subprocess.run") as mock_subproc, \
             patch.dict(os.environ, {}, clear=True):
            app.run()
            mock_subproc.assert_called_once()
            cmd = mock_subproc.call_args[0][0]
            assert "--host" in cmd and "0.0.0.0" in cmd
            assert "--port" in cmd and "8001" in cmd

    @pytest.mark.parametrize("empty_or_invalid_port", ["", "   ", "abc", "99999", "-1"])
    def test_run_falls_back_to_default_port_8001_on_invalid_env(self, empty_or_invalid_port: str) -> None:
        """Verify invalid or empty CHAINLIT_PORT falls back safely to default 8001."""
        with patch("subprocess.run") as mock_subproc, \
             patch.dict(os.environ, {"CHAINLIT_PORT": empty_or_invalid_port}):
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
```

#### New `TestModuleTeardown` Class:
```python
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
```

---

## 5. Verification Method

1. **Phase 5 Verification Gate**:
   Execute the full Phase 5 test suite:
   ```bash
   uv run pytest tests/unit/test_chainlit_ui.py -v
   ```
   **Expected**: 38+ unit tests passing with 0 failures.

2. **Teardown Module Cleanup Isolation**:
   ```bash
   uv run python -c "
   import cuk_assistant.ui.app as app
   import tests.unit.test_chainlit_ui as tui
   tui.teardown_module()
   assert app.cl is None, f'Expected None, got {app.cl}'
   print('Teardown isolation verified: app.cl is None!')
   "
   ```

3. **Phase 5 Full Gate Verification**:
   ```bash
   uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q
   ```
   **Expected**: 0 failures.

4. **Lint & Code Style**:
   ```bash
   uv run ruff check tests/unit/test_chainlit_ui.py cuk_assistant/ui/app.py
   ```
   **Expected**: 0 errors, 0 warnings.
