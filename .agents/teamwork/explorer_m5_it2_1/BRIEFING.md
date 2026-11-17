# BRIEFING — 2026-11-16T18:18:00Z

## Mission
Analyze Challenger 1 and Challenger 2 findings and formulate exact remediation plan for `cuk_assistant/ui/app.py`.

## 🔒 My Identity
- Archetype: explorer
- Roles: App Remediation Explorer
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/
- Original parent: 30963065-bb08-41aa-acec-725022359cce
- Milestone: Milestone M5 (Iteration 2)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement / modify source code directly
- Strict Sandbox: NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files
- Output report to `.agents/teamwork/explorer_m5_it2_1/handoff.md` and notify orchestrator via `send_message`

## Current Parent
- Conversation ID: 30963065-bb08-41aa-acec-725022359cce
- Updated: 2026-11-16T18:18:00Z

## Investigation State
- **Explored paths**:
  - `cuk_assistant/ui/app.py` (lines 1-300)
  - `tests/unit/test_chainlit_ui.py` (lines 1-613)
  - `.agents/teamwork/challenger_m5_1/handoff.md`
  - `.agents/teamwork/challenger_m5_2/handoff.md`
  - `PROJECT.md`, `ORIGINAL_REQUEST.md`, `docs/api_contracts.md`, `cuk_assistant/pipeline/orchestrator.py`, `cuk_assistant/api/routes/chat.py`
- **Key findings**:
  - Confirmed and reproduced all 7 core defects in `cuk_assistant/ui/app.py` plus Challenger 2 CLI robustness defects:
    1. `title=None`, `page_number=None`, `source_url=None`, `quoted_snippet=None` crashes citation card rendering with `TypeError`.
    2. `options` containing strings or `options=None` crashes slot prompt chip rendering with `AttributeError` or `TypeError`.
    3. `token=None` with text fallback evaluates to `None` and calls `stream_token(None)`, causing `TypeError`.
    4. Non-dict `action.payload` and `active_slots=None` crash `on_slot_selected` with `AttributeError` / `TypeError`.
    5. Missing `try...except...finally` and missing `error` event handler leaves UI message hanging and renders empty response with feedback chips.
    6. `done` event with `trace_id=None` overwrites generated trace ID with `None`, breaking telemetry.
    7. Default port in `app.run()` is `"8000"`, conflicting with FastAPI on port 8000; should default to `"8001"`, with CLI argument sanitization and `CalledProcessError` handling.
  - Successfully verified in-memory simulation of proposed remediation for all 7 areas + CLI robustness.
- **Unexplored areas**: None. Full line-by-line strategy completed.

## Key Decisions Made
- Formulate complete replacement code and exact line-by-line diffs for `cuk_assistant/ui/app.py`.
- Document accompanying fixes for `tests/unit/test_chainlit_ui.py` (port 8001 assertion, teardown module reload, contextvars mock session, new adversarial tests).

## Artifact Index
- `.agents/teamwork/explorer_m5_it2_1/handoff.md` — Complete App Remediation Report and Line-by-Line Blueprint
