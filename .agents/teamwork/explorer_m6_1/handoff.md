# Milestone M6 Evaluation & Regression Suite: Investigation & Blueprint

**State Folder**: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_1/`  
**Target Milestone**: M6 (Observability, Evals, Containerization & Sign-Off)  
**Investigator**: `explorer_m6_1` (Read-Only)  
**Status**: Complete  

---

## 1. Observation

### 1.1 Existing Evaluation Engine & Dataset
1. **Dataset Structure (`evals/golden_dataset.jsonl`)**:
   - File exists at `evals/golden_dataset.jsonl` with **55 test cases** (verified via `wc -l evals/golden_dataset.jsonl`).
   - Each entry conforms to `GoldenTestCase` schema (`cuk_assistant/evals/schemas.py:10-30`):
     ```json
     {"eval_id": "eval_001", "query": "What is the fee refund policy after admission cancellation?", "expected_slots": {"intent": "admission", "department": null}, "expected_keywords": ["refund", "cancellation", "deduction", "fee"], "ground_truth_answer": "...", "acceptable_source_patterns": ["*admission*", "*notification*", "*fee*", "*refund*"]}
     ```
2. **Evaluation Harness (`cuk_assistant/evals/evaluator.py`)**:
   - `RAGEvaluator` class (`lines 88-456`) implements:
     - `evaluate_slots(query, expected_slots)`: Computes slot extraction accuracy with `FacetedSlotFiller`.
     - `compute_citation_metrics(quoted_snippets, retrieved_contexts, expected_keywords)`: Computes verbatim citation precision and recall using `VerbatimCitationVerifier`.
     - `evaluate_test_case(test_case, top_k=5)`: Evaluates single case, runs hybrid retrieval at `wide_k=30` and `top_k=5`, detects first relevant chunk rank, calculates Reciprocal Rank (RR), and applies standardized failure attribution codes (`RETRIEVAL_EMPTY`, `RETRIEVAL_RECALL_MISS`, `MISSED_TOP_RANKED`).
     - `evaluate_dataset(dataset_path_or_cases, top_k=5)`: Batch processor producing typed `EvaluationSummary`.
3. **Live Benchmark Performance Verification**:
   - Executed `uv run cuk-eval run` over `evals/golden_dataset.jsonl` with `top_k=5`:
     - **Execution time**: **14 seconds** for all 55 test cases.
     - **Retrieval Hit Rate@5**: **56.4%** (31 / 55 queries hit, exceeding the gate threshold of 0.50 / 50.0%).
     - **Mean Reciprocal Rank (MRR)**: **0.448** (exceeding the gate threshold of 0.400).
     - **Mean Keyword Recall**: **29.1%**.
     - **Slot Extraction Accuracy**: **55.0%**.
     - **Diagnostic Attribution Breakdown**:
       - `RETRIEVAL_RECALL_MISS`: 16 cases (29.1%)
       - `MISSED_TOP_RANKED`: 8 cases (14.5%)
       - Zero unhandled exceptions or crashes.

### 1.2 Query Mining and Starter Menu Hierarchy
1. **Query Mining Architecture (`cuk_assistant/evals/query_miner.py`)**:
   - `MenuHierarchyMiner` aggregates document metadata (`Document`) and chunk AST headings (`ChunkRecord`).
   - Clusters items into 4 top-level domains: `admissions`, `examinations`, `academics`, `campus`.
   - Generates clickable prompt chips and structured `MenuItem` entries, fallback to rich baseline CUK prompts.
   - Serializes to `StarterMenuResponse` (`version="1.0"`, `categories: list[MenuCategory]`).
2. **CLI Mismatch**:
   - `cuk_assistant/evals/cli.py:249`:
     ```python
     output: Annotated[Path, typer.Option(...)] = Path("data/menu_hierarchy.json")
     ```
   - `cuk_assistant/api/routes/menu.py:189-196`:
     ```python
     menu_file = Path("configs/menu_hierarchy.json")
     if menu_file.is_file():
         with menu_file.open(encoding="utf-8") as f:
             data = json.load(f)
             return StarterMenuResponse(**data)
     ```
   - `PROJECT.md:39, 69` and `ORIGINAL_REQUEST.md:68` explicitly specify `configs/menu_hierarchy.json`.
3. **Verification**:
   - Ran `uv run cuk-eval mine-queries --output /tmp/test_menu.json`. Completed cleanly in `<1.0s`, generating 4 categories and 17 prompt chips strictly matching `StarterMenuResponse`.

### 1.3 Schema Consolidation (`PROJECT.md:55`)
1. **Current Schema Organization**:
   - `cuk_assistant/schemas/` currently contains: `metadata.py`, `chunks.py`, `document.py`, `llm.py`, `retrieval.py`, `__init__.py`.
   - `cuk_assistant/schemas/chat.py` is **missing**.
2. **Current Misplaced Schemas**:
   - `cuk_assistant/api/routes/chat.py:64-117`: Defines `FeedbackRequest`, `ChatRequest`, `ChatResponse`.
   - `cuk_assistant/pipeline/orchestrator.py:58-89`: Defines `CitationCard`, `TurnResult`.
   - `cuk_assistant/api/routes/menu.py:18-69`: Defines `MenuItem`, `MenuCategory`, `StarterMenuResponse`.
3. **Architectural Invariant Violation**:
   - Per `GEMINI.md` Rule 2.1: `schemas/` must contain pure Pydantic data models with zero external database/vendor dependencies. Moving these models into `cuk_assistant/schemas/chat.py` enforces Separation of Concerns (SoC) and provides clean re-exports for serving and pipeline layers.

---

## 2. Logic Chain

```
[Obs 1.1] Live index evaluation yields Hit Rate@5 = 0.564 (>= 0.50) and MRR = 0.448 (>= 0.40) in 14.2s.
       │
       ▼
