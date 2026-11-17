# Investigation & Architecture Report: MockUserSession Concurrency Defect & Copy-on-Write Remediation

**Author**: Teamwork Explorer (`explorer_m5_it3_1`)  
**Parent / Caller**: `efda6041-f6a1-4119-b860-77559828c316`  
**Working Directory**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m5_it3_1/`  
**Target Code Under Review**: `tests/unit/test_chainlit_ui.py`  
**Milestone**: M5 Iteration 3  
**Date**: 2026-11-16T18:43:00Z  

---

## 1. Observation

### O1. Current Implementation in `tests/unit/test_chainlit_ui.py`
In `tests/unit/test_chainlit_ui.py` (lines 36-63):
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

### O2. Test Setup and Fixture Interaction
In `tests/unit/test_chainlit_ui.py` (lines 166-178):
```python
@pytest.fixture(autouse=True)
def clean_mock_state() -> Generator[None, None, None]:
    """Isolate session state, sent messages, and singletons for each test."""
    mock_cl.user_session.clear()
    MockMessage.sent_messages.clear()
    app._orchestrator = None
    app._telemetry_sink = None
    yield
    mock_cl.user_session.clear()
    MockMessage.sent_messages.clear()
    app._orchestrator = None
    app._telemetry_sink = None
```
When `clean_mock_state` runs before a test, it invokes `mock_cl.user_session.clear()`. If `self._var.get()` was `None`, it executes `self._var.set({})`, binding a single dict object (`{}`) in the test runner's context. If `self._var.get()` was already populated, it invokes `store.clear()`, clearing that same dict in-place.

### O3. Empirical Reproduction Results
1. **Concurrent Async Tasks (`asyncio.gather`)**:
   Executed command:
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
       assert r_a == 'Alice' and r_b == 'Bob', f'Collision: r_a={r_a}, r_b={r_b}'

   asyncio.run(test_concurrent())
   "
   ```
   **Output**: Exit code 1.
   ```
   AssertionError: Collision: r_a=Bob, r_b=Bob
   ```
   Both tasks observed `'Bob'`. Task B mutated the shared dictionary in-place, overwriting Task A's write before Task A awoke from `asyncio.sleep`.

2. **ContextVar Copy Isolation (`contextvars.copy_context`)**:
   Executed command:
   ```bash
   uv run python -c "
   import contextvars
   from tests.unit.test_chainlit_ui import MockUserSession

   session = MockUserSession()
   session.clear()

   ctx1 = contextvars.copy_context()
   ctx2 = contextvars.copy_context()

   ctx1.run(session.set, 'user', 'Alice')
   ctx2.run(session.set, 'user', 'Bob')

   r1 = ctx1.run(session.get, 'user')
   r2 = ctx2.run(session.get, 'user')

   assert r1 == 'Alice' and r2 == 'Bob', f'Collision: r1={r1}, r2={r2}'
   "
   ```
   **Output**: Exit code 1.
   ```
   AssertionError: Collision: r1=Bob, r2=Bob
   ```
   Both contexts observed `'Bob'` because the underlying dictionary reference was identical.

3. **Current Test Suite Status**:
   - `uv run pytest tests/unit/test_chainlit_ui.py -v`: 42 passed in 0.28s.
   - `uv run ruff check tests/unit/test_chainlit_ui.py`: 0 errors.
   - Test suite currently contains zero concurrency tests for `MockUserSession`.

---

## 2. Logic Chain

1. **Python `contextvars` Mechanics vs Mutable Object References (O1, O2, O3)**:
   - A `ContextVar` maintains a mapping of context objects to values.
   - When an asynchronous task is created via `asyncio.create_task` or `asyncio.gather`, or when `contextvars.copy_context()` is invoked, Python creates a shallow copy of the context mapping.
   - If the value stored in the `ContextVar` is a mutable object (such as a standard Python `dict`), copying the context copies the *reference* to that dictionary. Both the parent context and child/sibling contexts point to the exact same dictionary in heap memory.
