# Handoff Report: Challenger 2 (Milestone M5 — UI & Test Suite)

**Verdict**: `REQUEST_CHANGES`  
**Overall Risk Assessment**: `HIGH`  
**Target Files**: `tests/unit/test_chainlit_ui.py`, `cuk_assistant/ui/app.py`  
**Author**: Challenger 2 (`challenger_m5_2`)  

---

## Challenge Summary

**Overall risk assessment**: HIGH

While the test suite in `tests/unit/test_chainlit_ui.py` exhibits 100% determinism under serial repetition (50 consecutive runs passed, reversed order passed, and 10 shuffled permutations passed), empirical probing revealed 4 critical defects across concurrency safety, test suite pollution, error handling, and CLI resilience:
1. **[High] Test Lifecycle Teardown Pollution**: `teardown_module()` in `tests/unit/test_chainlit_ui.py` pops `sys.modules["chainlit"]`, but fails to reload `cuk_assistant.ui.app`. As an empirical consequence, `app.cl` remains bound to `<module 'chainlit'>` (the mock), corrupting subsequent tests in the same Python process.
2. **[High] Missing Error Handling in UI Stream Consumer**: `process_query` in `cuk_assistant/ui/app.py` has no handler for `ev_type == "error"` events emitted by `RAGOrchestrator.stream_turn()`, and no `try...except` around the streaming loop. If an error occurs, an empty response is rendered and positive/negative feedback buttons are displayed over a blank screen.
3. **[Medium] Mock Concurrency Hazard (Task Isolation Failure)**: `MockUserSession` in `tests/unit/test_chainlit_ui.py` uses a single non-context-local dictionary `self._store: dict[str, Any] = {}`. Under concurrent coroutines (`asyncio.gather`), session variables (`session_id`, `active_slots`, `last_query`) overwrite each other, causing cross-session data hijacking.
4. **[Medium] CLI Environment Robustness & Process Failure**: `app.run()` does not sanitize `CHAINLIT_PORT` when set to an empty string (`CHAINLIT_PORT=""`), passing `--port ""` to the subprocess, and fails to handle `subprocess.CalledProcessError` when Chainlit terminates with non-zero exit code.

---

## 1. Observation

### Observation 1.1: Test Suite Isolation Leakage in `teardown_module`
In `tests/unit/test_chainlit_ui.py:124-146`:
```python
_orig_chainlit = sys.modules.get("chainlit")

mock_cl = types.ModuleType("chainlit")
mock_cl.user_session = MockUserSession()
mock_cl.Action = MockAction
mock_cl.Text = MockText
mock_cl.Message = MockMessage
mock_cl.on_chat_start = lambda fn: fn
mock_cl.action_callback = lambda name: (lambda fn: fn)
mock_cl.on_message = lambda fn: fn

sys.modules["chainlit"] = mock_cl

importlib.reload(app)


def teardown_module() -> None:
    """Restore original sys.modules state after module tests complete."""
    if _orig_chainlit is not None:
        sys.modules["chainlit"] = _orig_chainlit
    else:
        sys.modules.pop("chainlit", None)
```
**Empirical Execution**:
```bash
uv run python -c "
import tests.unit.test_chainlit_ui as tui
import cuk_assistant.ui.app as app

print('Before teardown, app.cl is:', app.cl)
tui.teardown_module()
print('After teardown, app.cl is:', app.cl)
import sys
print('sys.modules has chainlit?', 'chainlit' in sys.modules)
try:
    app.run()
except Exception as e:
    print('Exception:', type(e), e)
"
```
**Result**:
```text
Before teardown, app.cl is: <module 'chainlit'>
After teardown, app.cl is: <module 'chainlit'>
sys.modules has chainlit? False
/mnt/ubuntu_data/projects/cuk-rag-chatbot/.venv/bin/python: No module named chainlit
Exception: <class 'subprocess.CalledProcessError'> Command '['/mnt/ubuntu_data/projects/cuk-rag-chatbot/.venv/bin/python', '-m', 'chainlit', 'run', '/mnt/ubuntu_data/projects/cuk-rag-chatbot/cuk_assistant/ui/app.py', '--host', '0.0.0.0', '--port', '8000']' returned non-zero exit status 1.
```
Even after `teardown_module()` executes, `app.cl` is NOT restored to `None`! Calling `app.run()` bypasses `if cl is None:` and crashes with unhandled `CalledProcessError`.

