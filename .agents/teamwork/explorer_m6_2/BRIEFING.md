# BRIEFING — 2026-11-16T19:04:00Z

## Mission
Investigate and design specifications for Milestone M6 Containerization (Multi-stage CPU Dockerfile, docker-compose.yml) & Makefile targets.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, analyzer, spec designer
- Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
- State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_2/
- Original parent: efda6041-f6a1-4119-b860-77559828c316
- Milestone: M6

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Multi-stage CPU Dockerfile with Python 3.12, ONNX runtime, FastEmbed model cache (`BAAI/bge-small-en-v1.5`), `uv`.
- Security best practices (non-root user, lean layers, `.dockerignore`).
- docker-compose.yml for FastAPI (port 8000) and Chainlit (port 8001), shared volumes, health checks, env mappings.
- Makefile targets: ingest, chat, ui, eval, test, lint.
- Follow protected paths rules (no reading raw data/pdfs, secrets, caches).

## Current Parent
- Conversation ID: efda6041-f6a1-4119-b860-77559828c316
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `pyproject.toml`, `uv.lock`, `.env.example`, `PROJECT.md`, `Makefile`
  - `cuk_assistant/core/config.py`, `cuk_assistant/core/factory.py`
  - `cuk_assistant/api/main.py`, `cuk_assistant/api/routes/health.py`, `cuk_assistant/api/routes/chat.py`
  - `cuk_assistant/ui/app.py`, `tests/unit/test_chainlit_ui.py`
  - `cuk_assistant/ingestion/cli/ingest.py`, `cuk_assistant/ingestion/cli/index.py`
  - `cuk_assistant/evals/cli.py`, `scripts/interactive_chat.py`, `scripts/run_ingest.py`
  - `cuk_assistant/retrieval/fastembed_adapter.py`, `cuk_assistant/retrieval/flashrank_reranker.py`
  - `cuk_assistant/agent/session_store.py`
- **Key findings**:
  - Multi-stage CPU Dockerfile needs `python:3.12-slim-bookworm` with `uv` copied from `ghcr.io/astral-sh/uv:0.5.26`.
  - FastEmbed ONNX model (`BAAI/bge-small-en-v1.5`) and FlashRank (`ms-marco-TinyBERT-L-2-v2`) must be pre-warmed at build time in `/opt/model_cache/fastembed` via `FASTEMBED_CACHE_PATH`.
  - Non-root user `appuser:10001` with `appgroup:10001` ensures enterprise container security.
  - Shared volume `cuk_data:/app/data` is critical: both FastAPI and Chainlit connect to `data/lancedb/` and `data/sessions.db` in SQLite WAL mode.
  - `docker-compose.yml` mounts `cuk_data`, maps ports 8000 (FastAPI) and 8001 (Chainlit), checks `/health` on 8000 with `depends_on: { api: { condition: service_healthy } }`.
  - `Makefile` targets: `ingest` (`cuk-ingest && cuk-index`), `chat` (`interactive_chat.py`), `ui` (`chainlit run cuk_assistant/ui/app.py`), `eval` (`cuk-eval run`), `test` (`pytest`), `lint` (`ruff check & format check`).
  - Unit tests (651 passed), live hybrid search tests (7 passed), and regression evals (56.4% Hit Rate@5, 0.448 MRR) all verified passing.
- **Unexplored areas**: None. All Milestone M6 containerization and Makefile targets investigated and specified.

## Key Decisions Made
- Generated complete production blueprints in `handoff.md` with verbatim Dockerfile, .dockerignore, docker-compose.yml, and Makefile.
- Flagged requirement for implementer to add `chainlit>=1.3.0` to `pyproject.toml`.

## Artifact Index
- handoff.md — Comprehensive blueprint for M6 containerization & Makefile
- progress.md — Liveness heartbeat & task tracking
- DISPATCH.md — Received instructions log
