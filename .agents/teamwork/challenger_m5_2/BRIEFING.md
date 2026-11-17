# BRIEFING — 2026-11-16T18:12:00Z

## Mission
Adversarially probe concurrency safety, CLI execution under extreme args, and test determinism for tests/unit/test_chainlit_ui.py and cuk_assistant/ui/app.py.

## 🔒 My Identity
- Archetype: EMPIRICAL CHALLENGER
- Roles: critic, specialist
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2
- Original parent: 30963065-bb08-41aa-acec-725022359cce
- Milestone: M5
- Instance: 2 of 2

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Protected paths: Never read, edit, delete, or inspect files under: data/cache/, data/logs/, data/raw/pdf/, data/processed/, or any *.pdf files.
- .agents/teamwork/ holds only agent metadata. Never place source code or tests there.
- Empirical rigor: write and execute tests. If cannot reproduce empirically, does not count.

## Current Parent
- Conversation ID: 30963065-bb08-41aa-acec-725022359cce
- Updated: not yet

## Review Scope
- **Files to review**: tests/unit/test_chainlit_ui.py, cuk_assistant/ui/app.py
- **Interface contracts**: PROJECT.md, docs/api_contracts.md, R7/Survey
- **Review criteria**: Concurrency safety, CLI execution under extreme args, test determinism, boundary conditions

## Attack Surface
- **Hypotheses tested**:
  1. Concurrency isolation in MockUserSession and MockMessage under concurrent tasks
  2. Module-level pollution and teardown leaks from test_chainlit_ui.py to app.cl
  3. UI error handling when stream_turn yields error events or raises exceptions
  4. CLI robustness under empty/invalid environment variables and subprocess errors
  5. Test suite determinism under 50 serial iterations and shuffled permutations
- **Vulnerabilities found**:
  1. `teardown_module()` in `test_chainlit_ui.py` fails to reload `app`, leaving `app.cl` permanently pointed to mock
  2. `MockUserSession` lacks task/context isolation, resulting in cross-session state clobbering
  3. `process_query` in `app.py` drops `{"type": "error"}` events and lacks exception handling during streaming
  4. `CHAINLIT_PORT=""` passes empty port `--port ""` and crashes on `CalledProcessError`
- **Untested angles**: Full end-to-end WebSocket networking with browser client (Chainlit package not installed in environment)

## Loaded Skills
- **Source**: /home/mihawk/.gemini/config/skills/test-automator/SKILL.md
- **Local copy**: None (system prompt skill)
- **Core methodology**: Rigorous empirical test automation, stress harnesses, concurrency and boundary testing

## Key Decisions Made
- Executed empirical reproducers for concurrency, teardown leakage, CLI argument edge cases, and test shuffle determinism.
- Formulated verdict: REQUEST_CHANGES based on 4 confirmed empirical findings.

## Artifact Index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m5_2/handoff.md — Final verdict and empirical challenge report
