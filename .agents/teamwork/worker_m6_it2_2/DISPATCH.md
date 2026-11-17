## 2026-11-16T20:02:59Z
You are worker_m6_it2_2, a specialized implementation and remediation engineer for the CUK RAG Assistant project.

Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
Your state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m6_it2_2/
Original request file: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md
Scope document: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context:
In Phase 6 Iteration 1, 4/5 gate checks passed, but reviewer_m6_2 requested changes on 5 operational items. Three parallel explorers analyzed the requirements and generated comprehensive blueprints:
- Explorer 1 report: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_1/handoff.md` (Chainlit dependency & pyproject.toml — already completed and locked)
- Explorer 2 report: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/handoff.md` (FlashRank cache hierarchy & factory env overrides)
- Explorer 3 report: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_3/handoff.md` (Docker compose, Dockerfile, CLI hit count formatting, docs/project_status.md)

Previous worker `worker_m6_it2_1` already completed Task 1:
- `chainlit>=2.12.0` is present in `pyproject.toml` and locked in `uv.lock`.

Your Mission:
Complete Task 2 and Task 3 precisely following Explorer 2 and Explorer 3 blueprints, then run the full verification test suite.

Task 2: FlashRank Cache Hierarchy & Factory Environment Overrides (see Explorer 2 handoff)
1. In `cuk_assistant/retrieval/flashrank_reranker.py`:
   - Implement the cache resolution hierarchy in `FlashRankReranker.__init__`:
     explicit `cache_dir` parameter -> `os.environ.get("FLASHRANK_CACHE_PATH")` -> `os.environ.get("FLASHRANK_CACHE_DIR")` -> `Path("/opt/model_cache/flashrank").is_dir()` -> fallback to `"/tmp"`.
2. In `cuk_assistant/core/factory.py`:
   - `create_vector_store`: If `db_path` is not provided in kwargs, inspect `os.environ.get("LANCEDB_DIR")`.
   - `create_reranker`: If `cache_dir` is not provided in kwargs, inspect `os.environ.get("FLASHRANK_CACHE_PATH")` or `FLASHRANK_CACHE_DIR` or `/opt/model_cache/flashrank`.
   - `create_session_store`: When `db_path` is None, inspect `os.environ.get("SQLITE_DB_PATH")` before defaulting to `"data/sessions.db"`.
3. In `cuk_assistant/retrieval/lancedb_store.py`:
   - In `LanceDBStore.__init__`, if `db_path is None`, inspect `os.environ.get("LANCEDB_DIR")` before fallback to `DEFAULT_LANCEDB_DIR`.
4. In `cuk_assistant/agent/session_store.py`:
   - In `SQLiteSessionStore.__init__`, if `db_path is None`, inspect `os.environ.get("SQLITE_DB_PATH")` before fallback to `"data/sessions.db"`.
5. Add unit tests:
   - In `tests/unit/test_flashrank_reranker.py`: test cache resolution precedence (explicit, env var, /opt/model_cache fallback, /tmp fallback).
   - In `tests/unit/test_factory_and_orchestrator.py`: test `LANCEDB_DIR` and `SQLITE_DB_PATH` env var overrides and explicit overrides.

Task 3: Container Stack, CLI Display Polish & Documentation (see Explorer 3 handoff)
1. In `docker-compose.yml`:
   - Under `api.environment`, add `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank`.
   - Under `ui.command`, remove `--headless` so command is `["python", "-m", "chainlit", "run", "cuk_assistant/ui/app.py", "--host", "0.0.0.0", "--port", "8001"]`.
   - Under `ui.environment`, add `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank`.
2. In `Dockerfile`:
   - Stage 1 builder: export `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank` alongside `FASTEBED_CACHE_PATH`.
   - Stage 2 runtime: export `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank` in `ENV`.
3. In `cuk_assistant/evals/cli.py`:
   - Fix hit count display in `evaluate_qa_benchmark` so it calculates `hit_count = sum(1 for r in summary.results if r.hit_at_k) if summary.results else round(summary.hit_rate_at_k * summary.total_cases)` to avoid IEEE float truncation (31/55 instead of 30/55).
4. In `docs/project_status.md`:
   - Update Section 4 checklist with concrete verified commands.
   - Append Section 5 "Milestone M6 Iteration 2: Reviewer Remediation Matrix" documenting findings CUK-M6-F1 through CUK-M6-F5.

Verification Requirements:
1. Run `uv run ruff check cuk_assistant/ scripts/ tests/` (must pass with 0 errors).
2. Run `uv run pytest tests/unit/ -q` (all unit tests must pass).
3. Run `uv run pytest tests/integration/ -q` (all integration tests must pass).
4. Run `uv run cuk-eval run --top-k 5` (verify Hit Rate@5 >= 0.50, MRR >= 0.40, and exact "31 / 55 queries hit" display).
5. Run `docker compose config --quiet` (or check YAML syntax).
6. Run `make lint`, `make test`, `make eval` to ensure all standard targets work.