2. **Defect in `MockUserSession.set()` and `MockUserSession.clear()`**:
   - Line 55: `self._store()[key] = value`.
     This executes `dict.__setitem__` directly on the retrieved dictionary. It never calls `self._var.set()`. Because no new value is bound to the `ContextVar` in the current context, all contexts continue pointing to the same modified dictionary.
   - Line 60: `store.clear()`.
     If `store` is not `None`, calling `store.clear()` clears the shared dictionary in-place. If another task holds a reference to that context, its session state is unexpectedly wiped.
3. **Copy-on-Write (CoW) Resolution**:
   - In `set()`:
     ```python
     def set(self, key: str, value: Any) -> None:
         store = dict(self._store())
         store[key] = value
         self._var.set(store)
     ```
     By creating a fresh shallow copy (`dict(...)`) and calling `self._var.set(store)`:
     - The active context's `ContextVar` pointer is rebound to the newly created dictionary.
     - Sibling tasks and parent tasks retain their prior dictionary references, achieving true isolation.
     - Subsequent mutations in the current task create their own copies, completely eliminating race conditions.
   - In `clear()`:
     ```python
     def clear(self) -> None:
         self._var.set({})
     ```
     By binding a fresh `{}` dict directly to `self._var` in the active context, the current context is cleared without mutating any dictionary instance referenced by sibling or parent contexts.
4. **Empirical Validation of the Proposed Solution**:
   - Sibling concurrent tasks (`asyncio.gather`): Pass (`r_a == 'Alice'`, `r_b == 'Bob'`).
   - Independent copied contexts (`contextvars.copy_context()`): Pass (`r1 == 'Alice'`, `r2 == 'Bob'`).
   - Child task mutations via `asyncio.create_task`: Child writes do not leak to parent (`p_initial == 'val0'`, `p_child is None`).
   - Child task clear via `asyncio.create_task`: Child clear does not clear parent (`p_root == 'stay'`).
   - All 42 existing tests in `tests/unit/test_chainlit_ui.py` pass without regression.

---

## 3. Caveats

1. **Top-Level Copy-on-Write Scope**:
   - `dict(self._store())` performs a shallow copy of top-level keys. If a caller retrieves a mutable nested object (e.g. `raw_slots = session.get("active_slots")`) and mutates that nested dict in-place without calling `set()`, tasks sharing that nested object reference could still experience shared mutations.
   - In `cuk_assistant/ui/app.py`, this is already safely handled: lines 107 and 151 explicitly create fresh shallow copies before mutation (`dict(raw_slots) if isinstance(raw_slots, dict) else {}`) and call `cl.user_session.set("active_slots", active_slots)`. Hence, top-level CoW in `MockUserSession` is sufficient and avoids deepcopy overhead.
2. **Import Ordering & Linting**:
   - `import asyncio` must be added to `tests/unit/test_chainlit_ui.py` to support the new async isolation tests. It must be placed in alphabetical order before `import contextvars` to adhere to `ruff` I001 import formatting rules.

---

## 4. Conclusion

The root cause identified by `challenger_m5_it2_2` is 100% verified and reproducible. The defect stems from in-place dictionary mutation and in-place clearing, which violates Python `ContextVar` semantics under concurrent asynchronous task scheduling.

### Recommended Remediation Strategy (for Worker)

In `tests/unit/test_chainlit_ui.py`:

#### 1. Add `import asyncio` in Alphabetical Order
At line 17:
```python
from __future__ import annotations

import asyncio
import contextvars
import importlib
...
```

#### 2. Update `MockUserSession` to Copy-on-Write Semantics
Replace lines 54-63:
```python
<<<<
    def set(self, key: str, value: Any) -> None:
        self._store()[key] = value

    def clear(self) -> None:
        store = self._var.get()
        if store is not None:
            store.clear()
        else:
            self._var.set({})
====
    def set(self, key: str, value: Any) -> None:
        store = dict(self._store())
        store[key] = value
        self._var.set(store)

    def clear(self) -> None:
        self._var.set({})
>>>>
```

