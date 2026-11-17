# Milestone M5 Adversarial Challenge Report: Chainlit Web UI & Unit Test Suite

**Challenger**: Challenger 1 (critic, specialist)  
**Target Files**: `cuk_assistant/ui/app.py`, `tests/unit/test_chainlit_ui.py`  
**Verdict**: **`REQUEST_CHANGES`**  
**Overall Risk Assessment**: **HIGH**

---

## 1. Observation

### O1. Baseline Suite Execution
Command: `uv run pytest tests/unit/test_chainlit_ui.py -v`  
Result: 23 passed in 0.23s.  
Lint check: `uv run ruff check cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py` -> 0 errors.

### O2. Unchecked Subscript on `title` in Citation Card Rendering
Location: `cuk_assistant/ui/app.py:195, 218`
```python
195: title = event.get("title", "Official University Document")
...
218: cl.Text(
         name=f"[{idx}] {title[:32]}... (p. {page_num})",
         content=card_content,
         display="side",
     )
```
Observation: When `event` contains `{"type": "citation_card", "title": None}` (a standard serialization output when `CitationCard.title` is `None`), `event.get("title", ...)` evaluates to `None`. At line 218, `title[:32]` evaluates `None[:32]`.  
Reproduction Output:
```
TypeError: 'NoneType' object is not subscriptable
```
The stream crashes prematurely, aborting side element attachment and subsequent execution.

### O3. Crash on String-List Options in Slot-Filling Disambiguation Chips
Location: `cuk_assistant/ui/app.py:176-184`
```python
176: elif ev_type == "slot_prompt":
177:     target_slot = event.get("target_slot", "slot")
178:     options = event.get("options", [])
179:     for opt in options:
180:         val = opt.get("value", "")
```
Observation: `docs/api_contracts.md` (line 1114) specifies options formatted as a list of strings: `event: quick_replies {target_slot: "program", options: ["B.Tech CSE", "MCA", "M.Tech"]}`. When `options` is a list of strings (or when `"options": None`), line 180 `opt.get("value", "")` crashes.  
Reproduction Output:
```
AttributeError: 'str' object has no attribute 'get'
# Or if options: None -> TypeError: 'NoneType' object is not iterable
```

### O4. Streaming Token Evaluates to `None` with `text` Fallback
Location: `cuk_assistant/ui/app.py:172-174`
```python
172: if ev_type == "token":
173:     token = event.get("token", event.get("text", ""))
174:     await msg.stream_token(token)
```
Observation: When `event` is `{"type": "token", "token": None, "text": "sample"}`, `event.get("token", ...)` evaluates to `None` because the key `"token"` exists in the dictionary. The default `event.get("text", "")` is never executed. Line 174 calls `msg.stream_token(None)`.  
Reproduction Output:
```
TypeError: can only concatenate str (not "NoneType") to str
```

### O5. Crash on Non-Dictionary Payload in `on_slot_selected`
Location: `cuk_assistant/ui/app.py:106-107`
```python
106: active_slots: dict[str, Any] = cl.user_session.get("active_slots", {})
107: target_slot = (action.payload or {}).get("target_slot")
```
Observation: If `action.payload` is a non-dictionary truthy value (e.g. string `"semester"`, integer, or list), `(action.payload or {})` yields that value. Calling `.get("target_slot")` raises `AttributeError`. Furthermore, if `active_slots` in `user_session` is `None`, line 109 `active_slots[target_slot] = action.value` crashes.  
Reproduction Output:
```
Payload 'semester' crashed with AttributeError: 'str' object has no attribute 'get'
Payload active_slots=None crashed with TypeError: 'NoneType' object does not support item assignment
```

### O6. Uncaught Exception During Event Streaming Leaves UI Message Hanging
Location: `cuk_assistant/ui/app.py:164-226`
Observation: `async for event in orchestrator.stream_turn(...)` is executed without a `try ... except` wrapper. If an error occurs during retrieval, reranking, or LLM generation (e.g. `RuntimeError: Connection broken`), the exception bubbles up uncaught. `msg.update()` is never invoked, leaving the message in an incomplete, unfinalized state without feedback or an error message presented to the student.  
Reproduction Output:
```
RuntimeError: Connection broken (msg.updated=False, msg.actions=[])
```

