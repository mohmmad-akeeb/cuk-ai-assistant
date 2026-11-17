# Task Assignment: Explorer 2 (Milestone M5 - Iteration 2)

## Mission
Analyze Challenger 1 and Challenger 2 reports and design test extensions and teardown module cleanup for `tests/unit/test_chainlit_ui.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_2/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Challenger findings:
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/handoff.md`
- `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md`

## Scope of Analysis
Design test additions for `tests/unit/test_chainlit_ui.py`:
1. Tests for citation cards with `title=None`, `page_number=None`.
2. Tests for slot prompts with string-list options `["B.Tech", "MCA"]` and `options=None`.
3. Tests for `token=None` with text fallback.
4. Tests for non-dict payloads in `on_slot_selected`.
5. Tests for stream exceptions and `error` events in `process_query`.
6. Tests for `done` event with `trace_id=None`.
7. Tests asserting port default is `"8001"`.
8. Design `teardown_module()` in `test_chainlit_ui.py` to reload `cuk_assistant.ui.app` so `app.cl` is restored to `None`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your report to `.agents/teamwork/explorer_m5_it2_2/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:12:48Z
You are assigned as Test Extension Explorer for Milestone M5 Iteration 2.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_2/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read Challenger findings at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_1/handoff.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md`.
Design test additions for tests/unit/test_chainlit_ui.py to cover all edge cases, and teardown restoration.
Do NOT modify code files directly.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it2_2/handoff.md` and notify orchestrator via send_message.
