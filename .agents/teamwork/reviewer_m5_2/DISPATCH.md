# Task Assignment: Reviewer 2 (Milestone M5)

## Mission
Independently review `tests/unit/test_chainlit_ui.py` for edge cases, async robustness, test pollution, and full regression status.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m5_2/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Inspect `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.
Read worker handoff: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_1/handoff.md`.

## Verification Tasks
- Run Phase 5 Gate: `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q`.
- Check if importing `cuk_assistant.ui.app` outside the test leaves any leaked mock state.
- Run `uv run pytest tests/unit/ -q` to verify zero regressions.
- Formulate your independent verdict: `APPROVE` or `REQUEST_CHANGES`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your review report with verdict to `.agents/teamwork/reviewer_m5_2/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:03:51Z
You are assigned as Reviewer 2 for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m5_2/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Read worker handoff at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_1/handoff.md`.
Run Phase 5 Gate test and regression checks.
Formulate your verdict (APPROVE or REQUEST_CHANGES).
Write your report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m5_2/handoff.md` and notify orchestrator via send_message.
