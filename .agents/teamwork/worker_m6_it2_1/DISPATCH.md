## 2026-11-16T19:37:07Z
You are worker_m6_it2_1 (Implementation Worker for Milestone M6 Iteration 2 Remediation).

Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
Your state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m6_it2_1/
You must create and maintain progress.md and handoff.md in your state folder.

Read the authoritative specifications and explorer blueprints:
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m6_2/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_1/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_3/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Protected Paths Invariant (Strict Non-Negotiable):
Never read, list, search, open, edit, copy, or summarize contents from:
- data/cache/, data/logs/, data/raw/pdf/, data/processed/, and any *.pdf files
- .env, .env.* (except .env.example)

Tasks to implement (strictly following explorer blueprints):
1. **Chainlit Dependency (explorer_m6_it2_1 blueprint)**:
   - Run `uv add chainlit` to register `chainlit` in `pyproject.toml` and lock in `uv.lock`.
   - Verify `uv run chainlit --help` and `make ui` work.
2. **FlashRank Cache & Factory Overrides (explorer_m6_it2_2 blueprint)**:
   - In `cuk_assistant/retrieval/flashrank_reranker.py`, resolve `cache_dir`:
     Check passed `cache_dir` or `kwargs.pop("cache_dir", None)`, then `os.environ.get("FLASHRANK_CACHE_PATH")` or `os.environ.get("FLASHRANK_CACHE_DIR")`, then check `Path("/opt/model_cache/flashrank").is_dir()`, else fallback to `/tmp`.
   - In `cuk_assistant/core/factory.py`:
     * `create_vector_store`: check `os.environ.get("LANCEDB_DIR")` if `db_path` not explicitly passed.
     * `create_reranker`: check `os.environ.get("FLASHRANK_CACHE_PATH")` or `Path("/opt/model_cache/flashrank").is_dir()`.
     * `create_session_store`: check `os.environ.get("SQLITE_DB_PATH")` if `db_path` is None.
   - In `cuk_assistant/retrieval/lancedb_store.py`: allow `db_path: str | Path | None = None` and check `os.environ.get("LANCEDB_DIR")`.
   - In `cuk_assistant/agent/session_store.py`: allow `db_path: Path | str | None = None` and check `os.environ.get("SQLITE_DB_PATH")`.
   - Add unit tests in `tests/unit/test_flashrank_reranker.py` and `tests/unit/test_factory_and_orchestrator.py` per blueprint.
3. **Container Stack & CLI Display Polish (explorer_m6_it2_3 blueprint)**:
   - In `Dockerfile`: export `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank` in Stage 1 and Stage 2 runtime ENV.
   - In `docker-compose.yml`:
     * Remove unsupported `--headless` flag from `ui` service command.
     * Add `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank` to `api` and `ui` environment sections.
   - In `cuk_assistant/evals/cli.py:171`: fix float hit count calculation using `sum(1 for r in summary.results if r.hit_at_k) if summary.results else round(...)`.
   - In `docs/project_status.md`: update operational deliverables checklist with genuine verification details, and add Section 5 ("Milestone M6 Iteration 2: Reviewer Remediation Matrix").

Verification Commands to run and document in handoff.md:
- `uv run ruff check cuk_assistant/ scripts/ tests/`
- `uv run ruff format --check cuk_assistant/ scripts/ tests/`
- `uv run pytest tests/unit/ -q`
- `uv run pytest tests/integration/ -v`
- `uv run cuk-eval run --top-k 5 --strict`
- `make help`
- `make lint`

Write your complete report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m6_it2_1/handoff.md` and notify the orchestrator via send_message.
