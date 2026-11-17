# BRIEFING — 2026-11-16T19:35:00Z

## Mission
Analyze Model Caching & Factory Overrides: FlashRankReranker cache_dir resolution and factory environment variable overrides (LANCEDB_DIR, SQLITE_DB_PATH). Produce blueprint for Worker.

## 🔒 My Identity
- Archetype: explorer
- Roles: read-only investigator, blueprint synthesizer
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2
- Original parent: 8a6b0147-15e0-4f29-9851-c4ea1605a26e
- Milestone: M6 Iteration 2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Protected paths: never read data/cache/, data/logs/, data/raw/pdf/, data/processed/, *.pdf files, .env, .env.* (except .env.example)
- Deliver findings via handoff.md and send_message

## Current Parent
- Conversation ID: 8a6b0147-15e0-4f29-9851-c4ea1605a26e
- Updated: 2026-11-16T19:35:00Z

## Investigation State
- **Explored paths**:
  - `cuk_assistant/retrieval/flashrank_reranker.py`
  - `cuk_assistant/core/factory.py`
  - `cuk_assistant/retrieval/lancedb_store.py`
  - `cuk_assistant/agent/session_store.py`
  - `Dockerfile`
  - `docker-compose.yml`
  - `tests/unit/test_flashrank_reranker.py`
  - `tests/unit/test_factory_and_orchestrator.py`
- **Key findings**:
  - `FlashRankReranker` defaults to `/tmp` and ignores pre-warmed weights in `/opt/model_cache/flashrank`. Upstream `flashrank.Ranker` has no internal env var support, so it must be handled in the adapter.
  - `Dockerfile` and `docker-compose.yml` set `LANCEDB_DIR` and `SQLITE_DB_PATH` but lack `FLASHRANK_CACHE_PATH`.
  - Factory functions `create_vector_store` and `create_session_store` defaulted to hardcoded paths and ignored `LANCEDB_DIR` and `SQLITE_DB_PATH`.
  - Full precedence chain formulated and verified for FlashRank cache: explicit param -> `FLASHRANK_CACHE_PATH` -> `FLASHRANK_CACHE_DIR` -> `/opt/model_cache/flashrank` -> `/tmp`.
  - Factory and store overrides formulated for `LANCEDB_DIR` and `SQLITE_DB_PATH`.
- **Unexplored areas**: None. Complete blueprint ready for Worker.

## Key Decisions Made
- Formulated exact diffs and resolution logic across `flashrank_reranker.py`, `factory.py`, `lancedb_store.py`, `session_store.py`, `Dockerfile`, `docker-compose.yml`, and unit tests.

## Artifact Index
- DISPATCH.md — Dispatch history
- BRIEFING.md — Persistent context & state
- progress.md — Liveness heartbeat
- handoff.md — Final handoff report