### O7. Silent Ingestion of `error` Events Yields Empty Message with Feedback Chips
Location: `cuk_assistant/ui/app.py:170-226`
Observation: `stream_turn` specifies an `error` event type (`docs/api_contracts.md:271`, `orchestrator.py:338`). In `app.py`, `ev_type == "error"` is not handled by any branch. The error message is silently ignored, and the UI attaches feedback upvote/downvote buttons to an empty message.  
Reproduction Output:
```
content='', actions=['feedback_upvote', 'feedback_downvote']
```

### O8. Trace ID Overwritten by `None` on Terminal `done` Event
Location: `cuk_assistant/ui/app.py:162, 224-225`
```python
162: turn_trace_id: str = uuid.uuid4().hex
...
224: elif ev_type == "done":
225:     turn_trace_id = event.get("trace_id", turn_trace_id)
```
Observation: When `event` is `{"type": "done", "trace_id": None}`, `event.get("trace_id", ...)` returns `None`, wiping out the valid UUID generated at line 162. Feedback buttons are attached with `value=None`, polluting the telemetry sink with `trace_id="None"`.  
Reproduction Output:
```
Feedback action value: None
```

### O9. Default Port Conflict Against System Architecture
Location: `cuk_assistant/ui/app.py:278`, `tests/unit/test_chainlit_ui.py:608`
```python
# app.py:278
port = os.environ.get("CHAINLIT_PORT", "8000")
# test_chainlit_ui.py:608
assert "--port" in cmd and "8000" in cmd
```
Observation: `PROJECT.md` line 41 specifies `docker-compose.yml (FastAPI 8000, Chainlit 8001)`. `ORIGINAL_REQUEST.md` line 72 & line 94 specify Chainlit on port 8001. Defaulting to port 8000 causes a port collision with FastAPI (`cuk_assistant/api/main.py`) when run without explicitly setting `CHAINLIT_PORT`. The test suite actively asserts the incorrect default port (`8000`).

---

## 2. Logic Chain

1. **Premise 1 (Resilient UI Requirement)**: The user-facing Chainlit interface operates in a hostile network environment where SSE streams may encounter timeouts, malformed payloads, optional metadata fields with `None` values, or pipeline errors.
2. **Premise 2 (Empirical Failure Evidence)**: As proven in O2, O3, O4, O5, O6, O7, O8, and O9, multiple code paths in `app.py` directly cause unhandled runtime exceptions (`TypeError`, `AttributeError`) or behavioral degradation (silent error swallowing, trace ID corruption, port conflict).
3. **Premise 3 (Test Suite Blind Spots)**: `tests/unit/test_chainlit_ui.py` passed 23/23 tests because its test doubles only supply happy-path dictionary fixtures. It does not test explicit `None` fields, string list options, `error` event envelopes, stream exceptions, or port specification conformance.
4. **Conclusion**: `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py` fail adversarial verification under edge conditions and contract specifications. Changes are required before sign-off.

---

## 3. Caveats

- Physical WebSocket disconnects and browser tab terminations cannot be simulated directly in unit test doubles; these rely on Chainlit's internal ASGI server lifecycle.
- Chainlit itself is not installed in the active environment; testing correctly leverages `types.ModuleType("chainlit")` injection, which is architecturally appropriate for unit testing.

---

## 4. Conclusion & Required Changes

**Verdict**: **`REQUEST_CHANGES`**

The following concrete fixes must be applied by the implementation worker:

### In `cuk_assistant/ui/app.py`:
1. **Citation Card Field Sanitization**:
   Change `title = event.get("title", "Official University Document")` to:
   ```python
   title = event.get("title") or "Official University Document"
   source_url = event.get("source_url") or "https://cukashmir.ac.in"
   page_num = event.get("page_number") or 1
   snippet = event.get("quoted_snippet") or ""
   ```
