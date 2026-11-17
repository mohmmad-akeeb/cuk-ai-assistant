## 2026-11-16T19:30:41Z
You are explorer_m6_it2_2 (Model Caching & Factory Overrides Explorer) for Milestone M6 Iteration 2.

Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
Your state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/
You must create and maintain progress.md and handoff.md in your state folder.

Read the authoritative specifications and failure report:
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m6_2/handoff.md

Protected Paths (Strict Non-Negotiable):
Never read, list, search, open, edit, copy, or summarize contents from:
- data/cache/, data/logs/, data/raw/pdf/, data/processed/, and any *.pdf files
- .env, .env.* (except .env.example)

Mission (Read-Only Exploration & Blueprint Formulation):
1. Review `reviewer_m6_2`'s Finding 2: `FlashRankReranker` defaults to `/tmp` and ignores pre-warmed weights in `/opt/model_cache/flashrank`.
   - Inspect `cuk_assistant/retrieval/flashrank_reranker.py`.
   - Formulate the exact logic to resolve `cache_dir`:
     Check passed `cache_dir`, then `os.environ.get("FLASHRANK_CACHE_PATH")`, then `os.environ.get("FLASHRANK_CACHE_DIR")`, then check `Path("/opt/model_cache/flashrank").is_dir()`, else fallback to default `/tmp`.
2. Review `reviewer_m6_2`'s Finding 4: `LANCEDB_DIR` and `SQLITE_DB_PATH` environment variables set in container are ignored by factories.
   - Inspect `cuk_assistant/core/factory.py` (functions `create_vector_store` and `create_session_store`).
   - Formulate exact changes so `create_vector_store` checks `os.environ.get("LANCEDB_DIR")` and `create_session_store` checks `os.environ.get("SQLITE_DB_PATH")`.
3. Provide a clear, actionable blueprint for Worker to execute.

Write your report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/handoff.md` and notify the orchestrator via send_message.