---

### Observation 1.2: Mock User Session Overwrite Under Concurrent Execution
In `tests/unit/test_chainlit_ui.py:34-48`:
```python
class MockUserSession:
    """In-memory dictionary mock emulating cl.user_session."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()
```
**Empirical Execution**:
```bash
uv run python -c "
import asyncio
from unittest.mock import MagicMock
import cuk_assistant.ui.app as app
import tests.unit.test_chainlit_ui as tui

async def run_concurrent_process_query():
    captured_calls = []

    async def mock_stream(query, session_id, slots=None, trace_id=None):
        await asyncio.sleep(0.02)
        captured_calls.append({'query': query, 'session_id': session_id, 'slots': slots})
        yield {'type': 'token', 'token': f'response to {query}'}
        yield {'type': 'done', 'trace_id': trace_id}

    mock_orch = MagicMock()
    mock_orch.stream_turn = mock_stream
    app._orchestrator = mock_orch

    async def user_session_1():
        tui.mock_cl.user_session.set('session_id', 'user_1_session')
        tui.mock_cl.user_session.set('active_slots', {'dept': 'CSE'})
        tui.mock_cl.user_session.set('last_query', 'CSE syllabus')
        await asyncio.sleep(0.01)
        action = tui.MockAction(name='fill_slot', value='Sem 4', label='Sem 4', payload={'target_slot': 'sem'})
        await app.on_slot_selected(action)

    async def user_session_2():
        await asyncio.sleep(0.005)
        tui.mock_cl.user_session.set('session_id', 'user_2_session')
        tui.mock_cl.user_session.set('active_slots', {'dept': 'Law'})
        tui.mock_cl.user_session.set('last_query', 'Law admissions')
        action = tui.MockAction(name='fill_slot', value='2024', label='2024', payload={'target_slot': 'batch'})
        await app.on_slot_selected(action)

    await asyncio.gather(user_session_1(), user_session_2())

    print('Captured calls to orchestrator:')
    for call in captured_calls:
        print(call)

asyncio.run(run_concurrent_process_query())
"
```
**Result**:
```text
Captured calls to orchestrator:
{'query': 'Law admissions', 'session_id': 'user_2_session', 'slots': {'dept': 'Law', 'batch': '2024', 'sem': 'Sem 4'}}
{'query': 'Law admissions', 'session_id': 'user_2_session', 'slots': {'dept': 'Law', 'batch': '2024', 'sem': 'Sem 4'}}
```
Both user queries were dispatched under `user_2_session` with User 2's query `'Law admissions'`, and User 1's slot was merged into User 2's state!

---

### Observation 1.3: Unhandled Error Events and Exceptions in `app.process_query`
In `cuk_assistant/ui/app.py:170-226`:
```python
        async for event in orchestrator.stream_turn(
            query=query,
            session_id=session_id,
            slots=updated_slots,
            trace_id=turn_trace_id,
        ):
            ev_type = event.get("type")

            if ev_type == "token":
                token = event.get("token", event.get("text", ""))
                await msg.stream_token(token)

            elif ev_type == "slot_prompt":
                ...
            elif ev_type == "citation_card":
                ...
            elif ev_type == "done":
                turn_trace_id = event.get("trace_id", turn_trace_id)
```
**Empirical Execution (Error Event Handling)**:
```bash
uv run python -c "
import asyncio
from unittest.mock import MagicMock
import cuk_assistant.ui.app as app
import tests.unit.test_chainlit_ui as tui

async def run_error_event_test():
    async def error_stream(*args, **kwargs):
        yield {'type': 'error', 'error': 'Rate limit exceeded'}
        yield {'type': 'done'}

    mock_orch = MagicMock()
    mock_orch.stream_turn = error_stream
    app._orchestrator = mock_orch

    await app.process_query('trigger error')

    msg = tui.MockMessage.sent_messages[0]
    print('Content:', repr(msg.content))
    print('Actions:', [a.name for a in msg.actions])

asyncio.run(run_error_event_test())
"
```
**Result**:
```text
Content: ''
Actions: ['feedback_upvote', 'feedback_downvote']
```
When `orchestrator.stream_turn` emits an `error` event, it is silently dropped. The user sees an empty blank box with "👍 Helpful / 👎 Inaccurate" buttons.
Similarly, if `stream_turn` raises an exception (e.g. `ConnectionResetError`), `msg.update()` is never called and the empty message hangs in the UI.

