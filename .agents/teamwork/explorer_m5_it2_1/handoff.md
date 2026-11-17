# App Remediation Handoff Report (Milestone M5 — Iteration 2)

**Author**: App Remediation Explorer (`explorer_m5_it2_1`)  
**Target File**: `cuk_assistant/ui/app.py`  
**Related Test File**: `tests/unit/test_chainlit_ui.py`  
**Parent / Caller**: `30963065-bb08-41aa-acec-725022359cce`  
**Date**: 2026-11-16T18:20:00Z  

---

## 1. Observation

Direct examination of `cuk_assistant/ui/app.py` and empirical execution against Challenger 1 (`challenger_m5_1`) and Challenger 2 (`challenger_m5_2`) findings confirmed 7 core defects in `app.py` and 2 CLI robustness defects:

### O1. Unchecked Subscript on `title` in Citation Card Rendering
- **Location**: `cuk_assistant/ui/app.py:195, 218`
- **Code**:
  ```python
  195: title = event.get("title", "Official University Document")
  ...
  218: cl.Text(
           name=f"[{idx}] {title[:32]}... (p. {page_num})",
           content=card_content,
           display="side",
       )
  ```
- **Finding**: When `event` contains `{"type": "citation_card", "title": None}` (standard Pydantic serialization when `CitationCard.title` is unset/None), `event.get("title", ...)` evaluates to `None` because the key `"title"` is present in the dictionary. Line 218 executes `None[:32]`.
- **Reproduced Error**: `TypeError: 'NoneType' object is not subscriptable`.
- **Impact**: Premature termination of stream consumption; citation cards are not rendered.

### O2. Crash on Non-Dict/String List in Slot-Filling Options and `options=None`
- **Location**: `cuk_assistant/ui/app.py:176-184`
- **Code**:
  ```python
  176: elif ev_type == "slot_prompt":
  177:     target_slot = event.get("target_slot", "slot")
  178:     options = event.get("options", [])
  179:     for opt in options:
  180:         val = opt.get("value", "")
  ```
- **Finding**: Per `docs/api_contracts.md:1114`, quick replies may be formatted as plain string lists (e.g. `["B.Tech CSE", "MCA"]`). When `options` is a list of strings, line 180 executes `"B.Tech CSE".get("value")`. When `options` is `None` in the event payload, line 178 evaluates to `None` and line 179 attempts `for opt in None`.
- **Reproduced Error**:
  - String list: `AttributeError: 'str' object has no attribute 'get'`
  - None options: `TypeError: 'NoneType' object is not iterable`

### O3. Streaming Token Evaluates to `None` When `token=None` with `text` Fallback
- **Location**: `cuk_assistant/ui/app.py:172-174`
- **Code**:
  ```python
  172: if ev_type == "token":
  173:     token = event.get("token", event.get("text", ""))
  174:     await msg.stream_token(token)
  ```
- **Finding**: When `event` is `{"type": "token", "token": None, "text": "sample"}`, `event.get("token", ...)` encounters the key `"token"` with value `None` and returns `None` without ever evaluating `event.get("text", "")`. Line 174 invokes `await msg.stream_token(None)`.
- **Reproduced Error**: `TypeError: can only concatenate str (not "NoneType") to str`.

### O4. Non-Dict Payload and `active_slots=None` Crash in `on_slot_selected`
- **Location**: `cuk_assistant/ui/app.py:106-109`
- **Code**:
  ```python
  106: active_slots: dict[str, Any] = cl.user_session.get("active_slots", {})
  107: target_slot = (action.payload or {}).get("target_slot")
  108: if target_slot:
  109:     active_slots[target_slot] = action.value
  ```
- **Finding**:
  1. If `action.payload` is a non-dict truthy value (e.g. string `"semester"`, integer, or list), `(action.payload or {})` returns `"semester"`. Calling `.get("target_slot")` raises `AttributeError: 'str' object has no attribute 'get'`.
  2. If `active_slots` stored in `cl.user_session` is `None`, `cl.user_session.get("active_slots", {})` returns `None`. Line 109 `active_slots[target_slot] = ...` raises `TypeError: 'NoneType' object does not support item assignment`.