[Logic 2.1] An automated pytest integration test (`tests/integration/test_golden_regression.py`)
           can directly invoke `evaluator.evaluate_dataset("evals/golden_dataset.jsonl", top_k=5)`.
       │
       ▼
[Logic 2.2] Wrapping `RAGEvaluator` and `EvaluationSummary` in `scope="module"` pytest fixtures
           ensures the 384d FastEmbed ONNX model and LanceDB connection load exactly once,
           executing all test assertions in ~14 seconds without redundant overhead.
       │
       ▼
[Obs 1.2] `cuk_assistant/api/routes/menu.py:189` reads `configs/menu_hierarchy.json`,
           while `cli.py:249` defaults to `data/menu_hierarchy.json`.
       │
       ▼
[Logic 2.3] Updating the default output in `cuk_assistant/evals/cli.py` to `configs/menu_hierarchy.json`
           and running `cuk-eval mine-queries` ensures zero-config generation and runtime alignment.
       │
       ▼
[Obs 1.3] `ChatRequest`, `ChatResponse`, `FeedbackRequest`, `CitationCard`, and `TurnResult`
           are defined directly within route and pipeline implementation files.
       │
       ▼
[Logic 2.4] Consolidating all chat, feedback, turn, and citation schemas into `cuk_assistant/schemas/chat.py`
           and re-exporting in `__init__.py`, `api/routes/chat.py`, and `pipeline/orchestrator.py`
           strictly fulfills `PROJECT.md:55` and `GEMINI.md` SoC invariants with 100% backward compatibility.