2. **Polymorphic Slot Prompt Options**:
   Support both dictionary options (`{"value": ..., "label": ...}`) and plain string options (`"B.Tech CSE"`):
   ```python
   options = event.get("options") or []
   for opt in options:
       if isinstance(opt, dict):
           val = opt.get("value") or ""
           lbl = opt.get("label") or val
           desc = opt.get("description")
       else:
           val = str(opt)
           lbl = str(opt)
           desc = None
   ```
3. **Safe Token Extraction**:
   Change token parsing to:
   ```python
   token = event.get("token") or event.get("text") or ""
   if token:
       await msg.stream_token(token)
   ```
4. **Defensive Action Payload & Active Slots Handling**:
   In `on_slot_selected`:
   ```python
   active_slots: dict[str, Any] = cl.user_session.get("active_slots") or {}
   payload = action.payload if isinstance(action.payload, dict) else {}
   target_slot = payload.get("target_slot")
   ```
5. **Stream Exception Handling & Error Event Presentation**:
   Wrap `async for event in orchestrator.stream_turn(...)` in a `try ... except Exception as exc:` block:
   ```python
   try:
       async for event in orchestrator.stream_turn(...):
           ...
           elif ev_type == "error":
               err_msg = event.get("error") or event.get("message") or "An error occurred."
               await msg.stream_token(f"\n\n⚠️ *{err_msg}*")
   except Exception as exc:
       logger.exception("Error during turn streaming: %s", exc)
       await msg.stream_token(f"\n\n⚠️ *Service temporarily unavailable. Please try again.*")
   finally:
       await msg.update()
   ```
6. **Preserve Valid Trace ID on Done**:
   Change `turn_trace_id = event.get("trace_id", turn_trace_id)` to:
   ```python
   turn_trace_id = event.get("trace_id") or turn_trace_id
   ```
7. **Default Port Alignment**:
   In `app.py:278`, default `CHAINLIT_PORT` to `"8001"` (aligning with `ORIGINAL_REQUEST.md:72` and `PROJECT.md:41`). Update `test_chainlit_ui.py:608` to assert `"8001"`.

### In `tests/unit/test_chainlit_ui.py`:
Add dedicated test cases verifying:
1. `citation_card` with explicit `title=None`, `page_number=None`, `source_url=None`.
2. `slot_prompt` with string list options `["B.Tech", "M.Tech"]` and `options=None`.
3. `token` event with `token=None` and `text="fallback"`.
4. `on_slot_selected` with non-dict payloads (string, None).
5. `process_query` handling stream exceptions and `error` events gracefully.
6. `done` event with `trace_id=None` preserving generated fallback trace ID.
7. Port default asserting `"8001"`.

---

## 5. Verification Method

To verify the defects and subsequent fixes, run the empirical probe harness:

```bash
uv run python -c "
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import tests.unit.test_chainlit_ui as t_ui
from tests.unit.test_chainlit_ui import MockMessage, MockAction, mock_cl
import cuk_assistant.ui.app as app

async def run_check():
    # Probe 1: None title
    async def s1(*a, **k):
        yield {'type': 'citation_card', 'title': None, 'page_number': 1}
        yield {'type': 'done'}
    m1 = MagicMock(); m1.stream_turn = s1
    with patch.object(app, 'get_ui_orchestrator', return_value=m1):
        try:
            await app.process_query('q1')
            print('Probe 1: PASSED')
        except Exception as e:
            print('Probe 1: FAILED ->', e)

    # Probe 2: string options
    async def s2(*a, **k):
        yield {'type': 'slot_prompt', 'target_slot': 'prog', 'options': ['B.Tech CSE', 'MCA']}
        yield {'type': 'done'}
    m2 = MagicMock(); m2.stream_turn = s2
    with patch.object(app, 'get_ui_orchestrator', return_value=m2):
        try:
            await app.process_query('q2')
            print('Probe 2: PASSED')
        except Exception as e:
            print('Probe 2: FAILED ->', e)

asyncio.run(run_check())
"
```

Invalidation condition: All 9 empirical probes run without crashes, error events are displayed to the user, and `uv run pytest tests/unit/test_chainlit_ui.py` passes with 100% assertions green on port 8001.
