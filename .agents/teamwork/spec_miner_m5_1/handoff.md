# Specification Mining Report: Milestone M5 (Chainlit UI & Test Specification)

## 1. Observation

### 1.1 Specification & Implementation Artifacts
- **Primary Source Code**: `cuk_assistant/ui/app.py` (300 lines). Contains the entire Chainlit web application for Central University of Kashmir AI Assistant (`cuk-ui`).
- **Interaction Contracts**: `docs/api_contracts.md` lines 932–1040:
  - Section 5.1: `Interactive Quick-Reply Slot-Filling Chips Contract` (`QuickReplyOption`, `QuickReplyPayload`, `handle_quick_replies`, `@cl.action_callback("fill_slot")`).
  - Section 5.2: `Citation Card & PDF Page Inspection Modal Contract` (`CitationCard`, `render_citation_cards`, `cl.Text(display="side")`).
- **Orchestrator Protocol**: `cuk_assistant/pipeline/orchestrator.py` lines 319–340:
  - `stream_turn(query, session_id, slots, ...)` yields events: `token`, `slot_prompt`, `citation_card`, `done`, `error`.
- **Environment Status**:
  - `pyproject.toml`: `chainlit` is not currently declared in `dependencies`.
  - Probing `uv run python -c "import chainlit"` produces verbatim: `ModuleNotFoundError: No module named 'chainlit'`.
  - `cuk_assistant/ui/app.py` lines 49–50 & 254–256 employs an explicit try/except block:
    ```python
    try:
        import chainlit as cl
        ...
    except ImportError:
        cl = None
    ```
  - Probing `cuk_assistant/ui/app.py` with mock `chainlit` in `sys.modules["chainlit"]` dynamically enables and binds all decorated handlers (`on_chat_start`, `on_starter_prompt`, `on_slot_selected`, `on_feedback_upvote`, `on_feedback_downvote`, `on_message`, `process_query`).

### 1.2 Public Interface & Signatures in `cuk_assistant/ui/app.py`
1. `get_ui_orchestrator() -> RAGOrchestrator` (line 29)
2. `get_ui_telemetry_sink() -> Any` (line 37)
3. `@cl.on_chat_start async def on_chat_start() -> None` (line 52)
4. `@cl.action_callback("starter_prompt") async def on_starter_prompt(action: cl.Action) -> None` (line 94)
5. `@cl.action_callback("fill_slot") async def on_slot_selected(action: cl.Action) -> None` (line 102)
6. `@cl.action_callback("feedback_upvote") async def on_feedback_upvote(action: cl.Action) -> None` (line 118)
7. `@cl.action_callback("feedback_downvote") async def on_feedback_downvote(action: cl.Action) -> None` (line 128)
8. `@cl.on_message async def on_message(message: cl.Message) -> None` (line 138)
9. `async def process_query(query: str, updated_slots: dict[str, Any] | None = None) -> None` (line 149)
10. `def run() -> None` (line 263)

---