```

---

## 3. Caveats

1. **Pre-populated LanceDB Store Requirement**:
   - `tests/integration/test_golden_regression.py` relies on `data/lancedb/` populated during Phase 3. If run in an empty CI environment without `data/lancedb/`, the test fixture should gracefully check for database existence and skip with a clear message: `"LanceDB table 'chunks' not found. Run 'make ingest' first."`
2. **Deterministic Retrieval Scope (Zero Hallucination / $0 Compute)**:
   - The regression test intentionally evaluates retrieval ranking (`hit_at_k`, `mrr`, `keyword_recall`) and deterministic slot extraction (`slot_accuracy`). It deliberately does not make external generative LLM calls per test case, guaranteeing 100% deterministic results, zero API cost, and rapid execution (<15s).
3. **configs/menu_hierarchy.json Git Tracking**:
   - `configs/menu_hierarchy.json` is a configuration artifact required by `GET /api/v1/menu/starter`. Generating it via `cuk-eval mine-queries` must be followed by checking it into version control.

---

## 4. Conclusion & Implementation Blueprint

The following blueprint provides the exact file specifications and code ready for implementation by the designated workers:

### Blueprint A: `tests/integration/test_golden_regression.py`
Create `tests/integration/test_golden_regression.py` to validate Hit Rate@5 and MRR against the golden dataset.

```python
"""tests/integration/test_golden_regression.py

Milestone M6 Regression Benchmark Integration Suite.
Validates retrieval quality, ranking effectiveness, and slot extraction accuracy
against the curated golden dataset (evals/golden_dataset.jsonl).

Regression Quality Gates (per docs/requirements.md & PROJECT.md):
- Hit Rate@5 >= 0.50 (50.0%)
- Mean Reciprocal Rank (MRR) >= 0.400
- Mean Slot Accuracy >= 0.500
- 100% failure diagnostic code attribution for misses
"""

from __future__ import annotations

from pathlib import Path
import pytest

from cuk_assistant.core.factory import create_retrieval_coordinator
from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.evals.evaluator import RAGEvaluator
from cuk_assistant.evals.schemas import EvaluationSummary


GOLDEN_DATASET_PATH = Path("evals/golden_dataset.jsonl")
LANCEDB_PATH = Path("data/lancedb")


@pytest.fixture(scope="module")
def evaluator() -> RAGEvaluator:
    """Initialize RAGEvaluator backed by live hybrid retrieval coordinator."""
    if not LANCEDB_PATH.exists():
        pytest.skip(f"LanceDB directory not found at {LANCEDB_PATH}. Run 'make ingest' first.")
    
    coordinator = create_retrieval_coordinator()
    return RAGEvaluator(retrieval_coordinator=coordinator)


@pytest.fixture(scope="module")
def golden_eval_summary(evaluator: RAGEvaluator) -> EvaluationSummary:
    """Execute evaluation across the golden dataset once for the test module."""
    if not GOLDEN_DATASET_PATH.exists():
        pytest.fail(f"Golden dataset missing at {GOLDEN_DATASET_PATH}")
    
    summary = evaluator.evaluate_dataset(GOLDEN_DATASET_PATH, top_k=5)
    return summary


