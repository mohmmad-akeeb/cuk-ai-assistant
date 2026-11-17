# BRIEFING — 2026-11-16T18:30:00Z

## Mission
Orchestrate the end-to-end implementation of the production-ready Central University of Kashmir (CUK) RAG Assistant (`cuk-assistant`) across 6 development phases and verification gates.

## 🔒 My Identity
- Archetype: teamwork_orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator/
- Original parent: parent
- Original parent conversation ID: b31a41c9-27db-4edc-8653-4616e119ce57

## 🔒 My Workflow
- **Pattern**: Project Pattern (Top-level Project Orchestrator)
- **Scope document**: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
1. **Decompose**: Survey existing codebase and documentation via parallel Explorers/Spec Miners, create PROJECT.md with architecture, feature inventory, milestones, and interface contracts.
2. **Dispatch & Execute**:
   - **Delegate (sub-orchestrator)**: For large milestones, spawn dedicated sub-orchestrators.
   - **Direct (iteration loop)**: For milestones executed at this level, run Explorer(3) -> Worker(1) -> Reviewer(2) -> Challenger(2) -> Forensic Auditor(1) -> Gate.
   - Dual track: Implementation Track + E2E Testing Track.
3. **On failure** (in this order):
   - Retry: nudge stuck agent or re-send task
   - Replace: spawn fresh agent with partial progress
   - Skip: proceed without (only if non-critical; auditor is NEVER skippable)
   - Redistribute: split stuck agent's remaining work
   - Redesign: re-partition decomposition
   - Escalate: top-level orchestrator cannot escalate to parent for technical redesign; redesigns internally.
4. **Succession**: Self-succeed at 16 cumulative sub-agent spawns when all subagents complete.
- **Work items**:
  0. Survey & Architecture Specification [DONE - PROJECT.md generated]
  1. Phase 1: Ingestion Lakehouse, Two-Tier Reconciliation & Delta Sync [DONE - 124 passed]
  2. Phase 2: Document Parsing, OCR & Layout-Aware Hierarchical Chunking [DONE - 42 passed]
  3. Phase 3: Hybrid LanceDB Storage, FastEmbed & FlashRank Reranker [DONE - 32 passed]
  4. Phase 4: Free-Tier LLM Pool, Multi-Layer Guardrails & Citation Verifier [DONE - 107 passed]
  5. Phase 5: Multi-Turn Memory, Pipeline Assembly & Serving Interfaces [DONE on worker - awaiting Gen 1 gate]
  6. Phase 6: Observability, Evals, Containerization & Final Sign-Off [PLANNED for Gen 1]
- **Current phase**: 5 (Serving Interfaces & Chainlit UI Tests)
- **Current focus**: Succession complete - Gen 1 successor spawned to verify M5 and execute M6.

