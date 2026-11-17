# Task Assignment: Explorer 2 (Milestone M5 - Mock Architecture)

## Mission
Investigate how `cuk_assistant/ui/app.py` interacts with `chainlit` and design the mock architecture for `tests/unit/test_chainlit_ui.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_2/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.

## Scope of Investigation
- Examine `cuk_assistant/ui/app.py` line by line.
- Check if `chainlit` is installed in `uv run python -c "import chainlit"` or if `sys.modules['chainlit']` mock strategy is needed when running tests in environments where `chainlit` may or may not be installed.
- Propose an airtight unit testing fixture and mocking strategy using `unittest.mock` (`AsyncMock`, `MagicMock`) that allows `test_chainlit_ui.py` to run via `uv run pytest tests/unit/test_chainlit_ui.py -q` in any environment without browser or network dependencies.
- Map out the exact list of unit test functions and assertions.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify code files directly.

## Deliverable
Write your report to `.agents/teamwork/explorer_m5_2/handoff.md` and message the orchestrator when done.

## 2026-11-16T17:49:46Z
You are assigned to investigate mock architecture for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_2/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Working directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`.
State directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_2/`.
Strict sandbox: NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT write or modify source code files.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_2/handoff.md` and message the orchestrator when done.