### O5. Missing Exception Handling & Unhandled `error` Events in `process_query`
- **Location**: `cuk_assistant/ui/app.py:164-253`
- **Code**:
  - `async for event in orchestrator.stream_turn(...)` is executed without a enclosing `try ... except ... finally`.
  - There is no branch for `ev_type == "error"` (emitted by `api/routes/chat.py:194` and `docs/api_contracts.md:271`).
- **Finding**:
  1. If `stream_turn` raises an exception (e.g. `RuntimeError: Connection reset`), the exception bubbles uncaught. `msg.update()` is never invoked, leaving the timeline message in a broken, hanging state.
  2. If `stream_turn` yields `{"type": "error", "message": "Rate limited"}`, the event is silently ignored. No tokens are streamed, and the method attaches positive/negative feedback action buttons to an empty message box.

### O6. `turn_trace_id` Overwritten by `None` on `done` Event
- **Location**: `cuk_assistant/ui/app.py:162, 224-225`
- **Code**:
  ```python
  162: turn_trace_id: str = uuid.uuid4().hex
  ...
  224: elif ev_type == "done":
  225:     turn_trace_id = event.get("trace_id", turn_trace_id)
  ```
- **Finding**: When `event` is `{"type": "done", "trace_id": None}`, `event.get("trace_id", ...)` returns `None`, wiping out the valid generated UUID from line 162. Feedback buttons are attached with `value=None`, polluting telemetry feedback sinks with null trace IDs.

### O7. Default Port Collision and CLI Robustness
- **Location**: `cuk_assistant/ui/app.py:278-297`
- **Code**:
  ```python
  278: port = os.environ.get("CHAINLIT_PORT", "8000")
  279: host = os.environ.get("CHAINLIT_HOST", "0.0.0.0")
  ...
  294: subprocess.run(cmd, check=True)
  ```
- **Finding**:
  1. `ORIGINAL_REQUEST.md:72` & `94` and `PROJECT.md:41` specify Chainlit on port **8001** (FastAPI on port 8000). Defaulting to 8000 causes a port collision when running the stack locally or under Docker Compose.
  2. If `CHAINLIT_PORT=""` is set in the environment, `os.environ.get("CHAINLIT_PORT", "8000")` evaluates to `""`, passing `["--port", ""]` to the subprocess, which causes an argument parser error.
  3. Non-zero exit codes from Chainlit raise `subprocess.CalledProcessError`, which is unhandled and results in an untracked traceback.

---

## 2. Logic Chain

1. **Step 1 (Dict Key Presence vs Truthiness)**: Python dictionary `.get(key, default)` returns `default` **only** if `key not in d`. If `key in d` and `d[key] is None`, `.get(key, default)` returns `None`. In event streams where schema serialization emits null values for unset optional fields (`title`, `page_number`, `source_url`, `quoted_snippet`, `token`, `options`, `trace_id`), relying on `.get(key, default)` results in `None` propagating into operations that require strings or iterables (`[:32]`, `for x in`, `+ token`). Replacing with `event.get(key) or fallback` guarantees fallback substitution for all falsy and null values.
2. **Step 2 (Polymorphism & Contract Conformance)**: The slot disambiguation contract (`docs/api_contracts.md`) allows `options` to be either an array of dicts `[{"value": ..., "label": ...}]` or plain strings `["B.Tech CSE", "MCA"]`. Checking `isinstance(opt, dict)` decouples the rendering loop from strict dictionary typing and guarantees robust fallback labels and descriptions.
3. **Step 3 (Session State Defense)**: In asynchronous UI frameworks, session keys may be reset, cleared, or set to null by external callbacks. Extracting `cl.user_session.get("active_slots")` as `dict(raw_slots) if isinstance(raw_slots, dict) else {}` and `action.payload` as `action.payload if isinstance(action.payload, dict) else {}` immunizes `on_slot_selected` against crashes.
4. **Step 4 (Stream Lifecycle Invariant)**: In Chainlit, every `cl.Message` sent via `await msg.send()` must be concluded with `await msg.update()` to transition the UI out of the loading/streaming indicator. Wrapping the event loop in `try ... except ... finally` guarantees `await msg.update()` is called on all code paths (happy path, error event, stream exception). Catching `ev_type == "error"` and exceptions renders informative markdown warnings (`\n\n⚠️ **Error:** ...`) and suppresses feedback buttons on failed turns.
5. **Step 5 (Architecture & System Consistency)**: The project specification explicitly partitions FastAPI to port 8000 and Chainlit to port 8001. Aligning the default `CHAINLIT_PORT` in `app.py` to `"8001"` and updating the corresponding assertion in `tests/unit/test_chainlit_ui.py:608` resolves the port conflict and maintains system-wide coherence.

