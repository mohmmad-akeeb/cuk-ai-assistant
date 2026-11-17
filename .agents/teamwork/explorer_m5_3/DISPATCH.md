# Task Assignment: Explorer 3 (Milestone M5 - Test Harness & Integration Alignment)

## Mission
Investigate existing test patterns in `tests/unit/` to ensure `tests/unit/test_chainlit_ui.py` conforms to pytest configuration, asyncio modes, and verification gate standards.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_3/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.

## Scope of Investigation
- Review `pyproject.toml` pytest configuration.
- Check how async tests are written in `tests/unit/test_api_endpoints.py`, `tests/unit/test_factory_and_orchestrator.py`, and `tests/unit/test_router.py`.
- Formulate the exact test structure and assertions for:
  - Startup initialization (`on_chat_start`) with starter actions
  - Starter prompt click handling (`on_starter_prompt`)
  - Slot selection action (`on_slot_selected`)
  - Feedback thumbs up/down (`on_feedback_upvote`, `on_feedback_downvote`)
  - Message handling with streaming chunks, slot chips, and citation cards (`on_message`, `process_query`)
  - Error and fallback handling when orchestrator encounters errors or diagnostic tags
  - Singleton retrieval (`get_ui_orchestrator`, `get_ui_telemetry_sink`)
- Verify that running the full Phase 5 gate:
  `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q`
  will pass 100% with zero regressions.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify code files directly.

## Deliverable
Write your report to `.agents/teamwork/explorer_m5_3/handoff.md` and message the orchestrator when done.


## 2026-11-16T17:49:51Z
You are assigned to investigate test harness and integration alignment for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_3/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Working directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`.
State directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_3/`.
Strict sandbox: NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify source code files.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_3/handoff.md` and message the orchestrator when done.