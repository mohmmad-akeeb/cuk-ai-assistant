# Adversarial Evaluation Report: Milestone M6 (Observability, Evals, Containerization & Sign-Off)

**Document Reference**: `CUK-M6-CHALLENGER-001`  
**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/challenger_m6_1/`  
**Challenger**: `challenger_m6_1` (Adversarial Regression & Evaluation Challenger)  
**Parent Agent ID**: `8a6b0147-15e0-4f29-9851-c4ea1605a26e`  
**Timestamp**: 2026-11-16T19:30:00Z  
**Verdict**: **APPROVE**  

---

## 1. Observation

Direct observations and verifiable outputs from empirical tests executed in the repository:

1. **Schema Consolidation & Validation (`cuk_assistant/schemas/chat.py`)**:
   - `FeedbackRequest` (lines 15–32):
     - Executed test with invalid scores (`score=0, 2, -2, 100, -100`): all raised `pydantic_core._pydantic_core.ValidationError` (`Value error, Score must be strictly -1 or 1.`).
     - Executed test with invalid types (`score="abc"`, `None`, `[]`, `{}`, `1.5`): all raised `ValidationError`.
     - Executed test with missing `trace_id`: raised `ValidationError` (`Field required`).
     - Executed test with `comment` of 501 characters: raised `ValidationError` (`String should have at most 500 characters`).
     - Nuance: in standard Pydantic lax mode, boolean `score=True` coerces to integer `1` (because Python `bool` subclasses `int`), whereas `score=False` (0) is rejected.
   - `ChatRequest` (lines 34–54):
     - Executed test with `query="test query"` only: `request.query == "test query"` and `request.message == "test query"`.
     - Executed test with `message="test message"` only: `request.query == "test message"` and `request.message == "test message"`.
     - Executed test with empty constructor `ChatRequest()`: sets `query=None, message=None`. In `cuk_assistant/api/routes/chat.py:101`, `query_str = (body.query or body.message or "").strip()` properly checks for non-empty text and raises HTTP 400.
     - Unexpected fields: `ConfigDict(extra="ignore")` discards extra attributes without error.
   - `CitationCard` (lines 70–86) and `TurnResult` (lines 88–101):
     - Required field validation: properly raises `ValidationError` if any required field is missing (`citation_id`, `doc_id`, `chunk_id`, `title`, `source_url`, `quoted_snippet` for `CitationCard`; `message_id`, `session_id`, `content` for `TurnResult`).
     - Mutability: models do not set `frozen=True` in `ConfigDict`, allowing field mutation post-instantiation.
     - JSON round-trip: verified `model_dump_json()` and `model_validate_json()` preserve all fields identically.

2. **Automated Regression Suite (`tests/integration/test_golden_regression.py`)**:
   - Live Coordinator Verification: `evaluator` module fixture (lines 29–40) directly calls `create_retrieval_coordinator()`, loading live LanceDB Arrow tables, FastEmbed ONNX (`bge-small-en-v1.5`), and FlashRank reranker (`ms-marco-TinyBERT-L-2-v2`).
   - Executed: `uv run pytest tests/integration/test_golden_regression.py -v`
     - Command exited with code `0`.
     - Output:
       ```text
       tests/integration/test_golden_regression.py::TestGoldenDatasetRegression::test_golden_dataset_structure_and_volume PASSED [ 20%]
       tests/integration/test_golden_regression.py::TestGoldenDatasetRegression::test_hit_rate_at_5_meets_regression_gate PASSED [ 40%]
       tests/integration/test_golden_regression.py::TestGoldenDatasetRegression::test_mrr_meets_regression_gate PASSED [ 60%]
       tests/integration/test_golden_regression.py::TestGoldenDatasetRegression::test_slot_extraction_accuracy_baseline PASSED [ 80%]
       tests/integration/test_golden_regression.py::TestGoldenDatasetRegression::test_diagnostic_failure_attribution PASSED [100%]
       ============================== 5 passed in 16.67s ==============================
       ```
     - Total golden cases evaluated: 55 ($\ge 50$ gate).
     - Hit Rate@5: 56.36% (56.4%) ($\ge 50.0\%$ threshold gate).
     - MRR: 0.4485 (0.448) ($\ge 0.400$ threshold gate).
     - Slot extraction accuracy: 55.0% ($\ge 50.0\%$ threshold gate).
     - Failure attribution: 100% of 24 missed cases attributed to canonical diagnostic codes (`RETRIEVAL_RECALL_MISS`: 16, `MISSED_TOP_RANKED`: 8).

3. **Evaluation CLI (`cuk-eval run`) & Strict Mode Stress Test**:
   - Executed: `uv run cuk-eval run --top-k 5 --strict`
     - Command exited with code `0`.
     - Output: Hit Rate@5 = 56.4%, MRR = 0.448, Slot Accuracy = 55.0%, Failure counts: `RETRIEVAL_RECALL_MISS` = 16, `MISSED_TOP_RANKED` = 8.
   - Tested Typer `CliRunner` failure paths:
     - Strict failure threshold: when simulated Hit Rate fell below `--min-hit-rate`, CLI printed `FAILED: Hit Rate@5 ... is below required threshold` and terminated with exit code `1`.
     - Missing dataset file: CLI printed `Error: Dataset file not found` and terminated with exit code `1`.
   - **Minor Defect Identified in `cuk_assistant/evals/cli.py:171`**:
     - Line 171 prints:
       `f"{int(summary.hit_rate_at_k * summary.total_cases)} / {summary.total_cases} queries hit"`
     - Because `summary.hit_rate_at_k = 31 / 55 = 0.5636363636363636`, `0.5636363636363636 * 55 = 30.999999999999996`.
     - `int(30.999999999999996)` evaluates to `30`.
     - The table displayed: `30 / 55 queries hit`, even though 31 queries actually hit (31 hits + 16 recall misses + 8 top-ranked misses = 55 total).
     - Recommendation: change `int(...)` to `round(...)` or `sum(1 for r in summary.results if r.hit_at_k)`.

4. **Integration & Unit Test Integrity**:
   - `uv run pytest tests/integration/ -q`: `12 passed in 19.05s`.
   - `uv run pytest tests/unit/ -q`: `652 passed, 13 skipped in 15.32s`.
   - `uv run ruff check cuk_assistant/ scripts/ tests/`: `All checks passed!`.
   - `uv run ruff format --check cuk_assistant/ scripts/ tests/`: `153 files already formatted`.
   - `docker compose config --quiet`: exited with code `0` (compose configuration is strictly valid).

---

## 2. Logic Chain

1. **Schema Consolidation Invariant**:
   - *Observation*: `cuk_assistant/schemas/chat.py` centralizes all conversational data models with clean imports in `api/routes/chat.py` and `pipeline/orchestrator.py`.
   - *Reasoning*: Moving schemas out of routing and pipeline implementation files restores strict adherence to Separation of Concerns (SoC) and Layering Invariants (`PROJECT.md:55`). Re-exporting in `cuk_assistant/schemas/__init__.py` and retaining re-exports in `orchestrator.py` guarantees zero breaking changes across existing callers.
   - *Deduction*: Empirical edge-case probing confirms validation is airtight for score ranges, required fields, and aliases.

2. **Ground Truth Live Benchmark**:
   - *Observation*: `test_golden_regression.py` executes directly against `create_retrieval_coordinator()` without mock intercepts.
   - *Reasoning*: Testing against real ONNX embeddings, Tantivy BM25 indices, and FlashRank models ensures the benchmark reflects actual runtime search precision.
   - *Deduction*: The live hit rate of 56.4% and MRR of 0.448 exceed the required regression gates ($\ge 50\%$ and $\ge 0.40$), and 100% of misses are tagged with diagnostic codes. The suite passes stably in 16.7s.

3. **Silent Failure and Regression Guardrails**:
   - *Observation*: `cuk-eval run --strict` enforces programmatic build/test gate failures if metrics degrade.
   - *Reasoning*: CLI strict mode and automated pytest regression gates provide redundant layers preventing performance drift in CI/CD.
   - *Deduction*: While a cosmetic truncation bug was discovered in CLI table output (`cli.py:171`), the underlying metrics, strict assertions, and regression test logic evaluate mathematical floats and pass properly.

---

## 3. Caveats

1. **CLI Hit Count Display Truncation**:
   - `cuk_assistant/evals/cli.py:171` displays `30 / 55 queries hit` due to `int()` truncation of floating-point multiplication (`30.999999999999996`). Actual hits are 31, and all percentages and gate checks evaluate correctly.
2. **Regression Test Attribution Gate Assumption**:
   - `tests/integration/test_golden_regression.py:95` asserts `len(failure_attribution_counts) > 0`. If retrieval performance were ever to reach 100% recall (0 misses), this assertion would fail.
3. **Relevance Pattern vs Keyword Matching**:
   - In `cuk_assistant/evals/evaluator.py`, `is_chunk_relevant` considers a chunk relevant if metadata matches `acceptable_source_patterns` (e.g. title/URL) OR text matches `expected_keywords`. In the 31 hits, 26 matched pattern-only, 1 keyword-only, and 4 matched both.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone M6 meets all architectural invariants, schema consolidation requirements, evaluation benchmarks, and container configuration standards. The golden regression test suite is stable and verifies live retrieval against LanceDB and ONNX models with zero mocks.

---

## 5. Verification Method

To independently reproduce and verify all findings:

1. **Run Golden Regression Suite**:
   ```bash
   uv run pytest tests/integration/test_golden_regression.py -v
   ```
   *Expected*: `5 passed in ~16s`.

2. **Run Full Test Suite**:
   ```bash
   uv run pytest tests/unit/ -q
   uv run pytest tests/integration/ -q
   ```
   *Expected*: `652 passed, 13 skipped` in unit; `12 passed` in integration.

3. **Run Evaluation CLI in Strict Mode**:
   ```bash
   uv run cuk-eval run --top-k 5 --strict
   ```
   *Expected*: Exit code 0, Hit Rate@5 $\approx 56.4\%$, MRR $\approx 0.448$.

4. **Verify Linter & Formatter**:
   ```bash
   uv run ruff check cuk_assistant/ scripts/ tests/
   uv run ruff format --check cuk_assistant/ scripts/ tests/
   ```
   *Expected*: 0 errors, 153 files formatted.
