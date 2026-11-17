# Handoff Report: Model Caching & Factory Overrides Exploration (Findings 2 & 4)

**Document Reference**: `CUK-M6-EXPLORER-002`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_it2_2/`  
**Agent**: `explorer_m6_it2_2`  
**Recipient**: Orchestrator (`8a6b0147-15e0-4f29-9851-c4ea1605a26e`) & Worker  
**Timestamp**: 2026-11-16T19:35:00Z  
**Type**: Hard Handoff  

---

## 1. Observation

Direct observations and verifiable code inspection from the codebase:

1. **FlashRank Reranker Cache Bypassing Pre-Warmed Model (`cuk_assistant/retrieval/flashrank_reranker.py:28-50`)**:
   - `FlashRankReranker.__init__` accepts `cache_dir: str | None = None`.
   - When `cache_dir` is not explicitly passed:
     ```python
     init_kwargs: dict[str, Any] = dict(kwargs)
     if self._cache_dir is not None:
         init_kwargs["cache_dir"] = self._cache_dir

     self._ranker = Ranker(
         model_name=self._model_name,
         **init_kwargs,
     )
     ```
   - Upstream `flashrank.Config` defines `default_cache_dir = "/tmp"`. `flashrank.Ranker` has zero native environment variable inspection.
   - In `Dockerfile` (lines 35–37), the model `ms-marco-TinyBERT-L-2-v2` is pre-warmed to `/opt/model_cache/flashrank` during the builder stage.
   - In `Dockerfile` Stage 2 runtime (lines 56–62), `FLASHRANK_CACHE_PATH` is NOT exported in `ENV`.
   - In `docker-compose.yml` (lines 18, 57), only `FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed` is configured; `FLASHRANK_CACHE_PATH` is omitted for both `api` and `ui` services.
   - In container runtime, `/tmp/ms-marco-TinyBERT-L-2-v2` does not exist; on first rerank request, `Ranker` attempts to download the model from Hugging Face, failing in offline / restricted environments.

2. **Factory Functions Ignoring Container Environment Variables (`cuk_assistant/core/factory.py:69, 226`)**:
   - In `cuk_assistant/core/factory.py`:
     ```python
     def create_vector_store(
         name: str = "lancedb",
         **kwargs: Any,
     ) -> VectorStoreProtocol:
         import cuk_assistant.retrieval.lancedb_store  # noqa: F401

         cls = get_vector_store_cls(name)
         logger.info("Factory instantiating vector store '%s' (%s)", name, cls.__name__)
         return cls(**kwargs)  # type: ignore[return-value]
     ```
     Does not check `os.environ.get("LANCEDB_DIR")`.
   - In `cuk_assistant/core/factory.py`:
     ```python
     def create_session_store(
         db_path: Path | str = "data/sessions.db",
         timeout_seconds: float = 5.0,
         **kwargs: Any,
     ) -> SessionStoreProtocol:
         logger.info("Factory instantiating SQLiteSessionStore at '%s'", db_path)
         return SQLiteSessionStore(db_path=db_path, timeout_seconds=timeout_seconds, **kwargs)
     ```
     Defaults `db_path` to `"data/sessions.db"` and does not check `os.environ.get("SQLITE_DB_PATH")`.
   - In `cuk_assistant/retrieval/lancedb_store.py` (line 81):
     `def __init__(self, db_path: str | Path = DEFAULT_LANCEDB_DIR, ...)` does not check `os.environ.get("LANCEDB_DIR")`.
   - In `cuk_assistant/agent/session_store.py` (line 114):
     `def __init__(self, db_path: Path | str = "data/sessions.db", ...)` does not check `os.environ.get("SQLITE_DB_PATH")`.

3. **Current Test Status**:
   - `uv run pytest tests/unit/test_flashrank_reranker.py tests/unit/test_factory_and_orchestrator.py -q`: 18 passed in 2.85s.
   - `uv run pytest tests/unit/test_retrieval_coordinator.py tests/unit/test_lancedb_store.py tests/unit/test_session_store.py -q`: 28 passed in 2.25s.
   - `uv run ruff check cuk_assistant/retrieval/ tests/unit/ cuk_assistant/core/factory.py`: All checks passed.

---

## 2. Logic Chain

1. **Premise 1**: Container pre-warming in `Dockerfile` is useless unless runtime components read from the pre-warmed location.
2. **Step 1**: Because `flashrank` upstream hardcodes `/tmp`, the wrapper `FlashRankReranker` must implement the resolution hierarchy:
   - Passed `cache_dir` parameter (explicit caller override)
   - `os.environ.get("FLASHRANK_CACHE_PATH")` (container deployment standard)
   - `os.environ.get("FLASHRANK_CACHE_DIR")` (alternative standard naming)
   - `Path("/opt/model_cache/flashrank").is_dir()` (automatic detection of container pre-warmed image without requiring env var)
   - Fallback to `"/tmp"` (standard local development default)
3. **Step 2**: Exporting `FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank` in `Dockerfile` (runtime stage) and `docker-compose.yml` (`api` and `ui` services) ensures standard twelve-factor environment configuration.
4. **Step 3**: In twelve-factor deployments, volume mounts and storage paths (`LANCEDB_DIR` and `SQLITE_DB_PATH`) are provided via environment variables.
   - `create_vector_store` must inject `os.environ.get("LANCEDB_DIR")` if `db_path` is not passed in `kwargs`.
   - `create_session_store` must resolve `db_path` from `os.environ.get("SQLITE_DB_PATH")` when `db_path is None`.
   - Corresponding adapters (`LanceDBStore` and `SQLiteSessionStore`) should accept `db_path: Path | str | None = None` and resolve from their respective environment variable before falling back to default paths.
   - This ensures both factory-based DI and direct adapter instantiations honor container environment overrides.

---

## 3. Caveats

- **No Caveats**: The changes are strictly additive and backwards-compatible with all existing callers and unit tests.

---

## 4. Conclusion & Actionable Blueprint for Worker

### Target 1: `cuk_assistant/retrieval/flashrank_reranker.py`

1. **Imports and Constants**:
   Add `os` and `Path`:
   ```python
   import logging
   import os
   from pathlib import Path
   from typing import Any
   ```
   Add cache path constants:
   ```python
   DEFAULT_RERANKER_MODEL = "ms-marco-TinyBERT-L-2-v2"
   DEFAULT_OPT_CACHE = Path("/opt/model_cache/flashrank")
   DEFAULT_CACHE_DIR = "/tmp"
   ```

2. **Constructor Resolution Logic**:
   Update `FlashRankReranker.__init__`:
   ```python
   @register_reranker("flashrank")
   class FlashRankReranker(RerankerProtocol):
       """Local CPU ONNX cross-encoder reranker backed by FlashRank."""

       def __init__(
           self,
           model_name: str = DEFAULT_RERANKER_MODEL,
           cache_dir: str | None = None,
           **kwargs: Any,
       ) -> None:
           resolved_cache = cache_dir or kwargs.pop("cache_dir", None)
           if not resolved_cache:
               resolved_cache = os.environ.get("FLASHRANK_CACHE_PATH") or os.environ.get(
                   "FLASHRANK_CACHE_DIR"
               )
           if not resolved_cache:
               if DEFAULT_OPT_CACHE.is_dir():
                   resolved_cache = str(DEFAULT_OPT_CACHE)
           if not resolved_cache:
               resolved_cache = DEFAULT_CACHE_DIR

           self._model_name = model_name
           self._cache_dir = str(resolved_cache)

           logger.info(
               "Initializing FlashRankReranker model=%s cache_dir=%s",
               self._model_name,
               self._cache_dir,
           )
           init_kwargs: dict[str, Any] = dict(kwargs)
           init_kwargs["cache_dir"] = self._cache_dir

           self._ranker = Ranker(
               model_name=self._model_name,
               **init_kwargs,
           )
   ```

---

### Target 2: `cuk_assistant/core/factory.py`

1. **`create_vector_store`**:
   ```python
   def create_vector_store(
       name: str = "lancedb",
       **kwargs: Any,
   ) -> VectorStoreProtocol:
       """Instantiate a registered vector store adapter."""
       import cuk_assistant.retrieval.lancedb_store  # noqa: F401

       cls = get_vector_store_cls(name)
       init_kwargs = dict(kwargs)
       if "db_path" not in init_kwargs or init_kwargs["db_path"] is None:
           env_lancedb_dir = os.environ.get("LANCEDB_DIR")
           if env_lancedb_dir:
               init_kwargs["db_path"] = env_lancedb_dir

       logger.info("Factory instantiating vector store '%s' (%s)", name, cls.__name__)
       return cls(**init_kwargs)  # type: ignore[return-value]
   ```

2. **`create_reranker`**:
   ```python
   def create_reranker(
       name: str = "flashrank",
       **kwargs: Any,
   ) -> RerankerProtocol:
       """Instantiate a registered reranker adapter."""
       import cuk_assistant.retrieval.flashrank_reranker  # noqa: F401

       cls = get_reranker_cls(name)
       init_kwargs = dict(kwargs)
       if "cache_dir" not in init_kwargs or init_kwargs["cache_dir"] is None:
           env_cache_path = os.environ.get("FLASHRANK_CACHE_PATH") or os.environ.get(
               "FLASHRANK_CACHE_DIR"
           )
           if env_cache_path:
               init_kwargs["cache_dir"] = env_cache_path
           elif Path("/opt/model_cache/flashrank").is_dir():
               init_kwargs["cache_dir"] = "/opt/model_cache/flashrank"

       logger.info("Factory instantiating reranker '%s' (%s)", name, cls.__name__)
       return cls(**init_kwargs)  # type: ignore[return-value]
   ```

3. **`create_session_store`**:
   ```python
   def create_session_store(
       db_path: Path | str | None = None,
       timeout_seconds: float = 5.0,
       **kwargs: Any,
   ) -> SessionStoreProtocol:
       """Instantiate high-concurrency SQLite session store in WAL mode."""
       if db_path is None:
           db_path = os.environ.get("SQLITE_DB_PATH") or "data/sessions.db"

       logger.info("Factory instantiating SQLiteSessionStore at '%s'", db_path)
       return SQLiteSessionStore(db_path=db_path, timeout_seconds=timeout_seconds, **kwargs)
   ```

---

### Target 3: Adapters Defense-in-Depth

1. **`cuk_assistant/retrieval/lancedb_store.py`**:
   Add `import os`:
   ```python
       def __init__(
           self,
           db_path: str | Path | None = None,
           table_name: str = CHUNKS_TABLE_NAME,
           parent_table_name: str = PARENT_TABLE_NAME,
       ) -> None:
           if db_path is None:
               db_path = os.environ.get("LANCEDB_DIR") or DEFAULT_LANCEDB_DIR
           raw_path = Path(db_path)
   ```

2. **`cuk_assistant/agent/session_store.py`**:
   Add `import os`:
   ```python
       def __init__(
           self,
           db_path: Path | str | None = None,
           timeout_seconds: float = 5.0,
       ) -> None:
           """Initialize session store with WAL mode pragmas and DDL schema."""
           if db_path is None:
               db_path = os.environ.get("SQLITE_DB_PATH") or "data/sessions.db"
   ```

---

### Target 4: Deployment Configurations

1. **`Dockerfile` Stage 2 Runtime ENV (lines 56–62)**:
   ```dockerfile
   ENV DEBIAN_FRONTEND=noninteractive \
       PYTHONUNBUFFERED=1 \
       PYTHONDONTWRITEBYTECODE=1 \
       PYTHONPATH=/app \
       PATH="/app/.venv/bin:$PATH" \
       FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed \
       FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank \
       LANCEDB_DIR=/app/data/lancedb \
       SQLITE_DB_PATH=/app/data/sessions.db \
       CHAINLIT_PORT=8001 \
       CHAINLIT_HOST=0.0.0.0
   ```

2. **`docker-compose.yml`**:
   Under `api.environment`:
   ```yaml
         - FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed
         - FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank
   ```
   Under `ui.environment`:
   ```yaml
         - FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed
         - FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank
   ```

---

### Target 5: Unit Tests

1. In `tests/unit/test_flashrank_reranker.py`:
   Add test methods using `unittest.mock.patch("cuk_assistant.retrieval.flashrank_reranker.Ranker")`:
   ```python
   from unittest.mock import patch
   from pathlib import Path

   def test_flashrank_cache_dir_precedence_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.setenv("FLASHRANK_CACHE_PATH", "/env/cache")
       with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
           reranker = FlashRankReranker(cache_dir="/explicit/cache")
           assert reranker._cache_dir == "/explicit/cache"
           assert mock_ranker.call_args.kwargs["cache_dir"] == "/explicit/cache"

   def test_flashrank_cache_dir_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.setenv("FLASHRANK_CACHE_PATH", "/env/model_cache/flashrank")
       with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
           reranker = FlashRankReranker()
           assert reranker._cache_dir == "/env/model_cache/flashrank"
           assert mock_ranker.call_args.kwargs["cache_dir"] == "/env/model_cache/flashrank"

   def test_flashrank_cache_dir_fallback_opt_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.delenv("FLASHRANK_CACHE_PATH", raising=False)
       monkeypatch.delenv("FLASHRANK_CACHE_DIR", raising=False)
       with patch.object(Path, "is_dir", side_effect=lambda: True):
           with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
               reranker = FlashRankReranker()
               assert reranker._cache_dir == "/opt/model_cache/flashrank"
               assert mock_ranker.call_args.kwargs["cache_dir"] == "/opt/model_cache/flashrank"

   def test_flashrank_cache_dir_fallback_tmp(self, monkeypatch: pytest.MonkeyPatch) -> None:
       monkeypatch.delenv("FLASHRANK_CACHE_PATH", raising=False)
       monkeypatch.delenv("FLASHRANK_CACHE_DIR", raising=False)
       with patch.object(Path, "is_dir", side_effect=lambda: False):
           with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
               reranker = FlashRankReranker()
               assert reranker._cache_dir == "/tmp"
               assert mock_ranker.call_args.kwargs["cache_dir"] == "/tmp"
   ```

2. In `tests/unit/test_factory_and_orchestrator.py`:
   Add factory override test methods:
   ```python
   def test_create_vector_store_lancedb_dir_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
       custom_dir = str(tmp_path / "custom_lancedb")
       monkeypatch.setenv("LANCEDB_DIR", custom_dir)
       store = create_vector_store()
       assert str(store._db_path) == custom_dir

   def test_create_vector_store_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
       monkeypatch.setenv("LANCEDB_DIR", str(tmp_path / "env_lancedb"))
       explicit_dir = str(tmp_path / "explicit_lancedb")
       store = create_vector_store(db_path=explicit_dir)
       assert str(store._db_path) == explicit_dir

   def test_create_session_store_sqlite_db_path_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
       custom_db = str(tmp_path / "custom_sessions.db")
       monkeypatch.setenv("SQLITE_DB_PATH", custom_db)
       store = create_session_store()
       assert str(store._db_path) == custom_db
       store.close()

   def test_create_session_store_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
       monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "custom_sessions.db"))
       store = create_session_store(db_path=":memory:")
       assert store._is_memory is True
       store.close()
   ```

---

## 5. Verification Method

To verify the blueprint after implementation:

1. **Ruff Check**:
   ```bash
   uv run ruff check cuk_assistant/ scripts/ tests/
   ```
   Must pass with 0 errors or warnings.

2. **Unit Tests**:
   ```bash
   uv run pytest tests/unit/test_flashrank_reranker.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_lancedb_store.py tests/unit/test_session_store.py -v
   ```
   All tests must pass.

3. **Full Test Suites**:
   ```bash
   uv run pytest tests/unit/ -q
   uv run pytest tests/integration/ -q
   ```
   0 failures across unit and integration suites.