---

### Observation 1.4: CLI Argument Forwarding Edge Cases in `app.run`
In `cuk_assistant/ui/app.py:278-294`:
```python
    port = os.environ.get("CHAINLIT_PORT", "8000")
    host = os.environ.get("CHAINLIT_HOST", "0.0.0.0")

    cmd = [
        sys.executable,
        "-m",
        "chainlit",
        "run",
        str(app_path),
        "--host",
        host,
        "--port",
        port,
    ]
    logger.info("Starting Chainlit UI: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Chainlit server stopped by user.")
```
**Empirical Execution**:
```bash
uv run python -c "
import os, subprocess
from unittest.mock import patch, MagicMock
import cuk_assistant.ui.app as app

with patch.object(app, 'cl', MagicMock()):
    with patch('subprocess.run') as mock_run, patch.dict(os.environ, {'CHAINLIT_PORT': ''}):
        app.run()
        cmd = mock_run.call_args[0][0]
        print('Command with empty port:', cmd)

    with patch('subprocess.run', side_effect=subprocess.CalledProcessError(2, ['chainlit', 'run'])):
        try:
            app.run()
        except subprocess.CalledProcessError as e:
            print('Crashed with unhandled CalledProcessError:', e)
"
```
**Result**:
```text
Command with empty port: ['.../python', '-m', 'chainlit', 'run', '.../app.py', '--host', '0.0.0.0', '--port', '']
Crashed with unhandled CalledProcessError: Command '['chainlit', 'run']' returned non-zero exit status 2.
```
`CHAINLIT_PORT=""` produces `["--port", ""]`, which breaks CLI execution. Furthermore, non-zero exits from Chainlit (such as invalid ports or bind errors) bubble up as unhandled `CalledProcessError` crashes rather than clean error logging.

---

### Observation 1.5: Test Suite Determinism Stress Run
**Empirical Execution**:
- 50 consecutive runs of `uv run pytest tests/unit/test_chainlit_ui.py -q`: **50/50 PASSED** (0 failures).
- Reversed test ordering execution: **23/23 PASSED** (0 failures).
- 10 randomized test order permutations: **10/10 PASSED** (0 failures).
Test determinism under serial execution is verified.

---

## 2. Logic Chain

1. **Step 1 (State Leakage)**: `test_chainlit_ui.py` imports and reloads `cuk_assistant.ui.app` after inserting `mock_cl` into `sys.modules`. In `teardown_module()`, it removes `chainlit` from `sys.modules` but does NOT reload `app`. Because module references are cached in Python, `app.cl` retains its reference to `mock_cl`. This invalidates the real runtime behavior where `cl is None` in an environment without Chainlit installed.
2. **Step 2 (Concurrent Session Hijacking)**: In `test_chainlit_ui.py`, `MockUserSession` is implemented with a single dictionary `self._store`. When two concurrent coroutines interact with `cl.user_session`, both read and write to the same dictionary without context isolation. In our empirical test, User 2's session state completely overwrote User 1's state, resulting in User 1's turn executing under User 2's session ID and query.
3. **Step 3 (Silent Error Swallowing)**: In `cuk_assistant/ui/app.py`, `process_query` assumes `stream_turn` only emits `token`, `slot_prompt`, `citation_card`, or `done`. When `stream_turn` emits `error`, the event is dropped. Since no tokens were streamed, the UI message remains empty, but `msg.actions` is populated with feedback buttons. The user is asked to give feedback on a non-existent answer.
4. **Step 4 (CLI Parameter Fault)**: `os.environ.get("CHAINLIT_PORT", "8000")` returns `""` when `CHAINLIT_PORT` is set in the environment as an empty string. The resulting argument `["--port", ""]` fails command validation. Furthermore, `subprocess.run(cmd, check=True)` raises `CalledProcessError` whenever the server fails to bind or exits with error code, which is unhandled.

