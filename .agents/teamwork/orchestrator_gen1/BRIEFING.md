# BRIEFING — 2026-11-16T19:07:00Z

## Mission
Orchestrate the end-to-end implementation of the production-ready Central University of Kashmir (CUK) RAG Assistant (`cuk-assistant`) across 6 development phases and verification gates (M5 complete, executing M6 to 100% completion).

## 🔒 My Identity
- Archetype: teamwork_orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen1/
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
  5. Phase 5: Multi-Turn Memory, Pipeline Assembly & Serving Interfaces [DONE - 53 UI tests pass, Phase 5 Gate 135 tests pass, 5/5 approvals]
  6. Phase 6: Observability, Evals, Containerization & Final Sign-Off [IN_PROGRESS - All Explorers complete, ready for Worker implementation in Gen 2]
- **Current phase**: 6 (Observability, Evals, Containerization & Final Sign-Off)
- **Current focus**: Self-succession to Gen 2 (spawn threshold 17/16 reached, all subagents completed)

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
- Updated: 2026-11-16T18:29:44Z

## Key Decisions Made
- Milestone M5 officially complete and signed off (5/5 gate approvals).
- Milestone M6 exploration completed by 3 parallel Explorers:
  - `explorer_m6_1`: Evals & Regression Suite blueprint (`tests/integration/test_golden_regression.py`, `cuk-eval mine-queries` -> `configs/menu_hierarchy.json`, `cuk_assistant/schemas/chat.py` consolidation).
  - `explorer_m6_2`: Containerization blueprint (`Dockerfile`, `.dockerignore`, `docker-compose.yml`, `Makefile`).
  - `explorer_m6_3`: Observability & final sign-off blueprint (`docs/project_status.md` at 100%).
- Spawn threshold reached (17/16), all subagents completed. Self-succession initiated to Gen 2.

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| reviewer_m5_it2_1 | teamwork_reviewer | M5 It 2: Code Review | completed | ceb236ac-6584-4bb5-ab07-ef5223b82b62 |
| reviewer_m5_it2_2 | teamwork_reviewer | M5 It 2: Serving Review | completed | 48c6863d-24d4-49f6-adb0-c9b38c104c83 |
| challenger_m5_it2_1 | teamwork_challenger | M5 It 2: Adversarial UI Probes | completed | b6dafb5e-692d-4d67-88d7-117b6514030c |
| challenger_m5_it2_2 | teamwork_challenger | M5 It 2: Concurrency Probes | completed | e3d55bcf-3dea-43cc-8cec-20eb7b0298f8 |
| auditor_m5_it2_1 | teamwork_auditor | M5 It 2: Forensic Audit | completed | 004e82fa-3b49-4a92-971b-95d2117c20a6 |
| explorer_m5_it3_1 | teamwork_explorer | M5 It 3: Concurrency Analysis | completed | 2df2bbd6-bc47-4fce-a5b1-8e6110e76c85 |
| explorer_m5_it3_2 | teamwork_explorer | M5 It 3: Test Extension Design | completed | f8a84ead-c145-4ed7-b8fc-dcad8afdc939 |
| explorer_m5_it3_3 | teamwork_explorer | M5 It 3: Regression Guard | completed | e00a5cd5-810c-438b-8a49-59113344bc85 |
| worker_m5_it3_1 | teamwork_worker | M5 It 3: CoW Implementation | completed | 5bfbe094-b1b7-4842-8430-503501a92220 |
| reviewer_m5_it3_1 | teamwork_reviewer | M5 It 3: Code Review | completed | f2f5379a-50e8-4eb1-be2b-ddd0b3fc9ccc |
| reviewer_m5_it3_2 | teamwork_reviewer | M5 It 3: Serving Review | completed | ea32bc0c-0d47-4750-9c01-225f1ed219f3 |
| challenger_m5_it3_1 | teamwork_challenger | M5 It 3: Concurrency Probes | completed | f4221041-7928-4034-a87e-d621d19c9fb2 |
| challenger_m5_it3_2 | teamwork_challenger | M5 It 3: Isolation Probes | completed | 60e81ee1-e338-466e-a312-25a4818d337a |
| auditor_m5_it3_1 | teamwork_auditor | M5 It 3: Forensic Audit | completed | c04cff2a-bec2-4d6f-a795-619ffeecd91a |
| explorer_m6_1 | teamwork_explorer | M6: Evals Blueprint | completed | 88da2266-123d-4d96-b597-be772a7b82cd |
| explorer_m6_2 | teamwork_explorer | M6: Docker & Makefile Blueprint | completed | a7ef0812-8915-4484-9453-72a9a65c89db |
| explorer_m6_3 | teamwork_explorer | M6: Observability & Sign-Off Blueprint | completed | d60b9d99-afab-41d6-b85b-c2e1fdffcc9f |

## Succession Status
- Succession required: yes
- Spawn count: 17 / 16
- Pending subagents: none
- Predecessor: 30963065-bb08-41aa-acec-725022359cce
- Successor spawned: 8a6b0147-15e0-4f29-9851-c4ea1605a26e
- Successor generation: gen2
- Successor state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen2/

## Active Timers
- Heartbeat cron: efda6041-f6a1-4119-b860-77559828c316/task-24 (to be killed)
- Safety timer: efda6041-f6a1-4119-b860-77559828c316/task-155 (to be killed)
- On succession: kill all timers before spawning successor
- On context truncation: handle timers as step 4 of the State Recovery section of your prompt says

## Artifact Index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md — Global architecture and milestone index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md — Original verbatim user request
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen1/GATE_STATUS.md — Gate tracking log
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen1/progress.md — Progress tracker
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen1/handoff.md — Soft handoff for Gen 2
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_1/handoff.md — M6 Evals & Schema blueprint
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_2/handoff.md — M6 Docker & Makefile blueprint
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_3/handoff.md — M6 Observability & Sign-Off blueprint