@pytest.mark.integration
class TestGoldenDatasetRegression:
    """Regression benchmark verification suite for CUK RAG Assistant."""

    def test_golden_dataset_structure_and_volume(
        self, golden_eval_summary: EvaluationSummary
    ) -> None:
        """Verify dataset loaded correctly and contains at least 50 test cases."""
        assert golden_eval_summary.total_cases >= 50, (
            f"Expected >= 50 golden test cases, found {golden_eval_summary.total_cases}"
        )
        assert golden_eval_summary.top_k == 5

    def test_hit_rate_at_5_meets_regression_gate(
        self, golden_eval_summary: EvaluationSummary
    ) -> None:
        """Assert Hit Rate@5 is at least 0.50 (50%). Live benchmark: 0.564."""
        assert golden_eval_summary.hit_rate_at_k >= 0.50, (
            f"Hit Rate@5 ({golden_eval_summary.hit_rate_at_k:.3%}) failed regression gate (>= 50%)"
        )

    def test_mrr_meets_regression_gate(
        self, golden_eval_summary: EvaluationSummary
    ) -> None:
        """Assert Mean Reciprocal Rank (MRR) is at least 0.40. Live benchmark: 0.448."""
        assert golden_eval_summary.mrr >= 0.40, (
            f"MRR ({golden_eval_summary.mrr:.3f}) failed regression gate (>= 0.400)"
        )

    def test_slot_extraction_accuracy_baseline(
        self, golden_eval_summary: EvaluationSummary
    ) -> None:
        """Assert slot extraction accuracy meets baseline (>= 0.50). Live benchmark: 0.550."""
        assert golden_eval_summary.mean_slot_accuracy >= 0.50, (
            f"Mean slot extraction accuracy ({golden_eval_summary.mean_slot_accuracy:.3f}) below 0.50"
        )

    def test_diagnostic_failure_attribution(
        self, golden_eval_summary: EvaluationSummary
    ) -> None:
        """Verify all missed queries are properly attributed with valid failure diagnostic codes."""
        valid_failure_codes = {
            FailureDiagnosticCode.RETRIEVAL_EMPTY.value,
            FailureDiagnosticCode.RETRIEVAL_RECALL_MISS.value,
            FailureDiagnosticCode.MISSED_TOP_RANKED.value,
        }
        for res in golden_eval_summary.results:
            if not res.hit_at_k:
                assert res.diagnostic_code is not None, (
                    f"Missed test case {res.eval_id} missing failure diagnostic code"
                )
                assert res.diagnostic_code.value in valid_failure_codes, (
                    f"Unexpected diagnostic code {res.diagnostic_code} for missed test case {res.eval_id}"
                )
```

---

### Blueprint B: Query Mining & Menu Hierarchy CLI
Update `cuk_assistant/evals/cli.py` line 249 to default to `Path("configs/menu_hierarchy.json")`:

```python
# In cuk_assistant/evals/cli.py:
@app.command(name="mine-queries")
def mine_queries(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path where mined menu hierarchy JSON will be saved.",
            dir_okay=False,
        ),
    ] = Path("configs/menu_hierarchy.json"),
