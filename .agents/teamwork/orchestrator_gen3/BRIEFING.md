# BRIEFING — 2026-11-16T20:22:00Z

## Mission
Command an autonomous team of specialized subagents to construct the production-ready Central University of Kashmir (CUK) RAG Assistant (`cuk-assistant`) from end to end (Phases 0-6 complete, 100% verified, production deliverables ready).

## 🔒 My Identity
- Archetype: teamwork_orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen3/
- Original parent: parent
- Original parent conversation ID: b31a41c9-27db-4edc-8653-4616e119ce57

## 🔒 My Workflow
- **Pattern**: Project Pattern (Top-level Project Orchestrator)
- **Scope document**: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
1. **Decompose**: Survey existing codebase and documentation via parallel Explorers/Spec Miners, create PROJECT.md with architecture, feature inventory, milestones, and interface contracts.
2. **Dispatch & Execute**:
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
  0. Survey & Architecture Specification [DONE]
  1. Phase 1: Ingestion Lakehouse, Two-Tier Reconciliation & Delta Sync [DONE - 124 passed]
  2. Phase 2: Document Parsing, OCR & Layout-Aware Hierarchical Chunking [DONE - 42 passed]
  3. Phase 3: Hybrid LanceDB Storage, FastEmbed & FlashRank Reranker [DONE - 32 passed]
  4. Phase 4: Free-Tier LLM Pool, Multi-Layer Guardrails & Citation Verifier [DONE - 107 passed]
  5. Phase 5: Multi-Turn Memory, Pipeline Assembly & Serving Interfaces [DONE - 53 UI tests pass, Phase 5 Gate 135 tests pass]
  6. Phase 6: Observability, Evals, Containerization & Final Sign-Off [DONE - Gate passed with 5/5 approvals/clean audit, 673 tests pass, 56.4% Hit Rate@5, 0.448 MRR]
- **Current phase**: 6 (Completed)
- **Current focus**: Final Human Reporting and Handoff

## 🔒 Key Constraints
- DISPATCH-ONLY: NEVER write, modify, or create source code files directly.
- NEVER run build/test commands yourself — require workers to do so.
- NEVER investigate or explore the problem at the code level — dispatch Explorers for technical investigation.
- File-editing tools allowed ONLY for metadata/state files (.md) in .agents/teamwork/ (and PROJECT.md / ORIGINAL_REQUEST.md).
- Protected paths: Never read, edit, delete, or inspect data/cache/, data/logs/, data/raw/pdf/, data/processed/, or *.pdf files.
- $0 / Local-First Compute Rule & Free-tier multi-provider pool.
- Strict Verbatim Grounding: Zero hallucination, programmatic citation verification.
- Audit enforcement: Forensic auditor binary veto. If audit reports INTEGRITY VIOLATION, milestone fails unconditionally.
- Never reuse a subagent after it has delivered its handoff — always spawn fresh.

## Current Parent
- Conversation ID: b31a41c9-27db-4edc-8653-4616e119ce57
- Updated: 2026-11-16T20:01:28Z

## Key Decisions Made
- Resumed after reboot as orchestrator_gen3.
- All prior phases (Phases 0-5) are complete and verified.
- Milestone M6 Iteration 2 executed: `worker_m6_it2_2` remediated all 5 items.
- Full verification swarm completed with unanimous approvals and clean audit:
  - `reviewer_m6_it2_1`: APPROVE
  - `reviewer_m6_it2_2`: APPROVE
  - `challenger_m6_it2_1`: APPROVE
  - `challenger_m6_it2_2`: APPROVE
  - `auditor_m6_it2_1`: CLEAN
- Gate Result: PASS. Project is 100% complete.

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| worker_m6_it2_2 | teamwork_worker | M6 It 2 Remediation & Verification | completed | 07df0007-1da3-4c2b-9d59-b4488185fdbf |
| reviewer_m6_it2_1 | teamwork_reviewer | M6 It 2 Code Review | completed | 1fb63a74-e4ac-409d-8f6c-98f4842cbceb |
| reviewer_m6_it2_2 | teamwork_reviewer | M6 It 2 Operations Review | completed | 64832f18-4ae4-4eff-a3f9-e000407717fe |
| challenger_m6_it2_1 | teamwork_challenger | M6 It 2 Benchmark & Regression | completed | a24305ff-8a44-4c5d-881b-e60164531240 |
| challenger_m6_it2_2 | teamwork_challenger | M6 It 2 Concurrency & Ops | completed | 9337f0df-80f0-4d32-99d9-56dbd6ca33f7 |
| auditor_m6_it2_1 | teamwork_auditor | M6 It 2 Forensic Audit | completed | 03075f1d-b8e8-40b8-948b-cea935c1c2b5 |

## Succession Status
- Succession required: no
- Spawn count: 6 / 16
- Pending subagents: none
- Predecessor: 8a6b0147-15e0-4f29-9851-c4ea1605a26e
- Successor spawned: not yet spawned
- Successor generation: none
- Successor state folder: none

## Active Timers
- Heartbeat cron: none (cancelled)
- Safety timer: none (cancelled)

## Artifact Index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md — Global architecture and milestone index
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md — Original verbatim user request
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen3/GATE_STATUS.md — Gate tracking log
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen3/progress.md — Progress tracker
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/orchestrator_gen3/handoff.md — Final orchestrator handoff report
