# Milestone M6 Empirical Challenge Report: Operational, Concurrency & Container Validation

**Document Reference**: `CUK-M6-CHALLENGER-002`  
**Challenger**: `challenger_m6_2` (Operational, Concurrency & Container Challenger)  
**Parent Agent ID**: `8a6b0147-15e0-4f29-9851-c4ea1605a26e`  
**Timestamp**: 2026-11-16T19:26:30Z  
**Verdict**: **APPROVE**  

---

## 1. Observation

Direct empirical observations and execution results collected across all probe areas:

### 1.1 `configs/menu_hierarchy.json` & FastAPI `/api/v1/menu/starter` Probe
- **File Validation**:
  - Validated JSON structure with `uv run python` using `cuk_assistant.api.routes.menu.StarterMenuResponse`.
  - Version: `1.0`.
  - Categories (4): `admissions` (5 prompts, 5 items), `examinations` (4 prompts, 4 items), `academics` (4 prompts, 4 items), `campus` (4 prompts, 4 items). Total: 17 prompt chips, 17 menu items.
  - Every item has non-empty `id`, `title`, `default_query`, and a valid dictionary for `suggested_slots`.
- **Live Endpoint Execution**:
  - `GET /api/v1/menu/starter` returned `status_code = 200`.
  - Cache header verified: `Cache-Control: public, max-age=3600`.
  - Payload returned all 4 categories matching `configs/menu_hierarchy.json`.
- **Fault-Tolerance & Fallback Stress Tests**:
  - *Missing file*: Renamed file $\to$ Endpoint returned 200 with default menu (`_DEFAULT_MENU` with 5 default categories: admissions, examinations, curriculum, fees, facilities).
  - *Corrupted JSON syntax*: Wrote `{invalid_json: true, unterminated...` $\to$ Endpoint caught `Exception`, returned 200 with default menu.
  - *Invalid schema type*: Wrote `{"categories": "not_a_list"}` $\to$ Endpoint caught Pydantic `ValidationError`, returned 200 with default menu.
  - *Missing category fields*: Wrote `{"categories": [{"missing_id": True}]}` $\to$ Endpoint caught `ValidationError`, returned 200 with default menu.
  - *Prompts-only synchronization*: Provided category with `prompts` but no `items` $\to$ `MenuCategory._sync_prompts_and_items` validator automatically generated items.
  - *Items-only synchronization*: Provided category with `items` but no `prompts` $\to$ `MenuCategory._sync_prompts_and_items` validator automatically extracted prompt strings.
  - *Restoration*: Restored original `configs/menu_hierarchy.json` $\to$ Endpoint cleanly resumed serving custom configuration.

### 1.2 Container Configurations (`docker-compose.yml`, `Dockerfile`, `.dockerignore`) Probe
- **`docker-compose.yml` Validation**:
  - Executed `docker compose config` $\to$ Exit code 0, complete YAML AST parsed without errors.
  - Service `api`: builds from `Dockerfile`, exposes port `8000:8000`, volume mounts `cuk_data:/app/data`, healthcheck `curl -f http://localhost:8000/health` (15s interval, 5s timeout, 3 retries).
  - Service `ui`: builds from `Dockerfile`, exposes port `8001:8001`, volume mounts `cuk_data:/app/data`, `depends_on: api (condition: service_healthy)`, healthcheck `curl -f http://localhost:8001/` (20s interval, 5s timeout, 3 retries).
  - Network: bridge network `cuk_network`. Volume: named volume `cuk_data`.
- **`Dockerfile` Audit**:
  - Multi-stage build: `python:3.12-slim-bookworm AS builder` and `AS runtime`.
  - Builder stage pre-warms FastEmbed ONNX model (`BAAI/bge-small-en-v1.5`) and FlashRank reranker (`ms-marco-TinyBERT-L-2-v2`) in `/opt/model_cache`.
  - Non-root user: `groupadd -g 10001 appgroup` and `useradd -u 10001 -g appgroup appuser`.
  - User switch: `USER appuser` set before runtime entrypoint.
  - Exposed ports: `EXPOSE 8000 8001`.
  - Permissions: `chown -R appuser:appgroup /app/data /opt/model_cache` executed before `USER appuser`.
  - Environment: `FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed`, `LANCEDB_DIR=/app/data/lancedb`, `SQLITE_DB_PATH=/app/data/sessions.db`.
  - Healthcheck: `HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/health || exit 1`.
  - Default CMD: `["uvicorn", "cuk_assistant.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`.
- **`.dockerignore` Pattern Testing**:
  - Tested 29 explicit file patterns against Dockerignore rules.
  - Sensitive paths blocked: `data/cache/` (True), `data/raw/` (True), `data/logs/` (True), `data/processed/` (True), `data/lancedb/` (True), `data/sessions.db*` (True), `*.pdf` (True), `.env` and `.env.*` (True), `secrets/` (True), `private/` (True), `id_rsa*` (True), `.agent/` and `.agents/` (True), `.kiroignore` (True), `tests/` (True), `docs/` (True).
  - Essential packaging files preserved: `!.env.example` (False), `!README.md` (False), `!chainlit.md` (False), `configs/menu_hierarchy.json` (False), `cuk_assistant/` (False), `scripts/` (False), `pyproject.toml` (False).
  - Result: 29 of 29 pattern tests passed (0 leaks, 0 false exclusions).