---

## 3. Caveats

1. **Test Double Module Scope**: Chainlit is not installed in the current virtual environment (unit tests use `types.ModuleType("chainlit")` doubles). Changes to `app.py` must maintain 100% compatibility with both the mock module doubles in `test_chainlit_ui.py` and the actual `chainlit` runtime when installed.
2. **Test File Synchronization**: Updating `app.py`'s default port from `"8000"` to `"8001"` requires updating line 608 in `tests/unit/test_chainlit_ui.py` (`assert "--port" in cmd and "8001" in cmd`). Running `pytest` before updating the test will fail on that single test assertion. Worker Worker must apply the test update simultaneously.

---

## 4. Conclusion & Complete Remediation Specification

### Remediation Blueprint for `cuk_assistant/ui/app.py`

#### 1. Fix `on_slot_selected` (Lines 102-117)
```python
    @cl.action_callback("fill_slot")
    async def on_slot_selected(action: cl.Action) -> None:
        """Handle user selection of an interactive slot-filling disambiguation chip."""
        await action.remove()
        raw_slots = cl.user_session.get("active_slots")
        active_slots: dict[str, Any] = dict(raw_slots) if isinstance(raw_slots, dict) else {}

        payload = action.payload if isinstance(action.payload, dict) else {}
        target_slot = payload.get("target_slot")
        if target_slot:
            active_slots[str(target_slot)] = action.value
            cl.user_session.set("active_slots", active_slots)

        label = action.label or action.value or "Selected"
        echo_msg = f"Selected: **{label}**"
        await cl.Message(content=echo_msg).send()

        last_query = cl.user_session.get("last_query") or str(action.value or "")
        await process_query(last_query, updated_slots=active_slots)
```

