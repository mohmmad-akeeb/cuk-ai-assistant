# Task Assignment: Forensic Auditor (Milestone M5)

## Mission
Conduct comprehensive forensic integrity verification of `tests/unit/test_chainlit_ui.py` and `cuk_assistant/ui/app.py`.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/auditor_m5_1/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md` before starting work.
Inspect `tests/unit/test_chainlit_ui.py` and git history / diffs.

## Integrity Forensics Checks
Verify:
1. Static analysis: Zero hardcoded mock assertions bypassing actual logic.
2. Runtime verification: Tests genuinely exercise `cuk_assistant/ui/app.py` callbacks and logic branches.
3. Zero cheating: No mock tricks that assert True without executing target functions.
4. Binary verdict: `CLEAN` or `INTEGRITY VIOLATION`.

## Strict Sandbox Rule
NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Do NOT modify source code files.

## Deliverable
Write your forensic audit report with binary verdict to `.agents/teamwork/auditor_m5_1/handoff.md` and notify orchestrator via `send_message`.


## 2026-11-16T18:04:05Z
[Message] timestamp=2026-11-16T18:04:05Z sender=30963065-bb08-41aa-acec-725022359cce priority=MESSAGE_PRIORITY_HIGH
You are assigned as Forensic Auditor for Milestone M5: tests/unit/test_chainlit_ui.py.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/auditor_m5_1/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md`.
Inspect `tests/unit/test_chainlit_ui.py` and codebase diffs.
Perform forensic integrity checks: zero hardcoded bypasses, zero facade implementations, authentic test execution.
Formulate binary verdict: CLEAN or INTEGRITY VIOLATION.
Write your forensic audit report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/auditor_m5_1/handoff.md` and notify orchestrator via send_message.
