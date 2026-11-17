## 2026-11-16T19:09:31Z

You are the implementation Worker for Milestone M6 (Observability, Evals, Containerization & Final Sign-Off) of the Central University of Kashmir RAG Assistant project.

Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
Your state folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m6_1/
You must create and maintain progress.md and handoff.md in your state folder.

Read the following authoritative specification files FIRST before starting work:
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_1/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_2/handoff.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_3/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Protected Paths Invariant (Strict Non-Negotiable):
Never read, list, search, open, edit, copy, or summarize contents from:
- data/cache/, data/logs/, data/raw/pdf/, data/processed/, and any *.pdf files
- .env, .env.* (except .env.example)

Tasks to implement (strictly following the explorer handoff blueprints):
1. **Schema Consolidation (explorer_m6_1 blueprint C)**:
   - Create `cuk_assistant/schemas/chat.py` with pure Pydantic v2 data models (`ChatRequest`, `ChatResponse`, `CitationCard`, `FeedbackRequest`, `TurnResult`).
   - Re-export in `cuk_assistant/schemas/__init__.py`.
   - Update `cuk_assistant/api/routes/chat.py` to import `ChatRequest`, `ChatResponse`, `FeedbackRequest` from `cuk_assistant.schemas.chat` (keeping `__all__`).
   - Update `cuk_assistant/pipeline/orchestrator.py` to import `CitationCard`, `TurnResult` from `cuk_assistant.schemas.chat` (keeping `__all__`).
2. **Query Mining CLI & Menu Hierarchy (explorer_m6_1 blueprint B)**:
   - In `cuk_assistant/evals/cli.py`, change default output of `mine-queries` command to `Path("configs/menu_hierarchy.json")`.
   - Run `uv run cuk-eval mine-queries --output configs/menu_hierarchy.json` to generate the file.
3. **Automated Regression Suite (explorer_m6_1 blueprint A & explorer_m6_3 blueprint 4.2)**:
   - Create `tests/integration/test_golden_regression.py` validating that Hit Rate@5 >= 0.50 and MRR >= 0.40 over `evals/golden_dataset.jsonl`, testing diagnostic failure codes attribution.
4. **Containerization & Deployment Stack (explorer_m6_2 blueprints 4.1, 4.2, 4.3)**:
   - Create `Dockerfile`: Multi-stage CPU, Python 3.12-slim-bookworm, uv binary from official image, pre-warmed FastEmbed (`BAAI/bge-small-en-v1.5`) & FlashRank (`ms-marco-TinyBERT-L-2-v2`) in `/opt/model_cache`, non-root user `appuser:10001` in group `appgroup:10001`, exposed ports 8000 and 8001, healthcheck against `/health`.
   - Create `.dockerignore`: Strictly shielding git, agent teamwork metadata, venvs, caches, data/cache, data/raw, data/logs, data/processed, data/lancedb, data/sessions.db*, *.pdf, credentials.
   - Create `docker-compose.yml`: Services `api` (FastAPI on 8000) and `ui` (Chainlit on 8001), shared `cuk_data` volume, active healthchecks, environment variables with fallbacks.
5. **Makefile Hardening (explorer_m6_2 blueprint 4.4)**:
   - Update `Makefile` with all required targets: `install`, `crawl`, `nodes`, `ingest`, `chat`, `ui`, `eval`, `test`, `test-unit`, `test-network`, `lint`, `fmt`, `fmt-check`, `docker-build`, `docker-up`, `docker-down`, `docker-logs`, `help`.
6. **Project Status Tracker (explorer_m6_3 blueprint 4.1)**:
   - Update `docs/project_status.md` to reflect 100% completion across all phases, updating all checklist items to `[x]`, adding verification gate results matrix, and operational sign-off.

Verification Commands to run and document in handoff.md:
- `uv run pytest tests/integration/test_golden_regression.py -v`
- `uv run pytest tests/integration/ -v`
- `uv run pytest tests/unit/ -q`
- `uv run ruff check cuk_assistant/ scripts/ tests/`
- `uv run cuk-eval run --top-k 5`
- `make help`

Write your complete report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/worker_m6_1/handoff.md` and message the orchestrator when finished.