#### 2. Fix `process_query` (Lines 149-253)
```python
    async def process_query(
        query: str,
        updated_slots: dict[str, Any] | None = None,
    ) -> None:
        """Execute turn through orchestrator and stream synthesized answer to UI."""
        session_id = cl.user_session.get("session_id") or f"sess_{uuid.uuid4().hex}"
        orchestrator = get_ui_orchestrator()

        msg = cl.Message(content="")
        await msg.send()

        citation_elements: list[cl.Text] = []
        slot_actions: list[cl.Action] = []
        turn_trace_id: str = uuid.uuid4().hex
        has_error: bool = False

        try:
            async for event in orchestrator.stream_turn(
                query=query,
                session_id=session_id,
                slots=updated_slots,
                trace_id=turn_trace_id,
            ):
                ev_type = event.get("type")

                if ev_type == "token":
                    token = event.get("token") or event.get("text") or ""
                    if token:
                        await msg.stream_token(token)

                elif ev_type == "slot_prompt":
                    target_slot = event.get("target_slot") or "slot"
                    options = event.get("options") or []
                    for opt in options:
                        if isinstance(opt, dict):
                            val = str(opt.get("value") or "")
                            lbl = str(opt.get("label") or val)
                            desc = opt.get("description")
                        else:
                            val = str(opt)
                            lbl = str(opt)
                            desc = None

                        if not val and not lbl:
                            continue

                        slot_actions.append(
                            cl.Action(
                                name="fill_slot",
                                value=val,
                                label=lbl,
                                description=desc or f"Select {lbl}",
                                payload={"target_slot": target_slot},
                            )
                        )

                elif ev_type == "citation_card":
                    idx = len(citation_elements) + 1
                    title = event.get("title") or "Official University Document"
                    source_url = event.get("source_url") or "https://cukashmir.ac.in"
                    page_num = event.get("page_number") or 1
                    sec_heading = event.get("section_heading") or "General"
                    snippet = event.get("quoted_snippet") or ""
                    is_table = bool(event.get("is_table", False))
                    table_md = event.get("table_markdown")

                    if is_table and table_md:
                        card_content = (
                            f"### {title} (Page {page_num})\n"
                            f"**Source:** [{source_url}]({source_url})\n\n"
                            f"{table_md}"
                        )
                    else:
                        card_content = (
                            f"**Document:** [{title}]({source_url})\n\n"
                            f"**Page:** {page_num} | **Section:** {sec_heading}\n\n"
                            f'> "{snippet}"'
                        )

                    citation_elements.append(
                        cl.Text(
                            name=f"[{idx}] {title[:32]}... (p. {page_num})",
                            content=card_content,
                            display="side",
                        )
                    )

                elif ev_type == "error":
                    has_error = True
                    err_msg = (
                        event.get("message")
                        or event.get("error")
                        or event.get("error_code")
                        or "An error occurred while processing your request."
                    )
                    await msg.stream_token(f"\n\n⚠️ **Error:** {err_msg}")
                    if event.get("trace_id"):
                        turn_trace_id = str(event["trace_id"])

                elif ev_type == "done":
                    turn_trace_id = event.get("trace_id") or turn_trace_id

        except Exception as exc:
            has_error = True
            logger.exception("Error during turn streaming: %s", exc)
            await msg.stream_token(f"\n\n⚠️ **System Error:** {exc}")

        finally:
            # Attach side-panel citation cards if any were returned
            if citation_elements:
                msg.elements = citation_elements

            # Attach interactive slot chips if clarification is required
            if slot_actions:
                msg.actions = slot_actions
            elif not has_error:
                # Attach feedback buttons for verified completed turns
                feedback_actions = [
                    cl.Action(
                        name="feedback_upvote",
                        value=turn_trace_id,
                        label="👍 Helpful",
                        description="Answer is accurate and verified",
                    ),
                    cl.Action(
                        name="feedback_downvote",
                        value=turn_trace_id,
                        label="👎 Inaccurate",
                        description="Information is missing or outdated",
                    ),
                ]
                msg.actions = feedback_actions

            await msg.update()
```

#### 3. Fix CLI `run()` (Lines 263-298)
```python
def run() -> None:
    """Launch the Chainlit Web UI server for Central University of Kashmir Assistant."""
    if cl is None:
        print(
            "ERROR: 'chainlit' is not installed in the environment.\n"
            "Please run: uv add chainlit\n"
            "Then re-launch: cuk-ui",
            file=sys.stderr,
        )
        sys.exit(1)

    import subprocess
    from pathlib import Path

    app_path = Path(__file__).resolve()
    raw_port = os.environ.get("CHAINLIT_PORT", "").strip()
    port = raw_port if (raw_port.isdigit() and 1 <= int(raw_port) <= 65535) else "8001"
    raw_host = os.environ.get("CHAINLIT_HOST", "").strip()
    host = raw_host or "0.0.0.0"

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
    except subprocess.CalledProcessError as exc:
        logger.error("Chainlit server exited with code %s: %s", exc.returncode, exc)
        sys.exit(exc.returncode)
```

---

### Complete Proposed Source File for `cuk_assistant/ui/app.py`