## 2. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Lifecycle & DI Factory | `get_ui_orchestrator` | Lazily instantiates and caches singleton `RAGOrchestrator` via `create_rag_orchestrator()` | None (inspects `_orchestrator`) | `RAGOrchestrator` instance | Propagates factory errors; creates fresh if global cleared | `cuk_assistant/ui/app.py:29-35` |
| 2 | Lifecycle & DI Factory | `get_ui_telemetry_sink` | Lazily instantiates and caches singleton telemetry sink via `create_telemetry_sink()` | None (inspects `_telemetry_sink`) | `TelemetrySinkProtocol` / sink instance | Propagates factory errors; creates fresh if global cleared | `cuk_assistant/ui/app.py:37-43` |
| 3 | Session & Timeline | `on_chat_start` | Generates `session_id = f"sess_{uuid.uuid4().hex}"`, sets `active_slots = {}`, and sends greeting message with 4 starter prompt recommendation chips | None (triggered by `@cl.on_chat_start`) | `cl.Message` with 4 `starter_prompt` `cl.Action` chips | Throws if session state or message send fails | `cuk_assistant/ui/app.py:52-93` |
| 4 | Interactive Prompting | `on_starter_prompt` | Removes clicked chip, emits the prompt as a user `cl.Message`, and calls `process_query` | `action: cl.Action` | Action removed, user message sent, query streamed | Throws if action removal or query execution fails | `cuk_assistant/ui/app.py:94-101` |
| 5 | Slot Disambiguation | `on_slot_selected` | Handles `fill_slot` chips; updates `active_slots[target_slot] = action.value` in `cl.user_session`, echoes user choice, and triggers `process_query(last_query, updated_slots)` | `action: cl.Action` with `payload={"target_slot": ...}` | Chip removed, choice echoed, orchestrator rerun with updated slots | If payload or target_slot missing, active_slots unchanged; proceeds with last_query | `cuk_assistant/ui/app.py:102-117`, `docs/api_contracts.md:936-987` |
| 6 | Feedback & Observability | `on_feedback_upvote` | Handles `feedback_upvote` button; logs score=1, category="helpful" with `trace_id` to telemetry sink, acknowledges feedback, and removes button | `action: cl.Action` (`value=trace_id`) | Telemetry recorded, confirmation message sent, action removed | Checked via `hasattr(sink, "record_feedback")`; no crash if sink lacks method | `cuk_assistant/ui/app.py:118-127` |
| 7 | Feedback & Observability | `on_feedback_downvote` | Handles `feedback_downvote` button; logs score=-1, category="unhelpful" with `trace_id` to telemetry sink, acknowledges feedback, and removes button | `action: cl.Action` (`value=trace_id`) | Telemetry recorded, confirmation message sent, action removed | Checked via `hasattr(sink, "record_feedback")`; no crash if sink lacks method | `cuk_assistant/ui/app.py:128-137` |
| 8 | Chat Dispatch | `on_message` | Receives incoming chat message; strips whitespace, guards against blank queries, stores `last_query`, and invokes `process_query` | `message: cl.Message` | Calls `process_query` with active slots if non-empty | Early return on empty or whitespace-only messages | `cuk_assistant/ui/app.py:138-148` |
| 9 | Streaming & Synthesis | `process_query` Token Stream | Streams incremental text chunks from `orchestrator.stream_turn` to user UI via `msg.stream_token` | `query: str`, `updated_slots: dict \| None` | Real-time token streaming in active `cl.Message` | Supports both `"token"` and `"text"` keys in event payload | `cuk_assistant/ui/app.py:172-175` |
| 10 | Slot Disambiguation | `process_query` Slot Actions | Parses `slot_prompt` event, creates `cl.Action(name="fill_slot", ...)` with target_slot payload, and attaches to message (suppressing feedback buttons) | Event: `{"type": "slot_prompt", "target_slot": ..., "options": [...]}` | `msg.actions` populated with interactive disambiguation chips | Uses fallbacks if option `label` or `description` omitted | `cuk_assistant/ui/app.py:176-191, 232-234` |
| 11 | Grounding & Citations | `process_query` Citation Cards | Parses `citation_card` event, creates `cl.Text(display="side")` with markdown snippet or rendered table | Event: `{"type": "citation_card", ...}` | `msg.elements` attached with side-panel inspection cards | Handles table vs text formatting; applies 32-char title truncation | `cuk_assistant/ui/app.py:193-222, 228-230`, `docs/api_contracts.md:991-1040` |
| 12 | Observability & Finalization | `process_query` Done & Trace Binding | Parses `done` event, extracts `trace_id`, and attaches thumbs up/down feedback buttons to message when no slots are pending | Event: `{"type": "done", "trace_id": ...}` | `msg.actions` populated with upvote/downvote buttons; `msg.update()` sent | Falls back to generated UUID if trace_id missing | `cuk_assistant/ui/app.py:224-226, 235-253` |
| 13 | Serving & CLI | `run` CLI Entrypoint | CLI entrypoint (`cuk-ui`); checks if chainlit is installed; if missing, exits code 1 with remediation; if present, runs subprocess with host/port | Environment variables `CHAINLIT_PORT`, `CHAINLIT_HOST` | Launches `chainlit run` subprocess | Catches `KeyboardInterrupt` cleanly on user exit | `cuk_assistant/ui/app.py:263-298` |
| 14 | Architecture & Resilience | Chainlit Import Decoupling | Try/except pattern around chainlit import allows safe module import even in headless test environments | Python environment imports | `cl` object or `None` | Prevents runtime crash when chainlit is not installed | `cuk_assistant/ui/app.py:49-50, 254-256` |

---

