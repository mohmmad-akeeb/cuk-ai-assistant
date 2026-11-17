## 2026-11-16T18:46:10Z

You are worker_m5_it3_1.
Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_it3_1/

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read:
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_it2_2/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it3_1/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it3_2/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it3_3/handoff.md

Exclusive File Ownership:
You own ONLY:
- `tests/unit/test_chainlit_ui.py`
DO NOT modify `cuk_assistant/ui/app.py` or any other file (Explorers and Reviewers confirmed `app.py` is 100% sound and clean).

Tasks:
1. In `tests/unit/test_chainlit_ui.py`:
   a. Add `import asyncio` in alphabetical order before `import contextvars` (respecting `ruff` I001 sorting).
   b. In `MockUserSession`:
      Update `set` and `clear` to implement Copy-on-Write semantics:
      ```python
      def set(self, key: str, value: Any) -> None:
          store = dict(self._store())
          store[key] = value
          self._var.set(store)

      def clear(self) -> None:
          self._var.set({})
      ```
   c. Add section 10 and test class `TestMockUserSessionIsolation` verifying concurrent tasks (`asyncio.gather`), ContextVar copying (`contextvars.copy_context()`), clear isolation, and child task mutation boundaries (following the detailed designs in `explorer_m5_it3_1` and `explorer_m5_it3_2`).
2. Run comprehensive verification commands:
   - Concurrency isolation probe
   - Teardown isolation probe
   - Target UI test suite
   - Phase 5 Gate (bidirectional)
   - Repo-wide linter
   - Full unit suite
   - Integration suite
3. Write your complete handoff report in `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m5_it3_1/handoff.md`.
4. Send a message to parent with your verification results and completion summary.