```python
"""cuk_assistant/ui/app.py

Interactive Chainlit Web Application for Central University of Kashmir AI Assistant (`cuk-ui`).
Implements:
1. Real-time streaming response synthesis with markdown tables and bullet formatting.
2. Interactive Action Chips for faceted slot-filling (Departments, Batches, Semesters).
3. Side-panel inspection cards for verified verbatim citations with PDF page numbers.
4. Thumbs up/down user feedback loop recording to `/api/v1/chat/feedback`.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any

from cuk_assistant.core.factory import create_rag_orchestrator, create_telemetry_sink
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)

# Lazy initialization of shared orchestrator and sink
_orchestrator: RAGOrchestrator | None = None
_telemetry_sink: Any | None = None


def get_ui_orchestrator() -> RAGOrchestrator:
    """Retrieve or initialize singleton orchestrator for UI session."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_rag_orchestrator()
    return _orchestrator


def get_ui_telemetry_sink() -> Any:
    """Retrieve or initialize singleton telemetry sink for feedback."""
    global _telemetry_sink
    if _telemetry_sink is None:
        _telemetry_sink = create_telemetry_sink()
    return _telemetry_sink


# ---------------------------------------------------------------------------
# Chainlit Application Lifecycle & Event Callbacks
# ---------------------------------------------------------------------------

try:
    import chainlit as cl

    @cl.on_chat_start
    async def on_chat_start() -> None:
        """Initialize user session state and present starter recommendation chips."""
        session_id = f"sess_{uuid.uuid4().hex}"
        cl.user_session.set("session_id", session_id)
        cl.user_session.set("active_slots", {})

        # Starter recommendation chips
        starter_actions = [
            cl.Action(
                name="starter_prompt",
                value="What is the detailed syllabus for B.Tech CSE Semester 4?",
                label="📚 B.Tech CSE Syllabus",
                description="Explore course syllabus and credits",
            ),
            cl.Action(
                name="starter_prompt",
                value="What are the CUET-UG eligibility criteria and intake for admissions?",
                label="📝 Admissions & CUET",
                description="Check entrance requirements and seat matrix",
            ),
            cl.Action(
                name="starter_prompt",
                value="What are the passing criteria and attendance rules under CUK CBCS ordinances?",
                label="⚖️ CBCS Ordinances",
                description="University academic rules and regulations",
            ),
            cl.Action(
                name="starter_prompt",
                value="Show me the latest exam date sheets and notifications.",
                label="📅 Exam Date Sheets",
                description="Examination schedules and alerts",
            ),
        ]

        welcome_text = (
            "### Welcome to Central University of Kashmir (CUK) AI Assistant! 🎓\n\n"
            "I provide factual answers grounded in official university documents. "
            "Select a common topic below or type your inquiry:"
        )
        await cl.Message(content=welcome_text, actions=starter_actions).send()

    @cl.action_callback("starter_prompt")
    async def on_starter_prompt(action: cl.Action) -> None:
        """Handle click on quick starter recommendation button."""
        await action.remove()
        user_message = cl.Message(content=str(action.value))
        await user_message.send()
        await process_query(str(action.value))

    @cl.action_callback("fill_slot")
    async def on_slot_selected(action: cl.Action) -> None:
        """Handle user selection of an interactive slot-filling disambiguation chip."""
        await action.remove()
        raw_slots = cl.user_session.get("active_slots")
        active_slots: dict[str, Any] = dict(raw_slots) if isinstance(raw_slots, dict) else {}

        payload = action.payload if isinstance(action.payload, dict) else {}
        target_slot = payload.get("target_slot")
        if target_slot:
            active_slots[str(target_slot)] = action.value
            cl.user_session.set("active_slots", active_slots)

        label = action.label or action.value or "Selected"
        echo_msg = f"Selected: **{label}**"
        await cl.Message(content=echo_msg).send()

        last_query = cl.user_session.get("last_query") or str(action.value or "")
        await process_query(last_query, updated_slots=active_slots)

    @cl.action_callback("feedback_upvote")
    async def on_feedback_upvote(action: cl.Action) -> None:
        """Record positive satisfaction feedback for a dialogue turn."""
        trace_id = str(action.value or "")
        sink = get_ui_telemetry_sink()
        if hasattr(sink, "record_feedback"):
            sink.record_feedback(trace_id=trace_id, score=1, feedback_category="helpful")
        await cl.Message(content="*Thank you for your feedback! (Marked as helpful 👍)*").send()
        await action.remove()

    @cl.action_callback("feedback_downvote")
    async def on_feedback_downvote(action: cl.Action) -> None:
        """Record negative satisfaction feedback for a dialogue turn."""
        trace_id = str(action.value or "")
        sink = get_ui_telemetry_sink()
        if hasattr(sink, "record_feedback"):
            sink.record_feedback(trace_id=trace_id, score=-1, feedback_category="unhelpful")
        await cl.Message(content="*Thank you for your feedback! (Marked as unhelpful 👎)*").send()
        await action.remove()

    @cl.on_message
    async def on_message(message: cl.Message) -> None:
        """Main chat dispatch handling incoming user queries."""
        query_text = (message.content or "").strip()
        if not query_text:
            return

        cl.user_session.set("last_query", query_text)
        raw_slots = cl.user_session.get("active_slots")
        active_slots: dict[str, Any] = dict(raw_slots) if isinstance(raw_slots, dict) else {}
        await process_query(query_text, updated_slots=active_slots)

    async def process_query(
        query: str,
        updated_slots: dict[str, Any] | None = None,
    ) -> None:
        """Execute turn through orchestrator and stream synthesized answer to UI."""
        session_id = cl.user_session.get("session_id") or f"sess_{uuid.uuid4().hex}"
        orchestrator = get_ui_orchestrator()

        msg = cl.Message(content="")
        await msg.send()

        citation_elements: list[cl.Text] = []
        slot_actions: list[cl.Action] = []
        turn_trace_id: str = uuid.uuid4().hex
        has_error: bool = False

        try:
            async for event in orchestrator.stream_turn(
                query=query,
                session_id=session_id,
                slots=updated_slots,
                trace_id=turn_trace_id,
            ):
                ev_type = event.get("type")

                if ev_type == "token":
                    token = event.get("token") or event.get("text") or ""
                    if token:
                        await msg.stream_token(token)

                elif ev_type == "slot_prompt":
                    target_slot = event.get("target_slot") or "slot"
                    options = event.get("options") or []
                    for opt in options:
                        if isinstance(opt, dict):
                            val = str(opt.get("value") or "")
                            lbl = str(opt.get("label") or val)
                            desc = opt.get("description")
                        else:
                            val = str(opt)
                            lbl = str(opt)
                            desc = None

                        if not val and not lbl:
                            continue

                        slot_actions.append(
                            cl.Action(
                                name="fill_slot",
                                value=val,
                                label=lbl,
                                description=desc or f"Select {lbl}",
                                payload={"target_slot": target_slot},
                            )
                        )

                elif ev_type == "citation_card":
                    idx = len(citation_elements) + 1
                    title = event.get("title") or "Official University Document"
                    source_url = event.get("source_url") or "https://cukashmir.ac.in"
                    page_num = event.get("page_number") or 1
                    sec_heading = event.get("section_heading") or "General"
                    snippet = event.get("quoted_snippet") or ""
                    is_table = bool(event.get("is_table", False))
                    table_md = event.get("table_markdown")

                    if is_table and table_md:
                        card_content = (
                            f"### {title} (Page {page_num})\n"
                            f"**Source:** [{source_url}]({source_url})\n\n"
                            f"{table_md}"
                        )
                    else:
                        card_content = (
                            f"**Document:** [{title}]({source_url})\n\n"
                            f"**Page:** {page_num} | **Section:** {sec_heading}\n\n"
                            f'> "{snippet}"'
                        )

                    citation_elements.append(
                        cl.Text(
                            name=f"[{idx}] {title[:32]}... (p. {page_num})",
                            content=card_content,
                            display="side",
                        )
                    )

                elif ev_type == "error":
                    has_error = True
                    err_msg = (
                        event.get("message")
                        or event.get("error")
                        or event.get("error_code")
                        or "An error occurred while processing your request."
                    )
                    await msg.stream_token(f"\n\n⚠️ **Error:** {err_msg}")
                    if event.get("trace_id"):
                        turn_trace_id = str(event["trace_id"])

                elif ev_type == "done":
                    turn_trace_id = event.get("trace_id") or turn_trace_id

        except Exception as exc:
            has_error = True
            logger.exception("Error during turn streaming: %s", exc)
            await msg.stream_token(f"\n\n⚠️ **System Error:** {exc}")

        finally:
            # Attach side-panel citation cards if any were returned
            if citation_elements:
                msg.elements = citation_elements

            # Attach interactive slot chips if clarification is required
            if slot_actions:
                msg.actions = slot_actions
            elif not has_error:
                # Attach feedback buttons for verified completed turns
                feedback_actions = [
                    cl.Action(
                        name="feedback_upvote",
                        value=turn_trace_id,
                        label="👍 Helpful",
                        description="Answer is accurate and verified",
                    ),
                    cl.Action(
                        name="feedback_downvote",
                        value=turn_trace_id,
                        label="👎 Inaccurate",
                        description="Information is missing or outdated",
                    ),
                ]
                msg.actions = feedback_actions

            await msg.update()

except ImportError:
    cl = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CLI Entrypoint (`cuk-ui`)
# ---------------------------------------------------------------------------


def run() -> None:
    """Launch the Chainlit Web UI server for Central University of Kashmir Assistant."""
    if cl is None:
        print(
            "ERROR: 'chainlit' is not installed in the environment.\n"
            "Please run: uv add chainlit\n"
            "Then re-launch: cuk-ui",
            file=sys.stderr,
        )
        sys.exit(1)

    import subprocess
    from pathlib import Path

    app_path = Path(__file__).resolve()
    raw_port = os.environ.get("CHAINLIT_PORT", "").strip()
    port = raw_port if (raw_port.isdigit() and 1 <= int(raw_port) <= 65535) else "8001"
    raw_host = os.environ.get("CHAINLIT_HOST", "").strip()
    host = raw_host or "0.0.0.0"

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
    except subprocess.CalledProcessError as exc:
        logger.error("Chainlit server exited with code %s: %s", exc.returncode, exc)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    run()
```