## 3. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `on_message` Blank String | `message.content = "   \t\n  "` | Returns immediately; no query sent to orchestrator, no message dispatched, `last_query` remains unchanged. |
| 2 | `on_slot_selected` Empty Payload | `action.payload = None` or `{}` | `target_slot` evaluates to None; `active_slots` remains unmodified; queries orchestrator with `last_query`. |
| 3 | `on_slot_selected` Missing `last_query` | `cl.user_session.get("last_query")` is None | Falls back gracefully to `str(action.value)` as the query passed to `process_query`. |
| 4 | `on_feedback_upvote/downvote` Sink without method | `sink = object()` (no `record_feedback`) | Guarded by `hasattr(sink, "record_feedback")`; does not raise `AttributeError`; thank you message is still sent and action is removed. |
| 5 | `process_query` Event Token Key Fallback | Event `{"type": "token", "text": "chunk"}` (no `"token"` key) | `token = event.get("token", event.get("text", ""))` correctly extracts `"chunk"`. |
| 6 | `process_query` Markdown Table Citation Card | Event with `is_table = True`, `table_markdown = "| H1 | H2 |\n|---|---|\n| V1 | V2 |"` | Formats card content with `### {title} (Page {page})\n**Source:** [{url}]({url})\n\n{table_md}`, preserving native markdown table without quote indents. |
| 7 | `process_query` Text Snippet Citation Card | Event with `is_table = False`, `quoted_snippet = "Snippet quote"` | Formats card content with `**Document:** [{title}]({url})\n\n**Page:** {page} \| **Section:** {heading}\n\n> "{snippet}"`. |
| 8 | `process_query` Long Document Title Truncation | Document title with > 32 characters | Card name truncated to `f"[{idx}] {title[:32]}... (p. {page_number})"`. |
| 9 | `process_query` Missing Citation Fields | Event `{"type": "citation_card"}` with no details | Applies robust defaults: `title="Official University Document"`, `source_url="https://cukashmir.ac.in"`, `page_number=1`, `section_heading="General"`, `quoted_snippet=""`. |
| 10 | `process_query` Slot Prompt Suppresses Feedback | Turn emits both tokens and `slot_prompt` | `msg.actions` is populated solely with `slot_actions`. Feedback upvote/downvote buttons are omitted so incomplete turns cannot be rated. |
| 11 | `process_query` Session ID Generation Fallback | `cl.user_session.get("session_id")` is None | Generates new UUID session ID formatted as `sess_{hex}`. |
| 12 | `run` Missing Chainlit Dependency | `app.cl = None`, `app.run()` | Prints `"ERROR: 'chainlit' is not installed in the environment..."` to `sys.stderr` and terminates via `sys.exit(1)`. |
| 13 | `run` Custom Host & Port | `CHAINLIT_PORT="8005"`, `CHAINLIT_HOST="127.0.0.1"` | Launches `[sys.executable, "-m", "chainlit", "run", ..., "--host", "127.0.0.1", "--port", "8005"]`. |
| 14 | `run` User Termination (SIGINT) | `subprocess.run` raises `KeyboardInterrupt` | Catches exception without stacktrace, logs `"Chainlit server stopped by user."`, and exits cleanly. |

---

## 4. Logic Chain

1. **Observation 1.1**: The project requirements (R7, line 64 and line 83) specify creating `tests/unit/test_chainlit_ui.py` to test the Chainlit web UI (`cuk_assistant/ui/app.py`).
2. **Observation 1.1**: Running `import chainlit` fails with `ModuleNotFoundError` because chainlit is decoupled/optional and not installed in the dev environment.
3. **Observation 1.1 & 1.2**: In `cuk_assistant/ui/app.py`, all core logic is implemented in pure async Python functions:
   - `on_chat_start`, `on_starter_prompt`, `on_slot_selected`, `on_feedback_upvote`, `on_feedback_downvote`, `on_message`, `process_query`, `get_ui_orchestrator`, `get_ui_telemetry_sink`, and `run`.
4. **Verification Step**: Probing in Python verified that by providing a mock `chainlit` module in `sys.modules["chainlit"]` with lightweight mock implementations of `cl.Message`, `cl.Action`, `cl.Text`, and `cl.user_session`, `importlib.reload(app)` cleanly binds all functions.
5. **Deduction**: Unit testing Chainlit event handlers via a clean mock layer provides:
   - 100% deterministic, headless test execution under `pytest` with zero external network or process dependencies.
   - Comprehensive test coverage for all 14 discovered features and 14 edge cases.
   - Exact verification of the interaction contracts defined in `docs/api_contracts.md` Section 5.

---

## 5. Recommended Test Suite Architecture for `tests/unit/test_chainlit_ui.py`

### 5.1 Test Suite Organization (6 Test Classes, 17 Unit Tests)

1. **`TestChainlitSingletons`**:
   - `test_get_ui_orchestrator_initializes_and_caches`: Asserts `create_rag_orchestrator` is called once; second call returns cached singleton.
   - `test_get_ui_telemetry_sink_initializes_and_caches`: Asserts `create_telemetry_sink` is called once; second call returns cached singleton.

