# Task Assignment: Specification Miner (Milestone M5)

## Mission
Analyze `cuk_assistant/ui/app.py` and specification contracts in `docs/api_contracts.md` (lines 932-1040) to formulate precise behavioral test specifications for `tests/unit/test_chainlit_ui.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/spec_miner_m5_1/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.

## Scope of Investigation
- Analyze all functions and event handlers in `cuk_assistant/ui/app.py`:
  - `on_chat_start`
  - `on_starter_prompt`
  - `on_slot_selected`
  - `on_feedback_upvote`
  - `on_feedback_downvote`
  - `on_message`
  - `process_query`
  - `get_ui_orchestrator`
  - `get_ui_telemetry_sink`
- Enumerate all behavioral requirements, error handling paths, side-panel citation cards (`cl.Text`), and quick-reply action chips (`cl.Action`).
- Recommend the exact test specification to be implemented in `tests/unit/test_chainlit_ui.py`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify code files directly.

## Deliverable
Write your report to `.agents/teamwork/spec_miner_m5_1/handoff.md` and message the orchestrator when done.

## 2026-11-16T17:49:41Z
You are assigned to explore specifications for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/spec_miner_m5_1/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Working directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`.
State directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/spec_miner_m5_1/`.
Strict sandbox: NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify source code files.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/spec_miner_m5_1/handoff.md` and message the orchestrator when done.
