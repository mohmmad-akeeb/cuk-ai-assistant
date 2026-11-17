# Task Assignment: Challenger 2 (Milestone M5)

## Mission
Adversarially probe boundary conditions, thread/async concurrency safety, and CLI error handling for `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Inspect `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.

## Adversarial Tasks
- Probe concurrent session handling in UI mocks.
- Verify CLI environment edge cases (missing variables, non-integer port, signals).
- Confirm test suites execute with complete determinism under repeated runs.
- Provide empirical confirmation: `APPROVE` or `REQUEST_CHANGES`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your report with verdict to `.agents/teamwork/challenger_m5_2/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:04:00Z
You are assigned as Challenger 2 for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Inspect `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.
Adversarially probe concurrency safety, CLI execution under extreme args, test determinism.
Formulate your verdict (APPROVE or REQUEST_CHANGES).
Write your report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md` and notify orchestrator via send_message.