## 🔒 Key Constraints
- DISPATCH-ONLY: NEVER write, modify, or create source code files directly.
- NEVER run build/test commands yourself — require workers to do so.
- NEVER investigate or explore the problem at the code level — dispatch Explorers for technical investigation.
- File-editing tools allowed ONLY for metadata/state files (.md) in .agents/teamwork/ (and PROJECT.md / ORIGINAL_REQUEST.md).
- Protected paths: Never read, edit, delete, or inspect `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or `*.pdf` files.
- $0 / Local-First Compute Rule & Free-tier multi-provider pool.
- Strict Verbatim Grounding: Zero hallucination, programmatic citation verification.
- Audit enforcement: Forensic auditor binary veto. If audit reports INTEGRITY VIOLATION, milestone fails unconditionally.
- Never reuse a subagent after it has delivered its handoff — always spawn fresh.

## Current Parent
- Conversation ID: b31a41c9-27db-4edc-8653-4616e119ce57
- Updated: not yet

## Key Decisions Made
- PROJECT.md fully established with all 30 features and 6 milestones mapped.
- Milestone M5 Iteration 2 remediation completed and verified by worker_m5_it2_1 (42 UI tests pass, Phase 5 gate passes 124 tests, 0 lint errors, 640 unit tests pass).
- Cumulative spawn threshold (16/16) reached; self-succession executed.

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| spec_miner_survey_1 | teamwork_spec_miner | Phase 0: Survey specifications in docs/ | completed | 60dc7af8-51e2-4237-8575-b0428f56ae02 |
| explorer_survey_2 | teamwork_explorer | Phase 0: Survey existing codebase state | completed | 85820747-401b-48d8-825c-1e2cf0309fc4 |
| explorer_survey_3 | teamwork_explorer | Phase 0: Survey tests and verification gates | completed | 8f9ea639-ca36-4574-a331-886623c14df6 |
| spec_miner_m5_1 | teamwork_spec_miner | M5: Spec mining on app.py and contracts | completed | d8ac08cb-f05f-4c1b-b33f-eb2470060817 |
| explorer_m5_2 | teamwork_explorer | M5: Mock architecture for test_chainlit_ui | completed | b7e81470-d926-4f78-bfa1-4f7c7ca6ebd5 |
| explorer_m5_3 | teamwork_explorer | M5: Test harness and integration alignment | completed | f30d14d5-4e42-4019-9086-d85380ffede3 |
| worker_m5_1 | teamwork_worker | M5: Implement tests/unit/test_chainlit_ui.py | completed | 8aa9ac3a-f6e3-4232-a0e5-51c926cd49c1 |
| reviewer_m5_1 | teamwork_reviewer | M5: Independent code review and gate test | completed | 48c33339-d024-4394-85e7-bc3dbd1cb903 |
| reviewer_m5_2 | teamwork_reviewer | M5: Regression & edge case review | completed | f8a2a54c-af64-4e29-850b-d4713721bd9c |
| challenger_m5_1 | teamwork_challenger | M5: Adversarial edge cases and mutations | completed | d6125112-e990-4103-9597-473fcfe9777b |
| challenger_m5_2 | teamwork_challenger | M5: Concurrency and CLI robustness | completed | 670305a6-e986-48ea-af59-905bd7a1b069 |
| auditor_m5_1 | teamwork_auditor | M5: Forensic integrity audit | completed | a3ae7212-9a56-4a6e-8556-02566ac3badf |
| explorer_m5_it2_1 | teamwork_explorer | M5 It 2: App remediation planning | completed | 585e6291-20e5-4fdf-aa84-b5bd55ad2487 |
| explorer_m5_it2_2 | teamwork_explorer | M5 It 2: Test extension planning | completed | f4685960-e29c-4aa6-aa5d-8a73cf30817a |
| explorer_m5_it2_3 | teamwork_explorer | M5 It 2: Regression guard analysis | completed | a0feff7f-397f-4392-bbc3-a6f88520cb89 |
| worker_m5_it2_1 | teamwork_worker | M5 It 2: Implement app.py & test fixes | completed | e903d9c7-7b60-4b3e-bfe8-841edba6b0a4 |
| orchestrator_gen1 | self | Successor Generation 1 | in-progress | efda6041-f6a1-4119-b860-77559828c316 |

## Succession Status
- Succession required: yes
- Spawn count: 16 / 16
- Pending subagents: none
- Predecessor: none
- Successor spawned: efda6041-f6a1-4119-b860-77559828c316
- Successor generation: gen1
- Successor state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen1/

## Active Timers
- Heartbeat cron: 30963065-bb08-41aa-acec-725022359cce/task-484
- Safety timer: none
- On succession: kill all timers before spawning successor
- On context truncation: handle timers as step 4 of the State Recovery section of your prompt says

## Artifact Index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md — Global architecture and milestone index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md — Original verbatim user request
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator/GATE_STATUS.md — Gate tracking log
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator/handoff.md — Soft handoff report for Gen 1 successor