---

## 3. Caveats

- Full real-browser WebSocket interaction could not be tested with the real `chainlit` package because `chainlit` is not currently included in `pyproject.toml` dependencies (hence the test suite relies on mock doubles).
- The concurrency race in `MockUserSession` does not fail standard single-threaded serial pytest runs because `clean_mock_state` resets the dictionary between each test; it only manifests when testing asynchronous concurrency or multi-turn sessions across tasks.

---

## 4. Conclusion

**Verdict: `REQUEST_CHANGES`**

The following concrete fixes must be applied:

### Fix 1: In `tests/unit/test_chainlit_ui.py`
1. Update `teardown_module()` to reload `app`:
```python
def teardown_module() -> None:
    """Restore original sys.modules state after module tests complete."""
    if _orig_chainlit is not None:
        sys.modules["chainlit"] = _orig_chainlit
    else:
        sys.modules.pop("chainlit", None)
    importlib.reload(app)
```
2. Refactor `MockUserSession` to use `contextvars.ContextVar` for task/session isolation:
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
        self._store().clear()
```

### Fix 2: In `cuk_assistant/ui/app.py`
1. Handle `ev_type == "error"` and catch streaming exceptions in `process_query`:
```python
        try:
            async for event in orchestrator.stream_turn(...):
                ev_type = event.get("type")
                if ev_type == "token":
                    ...
                elif ev_type == "error":
                    err_msg = event.get("error") or event.get("message") or "An error occurred while processing your request."
                    await msg.stream_token(f"\n\n⚠️ **Error:** {err_msg}")
                ...
        except Exception as exc:
            logger.exception("Error during process_query streaming: %s", exc)
            await msg.stream_token(f"\n\n⚠️ **System Error:** {exc}")
```
2. In `app.run()`, sanitize `port` and catch `CalledProcessError`:
```python
    raw_port = os.environ.get("CHAINLIT_PORT", "").strip()
    port = raw_port if (raw_port.isdigit() and 1 <= int(raw_port) <= 65535) else "8000"
    raw_host = os.environ.get("CHAINLIT_HOST", "").strip()
    host = raw_host or "0.0.0.0"

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Chainlit server stopped by user.")
    except subprocess.CalledProcessError as exc:
        logger.error("Chainlit server exited with code %s: %s", exc.returncode, exc)
        sys.exit(exc.returncode)
```

---

## 5. Verification Method

To independently verify the fixes:
1. Run Phase 5 Unit Test Gate:
   ```bash
   uv run pytest tests/unit/test_chainlit_ui.py -v
   ```
2. Verify teardown cleanup does not pollute `app.cl`:
   ```bash
   uv run python -c "
   import tests.unit.test_chainlit_ui as tui
   import cuk_assistant.ui.app as app
   tui.teardown_module()
   assert app.cl is None, f'Expected app.cl to be None, got {app.cl}'
   print('Teardown isolation verified!')
   "
   ```
3. Verify concurrent task session isolation in mock:
   ```bash
   uv run python -c "
   import asyncio
   import tests.unit.test_chainlit_ui as tui
   async def test_session_isolation():
       tui.mock_cl.user_session.set('k', 'v1')
       await asyncio.sleep(0.01)
       assert tui.mock_cl.user_session.get('k') == 'v1'
   asyncio.run(asyncio.gather(test_session_isolation(), test_session_isolation()))
   print('Mock task isolation verified!')
   "
   ```
4. Verify error event rendering in `process_query`:
   Run `process_query` with a mock orchestrator yielding `{"type": "error", "error": "test failure"}` and assert that `msg.content` contains `"test failure"`.
5. Code style and linting:
   ```bash
   uv run ruff check cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py
   ```