#### 3. Add `TestMockUserSessionIsolation` Test Suite
Append Section 10 to `tests/unit/test_chainlit_ui.py` (and update the module docstring to note item 10):
```python
# ---------------------------------------------------------------------------
# 10. Mock User Session Concurrency and Context Isolation Tests
# ---------------------------------------------------------------------------


class TestMockUserSessionIsolation:
    """Verify MockUserSession provides true ContextVar task and copy isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_isolation(self) -> None:
        """Verify concurrent asyncio tasks mutating keys do not overwrite each other."""
        session = MockUserSession()
        session.clear()

        async def task_a() -> str | None:
            session.set("user", "Alice")
            await asyncio.sleep(0.01)
            return session.get("user")

        async def task_b() -> str | None:
            session.set("user", "Bob")
            await asyncio.sleep(0.01)
            return session.get("user")

        r_a, r_b = await asyncio.gather(task_a(), task_b())
        assert r_a == "Alice"
        assert r_b == "Bob"

    def test_contextvars_copy_isolation(self) -> None:
        """Verify explicit contextvars.copy_context() preserves independent session state."""
        session = MockUserSession()
        session.clear()

        ctx1 = contextvars.copy_context()
        ctx2 = contextvars.copy_context()

        ctx1.run(session.set, "user", "Alice")
        ctx2.run(session.set, "user", "Bob")

        assert ctx1.run(session.get, "user") == "Alice"
        assert ctx2.run(session.get, "user") == "Bob"

    @pytest.mark.asyncio
    async def test_child_task_mutation_does_not_mutate_parent(self) -> None:
        """Verify mutations in child asyncio.create_task do not leak back to parent context."""
        session = MockUserSession()
        session.clear()
        session.set("initial", "val0")

        async def child() -> tuple[str | None, str | None]:
            session.set("initial", "mutated_in_child")
            session.set("child_only", "child_val")
            return session.get("initial"), session.get("child_only")

        c_init, c_child = await asyncio.create_task(child())
        assert c_init == "mutated_in_child"
        assert c_child == "child_val"
        assert session.get("initial") == "val0"
        assert session.get("child_only") is None

    @pytest.mark.asyncio
    async def test_child_task_clear_does_not_clear_parent(self) -> None:
        """Verify session.clear() in child task does not clear parent session."""
        session = MockUserSession()
        session.clear()
        session.set("token", "secret123")

        async def child() -> str | None:
            session.clear()
            return session.get("token")

        c_tok = await asyncio.create_task(child())
        assert c_tok is None
        assert session.get("token") == "secret123"
```

---

## 5. Verification Method

To verify the remediation:

### Command 1: Standalone Concurrency and Context Isolation Validation
```bash
uv run python -c "
import asyncio
import contextvars
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
    assert r_a == 'Alice' and r_b == 'Bob', f'Collision: r_a={r_a}, r_b={r_b}'

asyncio.run(test_concurrent())

ctx1 = contextvars.copy_context()
ctx2 = contextvars.copy_context()
ctx1.run(session.set, 'user', 'Alice')
ctx2.run(session.set, 'user', 'Bob')
assert ctx1.run(session.get, 'user') == 'Alice'
assert ctx2.run(session.get, 'user') == 'Bob'

print('MockUserSession isolation verified successfully!')
"
```
- Current output: Fails with `AssertionError`.
- Remediated output: Prints `MockUserSession isolation verified successfully!` and exits 0.

### Command 2: Full UI Unit Test Suite Execution
```bash
uv run pytest tests/unit/test_chainlit_ui.py -v
```
Expected output: 46 passed in ~0.35s (42 original + 4 new isolation tests).

### Command 3: Cross-Module Verification
```bash
uv run pytest tests/unit/test_chainlit_ui.py tests/unit/test_api_endpoints.py tests/unit/test_factory_and_orchestrator.py -q
```
Expected output: 79 passed, 0 errors.

### Command 4: Code Quality and Linting
```bash
uv run ruff check tests/unit/test_chainlit_ui.py cuk_assistant/ scripts/ tests/
```
Expected output: `All checks passed!` with 0 warnings or errors.
