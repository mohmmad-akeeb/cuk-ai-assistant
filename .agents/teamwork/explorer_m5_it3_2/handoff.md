# Test Design & Investigation Handoff Report (Milestone M5 — Iteration 3)

**Author**: Teamwork Explorer (`explorer_m5_it3_2`)  
**Parent / Caller**: `efda6041-f6a1-4119-b860-77559828c316`  
**Working Directory**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it3_2/`  
**Target Subject**: Design of `TestMockUserSessionIsolation` for `tests/unit/test_chainlit_ui.py`  
**Date**: 2026-11-16T18:46:00Z  

---

## 1. Observation

### O1. Baseline Implementation & ContextVar In-Place Mutation Defect
In `tests/unit/test_chainlit_ui.py` (lines 36–64):
```python
class MockUserSession:
    """Task-isolated in-memory dictionary mock emulating cl.user_session."""

    def __init__(self) -> None:
        self._var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
            "user_session_store", default=None
        )

    def _store(self) -> dict[str, Any]:
        store = self._var.get()
        if store is None:
            store = {}
            self._var.set(store)
        return store

    def get(self, key: str, default: Any = None) -> Any:
        return self._store().get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store()[key] = value

    def clear(self) -> None:
        store = self._var.get()
        if store is not None:
            store.clear()
        else:
            self._var.set({})
```

1. **In-Place Mutation**: `self.set()` (line 55) executes `self._store()[key] = value`, modifying the dictionary in place without calling `self._var.set()`.
2. **In-Place Clear**: `self.clear()` (line 60) executes `store.clear()`, wiping the shared dictionary object across any execution contexts holding a shallow copy of the ContextVar reference.
3. **Missing Module Import**: In `tests/unit/test_chainlit_ui.py` (lines 15–29), `asyncio` is not imported, although `contextvars` is present at line 17.
4. **Zero Isolation Coverage**: In the existing 42 tests of `tests/unit/test_chainlit_ui.py`, exactly 0 test cases assert that `MockUserSession` isolates across concurrent async tasks or copied contexts.

### O2. Empirical Reproduction of Concurrency Collision
Running concurrent async tasks with `asyncio.gather` on the current code:
```bash
uv run python -c "
import asyncio
from tests.unit.test_chainlit_ui import MockUserSession

session = MockUserSession()
session.clear()

async def test_concurrent():
    async def task_a():
        session.set('user', 'Alice')
        await asyncio.sleep(0.01)
        return session.get('user')

    async def task_b():
        session.set('user', 'Bob')
        await asyncio.sleep(0.01)
        return session.get('user')

    r_a, r_b = await asyncio.gather(task_a(), task_b())
    print('r_a:', r_a, 'r_b:', r_b)

asyncio.run(test_concurrent())
"
```
**Empirical Output**:
```
r_a: Bob r_b: Bob
```
`task_a` was overwritten by `task_b` because both tasks shared the exact same dictionary reference in memory.

---

## 2. Logic Chain

1. **Python ContextVar Semantics**:
   - `contextvars.ContextVar` stores references. When a context is copied (either implicitly when an `asyncio.Task` is created or explicitly via `contextvars.copy_context()`), the mapping from `ContextVar` to object reference is duplicated.
   - However, mutable objects (such as `dict`) referenced by the `ContextVar` are **not** deep-copied.
   - Therefore, calling `dict.__setitem__` directly on `self._store()` mutates the dictionary in place for all sibling tasks and copied contexts.
2. **Copy-on-Write (COW) Resolution**:
   - In `MockUserSession.set()`, creating a shallow copy (`store = dict(self._store())`), modifying the key on the copy (`store[key] = value`), and binding the new dictionary via `self._var.set(store)` guarantees that each context/task maintains private state.
   - In `MockUserSession.clear()`, setting `self._var.set({})` replaces the ContextVar pointer in the active context without wiping out the dictionaries referenced by parent or sibling contexts.
3. **Test Class Scope & Coverage Matrix**:
   To ensure complete regression prevention and specification compliance, `TestMockUserSessionIsolation` must cover:
   - **M1. Default Values & Missing Keys**: Verifying standard `.get()` fallback semantics, distinct from keys set explicitly to `None`, and intra-task sequential overwrites.
   - **M2. Active Context Clear**: Verifying `.clear()` flushes keys in the active context and allows subsequent writes.
   - **M3. ContextVar Copy with Independent Keys**: Verifying disjoint keys in `copy_context()` do not leak across sibling contexts or to root.
   - **M4. ContextVar Copy with Identical Keys**: Verifying identical keys modified in `copy_context()` maintain distinct values without altering root context.
   - **M5. ContextVar Copy Clear Isolation**: Verifying `.clear()` in one copied context leaves sibling and root context dictionaries intact.
   - **M6. Concurrent Async Tasks with Identical Keys**: Verifying $N=10$ async tasks running under `asyncio.gather` with interleaving delays isolate writes to the same key.
   - **M7. Concurrent Async Tasks with Independent Keys**: Verifying concurrent tasks writing disjoint keys cannot observe each other's keys.
   - **M8. Concurrent Async Tasks Clear Isolation**: Verifying an async task invoking `.clear()` does not wipe session state in a concurrent reading task.
   - **M9. Global `mock_cl.user_session` Verification**: Verifying the injected singleton instance attached to `mock_cl` exhibits identical concurrency isolation.

---

## 3. Caveats

- **Chainlit Not Installed in Dev Environment**: As established in prior iterations, `chainlit` is mocked via `mock_cl` test doubles in unit testing. Full browser WebSocket concurrency will be exercised during integration / Docker testing in Milestone M6.
- **Read-Only Scope**: This report provides the architectural design, exact test code, and patch diff. The code has not been directly applied to the codebase by this agent in accordance with the explorer read-only constraint.

---

## 4. Conclusion & Test Specification

### 4.1 Exact Code for `TestMockUserSessionIsolation`
Add this test class to `tests/unit/test_chainlit_ui.py` under section `# 10. Mock User Session Isolation and Concurrency Tests`:

```python
# ---------------------------------------------------------------------------
# 10. Mock User Session Isolation and Concurrency Tests
# ---------------------------------------------------------------------------


class TestMockUserSessionIsolation:
    """Verify MockUserSession context isolation, copy-on-write semantics, and concurrency."""

    @pytest.fixture
    def session(self) -> MockUserSession:
        """Provide a clean MockUserSession instance for each test."""
        s = MockUserSession()
        s.clear()
        return s

    def test_default_value_and_nonexistent_keys(self, session: MockUserSession) -> None:
        """Verify default value fallback and non-existent key retrieval."""
        assert session.get("missing") is None
        assert session.get("missing_str", "fallback") == "fallback"
        assert session.get("missing_int", 42) == 42
        assert session.get("missing_dict", {"k": "v"}) == {"k": "v"}
        assert session.get("missing_none", None) is None

        # Key explicitly set to None must return None, not the fallback default
        session.set("explicit_none", None)
        assert session.get("explicit_none") is None
        assert session.get("explicit_none", "fallback") is None

        # Sequential overwrites within same context
        session.set("counter", 1)
        assert session.get("counter") == 1
        session.set("counter", 2)
        assert session.get("counter") == 2

    def test_clear_resets_current_context(self, session: MockUserSession) -> None:
        """Verify clear empties the session store in the active context."""
        session.set("alpha", 1)
        session.set("beta", "two")
        assert session.get("alpha") == 1
        assert session.get("beta") == "two"

        session.clear()
        assert session.get("alpha") is None
        assert session.get("beta") is None

        session.set("gamma", 3)
        assert session.get("gamma") == 3

    def test_copy_context_isolation_independent_keys(self, session: MockUserSession) -> None:
        """Verify independent keys set in copied contexts do not cross-contaminate."""
        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.set, "user", "Alice")
        ctx2.run(session.set, "role", "admin")

        assert ctx1.run(session.get, "user") == "Alice"
        assert ctx1.run(session.get, "role") is None
        assert ctx2.run(session.get, "role") == "admin"
        assert ctx2.run(session.get, "user") is None
        assert session.get("user") is None
        assert session.get("role") is None

    def test_copy_context_isolation_identical_keys(self, session: MockUserSession) -> None:
        """Verify identical keys modified in copied contexts maintain copy-on-write isolation."""
        session.set("session_id", "root_session")

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.set, "session_id", "session_alpha")
        ctx2.run(session.set, "session_id", "session_beta")

        assert ctx1.run(session.get, "session_id") == "session_alpha"
        assert ctx2.run(session.get, "session_id") == "session_beta"
        assert session.get("session_id") == "root_session"

    def test_copy_context_clear_isolation_across_siblings(self, session: MockUserSession) -> None:
        """Verify clear() in one copied context leaves sibling and parent contexts intact."""
        session.set("shared_key", "shared_val")
        session.set("active_slots", {"cohort": "2024"})

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.clear)

        assert ctx1.run(session.get, "shared_key") is None
        assert ctx1.run(session.get, "active_slots") is None
        assert ctx2.run(session.get, "shared_key") == "shared_val"
        assert ctx2.run(session.get, "active_slots") == {"cohort": "2024"}
        assert session.get("shared_key") == "shared_val"
        assert session.get("active_slots") == {"cohort": "2024"}

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_tasks_identical_keys(self, session: MockUserSession) -> None:
        """Verify concurrent async tasks writing to the same key maintain isolated values."""

        async def worker(worker_id: int) -> str:
            session.set("user_id", f"user_{worker_id}")
            await asyncio.sleep(0.005 * (worker_id % 3 + 1))
            return session.get("user_id")

        results = await asyncio.gather(*(worker(i) for i in range(10)))
        for i, val in enumerate(results):
            assert val == f"user_{i}", f"Expected user_{i}, got {val}"
        assert session.get("user_id") is None

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_tasks_independent_keys(self, session: MockUserSession) -> None:
        """Verify concurrent async tasks modifying independent keys do not leak across tasks."""

        async def worker(worker_id: int) -> tuple[str, list[Any]]:
            session.set(f"task_key_{worker_id}", f"val_{worker_id}")
            await asyncio.sleep(0.005 * (worker_id % 3 + 1))
            my_val = session.get(f"task_key_{worker_id}")
            other_vals = [session.get(f"task_key_{j}") for j in range(6) if j != worker_id]
            return my_val, other_vals

        results = await asyncio.gather(*(worker(i) for i in range(6)))
        for i, (my_val, other_vals) in enumerate(results):
            assert my_val == f"val_{i}"
            assert all(v is None for v in other_vals), f"Worker {i} leaked keys: {other_vals}"

        for i in range(6):
            assert session.get(f"task_key_{i}") is None

    @pytest.mark.asyncio
    async def test_asyncio_concurrent_clear_isolation(self, session: MockUserSession) -> None:
        """Verify clear() in one async task does not clobber session state in concurrent sibling tasks."""
        session.set("common_flag", "initial_state")

        async def task_clear() -> tuple[Any, Any]:
            await asyncio.sleep(0.002)
            session.clear()
            session.set("cleared_task_flag", "done")
            await asyncio.sleep(0.01)
            return session.get("common_flag"), session.get("cleared_task_flag")

        async def task_reader() -> tuple[Any, Any]:
            val1 = session.get("common_flag")
            await asyncio.sleep(0.008)
            val2 = session.get("common_flag")
            session.set("reader_flag", "active")
            return val1, val2

        (c_shared, c_flag), (r_val1, r_val2) = await asyncio.gather(task_clear(), task_reader())
        assert c_shared is None
        assert c_flag == "done"
        assert r_val1 == "initial_state"
        assert r_val2 == "initial_state"
        assert session.get("common_flag") == "initial_state"
        assert session.get("cleared_task_flag") is None
        assert session.get("reader_flag") is None

    @pytest.mark.asyncio
    async def test_mock_cl_user_session_concurrency(self) -> None:
        """Verify global mock_cl.user_session instance isolates concurrent task sessions."""

        async def task_a() -> str:
            mock_cl.user_session.set("user", "Alice")
            await asyncio.sleep(0.005)
            return mock_cl.user_session.get("user")

        async def task_b() -> str:
            mock_cl.user_session.set("user", "Bob")
            await asyncio.sleep(0.005)
            return mock_cl.user_session.get("user")

        r_a, r_b = await asyncio.gather(task_a(), task_b())
        assert r_a == "Alice"
        assert r_b == "Bob"
        assert mock_cl.user_session.get("user") is None
```

