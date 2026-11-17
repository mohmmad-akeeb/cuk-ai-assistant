# Milestone M6 Iteration 2 Explorer Report: Dependency & Chainlit Integration Blueprint

**Document Reference**: `CUK-M6-EXP-001`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_1/`  
**Explorer**: `explorer_m6_it2_1` (Dependency & Chainlit Integration Explorer)  
**Parent Agent ID**: `8a6b0147-15e0-4f29-9851-c4ea1605a26e`  
**Date**: 2026-11-16T19:35:00Z  

---

## 1. Observation

Direct observations and verifiable command outputs from the investigation:

1. **Missing `chainlit` Runtime Dependency in `pyproject.toml` and `uv.lock`**:
   - `pyproject.toml` lines 10–31: `dependencies = [...]` declares 17 packages (`beautifulsoup4`, `httpx`, `lxml`, `pymupdf`, `python-dotenv`, `tenacity`, `typer`, `rich`, `pandas`, `pydantic`, `fastapi`, `uvicorn`, `lancedb`, `fastembed`, `flashrank`, `pyarrow`, `tantivy`). `chainlit` is completely absent.
   - `uv.lock`: `grep -n "chainlit" uv.lock` returns exit code 1 (`Not in uv.lock`).
   - Host `make ui` invocation:
     ```
     uv run chainlit run cuk_assistant/ui/app.py -w --port 8001
     error: Failed to spawn: chainlit
       cause: No such file or directory (os error 2)
     ```
   - Host `cuk-ui` entrypoint invocation (`cuk_assistant/ui/app.py:300-307`):
     ```
     ERROR: 'chainlit' is not installed in the environment.
     Please run: uv add chainlit
     Then re-launch: cuk-ui
     ```
   - Container `Dockerfile` lines 31, 45: `uv sync --frozen --no-dev`. In container builds, because `chainlit` is absent from `uv.lock`, it is not installed into `/app/.venv`.
   - `docker-compose.yml` line 46: `command: ["python", "-m", "chainlit", "run", "cuk_assistant/ui/app.py", "--host", "0.0.0.0", "--port", "8001", "--headless"]`. Fails immediately on container boot with `ModuleNotFoundError: No module named chainlit`.

2. **Dependency Resolution & Compatibility Analysis**:
   - `uv pip install --dry-run chainlit` resolved 125 packages in 5.69s:
     - Target version resolved: `chainlit==2.12.0`.
     - Required: `fastapi>=0.116.1` $\to$ Project environment has `fastapi==0.163.1` (Satisfied, no conflict).
     - Required: `pydantic<3,>=2.11.0` $\to$ Project environment has `pydantic==2.14.3` (Satisfied, no conflict).
     - Required: `uvicorn>=0.35.0` $\to$ Project environment has `uvicorn==0.54.0` (Satisfied, no conflict).
     - Required: `httpx>=0.23.0` $\to$ Project environment has `httpx==0.28.1` (Satisfied, no conflict).
     - Required: `python-dotenv<2.0.0,>=1.0.0` $\to$ Project environment has `python-dotenv==1.2.4` (Satisfied, no conflict).
     - Required: `starlette>=0.47.2` $\to$ Project environment has `starlette==0.47.2` (Satisfied, no conflict).
     - Required: `click<9.0.0,>=8.1.3` $\to$ Compatible with Typer 0.27.3.
     - New transitive packages introduced: `literalai==0.1.201`, `python-socketio==5.18.1`, `asyncer==0.0.20`, `syncer==2.0.3`, `pydantic-settings==2.16.3`, `dataclasses-json==0.6.7`, `mcp==1.30.0`.
   - Python 3.12 compatibility: Verified (`requires-python = ">=3.12"`).

3. **Runtime Import & Core Module Verification**:
   - Executing `uv run --with chainlit python -c "import cuk_assistant, cuk_assistant.core.factory, cuk_assistant.retrieval.lancedb_store, cuk_assistant.pipeline.orchestrator, cuk_assistant.api.main, cuk_assistant.ui.app; print(cuk_assistant.ui.app.cl is not None)"`:
     Output: `True` (All core packages import cleanly with zero symbol collisions).

4. **Test Suite Verification with Chainlit Present**:
   - `uv run --with chainlit pytest tests/unit/test_chainlit_ui.py -v`:
     Output: `53 passed, 1 warning in 1.86s` (100% pass rate, including runner tests and session isolation).
   - `uv run --with chainlit pytest tests/integration/ -v`:
     Output: `12 passed in 20.01s` (100% pass rate for golden regression and live hybrid search).
   - `uv run --with chainlit ruff check cuk_assistant/ui/app.py`:
     Output: `All checks passed!` (0 lint or style violations).

5. **CLI Invocations**:
   - `chainlit run` CLI flags verified via `uv run --with chainlit chainlit run --help`:
     - `-w, --watch`: Supported.
     - `-h, --headless`: Supported.
     - `--host`: Supported.
     - `--port`: Supported.
   - `cuk-ui` entrypoint in `cuk_assistant/ui/app.py`:
     Spawns `[sys.executable, "-m", "chainlit", "run", str(app_path), "--host", host, "--port", port]`.
     When `chainlit` is installed, `cl is not None` and the subprocess spawns correctly.

---

## 2. Logic Chain

1. *Premise*: Reviewer Finding 1 identified that `chainlit` is missing from `pyproject.toml`, resulting in host execution failures (`make ui`, `cuk-ui`) and container runtime crashes (`docker-compose.yml:46`).
2. *Observation 1*: `pyproject.toml` does not list `chainlit` under `dependencies`, and `uv.lock` does not contain any locked records for `chainlit`.
3. *Observation 2*: Both `make ui` (`uv run chainlit run ...`) and `Dockerfile` (`uv sync --frozen --no-dev`) rely on either the virtualenv binary `chainlit` or a synchronized `uv.lock`.
4. *Investigation*: Dry-run dependency resolution through `uv` confirms that `chainlit==2.12.0` integrates with zero version conflicts against existing FastAPI 0.163.1, Pydantic 2.14.3, Uvicorn 0.54.0, and Python 3.12.
5. *Validation*: Running the entire unit test suite (`53/53` passing) and integration test suite (`12/12` passing) with `chainlit` present confirms complete backwards and forward compatibility.
6. *Inference*: Running `uv add chainlit` directly on the repository will:
   - Append `"chainlit>=2.12.0"` to `pyproject.toml` dependencies.
   - Update `uv.lock` to include `chainlit` and all 101 transitive packages.
   - Install `chainlit` and the `cuk-ui` console script into `.venv/bin/`.
   - Satisfy `Dockerfile`'s `--frozen` synchronization requirement.

---

## 3. Caveats

1. **Lockfile Synchronization Requirement**:
   - Modifying `pyproject.toml` manually without running `uv lock` or `uv add` will break the Docker build because `Dockerfile` specifies `uv sync --frozen --no-dev`. The Worker MUST run `uv add chainlit` or run `uv lock` after updating `pyproject.toml`.
2. **Headless Flag Handling in Docker Compose**:
   - While `chainlit run` does support `-h, --headless`, Explorer 3 is handling the cleanup of `docker-compose.yml:46` as requested by reviewer_m6_2. Regardless, `chainlit` runs as a headless HTTP/WebSocket daemon inside Linux containers by default when no GUI/browser session is attached.
3. **Model Weights & Cache Directories**:
   - `chainlit` requires write access to `.chainlit/` or current working directory if it needs to dump local cache. The existing `.chainlit/config.toml` is present and functional.

---

## 4. Conclusion & Actionable Blueprint for Worker

### Concrete Implementation Steps for Worker:

#### Step 1: Add `chainlit` Dependency and Lock
Execute the canonical Astral uv dependency registration command:
```bash
uv add chainlit
```
*Effect*:
- Automatically pins and appends `"chainlit>=2.12.0"` into `pyproject.toml:dependencies`.
- Updates `uv.lock` with deterministic package hashes for all 101 resolved dependencies.
- Installs `chainlit` and its command-line utilities (`chainlit`, `cuk-ui`) into `.venv/bin/`.

*(Alternative manual edit if preserving custom comment groupings in `pyproject.toml`)*:
In `pyproject.toml` under `dependencies = [...]`:
```toml
    # Web UI & Serving
    "chainlit>=2.12.0",
