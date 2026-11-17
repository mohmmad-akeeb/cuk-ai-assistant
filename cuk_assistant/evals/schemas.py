"""cuk_assistant/evals/schemas.py

Pydantic schemas for the regression evaluation benchmark suite.
Guarantees immutability and strict type adherence.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode


class GoldenTestCase(BaseModel):
    """Ground truth evaluation test case."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    eval_id: str = Field(..., description="Unique test case identifier (e.g. eval_001)")
    query: str = Field(..., description="Natural language user query")
    expected_slots: dict[str, Any] = Field(
        default_factory=dict,
        description="Ground-truth slot constraints (intent, department, program, semester, etc.)",
    )
    expected_keywords: list[str] = Field(
        default_factory=list,
        description="Salient keywords expected in relevant retrieval context chunks",
    )
    ground_truth_answer: str = Field(
        default="",
        description="Factual ground-truth response synthesized from university corpus",
    )
    acceptable_source_patterns: list[str] = Field(
        default_factory=list,
        description="Glob/fnmatch source URL, title, or doc_type patterns denoting relevant documents",
    )


class TestCaseEvalResult(BaseModel):
    """Detailed evaluation score and diagnostics for a single golden test case."""

    model_config = ConfigDict(extra="allow", frozen=True)

    eval_id: str = Field(..., description="Test case ID")
    query: str = Field(..., description="User query evaluated")
    hit_at_k: bool = Field(..., description="Whether a relevant chunk appeared in top-K")
    reciprocal_rank: float = Field(
        ..., description="Reciprocal rank (1/rank) of first relevant chunk"
    )
    keyword_recall: float = Field(
        ..., description="Proportion of expected keywords found in retrieved chunks (0.0 to 1.0)"
    )
    slot_accuracy: float = Field(
        ..., description="Accuracy of extracted query slots against expected slots (0.0 to 1.0)"
    )
    slots_extracted: dict[str, Any] = Field(
        default_factory=dict, description="Slots extracted by the slot filler"
    )
    first_relevant_rank: int | None = Field(
        default=None, description="1-indexed rank of first relevant chunk, or None"
    )
    retrieved_candidates_count: int = Field(
        default=0, description="Total candidates returned by retrieval coordinator"
    )
    citation_precision: float | None = Field(
        default=None,
        description="Fraction of asserted citations grounded verbatim in context chunks",
    )
    citation_recall: float | None = Field(
        default=None,
        description="Fraction of ground-truth keywords covered by citations",
    )
    diagnostic_code: FailureDiagnosticCode | None = Field(
        default=None, description="Diagnostic failure attribution code if degraded or missed"
    )
    diagnostic_details: dict[str, Any] = Field(
        default_factory=dict, description="Metadata explaining failure attribution"
    )


class EvaluationSummary(BaseModel):
    """Aggregated benchmark metrics across the entire golden evaluation dataset."""

    model_config = ConfigDict(extra="allow", frozen=True)

    total_cases: int = Field(..., description="Total test cases evaluated")
    top_k: int = Field(default=5, description="Cutoff threshold K used for Hit Rate@K")
    hit_rate_at_k: float = Field(
        ..., description="Percentage of queries with relevant chunk in top-K"
    )
    mrr: float = Field(..., description="Mean Reciprocal Rank across dataset")
    mean_keyword_recall: float = Field(..., description="Average keyword recall across dataset")
    mean_slot_accuracy: float = Field(..., description="Average slot extraction accuracy")
    mean_citation_precision: float | None = Field(
        default=None, description="Average citation precision (if citations evaluated)"
    )
    mean_citation_recall: float | None = Field(
        default=None, description="Average citation recall (if citations evaluated)"
    )
    failure_attribution_counts: dict[str, int] = Field(
        default_factory=dict, description="Tally of failure diagnostic codes emitted"
    )
    results: list[TestCaseEvalResult] = Field(
        default_factory=list, description="Per-test-case granular evaluation results"
    )


__all__ = [
    "EvaluationSummary",
    "GoldenTestCase",
    "TestCaseEvalResult",
]