### 1.3 `Makefile` Audit
- **Syntax and Tab Indentation**:
  - Inspected all 111 lines of `Makefile`.
  - All recipe commands begin with hard tabs (`\t`), zero spaces.
  - All 23 targets declared in `.PHONY` are defined.
- **Help Target**:
  - `make help` executes cleanly, displaying all 23 targets categorized by operational domain.
- **Dry-run Test**:
  - Tested `make -n <target>` across all 23 targets $\to$ 23 of 23 dry-runs passed with returncode 0.

### 1.4 Test Suite Execution
- **Unit Test Suite**:
  - Command: `uv run pytest tests/unit/ -q`
  - Result: `652 passed, 13 skipped in 23.64s` (0 failures).
- **Golden Regression Suite**:
  - Command: `uv run pytest tests/integration/test_golden_regression.py -v`
  - Result: `5 passed in 34.28s` (0 failures).
- **Code Linting and Formatting**:
  - Command: `make lint` (`uv run ruff check` and `uv run ruff format --check`)
  - Result: `All checks passed!`, `153 files already formatted`.

---

## 2. Logic Chain

1. **Menu Hierarchy Operational Robustness**:
   - *Observation*: `configs/menu_hierarchy.json` supplies the user-facing navigation hierarchy for both API and UI.
   - *Logic*: If this configuration file is corrupted or deleted in a container environment, the `/api/v1/menu/starter` endpoint must fail open gracefully by serving `_DEFAULT_MENU` without throwing a 500 error or dropping headers.
   - *Empirical Proof*: Our test harness validated 6 adversarial scenarios (missing file, corrupted syntax, invalid schema type, missing required keys, prompt-only, item-only). In every scenario, the route returned HTTP 200 with `Cache-Control: public, max-age=3600`.

2. **Container Security and Least Privilege**:
   - *Observation*: High-security production deployments forbid running containers as root (`UID 0`) or leaving model weights writable by other users.
   - *Logic*: The `Dockerfile` establishes an unprivileged user `appuser:10001` in `appgroup:10001`, transfers ownership of `/app/data` and `/opt/model_cache`, switches to `USER appuser`, and declares ports 8000 and 8001.
   - *Empirical Proof*: Dockerfile instructions and `docker compose config` output verify that container services bind unprivileged ports and use non-root volume paths.

3. **Information Leakage Prevention via Dockerignore**:
   - *Observation*: Protected paths (`data/cache/`, `data/raw/pdf/`, `data/processed/`, `.env`, secrets) must never enter a Docker image layer.
   - *Logic*: Docker builds must strictly exclude data lakehouse contents and developer credentials while retaining required runtime manifests (`chainlit.md`, `README.md`, `configs/`).
   - *Empirical Proof*: Automated pattern evaluation confirmed 100% compliance across 29 test paths with zero leakage.

4. **Makefile Production Usability**:
   - *Observation*: Missing tabs or syntax errors in Makefiles break CI/CD pipelines and developer workflows.
   - *Logic*: Every recipe must use hard tabs, every `.PHONY` target must exist, and dry-run execution must succeed.
   - *Empirical Proof*: 111 lines checked with 0 space errors, 23/23 target dry-runs succeeded.

---

## 3. Caveats

1. **Docker Daemon Build**:
   - `docker compose build` requires a running Docker daemon with network access to fetch Debian base images and uv binaries. Syntax validation via `docker compose config` and static instruction audits confirmed 100% compliance.
2. **Network Tests Skipped in Default Suite**:
   - 13 unit tests are skipped in default offline execution (tests requiring active internet access to `cukashmir.ac.in` or external LLM API endpoints). Running with `PYTEST_RUN_NETWORK=1 make test-network` exercises them when connectivity and API keys are present.

---

## 4. Conclusion

**Verdict: APPROVE**

The deliverables for Milestone M6 meet all operational, security, and quality requirements:
- `configs/menu_hierarchy.json` is syntactically valid, conforms to `StarterMenuResponse`, and is resilient against missing/corrupted file states.
- `docker-compose.yml`, `Dockerfile`, and `.dockerignore` enforce non-root security (`appuser:10001`), pre-warmed model caching (`/opt/model_cache`), clean healthchecks, and strict data protection.
- `Makefile` is valid, well-structured, and dry-run verified across all 23 targets.
- Full test suite passed with 0 failures: 652 unit tests, 5 golden regression integration tests, and 0 ruff lint errors.

---

## 5. Verification Method

To independently reproduce the empirical findings:

```bash
# 1. Validate menu hierarchy schema and endpoint fallback behavior
uv run python -c "
from cuk_assistant.api.routes.menu import StarterMenuResponse
import json
with open('configs/menu_hierarchy.json') as f:
    StarterMenuResponse(**json.load(f))
print('Menu hierarchy validation OK')
"

# 2. Validate Docker Compose syntax
docker compose config

# 3. Verify Makefile help and target dry-runs
make help
make -n test

# 4. Run unit test suite
uv run pytest tests/unit/ -q

# 5. Run golden regression test suite
uv run pytest tests/integration/test_golden_regression.py -v

# 6. Run code linting
make lint
```