### 4.2 Required Supporting Modifications in `tests/unit/test_chainlit_ui.py`
For the test class to execute cleanly:

1. **Import `asyncio`**:
   At line 17 of `tests/unit/test_chainlit_ui.py`:
   ```python
   import asyncio
   import contextvars
   ```
2. **Implement Copy-on-Write in `MockUserSession`**:
   Replace lines 54–63 with:
   ```python
       def set(self, key: str, value: Any) -> None:
           store = dict(self._store())
           store[key] = value
           self._var.set(store)

       def clear(self) -> None:
           self._var.set({})
   ```
3. **Update Module Docstring**:
   Add item 10 to module docstring:
   ```python
   10. MockUserSession context isolation, copy-on-write semantics, and concurrent task safety.
   ```

---

## 5. Verification Method

### 5.1 Verification Commands for the Implementer
Once the worker implements the changes:

```bash
# 1. Run the targeted isolation test class
uv run pytest tests/unit/test_chainlit_ui.py -k TestMockUserSessionIsolation -v

# 2. Run the entire Chainlit UI unit test suite (51 tests)
uv run pytest tests/unit/test_chainlit_ui.py -v

# 3. Cross-module verification in both directions
uv run pytest tests/unit/test_chainlit_ui.py tests/unit/test_api_endpoints.py -q
uv run pytest tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q

# 4. Code quality and formatting verification
uv run ruff check cuk_assistant/ scripts/ tests/
```

### 5.2 Invalidation Conditions
- Any test in `TestMockUserSessionIsolation` raises `AssertionError` (indicates regression back to in-place mutation).
- Any existing test in `test_chainlit_ui.py` fails (indicates regression in session handling in UI callbacks).
- `ruff` reports lint errors (e.g. unused imports, line lengths, or missing type hints).