---

### Accompanying Requirements for `tests/unit/test_chainlit_ui.py`

The implementing worker must also apply the following three enhancements in `tests/unit/test_chainlit_ui.py`:

1. **Default Port Assertion**:
   Change line 608:
   ```python
   # tests/unit/test_chainlit_ui.py:608
   assert "--port" in cmd and "8001" in cmd
   ```
2. **Teardown Module Isolation**:
   In `teardown_module()`:
   ```python
   def teardown_module() -> None:
       """Restore original sys.modules state after module tests complete."""
       if _orig_chainlit is not None:
           sys.modules["chainlit"] = _orig_chainlit
       else:
           sys.modules.pop("chainlit", None)
       importlib.reload(app)
   ```
3. **Mock Task Isolation**:
   Refactor `MockUserSession` to use `contextvars.ContextVar` to prevent state leakage under concurrent tests.
4. **Adversarial Test Cases**:
   Add test methods to verify:
   - `test_process_query_citation_card_sanitization_none_values`
   - `test_process_query_slot_prompt_polymorphic_options_and_none`
   - `test_process_query_token_fallback_and_none`
   - `test_on_slot_selected_defensive_payload_and_active_slots`
   - `test_process_query_stream_exception_handling`
   - `test_process_query_error_event_rendering_and_no_feedback`
   - `test_process_query_done_event_preserves_trace_id_when_none`
   - `test_run_sanitizes_empty_port_and_handles_called_process_error`