...
```

Execute query mining command:
```bash
uv run cuk-eval mine-queries --output configs/menu_hierarchy.json
```
This generates `configs/menu_hierarchy.json` directly where `GET /api/v1/menu/starter` expects it.

---

### Blueprint C: Pure Schema Consolidation (`cuk_assistant/schemas/chat.py`)
Create `cuk_assistant/schemas/chat.py` containing pure Pydantic v2 data models with zero external dependencies:

```python
"""cuk_assistant/schemas/chat.py

Pure Pydantic v2 data models for conversational chat, user feedback,
interactive citation cards, and turn results.
Governed by PROJECT.md:55, docs/requirements.md, and docs/api_contracts.md.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeedbackRequest(BaseModel):
    """Payload for user thumbs up/down reaction."""

    model_config = ConfigDict(extra="ignore")

    trace_id: str = Field(..., description="Trace identifier for the rated dialogue turn")
    message_id: str | None = Field(default=None, description="Optional message identifier")
    score: int = Field(..., description="Rating score: -1 for downvote, +1 for upvote")
    feedback_category: str | None = Field(default=None, description="Optional categorization")
    comment: str | None = Field(default=None, max_length=500, description="Optional feedback note")

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if v not in (-1, 1):
            raise ValueError("Score must be strictly -1 or 1.")
        return v


class ChatRequest(BaseModel):
    """Payload for conversational chat queries."""

    model_config = ConfigDict(extra="ignore")

    query: str | None = Field(default=None, description="User query prompt")
    message: str | None = Field(default=None, description="Alternative alias for query")
    session_id: str | None = Field(default=None, description="Conversation session UUID")
    slots: dict[str, Any] | None = Field(default=None, description="Pre-filled slot parameters")
    user_context: dict[str, Any] | None = Field(default=None, description="Client user context")

    @model_validator(mode="before")
    @classmethod
    def harmonize_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.get("query") and values.get("message"):
                values["query"] = values["message"]
            elif not values.get("message") and values.get("query"):
                values["message"] = values["query"]
        return values


class ChatResponse(BaseModel):
    """Synchronous chat response model."""

    model_config = ConfigDict(extra="ignore")

    message_id: str
    session_id: str
    role: str = "assistant"
    content: str
    quick_replies: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitationCard(BaseModel):
    """Interactive citation card payload for side-by-side inspection."""

    model_config = ConfigDict(extra="ignore")

    citation_id: str = Field(..., description="Unique citation handle (e.g. cite_1)")
    doc_id: str = Field(..., description="Parent document identifier")
    chunk_id: str = Field(..., description="Specific chunk identifier")
    title: str = Field(..., description="Document title")
    source_url: str = Field(..., description="Public link to document")
    doc_type: str = Field(default="document", description="Document type classification")
    page_number: int = Field(default=1, description="1-indexed PDF or document page number")
    section_heading: str | None = Field(default=None, description="Section heading")
    quoted_snippet: str = Field(..., description="Verified verbatim excerpt from document")
    is_table: bool = False
    table_markdown: str | None = None


class TurnResult(BaseModel):
    """Structured result of a completed RAG dialogue turn."""

    model_config = ConfigDict(extra="ignore")

    message_id: str
    session_id: str
    role: str = "assistant"
    content: str
    quick_replies: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostic_code: str | None = None


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CitationCard",
    "FeedbackRequest",
    "TurnResult",
]
```

**Re-export Adjustments**:
1. In `cuk_assistant/schemas/__init__.py`:
   ```python
   from cuk_assistant.schemas.chat import (
       ChatRequest,
       ChatResponse,
       CitationCard,
       FeedbackRequest,
       TurnResult,
   )
   ```
2. In `cuk_assistant/api/routes/chat.py`:
   Replace local class definitions with:
   ```python
   from cuk_assistant.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest
   ```
   Keep `__all__ = ["router", "ChatRequest", "ChatResponse", "FeedbackRequest"]` for 100% backward compatibility.
3. In `cuk_assistant/pipeline/orchestrator.py`:
   Replace local class definitions with:
   ```python
   from cuk_assistant.schemas.chat import CitationCard, TurnResult
   ```
   Keep `__all__` re-exporting `CitationCard` and `TurnResult`.

---

### Blueprint D: Makefile Target Additions
Per `ORIGINAL_REQUEST.md:73`, update `Makefile` to include the missing targets:
```makefile
# ── Interactive Chat CLI ──────────────────────────────────────────────────────
chat:
	uv run python scripts/interactive_chat.py

# ── Chainlit UI ───────────────────────────────────────────────────────────────
ui:
	uv run chainlit run cuk_assistant/ui/app.py -w --port 8001

# ── Golden Evaluation Benchmark ───────────────────────────────────────────────
eval:
	uv run cuk-eval run --strict --min-hit-rate 0.50
```

---

## 5. Verification Method

Independent verification steps after implementation:

1. **Integration Regression Test**:
   ```bash
   uv run pytest tests/integration/test_golden_regression.py -v
   ```
   *Expected Outcome*: 5 passed in ~14s, asserting Hit Rate@5 >= 0.50, MRR >= 0.40, total test cases >= 50.

2. **Full Integration Suite**:
   ```bash
   uv run pytest tests/integration/ -v
   ```
   *Expected Outcome*: Both `test_live_hybrid_search.py` (7 tests) and `test_golden_regression.py` (5 tests) pass with 0 errors.

3. **CLI Benchmark & Query Mining**:
   ```bash
   uv run cuk-eval run --strict --min-hit-rate 0.50
   uv run cuk-eval mine-queries --output configs/menu_hierarchy.json
   test -f configs/menu_hierarchy.json && echo "Menu hierarchy generated successfully"
   ```

4. **Code Quality and Schema Integrity**:
   ```bash
   uv run ruff check cuk_assistant/ tests/
   uv run pytest tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_api_chat_orchestrated.py -q
   ```
   *Expected Outcome*: 0 linting errors or warnings; all unit tests pass with consolidated schemas.
