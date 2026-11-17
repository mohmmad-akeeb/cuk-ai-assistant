# Task Assignment: Explorer 1 (Milestone M5 - Iteration 2)

## Mission
Analyze Challenger 1 and Challenger 2 reports and recommend exact line-by-line fix strategy for `cuk_assistant/ui/app.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Challenger findings:
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/handoff.md`
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md`

## Scope of Analysis
Formulate exact remediation for `cuk_assistant/ui/app.py`:
1. Citation card sanitization (`title=None`, `page_number=None`, `source_url=None`, `quoted_snippet=None`).
2. Slot prompt options: support both dicts (`{"value": ..., "label": ...}`) and strings (`"B.Tech CSE"`), and handle `options=None`.
3. Safe token extraction: handle `token=None` with text fallback.
4. Action payload & active slots defensive handling in `on_slot_selected` (non-dict payloads, None active_slots).
5. Exception handling & `error` event presentation in `process_query` with try/except/finally and user-visible error tokens.
6. Preserve valid trace ID when done event has `trace_id=None`.
7. Default port: default `CHAINLIT_PORT` to `"8001"`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your report to `.agents/teamwork/explorer_m5_it2_1/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:12:43Z
You are assigned as App Remediation Explorer for Milestone M5 Iteration 2.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Challenger findings at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/handoff.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md`.
Formulate exact remediation for cuk_assistant/ui/app.py.
Do NOT modify code files directly.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_1/handoff.md` and notify orchestrator via send_message.