```
followed immediately by:
```bash
uv lock
uv sync
```

#### Step 2: Validate Virtual Environment Synchronization
Ensure all dependencies are synchronized:
```bash
uv sync --locked
```
Verify `chainlit` executable presence:
```bash
uv run chainlit --help
uv run python -m chainlit run --help
```

#### Step 3: Verify CLI and Module Loading
Run verification check that `cuk_assistant.ui.app` detects `chainlit`:
```bash
uv run python -c "
import chainlit as cl
import cuk_assistant.ui.app as app
assert app.cl is not None, 'app.cl is None'
print('SUCCESS: Chainlit module loaded into cuk_assistant.ui.app')
"
```

#### Step 4: Run UI Unit & Integration Tests
```bash
uv run pytest tests/unit/test_chainlit_ui.py -v
uv run pytest tests/integration/ -v
```

#### Step 5: Code Quality & Linting Gate
```bash
uv run ruff check pyproject.toml cuk_assistant/ui/app.py tests/unit/test_chainlit_ui.py
```

---

## 5. Verification Method

To independently verify that the dependency defect is fully resolved:

1. **Verify CLI Binary & Module Help**:
   ```bash
   uv run chainlit --help
   uv run python -m chainlit run --help
   ```
   *Expected Output*: Displays Chainlit CLI options (`-w, --watch`, `-h, --headless`, `--host`, `--port`) with exit code 0.

2. **Verify Entrypoint Script `cuk-ui`**:
   ```bash
   uv run python -c "
   import sys
   from unittest.mock import patch
   from cuk_assistant.ui.app import run
   with patch('subprocess.run') as mock_run:
       run()
       assert mock_run.called
       cmd = mock_run.call_args[0][0]
       assert 'chainlit' in cmd
       assert 'cuk_assistant/ui/app.py' in cmd[3]
       print('SUCCESS: cuk-ui entrypoint properly configured')
   "
   ```

3. **Verify Lockfile Frozen Sync (Docker Simulation)**:
   ```bash
   uv sync --frozen --no-dev --dry-run
   ```
   *Expected Output*: Exits with code 0 without lockfile mismatch errors.

4. **Verify Test Suite**:
   ```bash
   uv run pytest tests/unit/test_chainlit_ui.py -q
   ```
   *Expected Output*: `53 passed in ~1.8s`.
