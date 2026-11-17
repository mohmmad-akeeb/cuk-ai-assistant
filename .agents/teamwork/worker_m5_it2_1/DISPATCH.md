# Task Assignment: Serving and UI Remediation Worker (Milestone M5 - Iteration 2)

## Mission
Apply the verified remediation fixes to `cuk_assistant/ui/app.py` and `tests/unit/test_chainlit_ui.py` based on the Iteration 2 Explorer blueprints.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_it2_1/

## Exclusive File Ownership
You exclusively own:
- `cuk_assistant/ui/app.py`
- `tests/unit/test_chainlit_ui.py`
DO NOT modify any other files.

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Explorer blueprints:
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/handoff.md`
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_2/handoff.md`
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_3/handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Tasks
1. Update `cuk_assistant/ui/app.py`:
   - Sanitize citation card fields: `title = event.get("title") or "Official University Document"`, `source_url = event.get("source_url") or "https://cukashmir.ac.in"`, `page_num = event.get("page_number") or 1`, `snippet = event.get("quoted_snippet") or ""`.
   - Support both dict options (`{"value": ..., "label": ...}`) and plain string options (`"B.Tech CSE"`) in `slot_prompt`, and handle `options=None`.
   - Safely extract token: `token = event.get("token") or event.get("text") or ""`.
   - Defensive action payload & active slots handling in `on_slot_selected` (safely extract `target_slot` and fallback `active_slots = {}` if None).
   - Wrap streaming in `try ... except ... finally`: handle `ev_type == "error"` by streaming `⚠️ *{err_msg}*`, catch exceptions and stream service error message, and ensure `msg.update()` is called in `finally`.
   - Preserve valid trace ID on `done` event: `turn_trace_id = event.get("trace_id") or turn_trace_id`.
   - Update default port to `"8001"` in `app.run()`.
2. Update `tests/unit/test_chainlit_ui.py`:
   - Add test cases covering: `citation_card` with `title=None, page_number=None`, `slot_prompt` with string list options and `options=None`, `token=None` with text fallback, non-dict payloads in `on_slot_selected`, stream exceptions and `error` events, `done` event with `trace_id=None`.
   - Update port default test assertion to `"8001"`.
   - In `teardown_module()`, call `importlib.reload(app)` to ensure `app.cl` is restored to `None`.
3. Verification commands:
   - `uv run pytest tests/unit/test_chainlit_ui.py -v`
   - `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q`
   - `uv run ruff check cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py`
   - `uv run pytest tests/unit/ -q`

## Deliverable
Write your report with execution outputs to `.agents/teamwork/worker_m5_it2_1/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:20:54Z
[Message] timestamp=2026-11-16T18:20:54Z sender=30963065-bb08-41aa-acec-725022359cce priority=MESSAGE_PRIORITY_HIGH content=You are assigned as Serving and UI Remediation Worker for Milestone M5 Iteration 2.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_it2_1/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Explorer blueprints at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/handoff.md`, `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_2/handoff.md`, and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_3/handoff.md`.
Exclusive file ownership: `cuk_assistant/ui/app.py` and `tests/unit/test_chainlit_ui.py`.
MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
Apply the fixes, run all verification tests and ruff check.
Write your completion report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_it2_1/handoff.md` and notify orchestrator via send_message.