---

## 5. Verification Method

Once Worker Worker applies the remediation to `cuk_assistant/ui/app.py` and `tests/unit/test_chainlit_ui.py`, verify independently using:

### Command 1: Unit Test Suite Execution
```bash
uv run pytest tests/unit/test_chainlit_ui.py -v
```
Expected: All tests pass (including port 8001 assertion).

### Command 2: Empirical Adversarial Probe Harness
```bash
uv run python -c "
import asyncio
from unittest.mock import MagicMock, patch
import tests.unit.test_chainlit_ui as t_ui
import cuk_assistant.ui.app as app

async def run_checks():
    # Probe 1: Citation card with None values
    async def s1(*a, **k):
        yield {'type': 'citation_card', 'title': None, 'page_number': None, 'source_url': None, 'quoted_snippet': None}
        yield {'type': 'done', 'trace_id': None}
    m1 = MagicMock(); m1.stream_turn = s1
    with patch.object(app, 'get_ui_orchestrator', return_value=m1):
        await app.process_query('q1')
        msg = t_ui.MockMessage.sent_messages[-1]
        assert '[1] Official University Document... (p. 1)' in msg.elements[0].name
        assert msg.actions[0].value is not None

    # Probe 2: String list options & options=None
    async def s2(*a, **k):
        yield {'type': 'slot_prompt', 'target_slot': 'prog', 'options': ['B.Tech CSE', 'MCA']}
        yield {'type': 'slot_prompt', 'target_slot': 'sem', 'options': None}
        yield {'type': 'done'}
    m2 = MagicMock(); m2.stream_turn = s2
    with patch.object(app, 'get_ui_orchestrator', return_value=m2):
        await app.process_query('q2')
        msg = t_ui.MockMessage.sent_messages[-1]
        assert [a.label for a in msg.actions] == ['B.Tech CSE', 'MCA']

    # Probe 3: Token with token=None and text fallback
    async def s3(*a, **k):
        yield {'type': 'token', 'token': None, 'text': 'fallback_token'}
        yield {'type': 'done'}
    m3 = MagicMock(); m3.stream_turn = s3
    with patch.object(app, 'get_ui_orchestrator', return_value=m3):
        await app.process_query('q3')
        msg = t_ui.MockMessage.sent_messages[-1]
        assert 'fallback_token' in msg.content

    # Probe 4: Non-dict payload & active_slots=None in slot callback
    action_bad = t_ui.MockAction(name='fill_slot', value='Sem 4', label='Sem 4', payload='not-a-dict')
    t_ui.mock_cl.user_session.set('active_slots', None)
    await app.on_slot_selected(action_bad)

    # Probe 5: Error event rendering & feedback suppression
    async def s5(*a, **k):
        yield {'type': 'error', 'message': 'Safety policy violation'}
        yield {'type': 'done'}
    m5 = MagicMock(); m5.stream_turn = s5
    with patch.object(app, 'get_ui_orchestrator', return_value=m5):
        await app.process_query('q5')
        msg = t_ui.MockMessage.sent_messages[-1]
        assert '⚠️ **Error:** Safety policy violation' in msg.content
        assert len(msg.actions) == 0

    # Probe 6: Stream exception handling
    async def s6(*a, **k):
        yield {'type': 'token', 'token': 'Initial text'}
        raise RuntimeError('Connection dropped')
    m6 = MagicMock(); m6.stream_turn = s6
    with patch.object(app, 'get_ui_orchestrator', return_value=m6):
        await app.process_query('q6')
        msg = t_ui.MockMessage.sent_messages[-1]
        assert '⚠️ **System Error:** Connection dropped' in msg.content
        assert msg.updated is True
        assert len(msg.actions) == 0

    print('ALL ADVERSARIAL PROBES PASSED SUCCESSFULLY!')

asyncio.run(run_checks())
"
```

### Command 3: Lint and Style Check
```bash
uv run ruff check cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py
```
Expected: 0 errors and 0 warnings.
