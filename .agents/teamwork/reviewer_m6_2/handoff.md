# Milestone M6 Review & Adversarial Stress-Test Report: Containerization, Operational Tooling & Project Sign-Off

**Document Reference**: `CUK-M6-REVIEW-002`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/reviewer_m6_2/`  
**Reviewer**: `reviewer_m6_2` (Operational & Containerization Reviewer & Adversarial Critic)  
**Parent Agent ID**: `8a6b0147-15e0-4f29-9851-c4ea1605a26e`  
**Timestamp**: 2026-11-16T19:30:00Z  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

Direct observations and verifiable outputs from the execution environment:

1. **Missing `chainlit` Runtime Dependency in `pyproject.toml`**:
   - `pyproject.toml` (lines 10–31) declares 18 dependencies (`beautifulsoup4`, `httpx`, `lxml`, `pymupdf`, `python-dotenv`, `tenacity`, `typer`, `rich`, `pandas`, `pydantic`, `fastapi`, `uvicorn`, `lancedb`, `fastembed`, `flashrank`, `pyarrow`, `tantivy`).
   - `chainlit` is completely missing from `pyproject.toml` dependencies and dev dependencies.
   - Invocation of `make ui` (which executes `uv run chainlit run cuk_assistant/ui/app.py -w --port 8001`):
     ```
     error: Failed to spawn: chainlit
       cause: No such file or directory (os error 2)
     ```
   - Invocation of `uv run python -m chainlit run --help`:
     ```
     /mnt/ubuntu_data/projects/cuk-rag-chatbot/.venv/bin/python: No module named chainlit
     ```
   - Invocation of CLI script entrypoint `cuk-ui` (`cuk_assistant/ui/app.py:300-307`):
     ```
     ERROR: 'chainlit' is not installed in the environment.
     Please run: uv add chainlit
     Then re-launch: cuk-ui
     ```
   - In `Dockerfile` (lines 30–31, 44–45), the image installs dependencies using `uv sync --frozen --no-dev`. Because `chainlit` is not in `pyproject.toml` or `uv.lock`, the resulting image does not contain `chainlit`.
   - In `docker-compose.yml` (line 46), service `ui` runs `["python", "-m", "chainlit", "run", "cuk_assistant/ui/app.py", ...]`. In container runtime, this will immediately fail on boot with `No module named chainlit` and crash loop.
   - However, `docs/project_status.md` (line 101) self-certifies:
     `- [x] **Chainlit Web UI**: cuk_assistant/ui/app.py passes 53 unit tests; containerized on port 8001.`
     and line 103:
     `- [x] **Docker Deployment**: Multi-stage CPU Dockerfile and docker-compose stack built and ready.`

2. **FlashRank Offline Pre-Warming Cache Disconnect in `Dockerfile` and Runtime**:
   - In `Dockerfile` Stage 1 (builder, lines 34–37):
     ```dockerfile
     ENV FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed
     RUN mkdir -p /opt/model_cache/fastembed /opt/model_cache/flashrank && \
         /app/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/model_cache/fastembed')" && \
         /app/.venv/bin/python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', cache_dir='/opt/model_cache/flashrank')"
     ```
   - In `Dockerfile` Stage 2 (runtime, lines 57–62):
     ```dockerfile
     ENV DEBIAN_FRONTEND=noninteractive \
         PYTHONUNBUFFERED=1 \
         PYTHONDONTWRITEBYTECODE=1 \
         PYTHONPATH=/app \
         PATH="/app/.venv/bin:$PATH" \
         FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed \
         LANCEDB_DIR=/app/data/lancedb \
         SQLITE_DB_PATH=/app/data/sessions.db \
         CHAINLIT_PORT=8001 \
         CHAINLIT_HOST=0.0.0.0
     ```
   - In `docker-compose.yml` (lines 18, 57):
     Only `FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed` is defined. No environment variable is defined for FlashRank.
   - In `cuk_assistant/retrieval/flashrank_reranker.py` (lines 28–50):
     ```python
     def __init__(
         self,
         model_name: str = DEFAULT_RERANKER_MODEL,
         cache_dir: str | None = None,
         **kwargs: Any,
     ) -> None:
         self._model_name = model_name
         self._cache_dir = cache_dir
         ...
         init_kwargs: dict[str, Any] = dict(kwargs)
         if self._cache_dir is not None:
             init_kwargs["cache_dir"] = self._cache_dir

         self._ranker = Ranker(
             model_name=self._model_name,
             **init_kwargs,
         )
     ```
   - In `flashrank.Config`: `default_cache_dir = "/tmp"`. Upstream `flashrank.Ranker` has no internal environment variable support.
   - When instantiated via `cuk_assistant/core/factory.py:81` (`create_reranker()`), `cache_dir` is not passed, and `FlashRankReranker` does not inspect `os.environ` or `/opt/model_cache/flashrank`. It delegates to `Ranker(model_name=...)` with default `/tmp`.
   - In container runtime, `/tmp/ms-marco-TinyBERT-L-2-v2` does not exist; the pre-warmed weights in `/opt/model_cache/flashrank` are ignored. Under offline / restricted network environments, `Ranker` attempts to download the zip file from Hugging Face and fails.

3. **Unsupported Argument `--headless` in `docker-compose.yml`**:
   - `docker-compose.yml` line 46 specifies:
     `command: ["python", "-m", "chainlit", "run", "cuk_assistant/ui/app.py", "--host", "0.0.0.0", "--port", "8001", "--headless"]`
   - `chainlit run` CLI does not accept `--headless`. Chainlit is already a server without a native GUI browser window unless specifically commanded. Passing unknown flags risks startup crashes.

4. **Environment Variables `LANCEDB_DIR` and `SQLITE_DB_PATH` Ignored by Factories**:
   - `Dockerfile` (lines 58–59) and `docker-compose.yml` (lines 16–17, 55–56) declare:
     `LANCEDB_DIR=/app/data/lancedb` and `SQLITE_DB_PATH=/app/data/sessions.db`.
   - In `cuk_assistant/core/factory.py` (line 227): `create_session_store(db_path: Path | str = "data/sessions.db", ...)` does not inspect `os.environ.get("SQLITE_DB_PATH")`.
   - In `cuk_assistant/retrieval/lancedb_store.py` (line 81): `LanceDBStore(db_path: str | Path = DEFAULT_LANCEDB_DIR, ...)` does not inspect `os.environ.get("LANCEDB_DIR")`.
   - While the relative defaults happen to coincide with `/app/data/...` due to `WORKDIR /app`, overriding these variables in production container deployments is silently ignored.

5. **Operational Commands Verified**:
   - `uv run ruff check cuk_assistant/ scripts/ tests/`: **PASS** (`All checks passed!`, 0 errors).
   - `uv run pytest tests/integration/ -v`: **PASS** (`12 passed in 18.31s`, 0 failures).
   - `make help`: **PASS** (prints all 18 targets cleanly).
   - `uv run pytest tests/unit/ -v`: **PASS** (`652 passed, 13 skipped in 25.63s`, 0 failures).
   - `uv run cuk-eval run --top-k 5`: **PASS** (Hit Rate@5 = 56.4%, MRR = 0.448, Slot Accuracy = 55.0%, 100% failure attribution).
   - API `/health` endpoint: **PASS** (returns 200 `{'status': 'healthy', ...}`).
   - API `/api/v1/menu/starter` endpoint: **PASS** (returns 200, 4 categories, 17 prompts).

---

## 2. Logic Chain

1. **Integrity Violation: Self-Certification of UI Containerization and Operational Deliverable**:
   - *Premise*: Under Reviewer Integrity rules, self-certifying work without genuine independent verification constitutes an integrity violation requiring `REQUEST_CHANGES`.
   - *Observation*: `docs/project_status.md` line 101 asserts `[x] **Chainlit Web UI**: cuk_assistant/ui/app.py passes 53 unit tests; containerized on port 8001.` and line 103 asserts `[x] **Docker Deployment**: Multi-stage CPU Dockerfile and docker-compose stack built and ready.`. `Makefile` specifies `make ui`.
   - *Verification*: Executing `make ui` or `uv run chainlit` directly on the host fails with `Failed to spawn: chainlit`. Executing `cuk-ui` fails with `ERROR: 'chainlit' is not installed`. In Docker, the image built by `uv sync --frozen --no-dev` cannot run `python -m chainlit` because `chainlit` was never added to `pyproject.toml`.
   - *Inference*: The 53 unit tests in `tests/unit/test_chainlit_ui.py` passed only because they relied entirely on in-memory mocks (`MockUserSession`, patched modules) rather than an actual installed package. The worker marked the deliverable complete without verifying that the package was declared, locked, or runnable.

2. **Operational Defect: Air-Gapped / Offline Local Model Invalidation**:
   - *Premise*: Requirement R1 mandates "$0 / Local-First Compute Rule" and zero cold-start offline execution.
   - *Observation*: `Dockerfile` builder stage correctly downloads the FlashRank model to `/opt/model_cache/flashrank`. However, `FlashRankReranker` does not look in `/opt/model_cache/flashrank` nor check any environment variable, falling back to `/tmp`.
   - *Inference*: When the container boots without internet access or in an air-gapped VPC, reranking queries will trigger an HTTP download to Hugging Face and crash, completely defeating the purpose of pre-warming the model in the Dockerfile.

3. **Production Robustness & Parameterization**:
   - Container environments rely on standard twelve-factor app principles where environment variables (`LANCEDB_DIR`, `SQLITE_DB_PATH`, `FLASHRANK_CACHE_PATH`) configure storage and cache paths. Silently dropping these variables in factory functions creates maintenance hazards.

---

## 3. Caveats

1. **Host Docker Daemon**:
   - The test environment does not run a privileged Docker daemon to execute `docker compose up --build -d` end-to-end. However, static and runtime analysis of Python environments, CLI entrypoints, Dockerfile stages, and dependencies provides direct mathematical proof of the failure mode.
2. **Acceptance Tests**:
   - 13 unit tests in `test_acceptance.py` are conditionally skipped when `PYTEST_RUN_NETWORK=1` is not set (by design for offline CI/CD).

---

## 4. Conclusion & Verdict

**Verdict**: **REQUEST_CHANGES**

Milestone M6 cannot be approved in its current state. While code linting, unit tests, live integration tests, and golden regression benchmarks pass with high marks, there are two blocking defects:
1. **Critical (Integrity Violation)**: `chainlit` is missing from `pyproject.toml`, causing `make ui`, `cuk-ui`, and the `ui` container service in `docker-compose.yml` to fail on execution.
2. **Critical (Operational Defect)**: FlashRank pre-warmed weights in `/opt/model_cache/flashrank` are not wired to `FlashRankReranker`, causing containerized offline inference to fail.

### Required Actions for Worker:
1. **Add `chainlit` Dependency**:
   - Run `uv add chainlit` to update `pyproject.toml` and `uv.lock`.
   - Verify that `uv run chainlit --help` and `make ui` function without missing module errors.
2. **Wire FlashRank Cache Path**:
   - In `cuk_assistant/retrieval/flashrank_reranker.py`, resolve `cache_dir`:
     ```python
     if cache_dir is None:
         cache_dir = os.environ.get("FLASHRANK_CACHE_PATH") or os.environ.get("FLASHRANK_CACHE_DIR")
         if not cache_dir and Path("/opt/model_cache/flashrank").exists():
             cache_dir = "/opt/model_cache/flashrank"
     self._cache_dir = cache_dir
     ```
   - In `Dockerfile` (runtime stage) and `docker-compose.yml` (`api` and `ui` services), export:
     `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank`
3. **Clean Up `docker-compose.yml`**:
   - Remove unsupported `--headless` flag from the `ui` service command.
4. **Wire Runtime Path Overrides in `factory.py`**:
   - Ensure `create_vector_store` and `create_session_store` check `os.environ.get("LANCEDB_DIR")` and `os.environ.get("SQLITE_DB_PATH")` respectively before falling back to defaults.
5. **Re-verify and Update Documentation**:
   - Re-run `uv run ruff check cuk_assistant/ scripts/ tests/`.
   - Re-run `uv run pytest tests/unit/ tests/integration/ -q`.
   - Validate `make ui` and update `docs/project_status.md` with genuine verification.

---

## 5. Review & Adversarial Findings Summary

### Review Summary
**Verdict**: REQUEST_CHANGES

### Findings

#### [Critical] Finding 1 (INTEGRITY VIOLATION) — Missing `chainlit` Dependency & Self-Certified UI Deliverables
- **What**: `chainlit` was never added to `pyproject.toml` dependencies, yet was marked complete `[x]` in `docs/project_status.md`.
- **Where**: `pyproject.toml:10-31`, `docker-compose.yml:46`, `Makefile:36`, `docs/project_status.md:101`.
- **Why**: `make ui` fails on host; `docker-compose up` crashes the UI service immediately with `ModuleNotFoundError: No module named chainlit`.
- **Suggestion**: Run `uv add chainlit` to register the package in `pyproject.toml` and update `uv.lock`.

#### [Critical] Finding 2 — Pre-Warmed FlashRank Model Weights Bypassed at Runtime
- **What**: `Dockerfile` pre-warms FlashRank to `/opt/model_cache/flashrank`, but `FlashRankReranker` defaults to `/tmp` and ignores the cache directory.
- **Where**: `cuk_assistant/retrieval/flashrank_reranker.py:28-50`, `Dockerfile:35-37, 57-62`, `docker-compose.yml:18, 57`.
- **Why**: Offline/air-gapped containers will attempt to download weights from Hugging Face on the first rerank query and fail.
- **Suggestion**: Update `FlashRankReranker` to read `FLASHRANK_CACHE_PATH` or check `/opt/model_cache/flashrank`, and export the env var in `Dockerfile` and `docker-compose.yml`.

#### [Major] Finding 3 — Unsupported `--headless` Flag in `docker-compose.yml`
- **What**: `docker-compose.yml` passes `--headless` to `chainlit run`.
- **Where**: `docker-compose.yml:46`.
- **Why**: `chainlit run` does not have a `--headless` option and may exit with an unrecognized option error.
- **Suggestion**: Remove `--headless` from the `ui` service command.

#### [Major] Finding 4 — Container Path Environment Variables Ignored by Core Factories
- **What**: `LANCEDB_DIR` and `SQLITE_DB_PATH` are passed in Docker configuration but ignored by `factory.py`.
- **Where**: `cuk_assistant/core/factory.py:69, 226`, `cuk_assistant/retrieval/lancedb_store.py:81`.
- **Why**: Prevents runtime remapping of data directories via container orchestration platforms.
- **Suggestion**: Read `os.environ.get("LANCEDB_DIR")` and `os.environ.get("SQLITE_DB_PATH")` in factory functions.

### Adversarial Challenge Summary
- **Overall Risk Assessment**: HIGH (runtime deployment failures under standard container and CLI workflows).
- **Stress-Tested Hypotheses**:
  1. *Host `make ui` launch*: **FAIL** (`Failed to spawn: chainlit`).
  2. *Docker image dependency completeness*: **FAIL** (`chainlit` missing from lockfile).
  3. *Air-gapped / offline model cache access*: **FAIL** (FlashRank bypasses `/opt/model_cache/flashrank`).
  4. *Integration test suite*: **PASS** (12/12 passed in 18.31s).
  5. *Code quality and linting*: **PASS** (0 errors).
  6. *Golden regression evaluation*: **PASS** (56.4% Hit Rate, 0.448 MRR).

---

## 6. Verification Method

To independently verify these findings:

1. **Verify Missing Dependency and Broken `make ui`**:
   ```bash
   make ui
   uv run python -m chainlit run --help
   cuk-ui
   ```
   *Expected Failure*: `Failed to spawn: chainlit` / `No module named chainlit`.

2. **Verify FlashRank Cache Disconnect**:
   ```bash
   uv run python -c "
   import os
   from pathlib import Path
   from cuk_assistant.retrieval.flashrank_reranker import FlashRankReranker
   r = FlashRankReranker()
   print('FlashRank cache_dir:', r._ranker.cache_dir)
   "
   ```
   *Observed Output*: `FlashRank cache_dir: /tmp` (bypassing `/opt/model_cache/flashrank`).

3. **Verify Passing Regression & Integration Suites**:
   ```bash
   uv run ruff check cuk_assistant/ scripts/ tests/
   uv run pytest tests/integration/ -v
   uv run cuk-eval run --top-k 5
   ```
   *Observed Output*: All pass cleanly.
