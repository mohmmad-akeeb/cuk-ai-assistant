# BRIEFING — 2026-11-16T19:37:30Z

## Mission
Orchestrate the end-to-end implementation of the production-ready Central University of Kashmir (CUK) RAG Assistant (`cuk-assistant`) across 6 development phases and verification gates (M5 complete, executing M6 Iteration 2 to 100% completion and final project sign-off).

## 🔒 My Identity
- Archetype: teamwork_orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen2/
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
  6. Phase 6: Observability, Evals, Containerization & Final Sign-Off [IN_PROGRESS - Iteration 2 Worker executing remediation]
- **Current phase**: 6 (Observability, Evals, Containerization & Final Sign-Off)
- **Current focus**: Milestone M6 Iteration 2 Worker Implementation (`worker_m6_it2_1`)

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
- Updated: 2026-11-16T19:07:53Z

## Key Decisions Made
- Milestone M5 verified and marked DONE.
- M6 Iteration 1 Gate: `reviewer_m6_2` requested changes.
- Dispatched 3 Explorers in Iteration 2 (`explorer_m6_it2_1`, `explorer_m6_it2_2`, `explorer_m6_it2_3`); all delivered complete blueprints.
- Dispatched `worker_m6_it2_1` (`525e8da8-a835-4cdc-a81c-543abce99acf`) to execute all remediation tasks.

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| worker_m6_1 | teamwork_worker | M6 It 1: Implementation | completed | 5481e978-bbc9-40c4-8410-3ae008e0f21c |
| reviewer_m6_1 | teamwork_reviewer | M6 It 1: Code Review | completed | 0c53a10d-9d5c-45d0-820b-23e9fc88efd5 |
| reviewer_m6_2 | teamwork_reviewer | M6 It 1: Operations Review | completed | f434a60e-b235-4f23-89e5-533713ca5e03 |
| challenger_m6_1 | teamwork_challenger | M6 It 1: Regression Probes | completed | 84f52154-650e-4577-9de4-4ddaa59bc802 |
| challenger_m6_2 | teamwork_challenger | M6 It 1: Ops Probes | completed | bb4ee388-8229-4b21-b0c9-0264f7624a0b |
| auditor_m6_1 | teamwork_auditor | M6 It 1: Forensic Audit | completed | 87983a4f-b360-4644-b693-c6e986398cc1 |
| explorer_m6_it2_1 | teamwork_explorer | M6 It 2: Dependency Explorer | completed | d019d6ec-4749-4ed3-ac2b-2d56cf1d8232 |
| explorer_m6_it2_2 | teamwork_explorer | M6 It 2: Cache & Factory Explorer | completed | 8b2f99b1-535f-4bc0-9fd2-2fadc15bedb8 |
| explorer_m6_it2_3 | teamwork_explorer | M6 It 2: Container & CLI Explorer | completed | be77bd01-e6f1-4ae2-8118-810db8790bd0 |
| worker_m6_it2_1 | teamwork_worker | M6 It 2: Remediation Worker | in-progress | 525e8da8-a835-4cdc-a81c-543abce99acf |

## Succession Status
- Succession required: no
- Spawn count: 10 / 16
- Pending subagents: 525e8da8-a835-4cdc-a81c-543abce99acf
- Predecessor: efda6041-f6a1-4119-b860-77559828c316
- Successor spawned: not yet spawned
- Successor generation: none
- Successor state folder: none

## Active Timers
- Heartbeat cron: 8a6b0147-15e0-4f29-9851-c4ea1605a26e/task-35
- Safety timer: 8a6b0147-15e0-4f29-9851-c4ea1605a26e/task-73
- On succession: kill all timers before spawning successor
- On context truncation: handle timers as step 4 of the State Recovery section of your prompt says

## Artifact Index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md — Global architecture and milestone index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md — Original verbatim user request
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen2/GATE_STATUS.md — Gate tracking log
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen2/progress.md — Progress tracker
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_1/handoff.md — It 2 Dependency blueprint
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/handoff.md — It 2 Cache & Factory blueprint
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_3/handoff.md — It 2 Container & CLI blueprint
