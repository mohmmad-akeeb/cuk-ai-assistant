"""tests/integration/test_golden_regression.py

Milestone M6 Regression Benchmark Integration Suite.
Validates retrieval quality, ranking effectiveness, and slot extraction accuracy
against the curated golden dataset (evals/golden_dataset.jsonl).

Regression Quality Gates (per docs/requirements.md, PROJECT.md, and M6 blueprints):
- Hit Rate@5 >= 0.50 (50.0%)
- Mean Reciprocal Rank (MRR) >= 0.400
- Mean Slot Accuracy >= 0.500
- 100% failure diagnostic code attribution for misses
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cuk_assistant.core.factory import create_retrieval_coordinator, create_telemetry_sink
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
    telemetry_sink = create_telemetry_sink("in_memory")
    return RAGEvaluator(
        retrieval_coordinator=coordinator,
        telemetry_sink=telemetry_sink,
    )


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

    def test_mrr_meets_regression_gate(self, golden_eval_summary: EvaluationSummary) -> None:
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

    def test_diagnostic_failure_attribution(self, golden_eval_summary: EvaluationSummary) -> None:
        """Verify all missed queries are properly attributed with valid failure diagnostic codes."""
        valid_failure_codes = {
            FailureDiagnosticCode.RETRIEVAL_EMPTY.value,
            FailureDiagnosticCode.RETRIEVAL_RECALL_MISS.value,
            FailureDiagnosticCode.MISSED_TOP_RANKED.value,
        }
        assert len(golden_eval_summary.failure_attribution_counts) > 0, (
            "Expected failure attribution counts to be populated"
        )
        for res in golden_eval_summary.results:
            if not res.hit_at_k:
                assert res.diagnostic_code is not None, (
                    f"Missed test case {res.eval_id} missing failure diagnostic code"
                )
                code_val = (
                    res.diagnostic_code.value
                    if hasattr(res.diagnostic_code, "value")
                    else str(res.diagnostic_code)
                )
                assert code_val in valid_failure_codes, (
                    f"Unexpected diagnostic code {res.diagnostic_code} for missed test case {res.eval_id}"
                )