2. **`TestChainlitLifecycle`**:
   - `test_on_chat_start`: Verifies session initialization (`session_id` starting with `sess_`, empty `active_slots`), welcome header message, and exactly 4 `starter_prompt` action buttons.
   - `test_on_starter_prompt`: Verifies clicking starter prompt removes action button, echoes user prompt message, and invokes `process_query(action.value)`.

3. **`TestChainlitMessageHandling`**:
   - `test_on_message_ignores_empty_or_whitespace`: Verifies queries with empty strings or whitespace do not trigger `process_query` or alter session state.
   - `test_on_message_dispatches_valid_query`: Verifies query is stripped, `last_query` is stored in session, and `process_query` is invoked with active slots.

4. **`TestChainlitSlotDisambiguation`**:
   - `test_slot_prompt_renders_interactive_actions`: Verifies `slot_prompt` event generates `cl.Action` chips with `name="fill_slot"`, `target_slot` in payload, and suppresses feedback buttons.
   - `test_on_slot_selected_updates_session_and_resumes`: Verifies clicking slot chip removes action, stores `target_slot: value` in `active_slots`, echoes selection, and reruns `process_query` with `last_query` and updated slots.
   - `test_on_slot_selected_missing_payload_graceful`: Verifies that if `action.payload` is None, `active_slots` remains unchanged and execution does not crash.

5. **`TestChainlitCitationsAndStreaming`**:
   - `test_token_streaming_and_turn_completion`: Verifies incremental tokens streamed via `msg.stream_token`, trace ID captured from `done` event, and `msg.update()` awaited.
   - `test_citation_card_text_snippet`: Verifies text citation creates `cl.Text` with `display="side"`, truncated title (32 chars), doc URL, page number, and blockquoted snippet.
   - `test_citation_card_table_markdown`: Verifies table citation creates `cl.Text` with `display="side"`, table header, doc URL, and native markdown table formatting.
   - `test_citation_card_default_fallbacks`: Verifies omitted fields default to `"Official University Document"`, page 1, `"General"`, and `"https://cukashmir.ac.in"`.
   - `test_feedback_actions_attached_when_no_slots`: Verifies completed turn without slot prompts attaches `feedback_upvote` and `feedback_downvote` buttons with `value=turn_trace_id`.

6. **`TestChainlitFeedbackAndCLI`**:
   - `test_feedback_upvote_records_score_1`: Verifies upvote records `score=1`, `category="helpful"`, echoes thank you message, and removes button.
   - `test_feedback_downvote_records_score_minus_1`: Verifies downvote records `score=-1`, `category="unhelpful"`, echoes thank you message, and removes button.
   - `test_feedback_safe_when_sink_lacks_method`: Verifies no error occurs if sink does not have `record_feedback`.
   - `test_run_cli_exits_when_cl_is_none`: Verifies `run()` prints error to stderr and calls `sys.exit(1)` when `cl is None`.
   - `test_run_cli_spawns_subprocess_with_env`: Verifies `run()` invokes `subprocess.run` with `CHAINLIT_PORT` and `CHAINLIT_HOST`.
   - `test_run_cli_handles_keyboard_interrupt`: Verifies `KeyboardInterrupt` is caught and handled gracefully without raising.

---

## 6. Caveats

- **Caveat 1**: `chainlit` is not currently in `pyproject.toml` dependencies. The test suite must provide its own lightweight in-memory `cl` mock harness so tests run reliably in CI and offline environments without network access.
- **Caveat 2**: When testing `run()` with `cl is None`, `sys.exit` must be patched with `side_effect=SystemExit(1)` (or `pytest.raises(SystemExit)`) so execution stops at the exit call rather than proceeding to `subprocess.run`.

---

## 7. Conclusion

All functional behaviors, event callbacks, interaction contracts, and error paths in `cuk_assistant/ui/app.py` and `docs/api_contracts.md` have been discovered, probed, and documented. The 6-class, 17-test specification outlined above is ready for immediate implementation in `tests/unit/test_chainlit_ui.py` to satisfy the Phase 5 Gate requirement.

---

## 8. Verification Method

To verify the discovered behaviors and execute the unit test suite once implemented:

```bash
# 1. Run the targeted Phase 5 unit test suite including test_chainlit_ui.py:
uv run pytest tests/unit/test_chainlit_ui.py -v

# 2. Run the complete Phase 5 Gate command per ORIGINAL_REQUEST.md:
uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q

# 3. Check code style and formatting:
uv run ruff check cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py
```
