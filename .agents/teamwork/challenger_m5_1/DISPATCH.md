# Task Assignment: Challenger 1 (Milestone M5)

## Mission
Empirically stress-test and adversarially challenge `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Inspect `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.

## Adversarial Tasks
- Test abnormal inputs, unusual event sequences (e.g. rapid token streaming, malformed citation payloads, duplicate slot clicks, invalid action payloads).
- Verify that `test_chainlit_ui.py` cannot falsely pass on broken logic (mutation test checks).
- Provide empirical confirmation: `APPROVE` or `REQUEST_CHANGES`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your report with verdict to `.agents/teamwork/challenger_m5_1/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:03:56Z
You are assigned as Challenger 1 for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Inspect `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.
Adversarially probe edge cases, unusual event streams, mutation coverage.
Formulate your verdict (APPROVE or REQUEST_CHANGES).
Write your report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/handoff.md` and notify orchestrator via send_message.
